import base64
import tempfile
from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from apps.api.serializers import TrackSerializer, _parse_external_subtitle_tokens
from apps.api.views import (
    _build_binary_stream_response,
    _build_ffmpeg_playback_command,
    _format_video_poster_label,
    _parse_timecode_seconds,
)
from apps.library.models import LibraryScanJob
from apps.library.tasks import _get_or_create_default_library


def _basic_auth_header(username, password):
    credential = f"{username}:{password}".encode("utf-8")
    token = base64.b64encode(credential).decode("ascii")
    return f"Basic {token}"


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ApiAuthenticationSmokeTests(TestCase):
    password = "correct-tv-password"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tv-client",
            password=self.password,
        )
        self.library = _get_or_create_default_library()
        LibraryScanJob.objects.create(
            library=self.library,
            status=LibraryScanJob.STATUS_DONE,
        )
        self.client = APIClient()

    def authenticate(self, username=None, password=None):
        self.client.credentials(
            HTTP_AUTHORIZATION=_basic_auth_header(username or self.user.username, password or self.password)
        )

    def test_basic_auth_reaches_android_tv_content_endpoints(self):
        self.authenticate()
        endpoints = [
            "/api/auth/me/",
            "/api/scan-jobs/latest/",
            "/api/video-curation/current/",
            "/api/videos/series-groups/?library={}&page_size=12&section=series".format(self.library.pk),
            "/api/videos/series-groups/?library={}&page_size=12&section=movies".format(self.library.pk),
            "/api/videos/series-groups/?library={}&page_size=12&curation_system=recently".format(self.library.pk),
            "/api/artists/?library={}&media_kind=audio&ordering=name&page_size=100".format(self.library.pk),
            "/api/albums/?library={}&media_kind=audio&ordering=title&page_size=100".format(self.library.pk),
            "/api/tracks/?library={}&media_kind=audio&ordering=canonical_title&page_size=100".format(self.library.pk),
            "/api/auto-import/settings/",
        ]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 200)

    def test_basic_auth_marks_auth_me_as_authenticated(self):
        self.authenticate()

        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["authenticated"])

    def test_content_endpoints_reject_missing_credentials(self):
        response = self.client.get("/api/tracks/")

        self.assertEqual(response.status_code, 403)

    def test_content_endpoints_reject_wrong_basic_credentials(self):
        self.authenticate(password="wrong-password")

        response = self.client.get("/api/tracks/")

        self.assertIn(response.status_code, {401, 403})

    def test_admin_can_create_user_without_switching_session(self):
        admin_password = "correct-admin-password"
        admin = get_user_model().objects.create_superuser(
            username="admin-client",
            password=admin_password,
        )
        self.authenticate(username=admin.username, password=admin_password)

        response = self.client.post("/api/auth/users/", {
            "username": "new-listener",
            "email": "new-listener@example.test",
            "password": "new-listener-password",
        }, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"]["username"], "new-listener")
        me_response = self.client.get("/api/auth/me/")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["user"]["username"], "admin-client")

    def test_staff_user_cannot_create_admin_user(self):
        staff_password = "correct-staff-password"
        staff = get_user_model().objects.create_user(
            username="staff-client",
            password=staff_password,
            is_staff=True,
        )
        self.authenticate(username=staff.username, password=staff_password)

        response = self.client.post("/api/auth/users/", {
            "username": "new-admin",
            "password": "new-admin-password",
            "is_staff": True,
        }, format="json")

        self.assertEqual(response.status_code, 403)

    def test_false_admin_flags_do_not_promote_created_user(self):
        admin_password = "correct-admin-password"
        admin = get_user_model().objects.create_superuser(
            username="admin-flag-client",
            password=admin_password,
        )
        self.authenticate(username=admin.username, password=admin_password)

        response = self.client.post("/api/auth/users/", {
            "username": "plain-listener",
            "password": "plain-listener-password",
            "is_staff": "false",
            "is_superuser": "false",
        }, format="json")

        self.assertEqual(response.status_code, 201)
        created = get_user_model().objects.get(username="plain-listener")
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)


class SubtitleTokenParsingTests(SimpleTestCase):
    def test_parses_external_subtitle_suffix_tokens(self):
        tokens = _parse_external_subtitle_tokens("movie.it.forced.director", "movie")

        self.assertEqual(tokens["language"], "it")
        self.assertTrue(tokens["forced"])
        self.assertFalse(tokens["default"])
        self.assertEqual(tokens["title"], "director")

    def test_marks_matching_stem_as_plain_subtitle(self):
        tokens = _parse_external_subtitle_tokens("movie", "movie")

        self.assertEqual(tokens, {"language": "", "title": "", "default": False, "forced": False})


class BinaryRangeResponseTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def build_temp_file(self, payload=b"abcdefghij"):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.write(payload)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def test_returns_partial_content_for_explicit_range(self):
        request = self.factory.get("/", HTTP_RANGE="bytes=2-5")
        response = _build_binary_stream_response(request, self.build_temp_file())

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], "bytes 2-5/10")
        self.assertEqual(response["Content-Length"], "4")
        self.assertEqual(b"".join(response.streaming_content), b"cdef")

    def test_returns_partial_content_for_suffix_range(self):
        request = self.factory.get("/", HTTP_RANGE="bytes=-3")
        response = _build_binary_stream_response(request, self.build_temp_file())

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], "bytes 7-9/10")
        self.assertEqual(b"".join(response.streaming_content), b"hij")

    def test_rejects_invalid_range(self):
        request = self.factory.get("/", HTTP_RANGE="items=2-5")
        response = _build_binary_stream_response(request, self.build_temp_file())

        self.assertEqual(response.status_code, 416)
        self.assertEqual(response["Content-Range"], "bytes */10")


class VideoPosterTimecodeTests(SimpleTestCase):
    def test_parses_seconds_and_colon_timecodes(self):
        self.assertEqual(_parse_timecode_seconds("42.5"), 42.5)
        self.assertEqual(_parse_timecode_seconds("1:02"), 62.0)
        self.assertEqual(_parse_timecode_seconds("1:02:03"), 3723.0)

    def test_formats_video_poster_label(self):
        self.assertEqual(_format_video_poster_label(62), "1:02")
        self.assertEqual(_format_video_poster_label(3723), "1:02:03")


class VideoPlaybackSafetyTests(SimpleTestCase):
    def test_video_tracks_do_not_advertise_waveform_urls(self):
        serializer = TrackSerializer()
        track = SimpleNamespace(pk="track-1", primary_file=SimpleNamespace(media_kind="video"))

        self.assertEqual(serializer.get_waveform_url(track), "")

    def test_transcode_command_runs_low_priority_and_single_threaded(self):
        command = _build_ffmpeg_playback_command(Path("/tmp/source.avi"), "transcode", Path("/tmp/output.mp4"))

        self.assertEqual(command[:6], ["ionice", "-c", "3", "nice", "-n", "15"])
        self.assertIn("-nostdin", command)
        self.assertIn("-threads", command)
        self.assertIn("-x264-params", command)
        self.assertIn("threads=1", command)
