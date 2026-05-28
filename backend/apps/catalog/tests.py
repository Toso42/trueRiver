from django.test import TestCase

from apps.catalog.models import MetadataEnrichmentJob, RemoteMetadataSettings, Track
from apps.catalog.remote_metadata import provider_settings_payload, run_metadata_enrichment_job_sync
from apps.library.models import Library, MediaFile


class RemoteMetadataSettingsTests(TestCase):
    def test_default_settings_use_manual_lookup_mode(self):
        settings_row = RemoteMetadataSettings.load()
        payload = provider_settings_payload(settings_row)

        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["lookup_mode"], RemoteMetadataSettings.LOOKUP_MANUAL)
        self.assertTrue(payload["video_enabled"])
        self.assertTrue(payload["audio_enabled"])
        self.assertIn("manual", payload["lookup_mode_options"])
        self.assertIn("auto", payload["lookup_mode_options"])
        self.assertIn("tmdb", payload["provider_order"]["video"])
        self.assertIn("musicbrainz", payload["provider_order"]["audio"])

    def test_disabled_lookup_finishes_job_without_provider_calls(self):
        RemoteMetadataSettings.objects.create(pk=1, enabled=False)
        library = Library.objects.create(
            name="Library",
            slug="library",
            ingest_path="/tmp/in",
            digest_path="/tmp/up",
            normalize_path="/tmp/out",
        )
        media_file = MediaFile.objects.create(
            library=library,
            relative_path="Movie.mkv",
            absolute_path="/tmp/up/Movie.mkv",
            path_hash="hash",
            filename="Movie.mkv",
            extension=".mkv",
            media_kind="video",
        )
        track = Track.objects.create(
            primary_file=media_file,
            canonical_title="Movie",
            canonical_sort_title="movie",
        )
        job = MetadataEnrichmentJob.objects.create(
            library=library,
            target_track_ids=[str(track.pk)],
        )

        result = run_metadata_enrichment_job_sync(str(job.pk))
        job.refresh_from_db()

        self.assertEqual(result["status"], MetadataEnrichmentJob.STATUS_DONE)
        self.assertEqual(job.candidate_count, 0)
        self.assertEqual(job.result_payload["items"][0]["status"], "remote_lookup_disabled")
