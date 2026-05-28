import hashlib
import json
from pathlib import Path
import re
import subprocess

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.catalog.models import Album, Artist, ArtistProfileImage, MetadataEnrichmentJob, RemoteMetadataSettings, Track, TrackDedupCandidate, TrackDedupJob, TrackVersionGroup, TrackVersionMembership
from apps.catalog.remote_metadata import provider_settings_payload
from apps.library.models import AccessoryFile, AutoImportSettings, DEFAULT_META_FIELD_NAMES, Library, LibraryDigestError, LibraryDigestJob, LibraryScanJob, LibraryScanSkip, MediaFile, SourceFolder
from apps.library.models import MediaFileMetaValue, MetaFieldDefinition, MetaNormalizationRule
from apps.library.models import SavedPlaylist, SavedPlaylistEntry
from apps.tags.models import AlbumTagAssignment, ArtistTagAssignment, TagDefinition, TagValue, TrackTagAssignment
from utils.drf_extensions import LoggedModelSerializer

User = get_user_model()
PLAYBACK_CACHE_DIR = Path("/tmp/triver-playback")
PLAYBACK_CACHE_VERSION = 3


def _candidate_media_paths(media_file):
    if not media_file:
        return []
    candidates = []
    if media_file.absolute_path:
        candidates.append(Path(media_file.absolute_path))
    if media_file.digest_relative_path:
        library = getattr(media_file, "library", None)
        digest_path = getattr(library, "digest_path", "") if library else ""
        if digest_path:
            candidates.append(Path(digest_path) / Path(media_file.digest_relative_path))
    return candidates


def _video_poster_root():
    return Path(getattr(settings, "TRIVER_DUMP_ROOT", "/tmp")).resolve() / "video-posters"


def _existing_video_card_cover_url(track):
    primary_file = getattr(track, "primary_file", None)
    if getattr(primary_file, "media_kind", "") != "video":
        return ""
    for candidate in _candidate_media_paths(primary_file):
        if not candidate.exists() or not candidate.is_file():
            continue
        stat_result = candidate.stat()
        source_key = f"{track.pk}-{int(stat_result.st_mtime)}-{stat_result.st_size}"
        for folder in ("selected", "default"):
            poster_path = _video_poster_root() / folder / f"{source_key}.jpg"
            if poster_path.exists() and poster_path.stat().st_size > 0:
                return f"/api/tracks/{track.pk}/poster/?v={int(poster_path.stat().st_mtime)}"
    return ""


def _user_avatar_file(user):
    avatar_root = Path(getattr(settings, "TRIVER_USER_AVATAR_ROOT", ""))
    if not getattr(user, "pk", None) or not avatar_root:
        return None
    for candidate in avatar_root.glob(f"{user.pk}.*"):
        if candidate.is_file():
            return candidate
    return None


class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    def get_avatar_url(self, user):
        avatar_file = _user_avatar_file(user)
        if not avatar_file:
            return ""
        version = int(avatar_file.stat().st_mtime)
        return f"/api/auth/me/avatar/image/?user_id={user.pk}&v={version}"

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "is_staff", "is_superuser", "avatar_url"]
        read_only_fields = ["id", "is_staff", "is_superuser"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["username", "email", "password", "first_name", "last_name"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


def _build_cover_url(resource: str, object_id) -> str:
    return f"/api/{resource}/{object_id}/cover/"


def _build_cover_url_if_available(resource: str, object_id, source_folder) -> str:
    if not source_folder:
        return ""
    cover = source_folder.get_best_cover_accessory()
    if not cover:
        return ""
    return _build_cover_url(resource, object_id)


def _tag_summary_for(obj):
    return [
        {
            "assignment_id": assignment.pk,
            "value_id": assignment.tag_value_id,
            "definition": assignment.tag_value.definition.key,
            "definition_id": assignment.tag_value.definition_id,
            "definition_label": assignment.tag_value.definition.label,
            "scope": assignment.tag_value.definition.scope,
            "normalized_key": assignment.tag_value.normalized_key,
            "display_order": assignment.tag_value.display_order,
            "value": str(assignment.tag_value),
        }
        for assignment in obj.tag_assignments.select_related("tag_value__definition").all()
    ]


def _has_video_tag(obj, *normalized_keys):
    wanted = {str(key or "").strip().lower() for key in normalized_keys if str(key or "").strip()}
    return any(
        assignment.tag_value.definition.key == "video-tag"
        and (
            assignment.tag_value.normalized_key in wanted
            or str(assignment.tag_value).strip().lower() in wanted
        )
        for assignment in obj.tag_assignments.select_related("tag_value__definition").all()
    )


def _album_cover_source_folder(album):
    if not album:
        return None
    track = album.tracks.select_related("primary_file__source_folder").first()
    primary_file = track.primary_file if track else None
    return primary_file.source_folder if primary_file else None


def _artist_auto_cover_source_folder(artist):
    credit = artist.track_credits.select_related("track__primary_file__source_folder").first()
    track = credit.track if credit else None
    primary_file = track.primary_file if track else None
    return primary_file.source_folder if primary_file else None


SOURCE_METADATA_LABELS = {
    "id3": {
        "TALB": "Album",
        "TCOM": "Composer",
        "TCON": "Genre",
        "TDRC": "Recording date",
        "TIT1": "Content group / Work name",
        "TIT2": "Title / Track name",
        "TIT3": "Subtitle / Version",
        "TPE1": "Lead performer / Artist",
        "TPE2": "Band / Orchestra",
        "TPE3": "Conductor",
        "TPE4": "Interpreted by / Remixer",
        "TPOS": "Disc number",
        "TPUB": "Publisher",
        "TRCK": "Track number",
        "TYER": "Year",
        "COMM": "Comment",
        "USLT": "Unsynchronised lyrics",
    },
    "vorbis": {
        "ALBUM": "Album",
        "ARTIST": "Artist",
        "COMMENT": "Comment",
        "COMPOSER": "Composer",
        "CONDUCTOR": "Conductor",
        "DATE": "Release date",
        "DISCNUMBER": "Disc number",
        "GENRE": "Genre",
        "ORCHESTRA": "Orchestra",
        "PERFORMER": "Performer",
        "TITLE": "Track name",
        "VERSION": "Track version",
        "TRACKVERSION": "Track version",
        "WORK": "Work name",
        "WORKNAME": "Work name",
        "WORKNUMBER": "Work number",
        "MOVEMENT": "Movement",
        "MOVEMENTNUMBER": "Movement number",
        "TRACKNUMBER": "Track number",
        "RELEASETYPE": "Release type",
        "LABEL": "Release label",
        "RELEASECOUNTRY": "Release country",
        "LYRICS": "Lyrics",
        "SOURCE": "Source medium",
    },
}

EXTRACTABLE_SUBTITLE_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text"}
EXTERNAL_SUBTITLE_EXTENSION_CODECS = {
    ".srt": "subrip",
    ".vtt": "webvtt",
    ".ass": "ass",
    ".ssa": "ssa",
    ".ttml": "ttml",
    ".dfxp": "ttml",
    ".smi": "sami",
    ".sub": "sub",
    ".idx": "idx",
    ".sup": "sup",
}
EXTRACTABLE_EXTERNAL_SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".ttml", ".dfxp", ".smi"}


def _source_metadata_label(source_family, source_name):
    normalized_source_name = str(source_name or "").upper()
    return (
        SOURCE_METADATA_LABELS.get(str(source_family or "").lower(), {}).get(normalized_source_name)
        or SOURCE_METADATA_LABELS.get("vorbis", {}).get(normalized_source_name)
        or ""
    )


def _get_latest_track_source_payload(track):
    source_metadata = track.source_metadata.order_by("-created_at").first()
    if not source_metadata:
        return {}
    return source_metadata.raw_payload or {}


def _subtitle_selector(prefix, raw_value):
    return f"{prefix}-{hashlib.sha1(str(raw_value or '').encode('utf-8')).hexdigest()[:16]}"


def _parse_external_subtitle_tokens(file_stem, base_stem):
    if file_stem == base_stem:
        return {"language": "", "title": "", "default": False, "forced": False}

    suffix = file_stem[len(base_stem):].lstrip("._- ")
    if not suffix:
        return {"language": "", "title": "", "default": False, "forced": False}

    tokens = [token.strip() for token in re.split(r"[._-]+", suffix) if token.strip()]
    language = ""
    forced = False
    default = False
    title_tokens = []

    for token in tokens:
        normalized = token.lower()
        if normalized in {"default", "def"}:
            default = True
            continue
        if normalized in {"forced", "force"}:
            forced = True
            continue
        if not language and re.fullmatch(r"[a-z]{2,3}", normalized):
            language = normalized
            continue
        title_tokens.append(token)

    return {
        "language": language,
        "title": " ".join(title_tokens).strip(),
        "default": default,
        "forced": forced,
    }


def _scan_external_subtitle_files(track, include_absolute_path=False):
    primary_file = track.primary_file
    if not primary_file:
        return []

    primary_path = Path(getattr(primary_file, "absolute_path", "") or "")
    if not primary_path.exists() or not primary_path.is_file():
        library = getattr(primary_file, "library", None)
        digest_relative_path = getattr(primary_file, "digest_relative_path", "") or ""
        if library and digest_relative_path:
            candidate = Path(library.digest_path) / digest_relative_path
            if candidate.exists() and candidate.is_file():
                primary_path = candidate

    if not primary_path.exists() or not primary_path.is_file():
        return []

    parent_path = primary_path.parent
    base_stem = primary_path.stem
    subtitle_streams = []

    try:
        candidates = sorted(parent_path.iterdir(), key=lambda path: path.name.lower())
    except OSError:
        return []

    for candidate in candidates:
        if not candidate.is_file() or candidate == primary_path:
            continue
        extension = candidate.suffix.lower()
        if extension not in EXTERNAL_SUBTITLE_EXTENSION_CODECS:
            continue
        candidate_stem = candidate.stem
        if candidate_stem != base_stem and not re.match(rf"^{re.escape(base_stem)}[._-].+", candidate_stem, flags=re.IGNORECASE):
            continue

        token_info = _parse_external_subtitle_tokens(candidate_stem, base_stem)
        extractable = extension in EXTRACTABLE_EXTERNAL_SUBTITLE_EXTENSIONS
        stream = {
            "selector": _subtitle_selector("ext", candidate.name),
            "source": "external",
            "index": None,
            "codec": EXTERNAL_SUBTITLE_EXTENSION_CODECS.get(extension, extension.lstrip(".")),
            "language": token_info["language"],
            "title": token_info["title"] or candidate.name,
            "default": token_info["default"],
            "forced": token_info["forced"],
            "extractable": extractable,
            "filename": candidate.name,
            "url": f"/api/tracks/{track.pk}/subtitles/{_subtitle_selector('ext', candidate.name)}/" if extractable else "",
        }
        if include_absolute_path:
            stream["absolute_path"] = str(candidate)
        subtitle_streams.append(stream)

    return subtitle_streams


def _get_ffprobe_streams(track, codec_type=None):
    payload = _get_latest_track_source_payload(track)
    probe_payload = payload.get("ffprobe") or {}
    streams = probe_payload.get("streams") or []
    if streams and any(stream.get("codec_type") == "subtitle" and stream.get("index") is None for stream in streams):
        primary_file = track.primary_file
        absolute_path = getattr(primary_file, "absolute_path", "") if primary_file else ""
        if absolute_path:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=index,codec_type,codec_name:stream_tags=language,title:stream_disposition=default,forced",
                    "-of",
                    "json",
                    absolute_path,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                try:
                    live_payload = json.loads(result.stdout or "{}")
                    streams = live_payload.get("streams") or streams
                except json.JSONDecodeError:
                    pass
    if codec_type is None:
        return streams
    return [stream for stream in streams if str(stream.get("codec_type") or "").lower() == codec_type]


def _coerce_video_dimension(value):
    try:
        if value in [None, ""]:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_ffprobe_fps(track):
    video_stream = next(iter(_get_ffprobe_streams(track, "video")), None)
    if not video_stream:
        return None
    raw_rate = str(video_stream.get("avg_frame_rate") or "").strip()
    if not raw_rate or raw_rate in {"0/0", "0"}:
        return None
    try:
        if "/" in raw_rate:
            numerator, denominator = raw_rate.split("/", 1)
            value = float(numerator) / float(denominator)
        else:
            value = float(raw_rate)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return round(value, 3)


def _enumerate_track_subtitle_streams(track, include_absolute_path=False):
    subtitle_streams = []
    for stream in _get_ffprobe_streams(track, "subtitle"):
        tags = stream.get("tags") or {}
        codec_name = stream.get("codec_name") or ""
        selector = str(stream.get("index"))
        extractable = str(codec_name or "").lower() in EXTRACTABLE_SUBTITLE_CODECS
        subtitle_streams.append({
            "selector": selector,
            "source": "embedded",
            "index": stream.get("index"),
            "codec": codec_name,
            "language": tags.get("language") or tags.get("LANGUAGE") or "",
            "title": tags.get("title") or tags.get("TITLE") or "",
            "default": bool((stream.get("disposition") or {}).get("default")),
            "forced": bool((stream.get("disposition") or {}).get("forced")),
            "extractable": extractable,
            "filename": "",
            "url": f"/api/tracks/{track.pk}/subtitles/{selector}/" if extractable else "",
        })
    subtitle_streams.extend(_scan_external_subtitle_files(track, include_absolute_path=include_absolute_path))
    return subtitle_streams


def _build_subtitle_stream_summary(track):
    return [
        {
            key: value
            for key, value in subtitle.items()
            if key != "absolute_path"
        }
        for subtitle in _enumerate_track_subtitle_streams(track, include_absolute_path=False)
    ]


def _get_primary_file_meta_values(track, field_name):
    primary_file = track.primary_file
    if not primary_file:
        return []
    meta_values = getattr(primary_file, "meta_values", None)
    if meta_values is None:
        return []
    values = []
    for meta_value in meta_values.all():
        if getattr(meta_value.field, "name", "") == field_name and meta_value.value_text:
            values.append(meta_value.value_text)
    return values


def _get_primary_file_meta_first(track, field_name):
    values = _get_primary_file_meta_values(track, field_name)
    return values[0] if values else ""


def _coerce_optional_int(value):
    try:
        if value in [None, ""]:
            return None
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _get_primary_extension(track):
    primary_file = track.primary_file
    return f".{str(getattr(primary_file, 'extension', '') or '').lower().lstrip('.')}" if primary_file else ""


def _is_browser_friendly_container(track):
    return _get_primary_extension(track) in {".mp4", ".m4v", ".webm", ".ogv"}


def _is_browser_friendly_video_codec(codec_name):
    return str(codec_name or "").lower() in {"h264", "avc1", "vp8", "vp9", "av1", "theora"}


def _is_browser_friendly_audio_codec(codec_name):
    return str(codec_name or "").lower() in {"aac", "mp3", "opus", "vorbis"}


def _derive_playback_strategy(track):
    payload = _get_latest_track_source_payload(track)
    if (payload.get("media_kind") or "").lower() != "video":
        return "direct"

    video_codec = next(iter(_get_ffprobe_streams(track, "video")), {}).get("codec_name") or ""
    audio_codec = next(iter(_get_ffprobe_streams(track, "audio")), {}).get("codec_name") or ""
    container_ok = _is_browser_friendly_container(track)
    video_ok = _is_browser_friendly_video_codec(video_codec)
    audio_ok = _is_browser_friendly_audio_codec(audio_codec) or not audio_codec

    if container_ok and video_ok and audio_ok:
        return "direct"
    if (not container_ok) and video_ok and audio_ok:
        return "remux"
    if video_ok and not audio_ok:
        return "audio_transcode"
    return "transcode"


def _playback_cache_path_for_track(track, playback_strategy):
    primary_file = track.primary_file
    source_path = Path(getattr(primary_file, "absolute_path", "") or "")
    if not source_path.exists():
        return None
    stat = source_path.stat()
    cache_key = f"v{PLAYBACK_CACHE_VERSION}-{track.pk}-{playback_strategy}-{int(stat.st_mtime)}-{stat.st_size}.mp4"
    return PLAYBACK_CACHE_DIR / cache_key


def _playback_lock_path_for_cache(cache_path):
    return cache_path.with_name(f"{cache_path.name}.lock")


def _playback_progress_path_for_cache(cache_path):
    return cache_path.with_name(f"{cache_path.name}.progress")


def _read_playback_progress_for_cache(cache_path, duration_seconds=None):
    progress_path = _playback_progress_path_for_cache(cache_path)
    total_seconds = max(float(duration_seconds or 0), 0.0)
    if not progress_path.exists():
        return {
            "percent": 100 if cache_path.exists() else 0,
            "seconds_done": 0,
            "seconds_total": round(total_seconds, 3),
        }
    progress_values = {}
    try:
        for line in progress_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            progress_values[key.strip()] = value.strip()
    except OSError:
        progress_values = {}

    try:
        seconds_done = int(progress_values.get("out_time_ms") or progress_values.get("out_time_us") or 0) / 1_000_000
    except (TypeError, ValueError):
        seconds_done = 0.0
    percent = 0
    if cache_path.exists():
        percent = 100
    elif total_seconds > 0:
        percent = max(0, min(99, int(round((seconds_done / total_seconds) * 100))))
    return {
        "percent": percent,
        "seconds_done": round(seconds_done, 3),
        "seconds_total": round(total_seconds, 3),
    }


def _is_playback_lock_present(cache_path):
    return _playback_lock_path_for_cache(cache_path).exists()


def _video_playback_status_for_serializer(track):
    primary_file = track.primary_file
    if getattr(primary_file, "media_kind", "audio") != "video":
        return {
            "strategy": "direct",
            "mode": "direct",
            "cache_ready": True,
            "building": False,
            "queue_busy": False,
            "progress": {"percent": 100, "seconds_done": 0, "seconds_total": 0},
            "message": "Ready to play.",
        }

    playback_strategy = _derive_playback_strategy(track)
    if playback_strategy == "direct":
        return {
            "strategy": playback_strategy,
            "mode": "direct",
            "cache_ready": True,
            "building": False,
            "queue_busy": False,
            "progress": {"percent": 100, "seconds_done": round(float(track.duration_seconds or 0), 3), "seconds_total": round(float(track.duration_seconds or 0), 3)},
            "message": "Ready to play.",
        }

    cache_path = _playback_cache_path_for_track(track, playback_strategy)
    if cache_path is None:
        return {
            "strategy": playback_strategy,
            "mode": "missing",
            "cache_ready": False,
            "building": False,
            "queue_busy": False,
            "progress": {"percent": 0, "seconds_done": 0, "seconds_total": round(float(track.duration_seconds or 0), 3)},
            "message": "The source file is not available right now.",
        }

    cache_ready = cache_path.exists()
    building = _is_playback_lock_present(cache_path)
    queue_busy = (PLAYBACK_CACHE_DIR / ".global-build.lock").exists() and not building and not cache_ready
    if cache_ready:
        message = "Ready to play."
    elif queue_busy:
        message = "Another video is being prepared. Selecting this video will move it to the front."
    elif building:
        message = "Preparing this video for smooth browser playback."
    elif playback_strategy == "remux":
        message = "This video needs a quick packaging step before the browser can play it."
    elif playback_strategy == "audio_transcode":
        message = "This video uses an audio format the browser cannot play yet. trueRiver will prepare a playable copy."
    else:
        message = "This video needs preparation before the browser can play it smoothly."
    return {
        "strategy": playback_strategy,
        "mode": "cached" if cache_ready else "preparing",
        "cache_ready": cache_ready,
        "building": building,
        "queue_busy": queue_busy,
        "progress": _read_playback_progress_for_cache(cache_path, duration_seconds=track.duration_seconds),
        "message": message,
    }


def _derive_subtitle_strategy(track):
    subtitle_streams = _build_subtitle_stream_summary(track)
    if not subtitle_streams:
        return "none"
    if any(stream.get("extractable") for stream in subtitle_streams):
        return "soft"
    return "burn_required"


class LibrarySerializer(LoggedModelSerializer):
    class Meta:
        model = Library
        fields = "__all__"


class LibraryScanJobSerializer(LoggedModelSerializer):
    class Meta:
        model = LibraryScanJob
        fields = "__all__"
        read_only_fields = [
            "started_at",
            "finished_at",
            "discovered_count",
            "queued_count",
            "processed_count",
            "skipped_count",
            "error_count",
            "removed_count",
            "last_error",
        ]


class LibraryDigestJobSerializer(LoggedModelSerializer):
    class Meta:
        model = LibraryDigestJob
        fields = "__all__"
        read_only_fields = [
            "started_at",
            "finished_at",
            "target_count",
            "processed_count",
            "created_track_count",
            "reused_track_count",
            "error_count",
            "last_error",
        ]


class LibraryDigestErrorSerializer(serializers.ModelSerializer):
    display_path = serializers.ReadOnlyField()

    class Meta:
        model = LibraryDigestError
        fields = "__all__"


class MediaFileSerializer(LoggedModelSerializer):
    display_path = serializers.ReadOnlyField()
    relevant_metadata = serializers.SerializerMethodField()
    raw_metadata = serializers.SerializerMethodField()
    editable_metadata = serializers.SerializerMethodField()

    class Meta:
        model = MediaFile
        fields = "__all__"
        read_only_fields = ["first_seen_at", "last_seen_at", "display_path"]

    def _serialize_meta_values(self, obj, *, relevant_only=False):
        preferred_order = [
            "TrackName",
            "TrackVersion",
            "SeriesTitle",
            "SeasonNumber",
            "EpisodeNumber",
            "EpisodeTitle",
            "AbsoluteEpisodeNumber",
            "Artist",
            "Album",
            "TrackNumber",
            "DiscNumber",
            "ReleaseDate",
            "Genre",
            "Comment",
            "Composer",
            "Conductor",
            "Executor",
            "BandName",
            "EnsembleName",
            "OrchestraName",
            "WorkName",
            "WorkNumber",
            "WorkType",
            "Movement",
            "MovementNumber",
            "ReleaseType",
            "ReleaseLabel",
            "ReleaseCountry",
            "Publisher",
            "Lyrics",
            "SourceMedium",
        ]
        preferred_set = {name.lower() for name in preferred_order}
        grouped = {}
        for value in obj.meta_values.select_related("field").filter(source_family__in=["user", "triver"]):
            field_name = value.field.name
            if relevant_only and field_name.lower() not in preferred_set:
                continue
            bucket = grouped.setdefault(field_name, [])
            bucket.append(value.value_text)

        if relevant_only:
            ordered_keys = [name for name in preferred_order if name in grouped]
        else:
            ordered_keys = sorted(grouped.keys(), key=lambda item: item.lower())

        return [
            {
                "field": key,
                "values": grouped[key],
                "display_value": " | ".join(grouped[key]),
            }
            for key in ordered_keys
        ]

    def _serialize_editable_metadata_section(self, obj, field_names, *, section):
        grouped = {}
        for value in obj.meta_values.select_related("field").filter(source_family__in=["user", "triver"]):
            bucket = grouped.setdefault(value.field.name, [])
            bucket.append({
                "id": str(value.id),
                "value": value.value_text,
                "source_family": value.source_family,
                "source_name": value.source_name,
                "is_primary": value.is_primary,
                "value_order": value.value_order,
            })

        rows = []
        seen = set()
        for field_name in field_names:
            normalized = field_name.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            values = grouped.get(field_name, [])
            if not values:
                continue
            rows.append({
                "section": section,
                "field": field_name,
                "values": values,
                "display_value": " | ".join(item["value"] for item in values),
            })
        return rows

    def _serialize_raw_metadata_section(self, obj):
        grouped = {}
        for value in obj.meta_values.select_related("field").exclude(source_family__in=["user", "triver"]):
            field_name = value.source_name or value.field.name
            bucket = grouped.setdefault(field_name, [])
            source_label = _source_metadata_label(value.source_family, value.source_name)
            bucket.append({
                "id": str(value.id),
                "value": value.value_text,
                "source_family": value.source_family,
                "source_name": value.source_name,
                "source_label": source_label,
                "field": value.field.name,
                "is_primary": value.is_primary,
                "value_order": value.value_order,
            })

        return [
            {
                "section": "source",
                "field": field_name,
                "source_family": grouped[field_name][0]["source_family"] if grouped[field_name] else "",
                "source_name": field_name,
                "source_label": grouped[field_name][0]["source_label"] if grouped[field_name] else "",
                "display_field": " / ".join(
                    item for item in [
                        (grouped[field_name][0]["source_family"] or "").upper() if grouped[field_name] else "",
                        field_name,
                        grouped[field_name][0]["source_label"] if grouped[field_name] else "",
                    ]
                    if item
                ),
                "read_only": True,
                "values": grouped[field_name],
                "display_value": " | ".join(item["value"] for item in grouped[field_name]),
            }
            for field_name in sorted(grouped.keys(), key=lambda item: item.lower())
        ]

    def get_relevant_metadata(self, obj):
        return self._serialize_meta_values(obj, relevant_only=True)

    def get_raw_metadata(self, obj):
        return self._serialize_meta_values(obj, relevant_only=False)

    def get_editable_metadata(self, obj):
        return {
            "triver": self._serialize_editable_metadata_section(obj, DEFAULT_META_FIELD_NAMES, section="triver"),
            "source": self._serialize_raw_metadata_section(obj),
        }


class LibraryScanSkipSerializer(serializers.ModelSerializer):
    display_path = serializers.ReadOnlyField()

    class Meta:
        model = LibraryScanSkip
        fields = "__all__"


class AutoImportSettingsSerializer(LoggedModelSerializer):
    class Meta:
        model = AutoImportSettings
        fields = "__all__"
        read_only_fields = [
            "library",
            "last_checked_at",
            "last_triggered_at",
            "last_trive_signature",
            "last_classic_signatures",
            "last_result",
            "last_error",
            "created_at",
            "updated_at",
        ]


class SourceFolderSerializer(serializers.ModelSerializer):
    display_path = serializers.ReadOnlyField()
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = SourceFolder
        fields = "__all__"

    def get_cover_url(self, obj):
        return _build_cover_url_if_available("source-folders", obj.pk, obj)


class AccessoryFileSerializer(serializers.ModelSerializer):
    display_path = serializers.ReadOnlyField()

    class Meta:
        model = AccessoryFile
        fields = "__all__"


class MetaFieldDefinitionSerializer(serializers.ModelSerializer):
    value_count = serializers.SerializerMethodField()

    class Meta:
        model = MetaFieldDefinition
        fields = "__all__"

    def get_value_count(self, obj):
        return obj.values.count()


class MetaNormalizationRuleSerializer(serializers.ModelSerializer):
    target_field_name = serializers.ReadOnlyField(source="target_field.name")

    class Meta:
        model = MetaNormalizationRule
        fields = "__all__"


class MediaFileMetaValueSerializer(serializers.ModelSerializer):
    field_name = serializers.ReadOnlyField(source="field.name")
    media_file_path = serializers.ReadOnlyField(source="media_file.display_path")

    class Meta:
        model = MediaFileMetaValue
        fields = "__all__"


class AlbumSerializer(LoggedModelSerializer):
    track_count = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    lead_artist_names = serializers.SerializerMethodField()
    first_track_id = serializers.SerializerMethodField()
    tag_summary = serializers.SerializerMethodField()
    version_count = serializers.SerializerMethodField()

    class Meta:
        model = Album
        fields = [
            "id",
            "title",
            "sort_title",
            "release_year",
            "triver_notes",
            "created_at",
            "updated_at",
            "track_count",
            "cover_url",
            "lead_artist_names",
            "first_track_id",
            "tag_summary",
            "version_count",
        ]

    def get_track_count(self, obj):
        return obj.tracks.count()

    def get_cover_url(self, obj):
        return _build_cover_url_if_available("albums", obj.pk, _album_cover_source_folder(obj))

    def get_lead_artist_names(self, obj):
        names = []
        for track in obj.tracks.prefetch_related("artist_credits__artist").all()[:8]:
            for credit in track.artist_credits.all():
                if credit.artist.name not in names:
                    names.append(credit.artist.name)
        return names[:3]

    def get_first_track_id(self, obj):
        track = obj.tracks.first()
        return str(track.id) if track else ""

    def get_tag_summary(self, obj):
        return _tag_summary_for(obj)

    def get_version_count(self, obj):
        groups = TrackVersionGroup.objects.filter(memberships__track__album=obj).distinct().prefetch_related("memberships")
        return max([group.memberships.count() for group in groups] or [0])


class AlbumCardSerializer(LoggedModelSerializer):
    cover_url = serializers.SerializerMethodField()
    lead_artist_names = serializers.SerializerMethodField()

    class Meta:
        model = Album
        fields = [
            "id",
            "title",
            "sort_title",
            "release_year",
            "cover_url",
            "lead_artist_names",
        ]

    def get_cover_url(self, obj):
        return f"/api/albums/{obj.pk}/cover/"

    def get_lead_artist_names(self, obj):
        names = []
        for track in obj.tracks.prefetch_related("artist_credits__artist").all()[:8]:
            for credit in track.artist_credits.all():
                if credit.artist.name not in names:
                    names.append(credit.artist.name)
        return names[:3]


class ArtistProfileImageSerializer(LoggedModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ArtistProfileImage
        fields = [
            "id",
            "artist",
            "relative_path",
            "original_filename",
            "content_type",
            "size",
            "source",
            "created_at",
            "updated_at",
            "image_url",
        ]
        read_only_fields = ["relative_path", "content_type", "size", "source"]

    def get_image_url(self, obj):
        return f"/api/artists/{obj.artist_id}/profile-images/{obj.pk}/"


class ArtistSerializer(LoggedModelSerializer):
    track_count = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    tag_summary = serializers.SerializerMethodField()
    version_count = serializers.SerializerMethodField()

    class Meta:
        model = Artist
        fields = [
            "id",
            "name",
            "sort_name",
            "triver_notes",
            "selected_cover_mode",
            "selected_cover_album",
            "selected_profile_image",
            "created_at",
            "updated_at",
            "track_count",
            "cover_url",
            "tag_summary",
            "version_count",
        ]
        read_only_fields = [
            "selected_cover_mode",
            "selected_cover_album",
            "selected_profile_image",
        ]

    def get_track_count(self, obj):
        return obj.track_credits.values("track_id").distinct().count()

    def get_cover_url(self, obj):
        if obj.selected_cover_mode == "upload" and obj.selected_profile_image_id:
            return _build_cover_url("artists", obj.pk)
        if obj.selected_cover_mode == "album" and obj.selected_cover_album_id:
            selected_url = _build_cover_url_if_available(
                "artists",
                obj.pk,
                _album_cover_source_folder(obj.selected_cover_album),
            )
            if selected_url:
                return selected_url
        return _build_cover_url_if_available("artists", obj.pk, _artist_auto_cover_source_folder(obj))

    def get_tag_summary(self, obj):
        return _tag_summary_for(obj)

    def get_version_count(self, obj):
        groups = TrackVersionGroup.objects.filter(memberships__track__artist_credits__artist=obj).distinct().prefetch_related("memberships")
        return max([group.memberships.count() for group in groups] or [0])


class ArtistCardSerializer(LoggedModelSerializer):
    cover_url = serializers.SerializerMethodField()

    class Meta:
        model = Artist
        fields = [
            "id",
            "name",
            "sort_name",
            "cover_url",
        ]

    def get_cover_url(self, obj):
        return f"/api/artists/{obj.pk}/cover/?mode=auto"


class TrackSerializer(LoggedModelSerializer):
    artist_summary = serializers.SerializerMethodField()
    tag_summary = serializers.SerializerMethodField()
    source_folder_summary = serializers.SerializerMethodField()
    album_title = serializers.SerializerMethodField()
    series_title = serializers.SerializerMethodField()
    season_number = serializers.SerializerMethodField()
    episode_number = serializers.SerializerMethodField()
    episode_title = serializers.SerializerMethodField()
    absolute_episode_number = serializers.SerializerMethodField()
    media_kind = serializers.SerializerMethodField()
    stream_url = serializers.SerializerMethodField()
    waveform_url = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    audio_format = serializers.SerializerMethodField()
    bitrate_kbps = serializers.SerializerMethodField()
    width = serializers.SerializerMethodField()
    height = serializers.SerializerMethodField()
    fps = serializers.SerializerMethodField()
    video_codec = serializers.SerializerMethodField()
    audio_codec = serializers.SerializerMethodField()
    browser_playable = serializers.SerializerMethodField()
    playback_strategy = serializers.SerializerMethodField()
    playback_cache_ready = serializers.SerializerMethodField()
    playback_status = serializers.SerializerMethodField()
    playback_url = serializers.SerializerMethodField()
    hls_manifest_url = serializers.SerializerMethodField()
    subtitle_strategy = serializers.SerializerMethodField()
    subtitle_streams = serializers.SerializerMethodField()
    version_summary = serializers.SerializerMethodField()

    class Meta:
        model = Track
        fields = [
            "id",
            "primary_file",
            "album",
            "canonical_title",
            "canonical_sort_title",
            "release_year",
            "disc_number",
            "track_number",
            "duration_seconds",
            "metadata_state",
            "last_error",
            "created_at",
            "updated_at",
            "album_title",
            "series_title",
            "season_number",
            "episode_number",
            "episode_title",
            "absolute_episode_number",
            "artist_summary",
            "tag_summary",
            "source_folder_summary",
            "media_kind",
            "stream_url",
            "waveform_url",
            "cover_url",
            "audio_format",
            "bitrate_kbps",
            "width",
            "height",
            "fps",
            "video_codec",
            "audio_codec",
            "browser_playable",
            "playback_strategy",
            "playback_cache_ready",
            "playback_status",
            "playback_url",
            "hls_manifest_url",
            "subtitle_strategy",
            "subtitle_streams",
            "version_summary",
        ]

    def get_artist_summary(self, obj):
        return [
            {
                "artist_id": str(credit.artist_id),
                "name": credit.artist.name,
                "role": credit.role,
                "is_primary": credit.is_primary,
            }
            for credit in obj.artist_credits.select_related("artist").all()
        ]

    def get_tag_summary(self, obj):
        return _tag_summary_for(obj)

    def get_version_summary(self, obj):
        return [
            {
                "membership_id": membership.pk,
                "group_id": membership.group_id,
                "group_title": membership.group.title,
                "serving_mode": membership.group.serving_mode,
                "role": membership.role,
                "label": membership.label,
                "sort_order": membership.sort_order,
                "is_default": membership.is_default,
                "group_member_count": membership.group.memberships.count(),
            }
            for membership in obj.version_memberships.select_related("group").all()
        ]

    def get_source_folder_summary(self, obj):
        primary_file = obj.primary_file
        if not primary_file or not primary_file.source_folder:
            return None
        return {
            "id": primary_file.source_folder_id,
            "name": primary_file.source_folder.name,
            "relative_path": primary_file.source_folder.relative_path,
            "display_path": primary_file.source_folder.display_path,
        }

    def get_album_title(self, obj):
        return obj.album.title if obj.album else ""

    def get_series_title(self, obj):
        if _has_video_tag(obj, "movie", "movies", "film"):
            return ""
        series_title = _get_primary_file_meta_first(obj, "SeriesTitle")
        if series_title:
            return series_title
        has_tv_series_tag = any(
            assignment.tag_value.definition.key == "video-tag"
            and (
                assignment.tag_value.normalized_key == "tv-series"
                or str(assignment.tag_value).strip().lower() == "tv series"
            )
            for assignment in obj.tag_assignments.select_related("tag_value__definition").all()
        )
        if not has_tv_series_tag:
            return ""
        if obj.album and obj.album.title:
            return obj.album.title
        primary_file = obj.primary_file
        source_folder = getattr(primary_file, "source_folder", None) if primary_file else None
        return getattr(source_folder, "name", "") or ""

    def get_season_number(self, obj):
        return _coerce_optional_int(_get_primary_file_meta_first(obj, "SeasonNumber"))

    def get_episode_number(self, obj):
        return _coerce_optional_int(_get_primary_file_meta_first(obj, "EpisodeNumber"))

    def get_episode_title(self, obj):
        return _get_primary_file_meta_first(obj, "EpisodeTitle")

    def get_absolute_episode_number(self, obj):
        return _coerce_optional_int(_get_primary_file_meta_first(obj, "AbsoluteEpisodeNumber"))

    def get_media_kind(self, obj):
        primary_file = obj.primary_file
        return getattr(primary_file, "media_kind", "") or "audio"

    def get_stream_url(self, obj):
        return f"/api/tracks/{obj.pk}/stream/"

    def get_waveform_url(self, obj):
        primary_file = obj.primary_file
        if getattr(primary_file, "media_kind", "") == "video":
            return ""
        return f"/api/tracks/{obj.pk}/waveform/"

    def get_cover_url(self, obj):
        primary_file = obj.primary_file
        if getattr(primary_file, "media_kind", "") == "video":
            return f"/api/tracks/{obj.pk}/poster/"
        return _build_cover_url_if_available("tracks", obj.pk, primary_file.source_folder if primary_file else None)

    def get_audio_format(self, obj):
        primary_file = obj.primary_file
        if not primary_file:
            return ""
        return (primary_file.extension or "").lower()

    def get_bitrate_kbps(self, obj):
        primary_file = obj.primary_file
        duration_seconds = float(obj.duration_seconds) if obj.duration_seconds is not None else 0.0
        size_bytes = getattr(primary_file, "size", None)
        if not primary_file or not size_bytes or duration_seconds <= 0:
            return None
        return int(round((float(size_bytes) * 8.0) / duration_seconds / 1000.0))

    def get_width(self, obj):
        video_stream = next(iter(_get_ffprobe_streams(obj, "video")), None)
        return _coerce_video_dimension((video_stream or {}).get("width"))

    def get_height(self, obj):
        video_stream = next(iter(_get_ffprobe_streams(obj, "video")), None)
        return _coerce_video_dimension((video_stream or {}).get("height"))

    def get_fps(self, obj):
        return _parse_ffprobe_fps(obj)

    def get_video_codec(self, obj):
        video_stream = next(iter(_get_ffprobe_streams(obj, "video")), None)
        return (video_stream or {}).get("codec_name") or ""

    def get_audio_codec(self, obj):
        audio_stream = next(iter(_get_ffprobe_streams(obj, "audio")), None)
        return (audio_stream or {}).get("codec_name") or ""

    def get_browser_playable(self, obj):
        return bool(_get_latest_track_source_payload(obj).get("browser_playable"))

    def get_playback_strategy(self, obj):
        return _derive_playback_strategy(obj)

    def get_playback_cache_ready(self, obj):
        return bool(_video_playback_status_for_serializer(obj).get("cache_ready"))

    def get_playback_status(self, obj):
        return _video_playback_status_for_serializer(obj)

    def get_playback_url(self, obj):
        return f"/api/tracks/{obj.pk}/playback/"

    def get_hls_manifest_url(self, obj):
        return ""

    def get_subtitle_strategy(self, obj):
        return _derive_subtitle_strategy(obj)

    def get_subtitle_streams(self, obj):
        return _build_subtitle_stream_summary(obj)


class TrackCardSerializer(LoggedModelSerializer):
    album_title = serializers.SerializerMethodField()
    media_kind = serializers.SerializerMethodField()
    stream_url = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    playback_url = serializers.SerializerMethodField()
    playback_cache_ready = serializers.SerializerMethodField()
    playback_status = serializers.SerializerMethodField()

    class Meta:
        model = Track
        fields = [
            "id",
            "primary_file",
            "album",
            "canonical_title",
            "canonical_sort_title",
            "release_year",
            "disc_number",
            "track_number",
            "duration_seconds",
            "album_title",
            "media_kind",
            "stream_url",
            "cover_url",
            "playback_url",
            "playback_cache_ready",
            "playback_status",
        ]

    def get_album_title(self, obj):
        return obj.album.title if obj.album else ""

    def get_media_kind(self, obj):
        primary_file = obj.primary_file
        return getattr(primary_file, "media_kind", "") or "audio"

    def get_stream_url(self, obj):
        return f"/api/tracks/{obj.pk}/stream/"

    def get_cover_url(self, obj):
        primary_file = obj.primary_file
        if getattr(primary_file, "media_kind", "") == "video":
            return _existing_video_card_cover_url(obj)
        return f"/api/tracks/{obj.pk}/cover/"

    def get_playback_url(self, obj):
        return f"/api/tracks/{obj.pk}/playback/"

    def _playback_status(self, obj):
        if not hasattr(obj, "_triver_card_playback_status"):
            obj._triver_card_playback_status = _video_playback_status_for_serializer(obj)
        return obj._triver_card_playback_status

    def get_playback_cache_ready(self, obj):
        return bool(self._playback_status(obj).get("cache_ready"))

    def get_playback_status(self, obj):
        return self._playback_status(obj)


class TrackDedupJobSerializer(LoggedModelSerializer):
    class Meta:
        model = TrackDedupJob
        fields = "__all__"


class TrackDedupCandidateSerializer(LoggedModelSerializer):
    tracks = serializers.SerializerMethodField()
    track_count = serializers.SerializerMethodField()

    class Meta:
        model = TrackDedupCandidate
        fields = [
            "id",
            "library",
            "job",
            "fingerprint",
            "status",
            "title",
            "score",
            "reasons",
            "track_ids",
            "notes",
            "created_at",
            "updated_at",
            "tracks",
            "track_count",
        ]

    def get_tracks(self, obj):
        track_ids = [str(track_id) for track_id in (obj.track_ids or [])]
        if not track_ids:
            return []
        tracks = (
            Track.objects
            .filter(pk__in=track_ids)
            .select_related("album", "primary_file", "primary_file__source_folder")
            .prefetch_related("artist_credits__artist", "tag_assignments__tag_value__definition", "version_memberships__group")
        )
        track_by_id = {str(track.pk): track for track in tracks}
        ordered_tracks = [track_by_id[track_id] for track_id in track_ids if track_id in track_by_id]
        return TrackSerializer(ordered_tracks, many=True, context=self.context).data

    def get_track_count(self, obj):
        return len(obj.track_ids or [])


class RemoteMetadataSettingsSerializer(LoggedModelSerializer):
    providers = serializers.SerializerMethodField()
    lookup_mode_options = serializers.SerializerMethodField()
    policy_options = serializers.SerializerMethodField()

    class Meta:
        model = RemoteMetadataSettings
        fields = [
            "id",
            "enabled",
            "lookup_mode",
            "video_enabled",
            "audio_enabled",
            "allow_remote_artwork",
            "preferred_language",
            "preferred_region",
            "overwrite_policy",
            "provider_order",
            "providers",
            "lookup_mode_options",
            "policy_options",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "providers", "lookup_mode_options", "policy_options", "created_at", "updated_at"]

    def get_providers(self, obj):
        return provider_settings_payload(obj)["providers"]

    def get_lookup_mode_options(self, obj):
        return provider_settings_payload(obj)["lookup_mode_options"]

    def get_policy_options(self, obj):
        return provider_settings_payload(obj)["policy_options"]


class MetadataEnrichmentJobSerializer(LoggedModelSerializer):
    requested_by_username = serializers.ReadOnlyField(source="requested_by.username")

    class Meta:
        model = MetadataEnrichmentJob
        fields = [
            "id",
            "library",
            "requested_by",
            "requested_by_username",
            "status",
            "mode",
            "media_scope",
            "provider_key",
            "overwrite_policy",
            "target_track_ids",
            "candidate_count",
            "updated_count",
            "result_payload",
            "started_at",
            "finished_at",
            "last_error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "requested_by",
            "requested_by_username",
            "status",
            "candidate_count",
            "updated_count",
            "result_payload",
            "started_at",
            "finished_at",
            "last_error",
            "created_at",
            "updated_at",
        ]


class SavedPlaylistEntrySerializer(serializers.ModelSerializer):
    track = TrackSerializer(read_only=True)

    class Meta:
        model = SavedPlaylistEntry
        fields = ["id", "position", "track", "created_at", "updated_at"]


class SavedPlaylistSerializer(LoggedModelSerializer):
    entries = SavedPlaylistEntrySerializer(many=True, read_only=True)
    tracks = serializers.SerializerMethodField()
    track_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        allow_empty=True,
    )

    class Meta:
        model = SavedPlaylist
        fields = [
            "id",
            "library",
            "name",
            "notes",
            "entries",
            "tracks",
            "track_ids",
            "created_at",
            "updated_at",
        ]

    def get_tracks(self, obj):
        ordered_tracks = [entry.track for entry in obj.entries.select_related("track__album", "track__primary_file").all()]
        return TrackSerializer(ordered_tracks, many=True).data

    def create(self, validated_data):
        track_ids = validated_data.pop("track_ids", [])
        playlist = SavedPlaylist(**validated_data)
        playlist.save(
            user=getattr(self, "_log_user", None),
            path=getattr(self, "_log_path", None),
            http_method=getattr(self, "_log_method", None),
        )
        self._replace_entries(playlist, track_ids)
        return playlist

    def update(self, instance, validated_data):
        track_ids = validated_data.pop("track_ids", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(
            user=getattr(self, "_log_user", None),
            path=getattr(self, "_log_path", None),
            http_method=getattr(self, "_log_method", None),
        )
        if track_ids is not None:
            self._replace_entries(instance, track_ids)
        return instance

    def _replace_entries(self, playlist, track_ids):
        playlist.entries.all().delete()
        if not track_ids:
            return
        tracks = {
            str(track.id): track
            for track in Track.objects.filter(id__in=track_ids)
        }
        entries = []
        for position, track_id in enumerate(track_ids):
            track = tracks.get(str(track_id))
            if not track:
                continue
            entries.append(
                SavedPlaylistEntry(
                    playlist=playlist,
                    track=track,
                    position=position,
                )
            )
        if entries:
            SavedPlaylistEntry.objects.bulk_create(entries)


class TagDefinitionSerializer(LoggedModelSerializer):
    owner_username = serializers.ReadOnlyField(source="owner.username")

    class Meta:
        model = TagDefinition
        fields = "__all__"
        read_only_fields = ["owner"]


class TagValueSerializer(LoggedModelSerializer):
    class Meta:
        model = TagValue
        fields = "__all__"


class TrackTagAssignmentSerializer(LoggedModelSerializer):
    tag_value = TagValueSerializer()

    class Meta:
        model = TrackTagAssignment
        fields = ["id", "track", "tag_value", "created_at", "updated_at"]

    def create(self, validated_data):
        tag_value_data = validated_data.pop("tag_value")
        tag_value, _ = TagValue.objects.get_or_create(
            definition=tag_value_data["definition"],
            value_text=tag_value_data.get("value_text", ""),
            value_number=tag_value_data.get("value_number"),
            value_bool=tag_value_data.get("value_bool"),
            value_date=tag_value_data.get("value_date"),
            defaults={"normalized_key": tag_value_data.get("normalized_key", "")},
        )
        validated_data["tag_value"] = tag_value
        return super().create(validated_data)


class AlbumTagAssignmentSerializer(LoggedModelSerializer):
    tag_value = TagValueSerializer()

    class Meta:
        model = AlbumTagAssignment
        fields = ["id", "album", "tag_value", "created_at", "updated_at"]

    def create(self, validated_data):
        tag_value_data = validated_data.pop("tag_value")
        tag_value, _ = TagValue.objects.get_or_create(
            definition=tag_value_data["definition"],
            value_text=tag_value_data.get("value_text", ""),
            value_number=tag_value_data.get("value_number"),
            value_bool=tag_value_data.get("value_bool"),
            value_date=tag_value_data.get("value_date"),
            defaults={"normalized_key": tag_value_data.get("normalized_key", "")},
        )
        validated_data["tag_value"] = tag_value
        return super().create(validated_data)


class ArtistTagAssignmentSerializer(LoggedModelSerializer):
    tag_value = TagValueSerializer()

    class Meta:
        model = ArtistTagAssignment
        fields = ["id", "artist", "tag_value", "created_at", "updated_at"]

    def create(self, validated_data):
        tag_value_data = validated_data.pop("tag_value")
        tag_value, _ = TagValue.objects.get_or_create(
            definition=tag_value_data["definition"],
            value_text=tag_value_data.get("value_text", ""),
            value_number=tag_value_data.get("value_number"),
            value_bool=tag_value_data.get("value_bool"),
            value_date=tag_value_data.get("value_date"),
            defaults={"normalized_key": tag_value_data.get("normalized_key", "")},
        )
        validated_data["tag_value"] = tag_value
        return super().create(validated_data)


class TrackVersionMembershipSerializer(LoggedModelSerializer):
    track_title = serializers.ReadOnlyField(source="track.canonical_title")

    class Meta:
        model = TrackVersionMembership
        fields = [
            "id",
            "group",
            "track",
            "track_title",
            "role",
            "label",
            "sort_order",
            "is_default",
            "created_at",
            "updated_at",
        ]


class TrackVersionGroupSerializer(LoggedModelSerializer):
    memberships = TrackVersionMembershipSerializer(many=True, read_only=True)

    class Meta:
        model = TrackVersionGroup
        fields = [
            "id",
            "title",
            "sort_title",
            "fingerprint",
            "serving_mode",
            "notes",
            "memberships",
            "created_at",
            "updated_at",
        ]
