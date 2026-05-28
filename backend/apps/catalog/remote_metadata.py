from __future__ import annotations

import json
import os
import re
import time
from difflib import SequenceMatcher
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings as django_settings
from django.utils import timezone

from apps.catalog.models import MetadataEnrichmentJob, RemoteMetadataSettings, Track


TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"
MUSICBRAINZ_API_BASE = "https://musicbrainz.org/ws/2"
COVER_ART_ARCHIVE_BASE = "https://coverartarchive.org"

REMOTE_METADATA_PROVIDERS = [
    {
        "key": "tmdb",
        "label": "TMDb",
        "media_scope": "video",
        "implemented": True,
        "credential_env": ["TRIVER_TMDB_ACCESS_TOKEN", "TRIVER_TMDB_API_KEY"],
        "attribution": "Metadata from TMDb. This product uses the TMDb API but is not endorsed or certified by TMDb.",
    },
    {
        "key": "omdb",
        "label": "OMDb",
        "media_scope": "video",
        "implemented": False,
        "credential_env": ["TRIVER_OMDB_API_KEY"],
        "attribution": "Optional OMDb lookup prepared for future matching.",
    },
    {
        "key": "tvdb",
        "label": "TheTVDB",
        "media_scope": "video",
        "implemented": False,
        "credential_env": ["TRIVER_TVDB_API_KEY"],
        "attribution": "Optional TheTVDB lookup prepared for future matching.",
    },
    {
        "key": "musicbrainz",
        "label": "MusicBrainz",
        "media_scope": "audio",
        "implemented": True,
        "credential_env": [],
        "attribution": "Metadata from MusicBrainz.",
    },
    {
        "key": "coverartarchive",
        "label": "Cover Art Archive",
        "media_scope": "audio",
        "implemented": True,
        "credential_env": [],
        "attribution": "Artwork from Cover Art Archive.",
    },
]


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _provider_configured(provider):
    env_names = provider.get("credential_env") or []
    if not env_names:
        return True
    return any(bool(_env(name)) for name in env_names)


def provider_settings_payload(settings_row: RemoteMetadataSettings | None = None):
    settings_row = settings_row or RemoteMetadataSettings.load()
    providers = []
    for provider in REMOTE_METADATA_PROVIDERS:
        providers.append({
            "key": provider["key"],
            "label": provider["label"],
            "media_scope": provider["media_scope"],
            "implemented": provider["implemented"],
            "configured": _provider_configured(provider),
            "credential_env": provider.get("credential_env") or [],
            "attribution": provider.get("attribution", ""),
        })
    return {
        "id": settings_row.pk,
        "enabled": settings_row.enabled,
        "lookup_mode": settings_row.lookup_mode,
        "video_enabled": settings_row.video_enabled,
        "audio_enabled": settings_row.audio_enabled,
        "allow_remote_artwork": settings_row.allow_remote_artwork,
        "preferred_language": settings_row.preferred_language,
        "preferred_region": settings_row.preferred_region,
        "overwrite_policy": settings_row.overwrite_policy,
        "provider_order": settings_row.provider_order or {},
        "providers": providers,
        "lookup_mode_options": [choice[0] for choice in RemoteMetadataSettings.LOOKUP_MODE_CHOICES],
        "policy_options": [choice[0] for choice in RemoteMetadataSettings.OVERWRITE_CHOICES],
    }


def _provider_by_key(key: str):
    normalized = str(key or "").strip().lower()
    for provider in REMOTE_METADATA_PROVIDERS:
        if provider["key"] == normalized:
            return provider
    return None


def _ordered_provider_keys(settings_row: RemoteMetadataSettings, media_kind: str, requested_provider: str = ""):
    requested = str(requested_provider or "").strip().lower()
    if requested and requested not in {"auto", "default"}:
        return [requested]
    order = settings_row.provider_order or {}
    scope = "video" if media_kind == "video" else "audio"
    keys = [str(key).strip().lower() for key in (order.get(scope) or []) if str(key).strip()]
    if scope == "video":
        fallback = ["tmdb", "omdb", "tvdb"]
    else:
        fallback = ["musicbrainz", "coverartarchive"]
    for key in fallback:
        if key not in keys:
            keys.append(key)
    return keys


def _http_json(url: str, *, headers=None, timeout=12):
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout) as response:
        raw_body = response.read().decode("utf-8")
    return json.loads(raw_body or "{}")


def _tmdb_auth():
    token = _env("TRIVER_TMDB_ACCESS_TOKEN")
    api_key = _env("TRIVER_TMDB_API_KEY")
    if token:
        return {"headers": {"Authorization": f"Bearer {token}", "Accept": "application/json"}, "api_key": ""}
    if api_key:
        return {"headers": {"Accept": "application/json"}, "api_key": api_key}
    return {"headers": {"Accept": "application/json"}, "api_key": ""}


def _tmdb_get(path: str, params=None, timeout=12):
    auth = _tmdb_auth()
    query = dict(params or {})
    if auth["api_key"]:
        query["api_key"] = auth["api_key"]
    url = f"{TMDB_API_BASE}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return _http_json(url, headers=auth["headers"], timeout=timeout)


def _musicbrainz_headers():
    contact = _env("TRIVER_MUSICBRAINZ_CONTACT")
    suffix = f" ({contact})" if contact else ""
    return {
        "Accept": "application/json",
        "User-Agent": f"trueRiver/0.1 metadata-enrichment{suffix}",
    }


def _musicbrainz_get(path: str, params=None, timeout=14):
    query = {"fmt": "json"}
    query.update(params or {})
    return _http_json(
        f"{MUSICBRAINZ_API_BASE}{path}?{urlencode(query)}",
        headers=_musicbrainz_headers(),
        timeout=timeout,
    )


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_match_text(value: str) -> str:
    normalized = str(value or "").lower()
    normalized = re.sub(r"\b(19|20)\d{2}\b", " ", normalized)
    normalized = re.sub(r"\b(?:s\d{1,3}e\d{1,3}|\d{1,3}x\d{1,3})\b", " ", normalized)
    normalized = re.sub(r"\[[^\]]+\]|\([^\)]*\)", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _filename_title(track: Track) -> str:
    media_file = track.primary_file
    if not media_file:
        return track.canonical_title
    name = media_file.filename or media_file.relative_path
    title = re.sub(r"\.[A-Za-z0-9]{2,6}$", "", str(name or ""))
    title = title.replace(".", " ").replace("_", " ")
    return _compact_text(title)


def _similarity(a: str, b: str) -> float:
    left = _normalize_match_text(a)
    right = _normalize_match_text(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return 0.82
    return SequenceMatcher(None, left, right).ratio()


def _first_existing_value(metadata, *field_names):
    wanted = {_normalize_match_text(field_name) for field_name in field_names}
    for key, values in (metadata or {}).items():
        if _normalize_match_text(key) not in wanted:
            continue
        if isinstance(values, (list, tuple)):
            for value in values:
                text = _compact_text(value)
                if text:
                    return text
        text = _compact_text(values)
        if text:
            return text
    return ""


def _existing_metadata(track: Track):
    media_file = track.primary_file
    if not media_file:
        return {}
    payload = {}
    for meta_value in media_file.meta_values.select_related("field").all():
        field_name = meta_value.field.name if meta_value.field else meta_value.source_name
        if not field_name:
            continue
        payload.setdefault(field_name, []).append(meta_value.value_text)
    return payload


def _track_artist_names(track: Track):
    names = []
    for credit in track.artist_credits.all():
        if credit.artist and credit.artist.name:
            names.append(credit.artist.name)
    return names


def _track_query_title(track: Track, metadata):
    return (
        _first_existing_value(metadata, "TrackName", "EpisodeTitle", "Title")
        or track.canonical_title
        or _filename_title(track)
    )


def _track_release_year(track: Track, metadata):
    raw = _first_existing_value(metadata, "ReleaseDate", "Year")
    if not raw and track.release_year:
        raw = str(track.release_year)
    match = re.search(r"\b(19|20)\d{2}\b", str(raw or ""))
    return match.group(0) if match else ""


def _poster_url(path: str, size="w500"):
    return f"{TMDB_IMAGE_BASE}/{size}{path}" if path else ""


def _has_metadata_value(value):
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return any(_compact_text(item) for item in value)
    return bool(_compact_text(value))


def _tmdb_genres(kind: str, language: str):
    try:
        payload = _tmdb_get(f"/genre/{kind}/list", {"language": language or "en-US"}, timeout=8)
    except Exception:
        return {}
    return {item.get("id"): item.get("name") for item in payload.get("genres") or [] if item.get("id") and item.get("name")}


def _tmdb_external_ids(kind: str, tmdb_id):
    try:
        return _tmdb_get(f"/{kind}/{tmdb_id}/external_ids", {}, timeout=8)
    except Exception:
        return {}


def _tmdb_episode_metadata(tmdb_id, season_number, episode_number, language):
    if season_number in {"", None} or episode_number in {"", None}:
        return {}
    try:
        season = int(season_number)
        episode = int(episode_number)
    except (TypeError, ValueError):
        return {}
    try:
        payload = _tmdb_get(f"/tv/{tmdb_id}/season/{season}/episode/{episode}", {"language": language or "en-US"}, timeout=8)
    except Exception:
        return {}
    metadata = {}
    if payload.get("name"):
        metadata["EpisodeTitle"] = payload["name"]
    if payload.get("air_date"):
        metadata["ReleaseDate"] = payload["air_date"]
    if payload.get("overview"):
        metadata["Overview"] = payload["overview"]
    return metadata


def _tmdb_candidate_from_result(result, *, kind, query_title, query_year, genres_by_id, metadata, settings_row):
    title_key = "title" if kind == "movie" else "name"
    date_key = "release_date" if kind == "movie" else "first_air_date"
    title = _compact_text(result.get(title_key))
    if not title:
        return None
    release_date = _compact_text(result.get(date_key))
    release_year = release_date[:4] if release_date else ""
    confidence = _similarity(query_title, title)
    if query_year and release_year and query_year == release_year:
        confidence = min(0.99, confidence + 0.08)
    elif query_year and release_year:
        confidence = max(0.0, confidence - 0.08)

    tmdb_id = result.get("id")
    external_ids = _tmdb_external_ids(kind, tmdb_id) if tmdb_id else {}
    genre_names = [
        genres_by_id.get(genre_id)
        for genre_id in (result.get("genre_ids") or [])
        if genres_by_id.get(genre_id)
    ]
    candidate_metadata = {}
    if kind == "movie":
        candidate_metadata["TrackName"] = title
    else:
        candidate_metadata["SeriesTitle"] = title
        candidate_metadata.update(_tmdb_episode_metadata(
            tmdb_id,
            _first_existing_value(metadata, "SeasonNumber"),
            _first_existing_value(metadata, "EpisodeNumber"),
            settings_row.preferred_language,
        ))
    if release_date:
        candidate_metadata.setdefault("ReleaseDate", release_date)
    if result.get("overview"):
        candidate_metadata.setdefault("Overview", result["overview"])
        candidate_metadata.setdefault("Comment", result["overview"])
    if genre_names:
        candidate_metadata["Genre"] = genre_names
    if tmdb_id:
        candidate_metadata["TMDbId"] = str(tmdb_id)
    if external_ids.get("imdb_id"):
        candidate_metadata["IMDbId"] = external_ids["imdb_id"]
    if external_ids.get("tvdb_id"):
        candidate_metadata["TVDbId"] = str(external_ids["tvdb_id"])
    if settings_row.allow_remote_artwork:
        if result.get("poster_path"):
            candidate_metadata["PosterUrl"] = _poster_url(result["poster_path"])
        if result.get("backdrop_path"):
            candidate_metadata["BackdropUrl"] = _poster_url(result["backdrop_path"], size="w780")

    return {
        "match_id": f"tmdb:{kind}:{tmdb_id}",
        "provider": "tmdb",
        "provider_label": "TMDb",
        "media_kind": "video",
        "label": title,
        "subtitle": " · ".join(part for part in [kind.replace("_", " "), release_year] if part),
        "confidence": round(max(0.0, min(confidence, 0.99)), 2),
        "external_ids": {
            "tmdb": str(tmdb_id or ""),
            "imdb": external_ids.get("imdb_id") or "",
            "tvdb": str(external_ids.get("tvdb_id") or ""),
        },
        "artwork": {
            "poster_url": candidate_metadata.get("PosterUrl", ""),
            "backdrop_url": candidate_metadata.get("BackdropUrl", ""),
        },
        "metadata": {key: value for key, value in candidate_metadata.items() if _has_metadata_value(value)},
    }


def _tmdb_candidates(track: Track, settings_row: RemoteMetadataSettings, metadata):
    if not _provider_configured(_provider_by_key("tmdb")):
        return {"status": "provider_unconfigured", "provider": "tmdb", "candidates": []}

    language = settings_row.preferred_language or "en-US"
    query_year = _track_release_year(track, metadata)
    series_title = _first_existing_value(metadata, "SeriesTitle")
    if series_title:
        kind = "tv"
        query_title = series_title
        params = {"query": query_title, "language": language, "include_adult": "false"}
        genres_by_id = _tmdb_genres("tv", language)
        path = "/search/tv"
    else:
        kind = "movie"
        query_title = _track_query_title(track, metadata)
        params = {
            "query": query_title,
            "language": language,
            "include_adult": "false",
            "region": settings_row.preferred_region or "US",
        }
        if query_year:
            params["year"] = query_year
        genres_by_id = _tmdb_genres("movie", language)
        path = "/search/movie"

    if not query_title:
        return {"status": "no_query", "provider": "tmdb", "query": "", "candidates": []}
    payload = _tmdb_get(path, params, timeout=12)
    candidates = []
    for result in (payload.get("results") or [])[:5]:
        candidate = _tmdb_candidate_from_result(
            result,
            kind=kind,
            query_title=query_title,
            query_year=query_year,
            genres_by_id=genres_by_id,
            metadata=metadata,
            settings_row=settings_row,
        )
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda item: item["confidence"], reverse=True)
    return {"status": "ready" if candidates else "no_match", "provider": "tmdb", "query": query_title, "candidates": candidates}


def _musicbrainz_escape(value: str) -> str:
    return str(value or "").replace('"', '\\"')


def _musicbrainz_candidate(recording, track: Track, metadata, settings_row: RemoteMetadataSettings):
    title = _compact_text(recording.get("title"))
    if not title:
        return None
    artist_credit = recording.get("artist-credit") or []
    artists = [
        _compact_text(entry.get("artist", {}).get("name"))
        for entry in artist_credit
        if _compact_text(entry.get("artist", {}).get("name"))
    ]
    releases = recording.get("releases") or []
    release = releases[0] if releases else {}
    release_group = release.get("release-group") or {}
    release_date = _compact_text(release.get("date"))
    album_title = _compact_text(release.get("title"))
    tags = sorted([
        tag.get("name")
        for tag in (recording.get("tags") or [])
        if tag.get("name")
    ])
    score = recording.get("score")
    try:
        confidence = float(score) / 100.0
    except (TypeError, ValueError):
        confidence = _similarity(_track_query_title(track, metadata), title)

    candidate_metadata = {
        "TrackName": title,
        "MusicBrainzRecordingId": recording.get("id") or "",
    }
    if artists:
        candidate_metadata["Artist"] = artists
    if album_title:
        candidate_metadata["Album"] = album_title
    if release_date:
        candidate_metadata["ReleaseDate"] = release_date
    if release.get("id"):
        candidate_metadata["MusicBrainzReleaseId"] = release["id"]
    if release_group.get("id"):
        candidate_metadata["MusicBrainzReleaseGroupId"] = release_group["id"]
    if artist_credit and artist_credit[0].get("artist", {}).get("id"):
        candidate_metadata["MusicBrainzArtistId"] = artist_credit[0]["artist"]["id"]
    if tags:
        candidate_metadata["Genre"] = tags[:6]

    if settings_row.allow_remote_artwork and release.get("id"):
        cover_url = _cover_art_archive_front_url(release["id"])
        if cover_url:
            candidate_metadata["PosterUrl"] = cover_url

    return {
        "match_id": f"musicbrainz:recording:{recording.get('id')}",
        "provider": "musicbrainz",
        "provider_label": "MusicBrainz",
        "media_kind": "audio",
        "label": title,
        "subtitle": " · ".join(part for part in [", ".join(artists), album_title, release_date[:4]] if part),
        "confidence": round(max(0.0, min(confidence, 0.99)), 2),
        "external_ids": {
            "musicbrainz_recording": recording.get("id") or "",
            "musicbrainz_release": release.get("id") or "",
            "musicbrainz_release_group": release_group.get("id") or "",
        },
        "artwork": {
            "poster_url": candidate_metadata.get("PosterUrl", ""),
        },
        "metadata": {key: value for key, value in candidate_metadata.items() if _has_metadata_value(value)},
    }


def _cover_art_archive_front_url(release_id: str):
    try:
        payload = _http_json(f"{COVER_ART_ARCHIVE_BASE}/release/{release_id}", headers={"Accept": "application/json"}, timeout=8)
    except Exception:
        return ""
    for image in payload.get("images") or []:
        if not image.get("front"):
            continue
        thumbnails = image.get("thumbnails") or {}
        return thumbnails.get("large") or thumbnails.get("500") or image.get("image") or ""
    return ""


def _musicbrainz_candidates(track: Track, settings_row: RemoteMetadataSettings, metadata):
    query_title = _track_query_title(track, metadata)
    artists = _track_artist_names(track)
    artist = artists[0] if artists else _first_existing_value(metadata, "Artist")
    if not query_title:
        return {"status": "no_query", "provider": "musicbrainz", "query": "", "candidates": []}
    if artist:
        query = f'recording:"{_musicbrainz_escape(query_title)}" AND artist:"{_musicbrainz_escape(artist)}"'
    else:
        query = f'recording:"{_musicbrainz_escape(query_title)}"'
    payload = _musicbrainz_get(
        "/recording/",
        {
            "query": query,
            "limit": 5,
            "inc": "artist-credits+releases+release-groups+tags",
        },
        timeout=14,
    )
    candidates = []
    for recording in payload.get("recordings") or []:
        candidate = _musicbrainz_candidate(recording, track, metadata, settings_row)
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda item: item["confidence"], reverse=True)
    return {"status": "ready" if candidates else "no_match", "provider": "musicbrainz", "query": query_title, "candidates": candidates}


def _not_available(provider_key: str, status: str):
    provider = _provider_by_key(provider_key) or {}
    return {
        "status": status,
        "provider": provider_key,
        "provider_label": provider.get("label", provider_key),
        "query": "",
        "candidates": [],
    }


def _track_remote_metadata_preview(track: Track, settings_row: RemoteMetadataSettings, provider_key: str = ""):
    media_file = track.primary_file
    media_kind = media_file.media_kind if media_file else ""
    metadata = _existing_metadata(track)
    base = {
        "track_id": str(track.pk),
        "track_title": track.canonical_title,
        "filename": media_file.filename if media_file else "",
        "display_path": media_file.display_path if media_file else "",
        "media_kind": media_kind or "unknown",
        "existing": metadata,
    }

    if not settings_row.enabled:
        return {**base, **_not_available("", "remote_lookup_disabled")}
    if media_kind == "video" and not settings_row.video_enabled:
        return {**base, **_not_available("", "video_lookup_disabled")}
    if media_kind == "audio" and not settings_row.audio_enabled:
        return {**base, **_not_available("", "audio_lookup_disabled")}
    if media_kind not in {"audio", "video"}:
        return {**base, **_not_available("", "unsupported_media")}

    last_result = None
    for key in _ordered_provider_keys(settings_row, media_kind, provider_key):
        provider = _provider_by_key(key)
        if not provider:
            last_result = _not_available(key, "provider_unknown")
            continue
        if provider["media_scope"] != media_kind:
            last_result = _not_available(key, "provider_wrong_media")
            continue
        if not provider["implemented"]:
            last_result = _not_available(key, "provider_prepared")
            continue
        if not _provider_configured(provider):
            last_result = _not_available(key, "provider_unconfigured")
            continue
        try:
            if key == "tmdb":
                result = _tmdb_candidates(track, settings_row, metadata)
            elif key == "musicbrainz":
                result = _musicbrainz_candidates(track, settings_row, metadata)
                time.sleep(1.1)
            else:
                result = _not_available(key, "provider_prepared")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            result = _not_available(key, "provider_error")
            result["detail"] = str(exc)
        last_result = result
        if result.get("candidates"):
            return {**base, **result}
    return {**base, **(last_result or _not_available("", "no_provider"))}


def run_metadata_enrichment_job_sync(job_id: str):
    job = MetadataEnrichmentJob.objects.select_related("library").get(pk=job_id)
    settings_row = RemoteMetadataSettings.load()
    job.status = MetadataEnrichmentJob.STATUS_RUNNING
    job.started_at = timezone.now()
    job.finished_at = None
    job.candidate_count = 0
    job.updated_count = 0
    job.last_error = ""
    job.result_payload = {}
    job.save(update_fields=[
        "status",
        "started_at",
        "finished_at",
        "candidate_count",
        "updated_count",
        "last_error",
        "result_payload",
        "updated_at",
    ])

    try:
        track_ids = [str(track_id) for track_id in (job.target_track_ids or []) if str(track_id)]
        tracks = (
            Track.objects
            .filter(pk__in=track_ids)
            .select_related("album", "primary_file", "primary_file__source_folder")
            .prefetch_related("artist_credits__artist", "primary_file__meta_values__field")
        )
        tracks_by_id = {str(track.pk): track for track in tracks}
        items = []
        candidate_count = 0
        for track_id in track_ids:
            if MetadataEnrichmentJob.objects.filter(pk=job.pk, status=MetadataEnrichmentJob.STATUS_CANCELED).exists():
                job.refresh_from_db()
                return {"job_id": str(job.pk), "status": job.status}
            track = tracks_by_id.get(track_id)
            if not track:
                items.append({
                    "track_id": track_id,
                    "status": "track_not_found",
                    "candidates": [],
                })
                continue
            item = _track_remote_metadata_preview(track, settings_row, provider_key=job.provider_key)
            candidate_count += len(item.get("candidates") or [])
            items.append(item)

        job.status = MetadataEnrichmentJob.STATUS_DONE
        job.finished_at = timezone.now()
        job.candidate_count = candidate_count
        job.result_payload = {
            "items": items,
            "settings": provider_settings_payload(settings_row),
            "mode": job.mode,
        }
        job.save(update_fields=["status", "finished_at", "candidate_count", "result_payload", "updated_at"])
        return {"job_id": str(job.pk), "status": job.status, "candidate_count": candidate_count}
    except Exception as exc:
        job.status = MetadataEnrichmentJob.STATUS_ERROR
        job.finished_at = timezone.now()
        job.last_error = str(exc)
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        raise


def settings_snapshot_from_env():
    payload = {
        "tmdb_configured": bool(_env("TRIVER_TMDB_ACCESS_TOKEN") or _env("TRIVER_TMDB_API_KEY")),
        "omdb_configured": bool(_env("TRIVER_OMDB_API_KEY")),
        "tvdb_configured": bool(_env("TRIVER_TVDB_API_KEY")),
        "musicbrainz_contact": bool(_env("TRIVER_MUSICBRAINZ_CONTACT")),
        "celery_eager": bool(getattr(django_settings, "CELERY_TASK_ALWAYS_EAGER", False)),
    }
    return payload
