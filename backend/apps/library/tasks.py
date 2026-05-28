from __future__ import annotations

import hashlib
import errno
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from datetime import datetime

from celery import chord, group, shared_task
from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from mutagen import File as MutagenFile

from apps.catalog.models import (
    Album,
    Artist,
    MediaTransformJob,
    MetadataWritebackJob,
    Track,
    TrackArtistCredit,
    TrackSourceMetadata,
)

from apps.library.models import (
    AccessoryFile,
    AutoImportSettings,
    BROWSER_FRIENDLY_VIDEO_EXTENSIONS,
    DIAGNOSTIC_EXTENSIONS,
    DEFAULT_META_FIELD_NAMES,
    DEFAULT_META_NORMALIZATION_RULES,
    IGNORED_FILENAMES,
    LibraryDigestError,
    LibraryDigestJob,
    Library,
    LibraryScanJob,
    LibraryScanSkip,
    MediaFile,
    MediaFileMetaValue,
    MetaFieldDefinition,
    MetaNormalizationRule,
    SourceFolder,
    SUPPORTED_ARTWORK_EXTENSIONS,
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_CUESHEET_EXTENSIONS,
    SUPPORTED_MEDIA_EXTENSIONS,
    SUPPORTED_PLAYLIST_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS,
)

logger = logging.getLogger(__name__)


DIGEST_COUNTER_KEYS = ("processed_count", "created_track_count", "reused_track_count", "error_count")
CLASSIC_IMPORT_PREFIX = "Classic"


def _positive_int_setting(name: str, default: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default
    return max(1, value)


def _non_negative_int_setting(name: str, default: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return max(0, default)
    return max(0, value)


def _non_negative_float_setting(name: str, default: float) -> float:
    try:
        value = float(getattr(settings, name, default))
    except (TypeError, ValueError):
        return max(0.0, default)
    return max(0.0, value)


def _bool_setting(name: str, default: bool = False) -> bool:
    value = getattr(settings, name, default)
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _sleep_if_configured(name: str, default: float = 0.0):
    seconds = _non_negative_float_setting(name, default)
    if seconds > 0:
        time.sleep(seconds)


def _scan_pause(iteration_count: int):
    every = _positive_int_setting("TRIVER_SCAN_SLEEP_EVERY", 20)
    if every and iteration_count % every == 0:
        _sleep_if_configured("TRIVER_SCAN_ITEM_SLEEP_SECONDS", 0.02)


def _digest_batch_size() -> int:
    return _positive_int_setting("TRIVER_DIGEST_BATCH_SIZE", 10)


def _digest_progress_interval() -> int:
    return _positive_int_setting("TRIVER_DIGEST_PROGRESS_INTERVAL", 1)


def _chunked(sequence, chunk_size: int):
    batch = []
    for item in sequence:
        batch.append(item)
        if len(batch) >= chunk_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _normalize_classic_source_key(value: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip().lower()).strip("-")
    return key or "source"


def _classic_import_sources_from_settings():
    raw_value = str(getattr(settings, "TRIVER_CLASSIC_IMPORT_SOURCES", "") or "")
    entries = []
    seen_keys = set()
    for raw_entry in re.split(r"[;\n]+", raw_value):
        entry = raw_entry.strip()
        if not entry:
            continue
        if "|" in entry:
            parts = [part.strip() for part in entry.split("|", 2)]
            if len(parts) != 3:
                continue
            key, label, container_path = parts
        elif "=" in entry:
            key, container_path = [part.strip() for part in entry.split("=", 1)]
            label = key
        else:
            container_path = entry
            key = Path(container_path).name
            label = key
        normalized_key = _normalize_classic_source_key(key)
        if normalized_key in seen_keys:
            continue
        seen_keys.add(normalized_key)
        path = Path(container_path)
        entries.append({
            "key": normalized_key,
            "label": label or normalized_key,
            "container_path": str(path),
            "relative_prefix": f"{CLASSIC_IMPORT_PREFIX}/{normalized_key}",
            "exists": path.exists(),
            "is_dir": path.is_dir(),
            "readable": os.access(path, os.R_OK) if path.exists() else False,
        })
    return entries


def classic_import_sources_payload():
    return {
        "prefix": CLASSIC_IMPORT_PREFIX,
        "sources": _classic_import_sources_from_settings(),
    }


def _auto_import_scan_pause(iteration_count: int):
    every = _positive_int_setting("TRIVER_AUTO_IMPORT_SCAN_SLEEP_EVERY", 250)
    if every and iteration_count % every == 0:
        _sleep_if_configured("TRIVER_AUTO_IMPORT_SCAN_SLEEP_SECONDS", 0.01)


def _tree_signature(root_path: Path):
    signature = {
        "exists": root_path.exists(),
        "readable": False,
        "file_count": 0,
        "total_size": 0,
        "latest_mtime_ns": 0,
        "latest_path": "",
        "error_count": 0,
        "stable": True,
    }
    if not signature["exists"] or not root_path.is_dir() or not os.access(root_path, os.R_OK):
        return signature

    signature["readable"] = True
    stack = [root_path]
    scanned_count = 0
    while stack:
        current_path = stack.pop()
        try:
            with os.scandir(current_path) as iterator:
                for entry in iterator:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        stat_result = entry.stat(follow_symlinks=False)
                    except OSError:
                        signature["error_count"] += 1
                        continue
                    scanned_count += 1
                    _auto_import_scan_pause(scanned_count)
                    mtime_ns = int(getattr(stat_result, "st_mtime_ns", int(stat_result.st_mtime * 1_000_000_000)))
                    signature["file_count"] += 1
                    signature["total_size"] += int(stat_result.st_size)
                    if mtime_ns > signature["latest_mtime_ns"]:
                        signature["latest_mtime_ns"] = mtime_ns
                        try:
                            signature["latest_path"] = Path(entry.path).relative_to(root_path).as_posix()
                        except ValueError:
                            signature["latest_path"] = str(entry.path)
        except OSError:
            signature["error_count"] += 1

    quiet_seconds = _non_negative_int_setting("TRIVER_AUTO_IMPORT_QUIET_SECONDS", 90)
    if quiet_seconds and signature["latest_mtime_ns"]:
        latest_seconds = signature["latest_mtime_ns"] / 1_000_000_000
        signature["stable"] = (time.time() - latest_seconds) >= quiet_seconds
    return signature


def _signature_payload(signature):
    return {
        "exists": bool(signature.get("exists")),
        "readable": bool(signature.get("readable")),
        "file_count": int(signature.get("file_count") or 0),
        "total_size": int(signature.get("total_size") or 0),
        "latest_mtime_ns": int(signature.get("latest_mtime_ns") or 0),
        "latest_path": str(signature.get("latest_path") or ""),
        "error_count": int(signature.get("error_count") or 0),
        "stable": bool(signature.get("stable", True)),
    }


def _signatures_differ(previous, current) -> bool:
    if previous is None:
        return True
    if previous == {}:
        return False
    return _signature_payload(previous) != _signature_payload(current)


def _io_job_is_active(library: Library) -> bool:
    scan_active = LibraryScanJob.objects.filter(
        library=library,
        status__in=[
            LibraryScanJob.STATUS_PENDING,
            LibraryScanJob.STATUS_DISCOVERING,
            LibraryScanJob.STATUS_PROCESSING,
        ],
    ).exists()
    digest_active = LibraryDigestJob.objects.filter(
        library=library,
        status__in=[
            LibraryDigestJob.STATUS_PENDING,
            LibraryDigestJob.STATUS_RUNNING,
        ],
    ).exists()
    return scan_active or digest_active


def _classic_source_signatures():
    signatures = {}
    for source in _classic_import_sources_from_settings():
        if not source["exists"] or not source["is_dir"] or not source["readable"]:
            continue
        signatures[source["key"]] = _signature_payload(_tree_signature(Path(source["container_path"])))
    return signatures


def _schedule_trive_auto_import(settings_obj: AutoImportSettings, force: bool):
    library = settings_obj.library
    signature = _signature_payload(_tree_signature(Path(library.ingest_path)))
    previous = settings_obj.last_trive_signature or {}
    changed = force or _signatures_differ(previous, signature)
    if not previous and not force:
        settings_obj.last_trive_signature = signature
        return {"scope": "trive", "action": "baseline", "signature": signature}
    if not changed:
        settings_obj.last_trive_signature = signature
        return {"scope": "trive", "action": "unchanged", "signature": signature}
    if not signature.get("stable", True):
        return {"scope": "trive", "action": "waiting_for_stable_files", "signature": signature}
    if not settings_obj.trive_scan_enabled:
        settings_obj.last_trive_signature = signature
        return {"scope": "trive", "action": "scan_disabled", "signature": signature}

    scan_job = LibraryScanJob.objects.create(library=library, status=LibraryScanJob.STATUS_PENDING)
    if settings_obj.trive_up_enabled:
        digest_job = LibraryDigestJob.objects.create(library=library, status=LibraryDigestJob.STATUS_PENDING)
        async_result = run_trive_import.delay(scan_job.id, digest_job.id, "")
        action = "trive_scan_and_up"
        result = {
            "scope": "trive",
            "action": action,
            "scan_job_id": scan_job.id,
            "digest_job_id": digest_job.id,
            "celery_task_id": async_result.id,
            "signature": signature,
        }
    else:
        async_result = discover_library.delay(scan_job.id, "")
        action = "trive_scan"
        result = {
            "scope": "trive",
            "action": action,
            "scan_job_id": scan_job.id,
            "celery_task_id": async_result.id,
            "signature": signature,
        }
    settings_obj.last_trive_signature = signature
    settings_obj.last_triggered_at = timezone.now()
    return result


def _schedule_classic_auto_import(settings_obj: AutoImportSettings, force: bool):
    signatures = _classic_source_signatures()
    previous = settings_obj.last_classic_signatures or {}
    changed = force or any(
        _signatures_differ(previous.get(key), signature)
        for key, signature in signatures.items()
    )
    if not signatures:
        return {"scope": "classic", "action": "no_sources", "signatures": signatures}
    if not previous and not force:
        settings_obj.last_classic_signatures = signatures
        return {"scope": "classic", "action": "baseline", "signatures": signatures}
    if not changed:
        settings_obj.last_classic_signatures = signatures
        return {"scope": "classic", "action": "unchanged", "signatures": signatures}
    unstable = [key for key, signature in signatures.items() if not signature.get("stable", True)]
    if unstable:
        return {"scope": "classic", "action": "waiting_for_stable_files", "sources": unstable, "signatures": signatures}
    if not settings_obj.classic_scan_enabled:
        settings_obj.last_classic_signatures = signatures
        return {"scope": "classic", "action": "scan_disabled", "signatures": signatures}

    source_keys = sorted(signatures.keys())
    scan_job = LibraryScanJob.objects.create(library=settings_obj.library, status=LibraryScanJob.STATUS_PENDING)
    if settings_obj.classic_up_enabled:
        digest_job = LibraryDigestJob.objects.create(library=settings_obj.library, status=LibraryDigestJob.STATUS_PENDING)
        async_result = run_classic_import.delay(scan_job.id, digest_job.id, source_keys)
        result = {
            "scope": "classic",
            "action": "classic_scan_and_up",
            "scan_job_id": scan_job.id,
            "digest_job_id": digest_job.id,
            "celery_task_id": async_result.id,
            "source_keys": source_keys,
            "signatures": signatures,
        }
    else:
        async_result = discover_classic_import_sources.delay(scan_job.id, source_keys)
        result = {
            "scope": "classic",
            "action": "classic_scan",
            "scan_job_id": scan_job.id,
            "celery_task_id": async_result.id,
            "source_keys": source_keys,
            "signatures": signatures,
        }
    settings_obj.last_classic_signatures = signatures
    settings_obj.last_triggered_at = timezone.now()
    return result


def _empty_digest_result():
    return {
        "processed_count": 0,
        "created_track_count": 0,
        "reused_track_count": 0,
        "error_count": 0,
        "last_error": "",
    }


def _merge_digest_result(target, source):
    for key in DIGEST_COUNTER_KEYS:
        target[key] = int(target.get(key) or 0) + int(source.get(key) or 0)
    if source.get("last_error"):
        target["last_error"] = source["last_error"]
    return target


def _has_digest_delta(result) -> bool:
    return any(int(result.get(key) or 0) for key in DIGEST_COUNTER_KEYS) or bool(result.get("last_error"))


def _record_digest_progress(job_id: int, result):
    updates = {}
    for key in DIGEST_COUNTER_KEYS:
        delta = int(result.get(key) or 0)
        if delta:
            updates[key] = F(key) + delta
    if result.get("last_error"):
        updates["last_error"] = result["last_error"]
    if updates:
        updates["updated_at"] = timezone.now()
        LibraryDigestJob.objects.filter(pk=job_id).update(**updates)


def _stable_signed_lock_key(namespace: str, value: str) -> int:
    digest = hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _acquire_catalog_xact_lock(namespace: str, value: str):
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_stable_signed_lock_key(namespace, value)])


def _get_or_create_default_library() -> Library:
    """
    Bootstrap minimale della prima libreria.

    Per questa fase Triver assume una sola library di default. In futuro questa logica
    andra' spostata in una configurazione esplicita lato API/admin.
    """

    library, _ = Library.objects.get_or_create(
        slug="true-river",
        defaults={
            "name": "True River",
            "ingest_path": settings.TRIVER_INGEST_ROOT,
            "digest_path": settings.TRIVER_DIGEST_ROOT,
            "normalize_path": settings.TRIVER_NORMALIZE_ROOT,
            "enabled": True,
            "notes": "Library bootstrap creata automaticamente dal primo scan.",
        },
    )
    changed = False
    if library.ingest_path != settings.TRIVER_INGEST_ROOT:
        library.ingest_path = settings.TRIVER_INGEST_ROOT
        changed = True
    if library.digest_path != settings.TRIVER_DIGEST_ROOT:
        library.digest_path = settings.TRIVER_DIGEST_ROOT
        changed = True
    if library.normalize_path != settings.TRIVER_NORMALIZE_ROOT:
        library.normalize_path = settings.TRIVER_NORMALIZE_ROOT
        changed = True
    if changed:
        library.save(update_fields=["ingest_path", "digest_path", "normalize_path", "updated_at"])
    _bootstrap_default_meta_registry()
    return library


def _normalize_meta_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", (value or "")).upper()


def _sanitize_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    return str(value).replace("\x00", "").strip()


def _sanitize_json_compatible(value):
    if isinstance(value, dict):
        return {
            _sanitize_text(key): _sanitize_json_compatible(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_json_compatible(item) for item in value]
    if isinstance(value, bytes):
        return _sanitize_text(value)
    if isinstance(value, str):
        return value.replace("\x00", "")
    return value


def _titleize_meta_name(raw_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", (raw_name or "")).strip()
    if not cleaned:
        return "Unknown"
    return "".join(part.capitalize() for part in cleaned.split())


def _infer_meta_source_family(media_file: MediaFile) -> str:
    extension = (media_file.extension or "").lower()
    if extension == "mp3":
        return "id3"
    if extension == "flac":
        return "vorbis"
    if extension in {"m4a", "aac"}:
        return "mp4"
    if extension == "wma":
        return "asf"
    return extension or "unknown"


def _detect_media_kind(extension: str) -> str:
    normalized_extension = (extension or "").lower()
    if normalized_extension in SUPPORTED_VIDEO_EXTENSIONS:
        return "video"
    return "audio"


def _is_browser_playable_video(extension: str) -> bool:
    return (extension or "").lower() in BROWSER_FRIENDLY_VIDEO_EXTENSIONS


def _normalize_scope_path(raw_path) -> str:
    normalized = str(raw_path or "").strip().replace("\\", "/")
    if normalized in {"", ".", "/"}:
        return ""

    normalized = normalized.lstrip("/")
    parts = []
    for part in Path(normalized).parts:
        if part in {"", ".", ".."}:
            raise ValueError("Invalid target path.")
        parts.append(part)
    return Path(*parts).as_posix() if parts else ""


def _resolve_scope_path(root_path: Path, target_path: str) -> Path:
    resolved_root = root_path.resolve()
    if not target_path:
        return resolved_root
    scoped_path = (resolved_root / target_path).resolve()
    if scoped_path != resolved_root and resolved_root not in scoped_path.parents:
        raise ValueError("Target path escapes library root.")
    return scoped_path


def _iter_scoped_file_paths(root_path: Path, target_path: str):
    scoped_path = _resolve_scope_path(root_path, target_path)
    if not scoped_path.exists():
        raise FileNotFoundError(f"Scoped path not found: {scoped_path}")
    if scoped_path.is_file():
        yield scoped_path
        return

    for current_root, _dirs, filenames in os.walk(scoped_path):
        filenames.sort()
        for filename in filenames:
            candidate = Path(current_root) / filename
            if candidate.is_file():
                yield candidate


def _path_matches_scope(relative_path: str, target_path: str) -> bool:
    if not target_path:
        return True
    normalized_relative = str(relative_path or "")
    return normalized_relative == target_path or normalized_relative.startswith(f"{target_path}/")


def _relative_prefix_q(field_name: str, prefixes) -> Q:
    query = Q(pk__in=[])
    for prefix in prefixes:
        normalized = str(prefix or "").strip("/")
        if not normalized:
            continue
        query |= Q(**{field_name: normalized}) | Q(**{f"{field_name}__startswith": f"{normalized}/"})
    return query


def _apply_relative_path_scope(queryset, field_name: str, target_path: str):
    if not target_path:
        return queryset
    return queryset.filter(
        Q(**{field_name: target_path}) | Q(**{f"{field_name}__startswith": f"{target_path}/"})
    )


def _bootstrap_default_meta_registry():
    field_cache = {}
    active_rule_keys = set()
    for field_name in DEFAULT_META_FIELD_NAMES:
        field, _ = MetaFieldDefinition.objects.get_or_create(
            normalized_name=_normalize_meta_token(field_name).lower(),
            defaults={
                "name": field_name,
                "source_family": "triver",
                "is_user_defined": False,
                "is_indexed": True,
            },
        )
        if field.name != field_name or field.source_family != "triver":
            field.name = field_name
            field.source_family = "triver"
            field.save(update_fields=["name", "source_family", "updated_at"])
        field_cache[field_name] = field

    for source_family, source_name, target_field_name in DEFAULT_META_NORMALIZATION_RULES:
        target_field = field_cache[target_field_name]
        normalized_source_name = _normalize_meta_token(source_name)
        active_rule_keys.add((source_family, normalized_source_name))
        rule, created = MetaNormalizationRule.objects.get_or_create(
            source_family=source_family,
            source_name_normalized=normalized_source_name,
            defaults={
                "source_name": source_name,
                "target_field": target_field,
                "is_active": True,
                "is_system": True,
            },
        )
        if not created and (rule.source_name != source_name or rule.target_field_id != target_field.id or not rule.is_active):
            rule.source_name = source_name
            rule.target_field = target_field
            rule.is_active = True
            rule.is_system = True
            rule.save(update_fields=["source_name", "target_field", "is_active", "is_system", "updated_at"])

    stale_rules = MetaNormalizationRule.objects.filter(is_system=True)
    for stale_rule in stale_rules:
        rule_key = (stale_rule.source_family, stale_rule.source_name_normalized)
        should_be_active = rule_key in active_rule_keys
        if stale_rule.is_active != should_be_active:
            stale_rule.is_active = should_be_active
            stale_rule.save(update_fields=["is_active", "updated_at"])


def _get_or_create_meta_field(raw_name: str, source_family: str) -> MetaFieldDefinition:
    field_name = _titleize_meta_name(raw_name)
    normalized_field_name = _normalize_meta_token(field_name).lower()
    field, _ = MetaFieldDefinition.objects.get_or_create(
        normalized_name=normalized_field_name,
        defaults={
            "name": field_name,
            "source_family": source_family,
            "is_user_defined": False,
            "is_indexed": True,
        },
    )
    return field


def _coerce_mutagen_values(raw_value):
    if raw_value is None:
        return []
    if hasattr(raw_value, "text"):
        return [_sanitize_text(item) for item in raw_value.text if _sanitize_text(item)]
    if hasattr(raw_value, "urls"):
        return [_sanitize_text(item) for item in raw_value.urls if _sanitize_text(item)]
    if isinstance(raw_value, (list, tuple)):
        return [_sanitize_text(item) for item in raw_value if _sanitize_text(item)]
    text = _sanitize_text(raw_value)
    return [text] if text else []


def _extract_raw_metadata_entries(media_file: MediaFile):
    if media_file.media_kind != "audio":
        return []
    parsed_file = MutagenFile(media_file.absolute_path, easy=False)
    raw_tags = getattr(parsed_file, "tags", None) or {}
    if not hasattr(raw_tags, "items"):
        return []

    source_family = _infer_meta_source_family(media_file)
    entries = []
    for raw_name, raw_value in raw_tags.items():
        values = _coerce_mutagen_values(raw_value)
        if not values:
            continue
        for index, value_text in enumerate(values):
            entries.append({
                "source_family": source_family,
                "source_name": _sanitize_text(raw_name),
                "source_name_normalized": _normalize_meta_token(_sanitize_text(raw_name)),
                "value_text": value_text,
                "value_order": index,
            })
    return entries


def _index_media_file_metadata(media_file: MediaFile):
    entries = _extract_raw_metadata_entries(media_file)
    MediaFileMetaValue.objects.filter(media_file=media_file).exclude(source_family="user").delete()

    indexed_values = []
    seen_primary_fields = set()
    for entry in entries:
        field = _get_or_create_meta_field(entry["source_name"], entry["source_family"])
        is_primary = field.normalized_name not in seen_primary_fields
        indexed_values.append(
            MediaFileMetaValue(
                media_file=media_file,
                field=field,
                source_family=entry["source_family"],
                source_name=entry["source_name"],
                source_name_normalized=entry["source_name_normalized"],
                value_text=entry["value_text"],
                value_order=entry["value_order"],
                is_primary=is_primary,
            )
        )
        if is_primary:
            seen_primary_fields.add(field.normalized_name)

    if indexed_values:
        MediaFileMetaValue.objects.bulk_create(indexed_values)


def _normalization_rule_for_source(source_family: str, source_name_normalized: str):
    return (
        MetaNormalizationRule.objects.select_related("target_field")
        .filter(
            source_family=source_family,
            source_name_normalized=source_name_normalized,
            is_active=True,
        )
        .first()
        or MetaNormalizationRule.objects.select_related("target_field")
        .filter(
            source_family="any",
            source_name_normalized=source_name_normalized,
            is_active=True,
        )
        .first()
    )


def _sync_triver_interpretation(media_file: MediaFile):
    _bootstrap_default_meta_registry()
    generated = {}
    raw_values = (
        MediaFileMetaValue.objects
        .select_related("field")
        .filter(media_file=media_file)
        .exclude(source_family__in=["triver", "user"])
        .order_by("source_name", "value_order", "id")
    )
    user_field_names = set(
        MediaFileMetaValue.objects
        .filter(media_file=media_file, source_family="user")
        .values_list("field__normalized_name", flat=True)
    )

    for raw_value in raw_values:
        rule = _normalization_rule_for_source(raw_value.source_family, raw_value.source_name_normalized)
        if not rule:
            continue
        target_field = rule.target_field
        if target_field.normalized_name in user_field_names:
            continue
        value_text = _sanitize_text(raw_value.value_text)
        if not value_text:
            continue
        bucket = generated.setdefault(target_field, [])
        if value_text not in bucket:
            bucket.append(value_text)

    MediaFileMetaValue.objects.filter(media_file=media_file, source_family="triver").delete()
    interpreted_values = []
    for field, values in generated.items():
        for index, value_text in enumerate(values):
            interpreted_values.append(
                MediaFileMetaValue(
                    media_file=media_file,
                    field=field,
                    source_family="triver",
                    source_name=field.name,
                    source_name_normalized=field.normalized_name,
                    value_text=value_text,
                    value_order=index,
                    is_primary=index == 0,
                )
            )
    if interpreted_values:
        MediaFileMetaValue.objects.bulk_create(interpreted_values)


def _interpreted_metadata_from_media_file(media_file: MediaFile):
    grouped_by_source = {"user": {}, "triver": {}}
    values = (
        MediaFileMetaValue.objects
        .select_related("field")
        .filter(media_file=media_file, source_family__in=["user", "triver"])
        .order_by("source_family", "field__name", "value_order", "id")
    )
    for value in values:
        grouped_by_source[value.source_family].setdefault(value.field.name, []).append(value.value_text)

    metadata = dict(grouped_by_source["triver"])
    metadata.update(grouped_by_source["user"])
    return metadata


def _classify_skip(filename: str, extension: str):
    normalized_name = filename.lower()
    if normalized_name in IGNORED_FILENAMES or normalized_name.startswith("._"):
        return (
            LibraryScanSkip.REASON_IGNORED_SYSTEM_FILE,
            f"File di sistema ignorato: {filename}",
        )
    if extension in SUPPORTED_ARTWORK_EXTENSIONS:
        return (
            LibraryScanSkip.REASON_ARTWORK_ASSET,
            f"Artwork rilevato: {extension}",
        )
    if extension in SUPPORTED_PLAYLIST_EXTENSIONS:
        return (
            LibraryScanSkip.REASON_PLAYLIST_ASSET,
            f"Playlist rilevata: {extension}",
        )
    if extension in SUPPORTED_CUESHEET_EXTENSIONS:
        return (
            LibraryScanSkip.REASON_CUE_SHEET,
            f"Cue sheet rilevato: {extension}",
        )
    if extension in DIAGNOSTIC_EXTENSIONS:
        return (
            LibraryScanSkip.REASON_DIAGNOSTIC_FILE,
            f"File diagnostico o applicativo: {extension}",
        )
    if extension:
        return (
            LibraryScanSkip.REASON_UNKNOWN_EXTENSION,
            f"Estensione sconosciuta o non ancora gestita: {extension}",
        )
    return (
        LibraryScanSkip.REASON_UNSUPPORTED_EXTENSION,
        "File senza estensione utile per l'ingest audio",
    )


def _classify_accessory_kind(extension: str) -> str:
    if extension in SUPPORTED_ARTWORK_EXTENSIONS:
        return AccessoryFile.KIND_ARTWORK
    if extension in SUPPORTED_PLAYLIST_EXTENSIONS:
        return AccessoryFile.KIND_PLAYLIST
    if extension in SUPPORTED_CUESHEET_EXTENSIONS:
        return AccessoryFile.KIND_CUE_SHEET
    if extension in DIAGNOSTIC_EXTENSIONS:
        return AccessoryFile.KIND_DIAGNOSTIC
    return AccessoryFile.KIND_UNKNOWN_SUPPORT


def _get_or_create_source_folder_for_relative(
    library: Library,
    folder_path: Path,
    relative_folder_path: str,
    root_label: str,
) -> SourceFolder:
    relative_folder_path = str(relative_folder_path or "").strip("/")
    parent_relative_path = ""
    if relative_folder_path:
        parent_path = Path(relative_folder_path).parent
        parent_relative_path = "" if str(parent_path) == "." else parent_path.as_posix()
    name = folder_path.name if relative_folder_path else root_label

    source_folder, created = SourceFolder.objects.get_or_create(
        library=library,
        relative_path=relative_folder_path,
        defaults={
            "absolute_path": str(folder_path),
            "name": name,
            "parent_relative_path": parent_relative_path,
            "path_depth": len(Path(relative_folder_path).parts) if relative_folder_path else 0,
            "removed_at": None,
        },
    )
    if not created:
        changed = (
            source_folder.absolute_path != str(folder_path)
            or source_folder.name != name
            or source_folder.parent_relative_path != parent_relative_path
            or source_folder.removed_at is not None
        )
        if changed:
            source_folder.absolute_path = str(folder_path)
            source_folder.name = name
            source_folder.parent_relative_path = parent_relative_path
            source_folder.path_depth = len(Path(relative_folder_path).parts) if relative_folder_path else 0
            source_folder.removed_at = None
            source_folder.save(update_fields=[
                "absolute_path",
                "name",
                "parent_relative_path",
                "path_depth",
                "removed_at",
                "last_seen_at",
                "updated_at",
            ])
        else:
            SourceFolder.objects.filter(pk=source_folder.pk).update(last_seen_at=timezone.now())
    return source_folder


def _get_or_create_source_folder(library: Library, ingest_root: Path, absolute_path: Path) -> SourceFolder:
    folder_path = absolute_path.parent
    relative_folder_path = folder_path.relative_to(ingest_root).as_posix()
    if relative_folder_path == ".":
        relative_folder_path = ""
    return _get_or_create_source_folder_for_relative(
        library,
        folder_path,
        relative_folder_path,
        ingest_root.name,
    )


def _parse_int_fragment(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = _sanitize_text(value)
    if not text:
        return None
    match = re.match(r"(\d+)", text)
    return int(match.group(1)) if match else None


def _first_tag_value(tags, *keys):
    for key in keys:
        value = tags.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            if not value:
                continue
            first = value[0]
            if isinstance(first, bytes):
                try:
                    return _sanitize_text(first.decode("utf-8", errors="ignore"))
                except Exception:
                    continue
            return _sanitize_text(first)
        if isinstance(value, bytes):
            return _sanitize_text(value.decode("utf-8", errors="ignore"))
        text = _sanitize_text(value)
        if text:
            return text
    return ""


def _parse_track_number_from_filename(filename: str):
    stem = Path(filename).stem
    match = re.match(r"^(\d{1,3})\b", stem)
    return int(match.group(1)) if match else None


def _split_logical_artists(values):
    if not values:
        return []

    def consume_escape(text, index):
        if index + 1 >= len(text):
            return "\\", index + 1
        return text[index + 1], index + 2

    separators = [" & ", ",", ";", " - "]
    parsed = []
    for raw_value in values:
        text = str(raw_value or "")
        current = []
        index = 0
        while index < len(text):
            if text[index] == "\\":
                escaped, next_index = consume_escape(text, index)
                current.append(escaped)
                index = next_index
                continue
            matched_separator = next((separator for separator in separators if text.startswith(separator, index)), None)
            if matched_separator:
                token = "".join(current).strip()
                if token:
                    parsed.append(token)
                current = []
                index += len(matched_separator)
                continue
            current.append(text[index])
            index += 1
        token = "".join(current).strip()
        if token:
            parsed.append(token)

    unique = []
    seen = set()
    for artist_name in parsed:
        if artist_name not in seen:
            seen.add(artist_name)
            unique.append(artist_name)
    return unique


def _contributor_names_by_role(interpreted_metadata):
    role_fields = {
        TrackArtistCredit.ROLE_COMPOSER: ("Composer",),
        TrackArtistCredit.ROLE_CONDUCTOR: ("Conductor",),
        TrackArtistCredit.ROLE_PERFORMER: ("Executor", "BandName", "EnsembleName", "OrchestraName"),
    }
    grouped = {}
    for role, field_names in role_fields.items():
        names = []
        for field_name in field_names:
            values = interpreted_metadata.get(field_name)
            if values is not None:
                names.extend(_split_logical_artists(values))
        if names:
            grouped[role] = names
    return grouped


def _strip_track_prefix(filename: str):
    stem = Path(filename).stem
    cleaned = re.sub(r"^\s*\d{1,3}\s*[-._ ]+\s*", "", stem).strip()
    return cleaned or stem


def _clean_video_name_fragment(value: str) -> str:
    text = re.sub(r"[\._]+", " ", str(value or ""))
    text = re.sub(r"[\[\]\(\)\{\}]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -._")
    if not text:
        return ""

    release_tokens = {
        "360p", "480p", "540p", "576p", "720p", "1080p", "2160p", "4k",
        "hdtv", "web", "webrip", "webdl", "web-dl", "bluray", "bdrip",
        "dvdrip", "x264", "x265", "h264", "h265", "hevc", "aac", "ac3",
        "dts", "ita", "eng", "multi", "sub", "subs", "proper", "repack",
    }
    kept_tokens = []
    for token in text.split():
        normalized = token.lower().strip(" -._")
        if normalized in release_tokens:
            continue
        kept_tokens.append(token)
    return " ".join(kept_tokens).strip(" -._")


def _parse_season_number_from_folder_name(value: str):
    normalized = re.sub(r"[\._-]+", " ", str(value or "")).strip().lower()
    if not normalized:
        return None
    patterns = [
        r"^(?:season|stagione)\s*0*(\d{1,3})$",
        r"^s\s*0*(\d{1,3})$",
        r"^s0*(\d{1,3})$",
    ]
    for pattern in patterns:
        match = re.match(pattern, normalized)
        if match:
            return int(match.group(1))
    return None


def _episode_pattern_matches(stem: str):
    patterns = [
        r"(?i)(?:^|[^a-z0-9])s(?P<season>\d{1,3})\s*[\._\- ]*\s*e(?P<episode>\d{1,3})(?=$|[^a-z0-9])",
        r"(?i)(?:^|[^a-z0-9])(?P<season>\d{1,3})\s*x\s*(?P<episode>\d{1,3})(?=$|[^a-z0-9])",
        r"(?i)(?:season|stagione|s)\s*(?P<season>\d{1,3}).{0,8}(?:episode|episodio|ep|e)\s*(?P<episode>\d{1,3})",
        r"(?i)(?:^|[^a-z0-9])(?:episode|episodio|ep)\s*0*(?P<episode>\d{1,3})(?=$|[^a-z0-9])",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, stem):
            yield match


VIDEO_PATH_METADATA_FIELDS = ("SeriesTitle", "SeasonNumber", "EpisodeNumber", "EpisodeTitle")


def _infer_video_path_metadata(media_file: MediaFile):
    relative_path = Path(media_file.relative_path or media_file.filename)
    parts = [part for part in relative_path.parts if part not in {"", ".", "Unrevisioned"}]
    filename = parts[-1] if parts else media_file.filename
    directories = list(parts[:-1])
    stem = Path(filename).stem

    inferred = {}
    season_number = None
    season_folder_index = None
    for index in range(len(directories) - 1, -1, -1):
        parsed_season = _parse_season_number_from_folder_name(directories[index])
        if parsed_season is not None:
            season_number = parsed_season
            season_folder_index = index
            break

    series_title = ""
    if season_folder_index is not None and season_folder_index > 0:
        series_title = _clean_video_name_fragment(directories[season_folder_index - 1])

    episode_number = None
    episode_title = ""
    matched_episode = None
    for match in _episode_pattern_matches(stem):
        matched_episode = match
        season_fragment = match.groupdict().get("season")
        if season_fragment:
            season_number = int(season_fragment)
        elif season_number is None:
            season_number = 1
        episode_number = int(match.group("episode"))
        break

    if matched_episode is not None:
        prefix = _clean_video_name_fragment(stem[:matched_episode.start()])
        suffix = _clean_video_name_fragment(stem[matched_episode.end():])
        if prefix and (not series_title or season_folder_index is None):
            series_title = prefix
        elif prefix and series_title and prefix.lower() != series_title.lower():
            episode_title = prefix
        elif not series_title and directories:
            series_title = _clean_video_name_fragment(directories[-1])
        if suffix:
            episode_title = suffix
    elif season_number is not None:
        episode_match = re.match(r"^\s*(?:e|ep|episode|episodio)?\s*0*(\d{1,3})(?:\b|[\._\- ])", stem, flags=re.IGNORECASE)
        if episode_match:
            episode_number = int(episode_match.group(1))
            episode_title = _clean_video_name_fragment(stem[episode_match.end():])

    if series_title and episode_number is not None:
        inferred["SeriesTitle"] = series_title
        inferred["SeasonNumber"] = str(season_number or 1)
        inferred["EpisodeNumber"] = str(episode_number)
        if episode_title:
            inferred["EpisodeTitle"] = episode_title

    return inferred


def _apply_video_path_metadata(media_file: MediaFile):
    _bootstrap_default_meta_registry()
    inferred = _infer_video_path_metadata(media_file)

    user_field_names = set(
        MediaFileMetaValue.objects
        .filter(media_file=media_file, source_family="user")
        .values_list("field__normalized_name", flat=True)
    )
    auto_field_names = [_normalize_meta_token(name).lower() for name in VIDEO_PATH_METADATA_FIELDS]
    MediaFileMetaValue.objects.filter(
        media_file=media_file,
        source_family="triver",
        field__normalized_name__in=auto_field_names,
    ).delete()
    if not inferred:
        return inferred

    fields = {
        field.name: field
        for field in MetaFieldDefinition.objects.filter(
            normalized_name__in=[_normalize_meta_token(name).lower() for name in inferred.keys()]
        )
    }

    values = []
    for field_name, value_text in inferred.items():
        clean_value = _sanitize_text(value_text)
        if not clean_value:
            continue
        field = fields.get(field_name)
        if field is None or field.normalized_name in user_field_names:
            continue
        values.append(
            MediaFileMetaValue(
                media_file=media_file,
                field=field,
                source_family="triver",
                source_name=field.name,
                source_name_normalized=field.normalized_name,
                value_text=clean_value,
                value_order=0,
                is_primary=True,
            )
        )

    if values:
        MediaFileMetaValue.objects.bulk_create(values)
        logger.warning(
            "trive-up inferred video metadata relative=%s values=%s",
            media_file.relative_path,
            inferred,
        )
    return inferred


def _looks_like_disc_folder(name: str):
    normalized = name.strip().lower()
    return bool(re.match(r"^(disc|disk|cd)\s*\d+$", normalized) or re.match(r"^\d+$", normalized))


def _resolve_context_folder(source_folder: SourceFolder | None):
    if source_folder is None:
        return None
    if _looks_like_disc_folder(source_folder.name) and source_folder.parent_relative_path:
        parent = SourceFolder.objects.filter(
            library=source_folder.library,
            relative_path=source_folder.parent_relative_path,
        ).first()
        if parent:
            return parent
    return source_folder


def _parse_folder_hints(source_folder: SourceFolder | None):
    context_folder = _resolve_context_folder(source_folder)
    if context_folder is None:
        return {"artist": "", "album": "", "folder_name": ""}

    folder_name = context_folder.name.strip()
    for separator in (" - ", " – ", " — "):
        if separator in folder_name:
            artist_name, album_title = folder_name.split(separator, 1)
            return {
                "artist": artist_name.strip(),
                "album": album_title.strip(),
                "folder_name": folder_name,
            }

    return {
        "artist": "",
        "album": folder_name,
        "folder_name": folder_name,
    }


def _extract_media_metadata(media_file: MediaFile):
    parsed_file = MutagenFile(media_file.absolute_path, easy=False)
    info = getattr(parsed_file, "info", None)
    folder_hints = _parse_folder_hints(media_file.source_folder)
    interpreted_metadata = _interpreted_metadata_from_media_file(media_file)

    title = _first_tag_value(interpreted_metadata, "TrackName")
    album = _first_tag_value(interpreted_metadata, "Album")
    artist_values = interpreted_metadata.get("Artist") or []
    artist_names = _split_logical_artists(artist_values)
    artist = artist_names[0] if artist_names else _first_tag_value(interpreted_metadata, "Artist")
    track_number_raw = _first_tag_value(interpreted_metadata, "TrackNumber")
    disc_number_raw = _first_tag_value(interpreted_metadata, "DiscNumber")
    year_raw = _first_tag_value(interpreted_metadata, "ReleaseDate")

    track_number = _parse_int_fragment(track_number_raw)
    if track_number is None:
        track_number = _parse_track_number_from_filename(media_file.filename)

    title = title or _strip_track_prefix(media_file.filename)
    fallback_folder_name = media_file.source_folder.name if media_file.source_folder else ""
    album = album or folder_hints["album"] or fallback_folder_name
    artist = artist or folder_hints["artist"] or "Unknown Artist"
    if not artist_names:
        artist_names = [artist]
    release_year = _parse_int_fragment(year_raw)
    disc_number = _parse_int_fragment(disc_number_raw)
    duration_seconds = getattr(info, "length", None)

    return {
        "canonical_title": title.strip() or media_file.filename,
        "album_title": album.strip() or "Unknown Album",
        "artist_name": artist.strip() or "Unknown Artist",
        "artist_names": [name for name in artist_names if _sanitize_text(name)],
        "contributor_names_by_role": _contributor_names_by_role(interpreted_metadata),
        "release_year": release_year,
        "disc_number": disc_number,
        "track_number": track_number,
        "duration_seconds": duration_seconds,
        "raw_payload": _sanitize_json_compatible({
            "interpreted_metadata": interpreted_metadata,
            "source_folder": {
                "id": media_file.source_folder_id,
                "relative_path": media_file.source_folder.relative_path if media_file.source_folder else "",
                "name": media_file.source_folder.name if media_file.source_folder else "",
            },
            "folder_hints": folder_hints,
            "filename_fallback_title": _strip_track_prefix(media_file.filename),
        }),
        "raw_title": _first_tag_value(interpreted_metadata, "TrackName"),
        "raw_album": _first_tag_value(interpreted_metadata, "Album"),
        "raw_year": _parse_int_fragment(year_raw),
        "raw_track_number": track_number_raw,
        "raw_disc_number": disc_number_raw,
        "raw_artists_display": [_sanitize_text(name) for name in artist_names if _sanitize_text(name)],
    }


def _read_video_stream_probe(file_path: Path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=index,codec_type,codec_name,width,height,avg_frame_rate:stream_tags=language,title:stream_disposition=default,forced",
            "-of",
            "json",
            str(file_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}
    try:
        return _sanitize_json_compatible(json.loads(result.stdout or "{}"))
    except json.JSONDecodeError:
        return {}


def _parse_ffprobe_duration_seconds(probe_payload) -> float | None:
    try:
        duration_value = ((probe_payload or {}).get("format") or {}).get("duration")
        if duration_value in [None, ""]:
            return None
        return float(duration_value)
    except (TypeError, ValueError):
        return None


def _extract_video_metadata(media_file: MediaFile):
    file_path = Path(media_file.absolute_path)
    folder_hints = _parse_folder_hints(media_file.source_folder)
    interpreted_metadata = _interpreted_metadata_from_media_file(media_file)
    probe_payload = _read_video_stream_probe(file_path)
    title = (
        _first_tag_value(interpreted_metadata, "EpisodeTitle")
        or _first_tag_value(interpreted_metadata, "TrackName")
        or _strip_track_prefix(media_file.filename)
    )
    series_title = _first_tag_value(interpreted_metadata, "SeriesTitle")
    season_number_raw = _first_tag_value(interpreted_metadata, "SeasonNumber")
    episode_number_raw = _first_tag_value(interpreted_metadata, "EpisodeNumber")
    fallback_folder_name = media_file.source_folder.name if media_file.source_folder else ""
    album = series_title or folder_hints["album"] or fallback_folder_name or "Unsorted Video"
    artist = folder_hints["artist"] or "Unknown Artist"
    episode_number = _parse_int_fragment(episode_number_raw)
    if episode_number is None:
        episode_number = _parse_track_number_from_filename(media_file.filename)

    return {
        "canonical_title": title.strip() or media_file.filename,
        "album_title": album.strip() or "Unsorted Video",
        "artist_name": artist.strip() or "Unknown Artist",
        "artist_names": [artist.strip() or "Unknown Artist"],
        "contributor_names_by_role": _contributor_names_by_role(interpreted_metadata),
        "release_year": None,
        "disc_number": None,
        "track_number": episode_number,
        "duration_seconds": _parse_ffprobe_duration_seconds(probe_payload),
        "raw_payload": {
            "media_kind": "video",
            "interpreted_metadata": interpreted_metadata,
            "inferred_path_metadata": _infer_video_path_metadata(media_file),
            "browser_playable": _is_browser_playable_video(f".{(media_file.extension or '').lower()}"),
            "source_folder": {
                "id": media_file.source_folder_id,
                "relative_path": media_file.source_folder.relative_path if media_file.source_folder else "",
                "name": media_file.source_folder.name if media_file.source_folder else "",
            },
            "folder_hints": folder_hints,
            "ffprobe": probe_payload,
            "filename_fallback_title": _strip_track_prefix(media_file.filename),
        },
        "raw_title": title,
        "raw_album": album,
        "raw_year": None,
        "raw_track_number": episode_number_raw,
        "raw_disc_number": "",
        "raw_artists_display": [artist.strip() or "Unknown Artist"],
    }


def _get_or_create_album(title: str, release_year: int | None):
    _acquire_catalog_xact_lock("album", f"{title}\0{release_year or ''}")
    album = Album.objects.filter(title=title, release_year=release_year).first()
    if album:
        return album
    return Album.objects.create(
        title=title,
        sort_title=title.lower(),
        release_year=release_year,
    )


def _get_or_create_artist(name: str):
    _acquire_catalog_xact_lock("artist", f"{name.lower()}\0{name}")
    artist, _ = Artist.objects.get_or_create(
        name=name,
        sort_name=name.lower(),
        defaults={"triver_notes": ""},
    )
    return artist


def _compute_file_hash(absolute_path: str) -> str:
    digest = hashlib.sha256()
    chunk_size = _positive_int_setting("TRIVER_DIGEST_HASH_CHUNK_BYTES", 256 * 1024)
    bytes_per_second = _non_negative_int_setting("TRIVER_DIGEST_HASH_BYTES_PER_SECOND", 1024 * 1024)
    started_at = time.monotonic()
    read_bytes = 0
    with open(absolute_path, "rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
            if bytes_per_second > 0:
                read_bytes += len(chunk)
                expected_elapsed = read_bytes / bytes_per_second
                actual_elapsed = time.monotonic() - started_at
                sleep_for = expected_elapsed - actual_elapsed
                if sleep_for > 0:
                    time.sleep(min(sleep_for, 1.0))
    return digest.hexdigest()


def _content_hash_max_bytes() -> int:
    return _non_negative_int_setting("TRIVER_DIGEST_CONTENT_HASH_MAX_BYTES", 0)


def _should_compute_content_hash(media_file: MediaFile, source_path: Path) -> bool:
    if getattr(settings, "TRIVER_DIGEST_FULL_CONTENT_HASH", False):
        return True
    try:
        size = int(media_file.size or source_path.stat().st_size or 0)
    except (OSError, TypeError, ValueError):
        size = 0
    return size > 0 and size <= _content_hash_max_bytes()


def _content_hash_for_promotion(media_file: MediaFile, source_path: Path) -> str:
    if media_file.content_hash:
        return media_file.content_hash
    if _should_compute_content_hash(media_file, source_path):
        return _compute_file_hash(str(source_path))
    logger.info(
        "trive-up skipping full content hash media file id=%s relative=%s size=%s",
        media_file.pk,
        media_file.relative_path,
        media_file.size,
    )
    return ""


def _candidate_legacy_paths(raw_path: str):
    if not raw_path:
        return []

    candidates = [Path(raw_path)]
    replacements = [
        ("/srv/triver/trivIn/", "/srv/triver/trive-In/"),
        ("/srv/triver/trivUp/", "/srv/triver/trive-Up/"),
        ("/srv/triver/trivOut/", "/srv/triver/trive-Out/"),
    ]
    for old_fragment, new_fragment in replacements:
        if old_fragment in raw_path:
            candidates.append(Path(raw_path.replace(old_fragment, new_fragment)))
    return candidates


def _resolve_existing_media_path(media_file: MediaFile) -> Path | None:
    candidates = []

    if media_file.absolute_path:
        candidates.extend(_candidate_legacy_paths(media_file.absolute_path))

    if media_file.digest_relative_path:
        digest_relative_path = Path(media_file.digest_relative_path)
        candidates.append(Path(media_file.library.digest_path) / digest_relative_path)

    if media_file.relative_path:
        relative_path = Path(media_file.relative_path)
        candidates.extend([
            Path(media_file.library.ingest_path) / relative_path,
            Path(media_file.library.digest_path) / "Unrevisioned" / relative_path,
            Path(media_file.library.digest_path) / relative_path,
        ])

    seen = set()
    for candidate in candidates:
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.exists() and candidate.is_file():
            if media_file.absolute_path != normalized:
                media_file.absolute_path = normalized
                media_file.save(update_fields=["absolute_path", "updated_at"])
            return candidate

    return None


def _split_digest_relative_path_for_media_file(digest_relative_path: Path):
    normalized_path = Path(digest_relative_path)
    if normalized_path.parts and normalized_path.parts[0] == "Unrevisioned":
        source_relative_path = Path(*normalized_path.parts[1:]) if len(normalized_path.parts) > 1 else Path(normalized_path.name)
        workflow_state = MediaFile.WORKFLOW_UNREVISIONED
    else:
        source_relative_path = normalized_path
        workflow_state = MediaFile.WORKFLOW_REVISED
    return source_relative_path.as_posix(), normalized_path.as_posix(), workflow_state


def _upsert_media_file_for_digest_path(library: Library, digest_root: Path, absolute_path: Path):
    extension = absolute_path.suffix.lower()
    digest_relative_path = absolute_path.relative_to(digest_root)
    relative_path, normalized_digest_relative_path, workflow_state = _split_digest_relative_path_for_media_file(digest_relative_path)
    source_folder = _get_or_create_source_folder(library, digest_root, absolute_path)

    stat_result = absolute_path.stat()
    mtime = datetime.fromtimestamp(
        stat_result.st_mtime,
        tz=timezone.get_current_timezone(),
    )
    path_hash = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
    inode = str(getattr(stat_result, "st_ino", ""))
    detected_media_kind = _detect_media_kind(extension)
    mime_type, _ = mimetypes.guess_type(str(absolute_path))
    filename = absolute_path.name

    media_file, created = MediaFile.objects.get_or_create(
        library=library,
        relative_path=relative_path,
        defaults={
            "source_folder": source_folder,
            "absolute_path": str(absolute_path),
            "path_hash": path_hash,
            "filename": filename,
            "extension": extension.lstrip("."),
            "media_kind": detected_media_kind,
            "mime_type": mime_type or "",
            "size": stat_result.st_size,
            "mtime": mtime,
            "inode": inode,
            "storage_stage": MediaFile.STORAGE_STAGE_TRIV_UP,
            "workflow_state": workflow_state,
            "digest_relative_path": normalized_digest_relative_path,
            "status": MediaFile.STATUS_DISCOVERED,
            "removed_at": None,
            "last_error": "",
        },
    )

    if not created:
        media_file.source_folder = source_folder
        media_file.absolute_path = str(absolute_path)
        media_file.path_hash = path_hash
        media_file.filename = filename
        media_file.extension = extension.lstrip(".")
        media_file.media_kind = detected_media_kind
        media_file.mime_type = mime_type or ""
        media_file.size = stat_result.st_size
        media_file.mtime = mtime
        media_file.inode = inode
        media_file.storage_stage = MediaFile.STORAGE_STAGE_TRIV_UP
        media_file.workflow_state = workflow_state
        media_file.digest_relative_path = normalized_digest_relative_path
        media_file.status = MediaFile.STATUS_DISCOVERED
        media_file.removed_at = None
        media_file.last_error = ""
        media_file.save(update_fields=[
            "source_folder",
            "absolute_path",
            "path_hash",
            "filename",
            "extension",
            "media_kind",
            "mime_type",
            "size",
            "mtime",
            "inode",
            "storage_stage",
            "workflow_state",
            "digest_relative_path",
            "status",
            "removed_at",
            "last_error",
            "last_seen_at",
            "updated_at",
        ])

    logger.warning(
        "trive-rescan upserted media file path=%s relative=%s kind=%s created=%s stage=%s workflow=%s",
        str(absolute_path),
        relative_path,
        detected_media_kind,
        created,
        MediaFile.STORAGE_STAGE_TRIV_UP,
        workflow_state,
    )

    AccessoryFile.objects.filter(
        library=library,
        removed_at__isnull=True,
    ).filter(
        Q(relative_path=relative_path)
        | Q(relative_path=normalized_digest_relative_path)
        | Q(absolute_path=str(absolute_path))
        | Q(filename=filename, size=stat_result.st_size)
        | Q(filename=filename, extension=extension.lstrip("."))
    ).update(removed_at=timezone.now())

    return {
        "media_file": media_file,
        "source_folder": source_folder,
        "relative_path": relative_path,
        "stat_result": stat_result,
    }


def _build_unrevisioned_relative_path(media_file: MediaFile) -> str:
    source_relative_path = Path(media_file.relative_path)
    return Path("Unrevisioned") / source_relative_path


def _resolve_variant_path(base_path: Path) -> Path:
    counter = 1
    while True:
        candidate = base_path.with_name(f"{base_path.stem}__variant_{counter:03d}{base_path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _move_file(source_path: Path, destination_path: Path):
    try:
        os.rename(str(source_path), str(destination_path))
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        if _bool_setting("TRIVER_ALLOW_CROSS_DEVICE_MOVES", False):
            logger.warning(
                "trive-move cross-device copy enabled source=%s destination=%s",
                str(source_path),
                str(destination_path),
            )
            shutil.move(str(source_path), str(destination_path))
            return
        raise RuntimeError(
            "Cross-device move refused. Mount trive-In, trive-Up, trive-Out and "
            "trive-dump through one shared TRIVER_STORAGE_HOST_PATH, or set "
            "TRIVER_ALLOW_CROSS_DEVICE_MOVES=true if slow physical copies are intended."
        ) from exc


def _move_with_collision_handling(source_path: Path, destination_path: Path) -> Path:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    final_destination = destination_path
    if destination_path.exists():
        final_destination = _resolve_variant_path(destination_path)
        logger.warning(
            "trive-move collision source=%s requested_destination=%s variant_destination=%s",
            str(source_path),
            str(destination_path),
            str(final_destination),
        )
    else:
        logger.warning(
            "trive-move source=%s destination=%s",
            str(source_path),
            str(final_destination),
        )
    _move_file(source_path, final_destination)
    return final_destination


def _move_to_dump(source_path: Path, source_root: Path, reason_code: str) -> Path:
    dump_root = Path(settings.TRIVER_DUMP_ROOT) / reason_code
    try:
        relative_path = source_path.relative_to(source_root)
    except ValueError:
        relative_path = Path(source_path.name)
    logger.warning(
        "trive-dump reason=%s source=%s source_root=%s relative=%s",
        reason_code,
        str(source_path),
        str(source_root),
        relative_path.as_posix(),
    )
    return _move_with_collision_handling(source_path, dump_root / relative_path)


def _candidate_accessory_paths(accessory_file: AccessoryFile):
    candidates = []
    if accessory_file.absolute_path:
        candidates.append(Path(accessory_file.absolute_path))
    if accessory_file.relative_path:
        relative_path = Path(accessory_file.relative_path)
        candidates.extend([
            Path(accessory_file.library.ingest_path) / relative_path,
            Path(accessory_file.library.digest_path) / "Unrevisioned" / relative_path,
            Path(accessory_file.library.digest_path) / relative_path,
        ])
    return candidates


def _resolve_existing_accessory_path(accessory_file: AccessoryFile) -> Path | None:
    seen = set()
    for candidate in _candidate_accessory_paths(accessory_file):
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.exists() and candidate.is_file():
            if accessory_file.absolute_path != normalized:
                accessory_file.absolute_path = normalized
                accessory_file.save(update_fields=["absolute_path", "updated_at"])
            return candidate
    return None


def _promote_accessory_file(accessory_file: AccessoryFile) -> bool:
    source_path = _resolve_existing_accessory_path(accessory_file)
    if source_path is None:
        return False

    destination_path = Path(accessory_file.library.digest_path) / "Unrevisioned" / Path(accessory_file.relative_path)
    if source_path == destination_path:
        final_destination = destination_path
    else:
        final_destination = _move_with_collision_handling(source_path, destination_path)
    logger.warning(
        "trive-promote accessory filename=%s source=%s destination=%s",
        accessory_file.filename,
        str(source_path),
        str(final_destination),
    )
    source_folder = _get_or_create_source_folder(accessory_file.library, Path(accessory_file.library.digest_path), final_destination)
    accessory_file.source_folder = source_folder
    accessory_file.absolute_path = str(final_destination)
    accessory_file.removed_at = None
    accessory_file.save(update_fields=["source_folder", "absolute_path", "removed_at", "last_seen_at", "updated_at"])
    return True


def _dump_remaining_ingest_files(library: Library, target_path: str = "") -> int:
    ingest_root = Path(library.ingest_path)
    if not ingest_root.exists() or not ingest_root.is_dir():
        return 0

    normalized_target_path = _normalize_scope_path(target_path)
    scoped_path = _resolve_scope_path(ingest_root, normalized_target_path)
    if not scoped_path.exists():
        return 0

    moved_count = 0
    if scoped_path.is_file():
        logger.warning(
            "trive-leftover source=%s library=%s",
            str(scoped_path),
            library.slug,
        )
        _move_to_dump(scoped_path, ingest_root, "leftover_after_trive_up")
        moved_count += 1
    else:
        for source_path in sorted(scoped_path.rglob("*")):
            if not source_path.is_file():
                continue
            logger.warning(
                "trive-leftover source=%s library=%s",
                str(source_path),
                library.slug,
            )
            _move_to_dump(source_path, ingest_root, "leftover_after_trive_up")
            moved_count += 1

    for directory in sorted(
        (path for path in scoped_path.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass
    return moved_count


def _promote_media_file(media_file: MediaFile, content_hash: str = ""):
    resolved_source_path = _resolve_existing_media_path(media_file)
    if resolved_source_path is None:
        raise FileNotFoundError(f"Unable to resolve media file on disk for {media_file.relative_path}")

    if media_file.storage_stage == MediaFile.STORAGE_STAGE_EXTERNAL:
        return {
            "action": "external_indexed",
            "absolute_path": str(resolved_source_path),
            "digest_relative_path": media_file.digest_relative_path or media_file.relative_path,
            "workflow_state": media_file.workflow_state or MediaFile.WORKFLOW_REVISED,
        }

    if media_file.storage_stage == MediaFile.STORAGE_STAGE_TRIV_UP and media_file.absolute_path:
        destination_path = Path(media_file.absolute_path)
        if destination_path.exists():
            relative_path = media_file.digest_relative_path or destination_path.relative_to(Path(media_file.library.digest_path)).as_posix()
            return {
                "action": "already_promoted",
                "absolute_path": str(destination_path),
                "digest_relative_path": relative_path,
                "workflow_state": media_file.workflow_state or MediaFile.WORKFLOW_UNREVISIONED,
            }

    destination_relative_path = _build_unrevisioned_relative_path(media_file)
    destination_absolute_path = Path(media_file.library.digest_path) / destination_relative_path
    destination_absolute_path.parent.mkdir(parents=True, exist_ok=True)

    source_path = resolved_source_path
    if destination_absolute_path.exists():
        if content_hash and _compute_file_hash(str(destination_absolute_path)) == content_hash:
            if source_path.exists() and source_path != destination_absolute_path:
                logger.warning(
                    "trive-promote exact-duplicate unlink source=%s destination=%s relative=%s",
                    str(source_path),
                    str(destination_absolute_path),
                    media_file.relative_path,
                )
                source_path.unlink()
            return {
                "action": "exact_duplicate",
                "absolute_path": str(destination_absolute_path),
                "digest_relative_path": destination_relative_path.as_posix(),
                "workflow_state": MediaFile.WORKFLOW_EXACT_DUPLICATE,
            }
        if not content_hash:
            logger.warning(
                "trive-promote collision without content hash source=%s destination=%s relative=%s",
                str(source_path),
                str(destination_absolute_path),
                media_file.relative_path,
            )
        destination_absolute_path = _resolve_variant_path(destination_absolute_path)
        destination_relative_path = destination_absolute_path.relative_to(Path(media_file.library.digest_path))
        workflow_state = MediaFile.WORKFLOW_VARIANT
    else:
        workflow_state = MediaFile.WORKFLOW_UNREVISIONED

    if source_path.exists() and source_path != destination_absolute_path:
        destination_absolute_path.parent.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "trive-promote media source=%s destination=%s relative=%s kind=%s",
            str(source_path),
            str(destination_absolute_path),
            media_file.relative_path,
            media_file.media_kind,
        )
        _move_file(source_path, destination_absolute_path)

    return {
        "action": "promoted",
        "absolute_path": str(destination_absolute_path),
        "digest_relative_path": destination_relative_path.as_posix(),
        "workflow_state": workflow_state,
    }


@shared_task(bind=True)
def discover_library(self, job_id: int, target_path: str = ""):
    """
    Fase 1 reale: discovery del filesystem.

    Il task legge solo attributi cheap del file:
    - path
    - filename
    - extension
    - size
    - mtime

    Non apre i media e non legge metadata embedded. Quella resta una fase successiva.
    """

    job = LibraryScanJob.objects.select_related("library").get(pk=job_id)
    library = job.library
    ingest_root = Path(library.ingest_path)
    try:
        normalized_target_path = _normalize_scope_path(target_path)
        scan_scope_path = _resolve_scope_path(ingest_root, normalized_target_path)
    except ValueError as exc:
        job.status = LibraryScanJob.STATUS_ERROR
        job.finished_at = timezone.now()
        job.last_error = str(exc)
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        return {"job_id": job.id, "status": job.status, "error": job.last_error, "target_path": target_path}
    LibraryScanSkip.objects.filter(scan_job=job).delete()

    job.status = LibraryScanJob.STATUS_DISCOVERING
    job.started_at = timezone.now()
    job.finished_at = None
    job.last_error = ""
    job.discovered_count = 0
    job.queued_count = 0
    job.processed_count = 0
    job.skipped_count = 0
    job.error_count = 0
    job.removed_count = 0
    job.save(update_fields=[
        "status",
        "started_at",
        "finished_at",
        "last_error",
        "discovered_count",
        "queued_count",
        "processed_count",
        "skipped_count",
        "error_count",
        "removed_count",
        "updated_at",
    ])

    if not ingest_root.exists() or not ingest_root.is_dir():
        job.status = LibraryScanJob.STATUS_ERROR
        job.finished_at = timezone.now()
        job.last_error = f"Ingest root non disponibile: {ingest_root}"
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        return {"job_id": job.id, "status": job.status, "error": job.last_error}
    if not scan_scope_path.exists():
        job.status = LibraryScanJob.STATUS_ERROR
        job.finished_at = timezone.now()
        job.last_error = f"Target path non disponibile: {scan_scope_path}"
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        return {"job_id": job.id, "status": job.status, "error": job.last_error, "target_path": normalized_target_path}

    seen_paths = set()
    seen_accessory_paths = set()
    seen_folder_paths = set()
    discovered_count = 0
    skipped_count = 0
    error_count = 0
    scanned_count = 0

    for absolute_path in _iter_scoped_file_paths(ingest_root, normalized_target_path):
        scanned_count += 1
        _scan_pause(scanned_count)
        filename = absolute_path.name
        extension = absolute_path.suffix.lower()
        relative_path = absolute_path.relative_to(ingest_root).as_posix()
        source_folder = _get_or_create_source_folder(library, ingest_root, absolute_path)
        seen_folder_paths.add(source_folder.relative_path)

        if filename.lower() in IGNORED_FILENAMES or filename.lower().startswith("._"):
            reason_code, reason_detail = _classify_skip(filename, extension)
            stat_result = absolute_path.stat()
            LibraryScanSkip.objects.create(
                scan_job=job,
                library=library,
                relative_path=relative_path,
                absolute_path=str(absolute_path),
                filename=filename,
                extension=extension.lstrip("."),
                size=stat_result.st_size,
                reason_code=reason_code,
                reason_detail=reason_detail,
            )
            _move_to_dump(absolute_path, ingest_root, reason_code)
            skipped_count += 1
            continue

        if extension not in SUPPORTED_MEDIA_EXTENSIONS:
            stat_result = absolute_path.stat()
            accessory_kind = _classify_accessory_kind(extension)
            mtime = datetime.fromtimestamp(
                stat_result.st_mtime,
                tz=timezone.get_current_timezone(),
            )
            seen_accessory_paths.add(relative_path)
            accessory_file, created = AccessoryFile.objects.get_or_create(
                library=library,
                relative_path=relative_path,
                defaults={
                    "source_folder": source_folder,
                    "absolute_path": str(absolute_path),
                    "filename": filename,
                    "extension": extension.lstrip("."),
                    "asset_kind": accessory_kind,
                    "size": stat_result.st_size,
                    "mtime": mtime,
                    "removed_at": None,
                },
            )
            if not created:
                changed = (
                    accessory_file.source_folder_id != source_folder.id
                    or accessory_file.absolute_path != str(absolute_path)
                    or accessory_file.filename != filename
                    or accessory_file.extension != extension.lstrip(".")
                    or accessory_file.asset_kind != accessory_kind
                    or accessory_file.size != stat_result.st_size
                    or accessory_file.mtime != mtime
                    or accessory_file.removed_at is not None
                )
                if changed:
                    accessory_file.source_folder = source_folder
                    accessory_file.absolute_path = str(absolute_path)
                    accessory_file.filename = filename
                    accessory_file.extension = extension.lstrip(".")
                    accessory_file.asset_kind = accessory_kind
                    accessory_file.size = stat_result.st_size
                    accessory_file.mtime = mtime
                    accessory_file.removed_at = None
                    accessory_file.save(update_fields=[
                        "source_folder",
                        "absolute_path",
                        "filename",
                        "extension",
                        "asset_kind",
                        "size",
                        "mtime",
                        "removed_at",
                        "last_seen_at",
                        "updated_at",
                    ])
                else:
                    AccessoryFile.objects.filter(pk=accessory_file.pk).update(last_seen_at=timezone.now())
            continue

        try:
            stat_result = absolute_path.stat()
            seen_paths.add(relative_path)
            mtime = datetime.fromtimestamp(
                stat_result.st_mtime,
                tz=timezone.get_current_timezone(),
            )
            path_hash = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
            inode = str(getattr(stat_result, "st_ino", ""))
            detected_media_kind = _detect_media_kind(extension)
            mime_type, _ = mimetypes.guess_type(str(absolute_path))

            media_file, created = MediaFile.objects.get_or_create(
                library=library,
                relative_path=relative_path,
                defaults={
                    "source_folder": source_folder,
                    "absolute_path": str(absolute_path),
                    "path_hash": path_hash,
                    "filename": filename,
                    "extension": extension.lstrip("."),
                    "media_kind": detected_media_kind,
                    "mime_type": mime_type or "",
                    "size": stat_result.st_size,
                    "mtime": mtime,
                    "inode": inode,
                    "storage_stage": MediaFile.STORAGE_STAGE_TRIV_IN,
                    "workflow_state": MediaFile.WORKFLOW_UNPROCESSED,
                    "digest_relative_path": "",
                    "status": MediaFile.STATUS_DISCOVERED,
                    "removed_at": None,
                    "last_error": "",
                },
            )

            if not created:
                changed = (
                    media_file.source_folder_id != source_folder.id
                    or media_file.absolute_path != str(absolute_path)
                    or media_file.filename != filename
                    or media_file.extension != extension.lstrip(".")
                    or media_file.size != stat_result.st_size
                    or media_file.mtime != mtime
                    or media_file.inode != inode
                    or media_file.status == MediaFile.STATUS_MISSING
                    or media_file.removed_at is not None
                )
                if changed:
                    media_file.source_folder = source_folder
                    media_file.absolute_path = str(absolute_path)
                    media_file.path_hash = path_hash
                    media_file.filename = filename
                    media_file.extension = extension.lstrip(".")
                    media_file.media_kind = detected_media_kind
                    media_file.mime_type = mime_type or ""
                    media_file.size = stat_result.st_size
                    media_file.mtime = mtime
                    media_file.inode = inode
                    media_file.storage_stage = MediaFile.STORAGE_STAGE_TRIV_IN
                    media_file.workflow_state = MediaFile.WORKFLOW_UNPROCESSED
                    media_file.digest_relative_path = ""
                    media_file.status = MediaFile.STATUS_DISCOVERED
                    media_file.removed_at = None
                    media_file.last_error = ""
                    media_file.save(update_fields=[
                        "source_folder",
                        "absolute_path",
                        "path_hash",
                        "filename",
                        "extension",
                        "media_kind",
                        "mime_type",
                        "size",
                        "mtime",
                        "inode",
                        "storage_stage",
                        "workflow_state",
                        "digest_relative_path",
                        "status",
                        "removed_at",
                        "last_error",
                        "last_seen_at",
                        "updated_at",
                    ])
                else:
                    MediaFile.objects.filter(pk=media_file.pk).update(last_seen_at=timezone.now())

            discovered_count += 1
            if discovered_count % 25 == 0:
                LibraryScanJob.objects.filter(pk=job.pk).update(
                    discovered_count=discovered_count,
                    skipped_count=skipped_count,
                    error_count=error_count,
                )
        except Exception as exc:  # pragma: no cover - defensive runtime path
            error_count += 1
            reason_code = LibraryScanSkip.REASON_UNKNOWN_ERROR
            if isinstance(exc, PermissionError):
                reason_code = LibraryScanSkip.REASON_PERMISSION_DENIED
            elif isinstance(exc, FileNotFoundError):
                reason_code = LibraryScanSkip.REASON_STAT_FAILED
            LibraryScanSkip.objects.create(
                scan_job=job,
                library=library,
                relative_path=absolute_path.relative_to(ingest_root).as_posix() if absolute_path.exists() else "",
                absolute_path=str(absolute_path),
                filename=filename,
                extension=extension.lstrip("."),
                reason_code=reason_code,
                reason_detail=str(exc),
            )
            LibraryScanJob.objects.filter(pk=job.pk).update(error_count=error_count, last_error=str(exc))

    removed_count = 0
    existing_media_queryset = MediaFile.objects.filter(
        library=library,
        storage_stage=MediaFile.STORAGE_STAGE_TRIV_IN,
    )
    existing_accessory_queryset = AccessoryFile.objects.filter(library=library)
    if normalized_target_path:
        existing_media_queryset = _apply_relative_path_scope(existing_media_queryset, "relative_path", normalized_target_path)
        existing_accessory_queryset = _apply_relative_path_scope(existing_accessory_queryset, "relative_path", normalized_target_path)

    existing_paths = set(existing_media_queryset.values_list("relative_path", flat=True))
    missing_paths = existing_paths - seen_paths
    if missing_paths:
        removed_count = MediaFile.objects.filter(
            library=library,
            relative_path__in=missing_paths,
        ).exclude(status=MediaFile.STATUS_MISSING).update(
            status=MediaFile.STATUS_MISSING,
            removed_at=timezone.now(),
        )

    existing_accessory_paths = set(existing_accessory_queryset.values_list("relative_path", flat=True))
    missing_accessory_paths = existing_accessory_paths - seen_accessory_paths
    if missing_accessory_paths:
        stale_accessory_ids = []
        for accessory_file in AccessoryFile.objects.filter(
            library=library,
            relative_path__in=missing_accessory_paths,
        ).select_related("library"):
            if _resolve_existing_accessory_path(accessory_file) is None:
                stale_accessory_ids.append(accessory_file.pk)
            elif accessory_file.removed_at is not None:
                accessory_file.removed_at = None
                accessory_file.save(update_fields=["removed_at", "last_seen_at", "updated_at"])
        if stale_accessory_ids:
            AccessoryFile.objects.filter(pk__in=stale_accessory_ids).update(removed_at=timezone.now())

    merged_media_duplicate_count = _dedupe_media_file_records(library, normalized_target_path)
    merged_accessory_duplicate_count = _dedupe_accessory_file_records(library, normalized_target_path)
    merged_source_folder_duplicate_count = _dedupe_source_folder_records(library, normalized_target_path)
    if merged_media_duplicate_count:
        logger.warning(
            "trive-scan merged duplicate media file records job=%s count=%s",
            job.id,
            merged_media_duplicate_count,
        )
    if merged_accessory_duplicate_count:
        logger.warning(
            "trive-scan merged duplicate accessory file records job=%s count=%s",
            job.id,
            merged_accessory_duplicate_count,
        )
    if merged_source_folder_duplicate_count:
        logger.warning(
            "trive-scan merged duplicate source folder records job=%s count=%s",
            job.id,
            merged_source_folder_duplicate_count,
        )

    source_folder_queryset = SourceFolder.objects.filter(library=library)
    if normalized_target_path:
        source_folder_queryset = source_folder_queryset.filter(relative_path__in=seen_folder_paths)
    for source_folder in source_folder_queryset:
        media_file_count = source_folder.media_files.exclude(status=MediaFile.STATUS_MISSING).count()
        accessory_file_count = source_folder.accessory_files.filter(removed_at__isnull=True).count()
        source_folder.file_count = media_file_count + accessory_file_count
        source_folder.audio_file_count = media_file_count
        source_folder.accessory_file_count = accessory_file_count
        if normalized_target_path:
            source_folder.removed_at = None
            source_folder.save(update_fields=[
                "file_count",
                "audio_file_count",
                "accessory_file_count",
                "removed_at",
                "updated_at",
            ])
        else:
            source_folder_is_present = (
                source_folder.relative_path in seen_folder_paths
                or media_file_count > 0
                or accessory_file_count > 0
            )
            source_folder.removed_at = None if source_folder_is_present else timezone.now()
            source_folder.save(update_fields=[
                "file_count",
                "audio_file_count",
                "accessory_file_count",
                "removed_at",
                "updated_at",
            ])

    library.last_discovery_at = timezone.now()
    library.save(update_fields=["last_discovery_at", "updated_at"])

    job.refresh_from_db()
    job.status = LibraryScanJob.STATUS_DONE if error_count == 0 else LibraryScanJob.STATUS_ERROR
    job.finished_at = timezone.now()
    job.discovered_count = discovered_count
    job.skipped_count = skipped_count
    job.error_count = error_count
    job.removed_count = removed_count
    job.save(update_fields=[
        "status",
        "finished_at",
        "discovered_count",
        "skipped_count",
        "error_count",
        "removed_count",
        "updated_at",
    ])

    return {
        "job_id": job.id,
        "status": job.status,
        "discovered_count": discovered_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "removed_count": removed_count,
        "target_path": normalized_target_path,
    }


def _selected_classic_import_sources(source_keys):
    sources = _classic_import_sources_from_settings()
    if not sources:
        raise ValueError("No classic import folders are configured.")
    requested_keys = [
        _normalize_classic_source_key(value)
        for value in (source_keys or [])
        if str(value or "").strip()
    ]
    source_by_key = {source["key"]: source for source in sources}
    if not requested_keys:
        requested_keys = list(source_by_key.keys())
    missing_keys = [key for key in requested_keys if key not in source_by_key]
    if missing_keys:
        raise ValueError(f"Unknown classic import folder: {', '.join(missing_keys)}")
    selected = [source_by_key[key] for key in requested_keys]
    unavailable = [
        source["label"]
        for source in selected
        if not source["exists"] or not source["is_dir"] or not source["readable"]
    ]
    if unavailable:
        raise ValueError(f"Classic import folder unavailable: {', '.join(unavailable)}")
    return selected


def _classic_relative_path(source, absolute_path: Path) -> str:
    source_root = Path(source["container_path"])
    relative_inside_source = absolute_path.relative_to(source_root).as_posix()
    return f"{source['relative_prefix']}/{relative_inside_source}".strip("/")


def _classic_source_folder(library: Library, source, absolute_path: Path) -> SourceFolder:
    source_root = Path(source["container_path"])
    folder_path = absolute_path.parent
    relative_folder = folder_path.relative_to(source_root).as_posix()
    if relative_folder == ".":
        relative_folder = ""
    prefixed_relative_folder = source["relative_prefix"]
    if relative_folder:
        prefixed_relative_folder = f"{prefixed_relative_folder}/{relative_folder}"
    return _get_or_create_source_folder_for_relative(
        library,
        folder_path,
        prefixed_relative_folder,
        source["label"],
    )


def _discover_classic_import_sources(job_id: int, source_keys):
    job = LibraryScanJob.objects.select_related("library").get(pk=job_id)
    library = job.library
    try:
        selected_sources = _selected_classic_import_sources(source_keys)
    except ValueError as exc:
        job.status = LibraryScanJob.STATUS_ERROR
        job.started_at = timezone.now()
        job.finished_at = timezone.now()
        job.last_error = str(exc)
        job.save(update_fields=["status", "started_at", "finished_at", "last_error", "updated_at"])
        return {"job_id": job.id, "status": job.status, "error": job.last_error}

    LibraryScanSkip.objects.filter(scan_job=job).delete()
    job.status = LibraryScanJob.STATUS_DISCOVERING
    job.started_at = timezone.now()
    job.finished_at = None
    job.last_error = ""
    job.discovered_count = 0
    job.queued_count = 0
    job.processed_count = 0
    job.skipped_count = 0
    job.error_count = 0
    job.removed_count = 0
    job.save(update_fields=[
        "status",
        "started_at",
        "finished_at",
        "last_error",
        "discovered_count",
        "queued_count",
        "processed_count",
        "skipped_count",
        "error_count",
        "removed_count",
        "updated_at",
    ])

    seen_paths = set()
    seen_accessory_paths = set()
    seen_folder_paths = set()
    discovered_count = 0
    skipped_count = 0
    error_count = 0
    scanned_count = 0

    for source in selected_sources:
        source_root = Path(source["container_path"])
        for absolute_path in _iter_scoped_file_paths(source_root, ""):
            scanned_count += 1
            _scan_pause(scanned_count)
            filename = absolute_path.name
            extension = absolute_path.suffix.lower()
            relative_path = _classic_relative_path(source, absolute_path)
            try:
                source_folder = _classic_source_folder(library, source, absolute_path)
                seen_folder_paths.add(source_folder.relative_path)
                stat_result = absolute_path.stat()
                mtime = datetime.fromtimestamp(
                    stat_result.st_mtime,
                    tz=timezone.get_current_timezone(),
                )

                if filename.lower() in IGNORED_FILENAMES or filename.lower().startswith("._"):
                    reason_code, reason_detail = _classify_skip(filename, extension)
                    LibraryScanSkip.objects.create(
                        scan_job=job,
                        library=library,
                        relative_path=relative_path,
                        absolute_path=str(absolute_path),
                        filename=filename,
                        extension=extension.lstrip("."),
                        size=stat_result.st_size,
                        reason_code=reason_code,
                        reason_detail=reason_detail,
                    )
                    skipped_count += 1
                    continue

                if extension not in SUPPORTED_MEDIA_EXTENSIONS:
                    seen_accessory_paths.add(relative_path)
                    accessory_kind = _classify_accessory_kind(extension)
                    accessory_file, created = AccessoryFile.objects.get_or_create(
                        library=library,
                        relative_path=relative_path,
                        defaults={
                            "source_folder": source_folder,
                            "absolute_path": str(absolute_path),
                            "filename": filename,
                            "extension": extension.lstrip("."),
                            "asset_kind": accessory_kind,
                            "size": stat_result.st_size,
                            "mtime": mtime,
                            "removed_at": None,
                        },
                    )
                    if not created:
                        accessory_file.source_folder = source_folder
                        accessory_file.absolute_path = str(absolute_path)
                        accessory_file.filename = filename
                        accessory_file.extension = extension.lstrip(".")
                        accessory_file.asset_kind = accessory_kind
                        accessory_file.size = stat_result.st_size
                        accessory_file.mtime = mtime
                        accessory_file.removed_at = None
                        accessory_file.save(update_fields=[
                            "source_folder",
                            "absolute_path",
                            "filename",
                            "extension",
                            "asset_kind",
                            "size",
                            "mtime",
                            "removed_at",
                            "last_seen_at",
                            "updated_at",
                        ])
                    continue

                seen_paths.add(relative_path)
                path_hash = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
                inode = str(getattr(stat_result, "st_ino", ""))
                detected_media_kind = _detect_media_kind(extension)
                mime_type, _ = mimetypes.guess_type(str(absolute_path))
                media_file, created = MediaFile.objects.get_or_create(
                    library=library,
                    relative_path=relative_path,
                    defaults={
                        "source_folder": source_folder,
                        "absolute_path": str(absolute_path),
                        "path_hash": path_hash,
                        "filename": filename,
                        "extension": extension.lstrip("."),
                        "media_kind": detected_media_kind,
                        "mime_type": mime_type or "",
                        "size": stat_result.st_size,
                        "mtime": mtime,
                        "inode": inode,
                        "storage_stage": MediaFile.STORAGE_STAGE_EXTERNAL,
                        "workflow_state": MediaFile.WORKFLOW_REVISED,
                        "digest_relative_path": relative_path,
                        "status": MediaFile.STATUS_DISCOVERED,
                        "removed_at": None,
                        "last_error": "",
                    },
                )
                if not created:
                    media_file.source_folder = source_folder
                    media_file.absolute_path = str(absolute_path)
                    media_file.path_hash = path_hash
                    media_file.filename = filename
                    media_file.extension = extension.lstrip(".")
                    media_file.media_kind = detected_media_kind
                    media_file.mime_type = mime_type or ""
                    media_file.size = stat_result.st_size
                    media_file.mtime = mtime
                    media_file.inode = inode
                    media_file.storage_stage = MediaFile.STORAGE_STAGE_EXTERNAL
                    media_file.workflow_state = MediaFile.WORKFLOW_REVISED
                    media_file.digest_relative_path = relative_path
                    media_file.status = MediaFile.STATUS_DISCOVERED
                    media_file.removed_at = None
                    media_file.last_error = ""
                    media_file.save(update_fields=[
                        "source_folder",
                        "absolute_path",
                        "path_hash",
                        "filename",
                        "extension",
                        "media_kind",
                        "mime_type",
                        "size",
                        "mtime",
                        "inode",
                        "storage_stage",
                        "workflow_state",
                        "digest_relative_path",
                        "status",
                        "removed_at",
                        "last_error",
                        "last_seen_at",
                        "updated_at",
                    ])
                discovered_count += 1
                if discovered_count % 25 == 0:
                    LibraryScanJob.objects.filter(pk=job.pk).update(
                        discovered_count=discovered_count,
                        skipped_count=skipped_count,
                        error_count=error_count,
                    )
            except Exception as exc:  # pragma: no cover - defensive runtime path
                error_count += 1
                reason_code = LibraryScanSkip.REASON_UNKNOWN_ERROR
                if isinstance(exc, PermissionError):
                    reason_code = LibraryScanSkip.REASON_PERMISSION_DENIED
                elif isinstance(exc, FileNotFoundError):
                    reason_code = LibraryScanSkip.REASON_STAT_FAILED
                LibraryScanSkip.objects.create(
                    scan_job=job,
                    library=library,
                    relative_path=relative_path,
                    absolute_path=str(absolute_path),
                    filename=filename,
                    extension=extension.lstrip("."),
                    reason_code=reason_code,
                    reason_detail=str(exc),
                )
                LibraryScanJob.objects.filter(pk=job.pk).update(error_count=error_count, last_error=str(exc))

    prefixes = [source["relative_prefix"] for source in selected_sources]
    prefix_filter = _relative_prefix_q("relative_path", prefixes)
    removed_count = 0
    existing_media_queryset = MediaFile.objects.filter(
        library=library,
        storage_stage=MediaFile.STORAGE_STAGE_EXTERNAL,
    ).filter(prefix_filter)
    missing_paths = set(existing_media_queryset.values_list("relative_path", flat=True)) - seen_paths
    if missing_paths:
        removed_count = MediaFile.objects.filter(
            library=library,
            relative_path__in=missing_paths,
        ).exclude(status=MediaFile.STATUS_MISSING).update(
            status=MediaFile.STATUS_MISSING,
            removed_at=timezone.now(),
        )

    existing_accessory_queryset = AccessoryFile.objects.filter(library=library).filter(prefix_filter)
    missing_accessory_paths = set(existing_accessory_queryset.values_list("relative_path", flat=True)) - seen_accessory_paths
    if missing_accessory_paths:
        AccessoryFile.objects.filter(
            library=library,
            relative_path__in=missing_accessory_paths,
        ).update(removed_at=timezone.now())

    source_folder_queryset = SourceFolder.objects.filter(library=library).filter(prefix_filter)
    for source_folder in source_folder_queryset:
        media_file_count = source_folder.media_files.exclude(status=MediaFile.STATUS_MISSING).count()
        accessory_file_count = source_folder.accessory_files.filter(removed_at__isnull=True).count()
        source_folder.file_count = media_file_count + accessory_file_count
        source_folder.audio_file_count = media_file_count
        source_folder.accessory_file_count = accessory_file_count
        source_folder.removed_at = None if source_folder.relative_path in seen_folder_paths or media_file_count or accessory_file_count else timezone.now()
        source_folder.save(update_fields=[
            "file_count",
            "audio_file_count",
            "accessory_file_count",
            "removed_at",
            "updated_at",
        ])

    library.last_discovery_at = timezone.now()
    library.save(update_fields=["last_discovery_at", "updated_at"])

    job.refresh_from_db()
    job.status = LibraryScanJob.STATUS_DONE if error_count == 0 else LibraryScanJob.STATUS_ERROR
    job.finished_at = timezone.now()
    job.discovered_count = discovered_count
    job.skipped_count = skipped_count
    job.error_count = error_count
    job.removed_count = removed_count
    job.save(update_fields=[
        "status",
        "finished_at",
        "discovered_count",
        "skipped_count",
        "error_count",
        "removed_count",
        "updated_at",
    ])
    return {
        "job_id": job.id,
        "status": job.status,
        "discovered_count": discovered_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "removed_count": removed_count,
        "sources": [source["key"] for source in selected_sources],
    }


@shared_task(bind=True)
def process_media_batch(self, job_id, media_file_ids):
    """
    Placeholder della fase 2.

    Qui andra' il parsing parallelo dei metadata e l'aggiornamento delle entita' logiche.
    """

    LibraryScanJob.objects.filter(pk=job_id).update(processed_count=F("processed_count") + len(media_file_ids))
    return {"job_id": job_id, "count": len(media_file_ids), "status": "not-implemented"}


@shared_task(bind=True)
def rescan_library_catalog(self, job_id: int, target_path: str = ""):
    job = LibraryScanJob.objects.select_related("library").get(pk=job_id)
    library = job.library
    digest_root = Path(library.digest_path)
    try:
        normalized_target_path = _normalize_scope_path(target_path)
        rescan_scope_path = _resolve_scope_path(digest_root, normalized_target_path)
    except ValueError as exc:
        job.status = LibraryScanJob.STATUS_ERROR
        job.finished_at = timezone.now()
        job.last_error = str(exc)
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        return {"job_id": job.id, "status": job.status, "error": job.last_error, "target_path": target_path}

    job.status = LibraryScanJob.STATUS_DISCOVERING
    job.started_at = timezone.now()
    job.finished_at = None
    job.last_error = ""
    job.discovered_count = 0
    job.queued_count = 0
    job.processed_count = 0
    job.skipped_count = 0
    job.error_count = 0
    job.removed_count = 0
    job.save(update_fields=[
        "status",
        "started_at",
        "finished_at",
        "last_error",
        "discovered_count",
        "queued_count",
        "processed_count",
        "skipped_count",
        "error_count",
        "removed_count",
        "updated_at",
    ])

    if not digest_root.exists() or not digest_root.is_dir():
        job.status = LibraryScanJob.STATUS_ERROR
        job.finished_at = timezone.now()
        job.last_error = f"Digest root unavailable: {digest_root}"
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        return {"job_id": job.id, "status": job.status, "error": job.last_error}
    if not rescan_scope_path.exists():
        job.status = LibraryScanJob.STATUS_ERROR
        job.finished_at = timezone.now()
        job.last_error = f"Target path non disponibile: {rescan_scope_path}"
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        return {"job_id": job.id, "status": job.status, "error": job.last_error, "target_path": normalized_target_path}

    seen_paths = set()
    seen_folder_paths = set()
    discovered_count = 0
    skipped_count = 0
    error_count = 0
    scanned_count = 0

    accessory_candidates = (
        AccessoryFile.objects.filter(library=library, removed_at__isnull=True)
        .exclude(extension="")
        .order_by("relative_path")
    )
    for accessory_file in accessory_candidates:
        scanned_count += 1
        _scan_pause(scanned_count)
        try:
            extension = f".{(accessory_file.extension or '').lower()}"
            if extension not in SUPPORTED_MEDIA_EXTENSIONS:
                continue
            absolute_path = Path(accessory_file.absolute_path)
            if not absolute_path.exists() or not absolute_path.is_file():
                continue
            if digest_root not in absolute_path.parents and absolute_path != digest_root:
                continue
            if normalized_target_path and rescan_scope_path not in absolute_path.parents and absolute_path != rescan_scope_path:
                continue
            promoted = _upsert_media_file_for_digest_path(library, digest_root, absolute_path)
            seen_paths.add(promoted["relative_path"])
            seen_folder_paths.add(promoted["source_folder"].relative_path)
            discovered_count += 1
            logger.warning(
                "trive-rescan promoted accessory to media filename=%s relative=%s absolute=%s",
                accessory_file.filename,
                accessory_file.relative_path,
                accessory_file.absolute_path,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime path
            error_count += 1
            logger.exception(
                "trive-rescan accessory promotion failed filename=%s relative=%s absolute=%s",
                accessory_file.filename,
                accessory_file.relative_path,
                accessory_file.absolute_path,
            )
            LibraryScanSkip.objects.create(
                scan_job=job,
                library=library,
                relative_path=accessory_file.relative_path,
                absolute_path=accessory_file.absolute_path,
                filename=accessory_file.filename,
                extension=accessory_file.extension,
                size=accessory_file.size,
                reason_code=LibraryScanSkip.REASON_UNKNOWN_ERROR,
                reason_detail=f"rescan_library_catalog accessory promotion: {exc.__class__.__name__}: {exc}",
            )
            LibraryScanJob.objects.filter(pk=job.pk).update(error_count=error_count, last_error=str(exc))

    for absolute_path in _iter_scoped_file_paths(digest_root, normalized_target_path):
        scanned_count += 1
        _scan_pause(scanned_count)
        filename = absolute_path.name
        extension = absolute_path.suffix.lower()
        digest_relative_path = absolute_path.relative_to(digest_root)
        relative_path, normalized_digest_relative_path, workflow_state = _split_digest_relative_path_for_media_file(digest_relative_path)

        if extension not in SUPPORTED_MEDIA_EXTENSIONS:
            skipped_count += 1
            continue

        try:
            promoted = _upsert_media_file_for_digest_path(library, digest_root, absolute_path)
            seen_paths.add(promoted["relative_path"])
            seen_folder_paths.add(promoted["source_folder"].relative_path)
            discovered_count += 1
            logger.warning(
                "trive-rescan discovered digest media filename=%s relative=%s absolute=%s",
                filename,
                promoted["relative_path"],
                str(absolute_path),
            )
            if discovered_count % 25 == 0:
                LibraryScanJob.objects.filter(pk=job.pk).update(
                    discovered_count=discovered_count,
                    skipped_count=skipped_count,
                    error_count=error_count,
                )
        except Exception as exc:  # pragma: no cover - defensive runtime path
            error_count += 1
            logger.exception(
                "trive-rescan failed filename=%s relative=%s absolute=%s",
                filename,
                relative_path,
                str(absolute_path),
            )
            LibraryScanSkip.objects.create(
                scan_job=job,
                library=library,
                relative_path=relative_path,
                absolute_path=str(absolute_path),
                filename=filename,
                extension=extension.lstrip("."),
                size=absolute_path.stat().st_size if absolute_path.exists() else None,
                reason_code=LibraryScanSkip.REASON_UNKNOWN_ERROR,
                reason_detail=f"rescan_library_catalog: {exc.__class__.__name__}: {exc}",
            )
            LibraryScanJob.objects.filter(pk=job.pk).update(error_count=error_count, last_error=str(exc))

    merged_media_duplicate_count = _dedupe_media_file_records(library, normalized_target_path)
    merged_accessory_duplicate_count = _dedupe_accessory_file_records(library, normalized_target_path)
    merged_source_folder_duplicate_count = _dedupe_source_folder_records(library, normalized_target_path)
    if merged_media_duplicate_count:
        logger.warning(
            "trive-rescan merged duplicate media file records job=%s count=%s",
            job.id,
            merged_media_duplicate_count,
        )
    if merged_accessory_duplicate_count:
        logger.warning(
            "trive-rescan merged duplicate accessory file records job=%s count=%s",
            job.id,
            merged_accessory_duplicate_count,
        )
    if merged_source_folder_duplicate_count:
        logger.warning(
            "trive-rescan merged duplicate source folder records job=%s count=%s",
            job.id,
            merged_source_folder_duplicate_count,
        )

    source_folder_queryset = SourceFolder.objects.filter(library=library)
    if normalized_target_path:
        source_folder_queryset = source_folder_queryset.filter(relative_path__in=seen_folder_paths)
    for source_folder in source_folder_queryset:
        try:
            media_count = source_folder.media_files.exclude(status=MediaFile.STATUS_MISSING).count()
            accessory_count = source_folder.accessory_files.filter(removed_at__isnull=True).count()
            update_values = {
                "file_count": media_count + accessory_count,
                "audio_file_count": media_count,
                "accessory_file_count": accessory_count,
            }
            if source_folder.relative_path in seen_folder_paths:
                update_values["removed_at"] = None
            SourceFolder.objects.filter(pk=source_folder.pk).update(**update_values)
        except Exception as exc:  # pragma: no cover - defensive runtime path
            error_count += 1
            logger.exception(
                "trive-rescan source folder counter update failed source_folder=%s relative=%s",
                source_folder.pk,
                source_folder.relative_path,
            )
            LibraryScanJob.objects.filter(pk=job.pk).update(error_count=error_count, last_error=str(exc))

    job.refresh_from_db()
    job.status = LibraryScanJob.STATUS_DONE if error_count == 0 else LibraryScanJob.STATUS_ERROR
    job.finished_at = timezone.now()
    job.discovered_count = discovered_count
    job.skipped_count = skipped_count
    job.error_count = error_count
    job.save(update_fields=[
        "status",
        "finished_at",
        "discovered_count",
        "skipped_count",
        "error_count",
        "updated_at",
    ])

    return {
        "job_id": job.id,
        "status": job.status,
        "discovered_count": discovered_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "target_path": normalized_target_path,
    }


def _initialise_library_digest_job(job: LibraryDigestJob, target_count: int):
    job.status = LibraryDigestJob.STATUS_RUNNING
    job.started_at = timezone.now()
    job.finished_at = None
    job.target_count = target_count
    job.processed_count = 0
    job.created_track_count = 0
    job.reused_track_count = 0
    job.error_count = 0
    job.last_error = ""
    job.save(update_fields=[
        "status",
        "started_at",
        "finished_at",
        "target_count",
        "processed_count",
        "created_track_count",
        "reused_track_count",
        "error_count",
        "last_error",
        "updated_at",
    ])
    LibraryDigestError.objects.filter(digest_job=job).delete()


def _library_digest_media_queryset(library: Library, target_path: str):
    media_files = (
        MediaFile.objects.select_related("source_folder")
        .filter(library=library)
        .exclude(status=MediaFile.STATUS_MISSING)
        .order_by("relative_path")
    )
    return _apply_relative_path_scope(media_files, "relative_path", target_path)


def _media_file_path_exists(media_file: MediaFile) -> bool:
    candidates = []
    if media_file.absolute_path:
        candidates.extend(_candidate_legacy_paths(media_file.absolute_path))
    if media_file.digest_relative_path:
        candidates.append(Path(media_file.library.digest_path) / Path(media_file.digest_relative_path))
    if media_file.relative_path:
        relative_path = Path(media_file.relative_path)
        candidates.extend([
            Path(media_file.library.ingest_path) / relative_path,
            Path(media_file.library.digest_path) / "Unrevisioned" / relative_path,
            Path(media_file.library.digest_path) / relative_path,
        ])
    return any(candidate.exists() and candidate.is_file() for candidate in candidates)


def _media_file_dedupe_score(media_file: MediaFile) -> tuple:
    referenced_count = (
        Track.objects.filter(primary_file=media_file).count()
        + TrackSourceMetadata.objects.filter(media_file=media_file).count()
        + MediaFileMetaValue.objects.filter(media_file=media_file).count()
        + MetadataWritebackJob.objects.filter(media_file=media_file).count()
        + MediaTransformJob.objects.filter(source_file=media_file).count()
    )
    stage_score = 1 if media_file.storage_stage == MediaFile.STORAGE_STAGE_TRIV_UP else 0
    active_score = 1 if media_file.removed_at is None else 0
    status_score = {
        MediaFile.STATUS_INDEXED: 4,
        MediaFile.STATUS_SYNCED: 4,
        MediaFile.STATUS_MODIFIED: 3,
        MediaFile.STATUS_PENDING_WRITE: 2,
        MediaFile.STATUS_DISCOVERED: 1,
        MediaFile.STATUS_ERROR: 0,
    }.get(media_file.status, 0)
    return (
        referenced_count,
        active_score,
        stage_score,
        status_score,
        1 if media_file.digest_relative_path else 0,
        1 if _media_file_path_exists(media_file) else 0,
        media_file.updated_at or media_file.created_at,
    )


def _dedupe_media_file_records(library: Library, target_path: str = "") -> int:
    candidate_queryset = MediaFile.objects.filter(library=library)
    candidate_queryset = _apply_relative_path_scope(candidate_queryset, "relative_path", target_path)
    record_groups = {}
    for record in candidate_queryset.only("id", "relative_path").order_by("relative_path", "created_at", "id").iterator(chunk_size=1000):
        record_groups.setdefault(record.relative_path, []).append(record.pk)

    merged_count = 0
    for relative_path, record_ids in record_groups.items():
        if len(record_ids) < 2:
            continue
        with transaction.atomic():
            records = list(
                MediaFile.objects
                .select_for_update()
                .filter(pk__in=record_ids)
                .order_by("created_at", "id")
            )
            if len(records) < 2:
                continue
            canonical = max(records, key=_media_file_dedupe_score)
            for duplicate in records:
                if duplicate.pk == canonical.pk:
                    continue
                logger.warning(
                    "trive-up merging duplicate media file duplicate=%s canonical=%s relative=%s",
                    duplicate.pk,
                    canonical.pk,
                    relative_path,
                )
                Track.objects.filter(primary_file=duplicate).update(primary_file=canonical)
                TrackSourceMetadata.objects.filter(media_file=duplicate).update(media_file=canonical)
                MediaFileMetaValue.objects.filter(media_file=duplicate).update(media_file=canonical)
                LibraryDigestError.objects.filter(media_file=duplicate).update(media_file=canonical)
                MetadataWritebackJob.objects.filter(media_file=duplicate).update(media_file=canonical)
                MediaTransformJob.objects.filter(source_file=duplicate).update(source_file=canonical)
                duplicate.delete()
                merged_count += 1
    return merged_count


def _track_dedupe_score(track: Track) -> tuple:
    referenced_count = (
        TrackSourceMetadata.objects.filter(track=track).count()
        + TrackArtistCredit.objects.filter(track=track).count()
        + MetadataWritebackJob.objects.filter(track=track).count()
    )
    return (
        1 if track.metadata_state != Track.STATE_ERROR else 0,
        1 if hasattr(track, "override") else 0,
        referenced_count,
        track.updated_at or track.created_at,
    )


def _move_unique_track_tags(duplicate: Track, canonical: Track):
    from apps.tags.models import TrackTagAssignment

    for assignment in TrackTagAssignment.objects.filter(track=duplicate).select_related("tag_value"):
        if TrackTagAssignment.objects.filter(track=canonical, tag_value=assignment.tag_value).exists():
            assignment.delete()
            continue
        assignment.track = canonical
        assignment.save(update_fields=["track", "updated_at"])


def _move_unique_track_version_memberships(duplicate: Track, canonical: Track):
    from apps.catalog.models import TrackVersionMembership

    for membership in TrackVersionMembership.objects.filter(track=duplicate).select_related("group"):
        if TrackVersionMembership.objects.filter(group=membership.group, track=canonical).exists():
            membership.delete()
            continue
        membership.track = canonical
        membership.save(update_fields=["track", "updated_at"])


def _move_track_override(duplicate: Track, canonical: Track):
    from apps.catalog.models import TrackMetadataOverride

    duplicate_override = TrackMetadataOverride.objects.filter(track=duplicate).first()
    if not duplicate_override:
        return
    if TrackMetadataOverride.objects.filter(track=canonical).exists():
        duplicate_override.delete()
        return
    duplicate_override.track = canonical
    duplicate_override.save(update_fields=["track", "updated_at"])


def _dedupe_track_records(library: Library, target_path: str = "") -> int:
    candidate_queryset = Track.objects.filter(primary_file__library=library, primary_file__isnull=False)
    candidate_queryset = _apply_relative_path_scope(candidate_queryset, "primary_file__relative_path", target_path)
    record_groups = {}
    for track in candidate_queryset.only("id", "primary_file_id").order_by("primary_file_id", "created_at", "id").iterator(chunk_size=1000):
        record_groups.setdefault(track.primary_file_id, []).append(track.pk)

    merged_count = 0
    for primary_file_id, record_ids in record_groups.items():
        if len(record_ids) < 2:
            continue
        with transaction.atomic():
            records = list(
                Track.objects
                .select_for_update()
                .filter(pk__in=record_ids)
                .order_by("created_at", "id")
            )
            if len(records) < 2:
                continue
            canonical = max(records, key=_track_dedupe_score)
            for duplicate in records:
                if duplicate.pk == canonical.pk:
                    continue
                logger.warning(
                    "trive-up merging duplicate track duplicate=%s canonical=%s primary_file=%s",
                    duplicate.pk,
                    canonical.pk,
                    primary_file_id,
                )
                _move_track_override(duplicate, canonical)
                _move_unique_track_tags(duplicate, canonical)
                _move_unique_track_version_memberships(duplicate, canonical)
                TrackSourceMetadata.objects.filter(track=duplicate).update(track=canonical)
                TrackArtistCredit.objects.filter(track=duplicate).delete()
                MetadataWritebackJob.objects.filter(track=duplicate).update(track=canonical)
                duplicate.saved_playlist_entries.update(track=canonical)
                duplicate.delete()
                merged_count += 1
    return merged_count


def _track_source_metadata_dedupe_score(source_metadata: TrackSourceMetadata) -> tuple:
    return (
        1 if source_metadata.raw_payload else 0,
        source_metadata.updated_at or source_metadata.created_at,
    )


def _dedupe_track_source_metadata_records(library: Library, target_path: str = "") -> int:
    candidate_queryset = TrackSourceMetadata.objects.filter(media_file__library=library)
    candidate_queryset = _apply_relative_path_scope(candidate_queryset, "media_file__relative_path", target_path)
    record_groups = {}
    for source_metadata in (
        candidate_queryset
        .only("id", "track_id", "media_file_id")
        .order_by("track_id", "media_file_id", "created_at", "id")
        .iterator(chunk_size=1000)
    ):
        record_groups.setdefault((source_metadata.track_id, source_metadata.media_file_id), []).append(source_metadata.pk)

    merged_count = 0
    for (track_id, media_file_id), record_ids in record_groups.items():
        if len(record_ids) < 2:
            continue
        with transaction.atomic():
            records = list(
                TrackSourceMetadata.objects
                .select_for_update()
                .filter(pk__in=record_ids)
                .order_by("created_at", "id")
            )
            if len(records) < 2:
                continue
            canonical = max(records, key=_track_source_metadata_dedupe_score)
            for duplicate in records:
                if duplicate.pk == canonical.pk:
                    continue
                logger.warning(
                    "trive-up merging duplicate track source metadata duplicate=%s canonical=%s track=%s media_file=%s",
                    duplicate.pk,
                    canonical.pk,
                    track_id,
                    media_file_id,
                )
                duplicate.delete()
                merged_count += 1
    return merged_count


def _source_folder_dedupe_score(source_folder: SourceFolder) -> tuple:
    referenced_count = (
        MediaFile.objects.filter(source_folder=source_folder).count()
        + AccessoryFile.objects.filter(source_folder=source_folder).count()
    )
    return (
        referenced_count,
        1 if source_folder.removed_at is None else 0,
        source_folder.file_count or 0,
        source_folder.audio_file_count or 0,
        source_folder.accessory_file_count or 0,
        source_folder.updated_at or source_folder.created_at,
    )


def _dedupe_source_folder_records(library: Library, target_path: str = "") -> int:
    candidate_queryset = SourceFolder.objects.filter(library=library)
    candidate_queryset = _apply_relative_path_scope(candidate_queryset, "relative_path", target_path)
    record_groups = {}
    for record in candidate_queryset.only("id", "relative_path").order_by("relative_path", "created_at", "id").iterator(chunk_size=1000):
        record_groups.setdefault(record.relative_path, []).append(record.pk)

    merged_count = 0
    for relative_path, record_ids in record_groups.items():
        if len(record_ids) < 2:
            continue
        with transaction.atomic():
            records = list(
                SourceFolder.objects
                .select_for_update()
                .filter(pk__in=record_ids)
                .order_by("created_at", "id")
            )
            if len(records) < 2:
                continue
            canonical = max(records, key=_source_folder_dedupe_score)
            for duplicate in records:
                if duplicate.pk == canonical.pk:
                    continue
                logger.warning(
                    "trive-up merging duplicate source folder duplicate=%s canonical=%s relative=%s",
                    duplicate.pk,
                    canonical.pk,
                    relative_path,
                )
                MediaFile.objects.filter(source_folder=duplicate).update(source_folder=canonical)
                AccessoryFile.objects.filter(source_folder=duplicate).update(source_folder=canonical)
                duplicate.delete()
                merged_count += 1
    return merged_count


def _accessory_file_path_exists(accessory_file: AccessoryFile) -> bool:
    seen = set()
    for candidate in _candidate_accessory_paths(accessory_file):
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.exists() and candidate.is_file():
            return True
    return False


def _accessory_file_dedupe_score(accessory_file: AccessoryFile) -> tuple:
    return (
        1 if accessory_file.removed_at is None else 0,
        1 if _accessory_file_path_exists(accessory_file) else 0,
        1 if accessory_file.source_folder_id else 0,
        accessory_file.size or 0,
        accessory_file.mtime or accessory_file.updated_at or accessory_file.created_at,
        accessory_file.updated_at or accessory_file.created_at,
    )


def _dedupe_accessory_file_records(library: Library, target_path: str = "") -> int:
    candidate_queryset = AccessoryFile.objects.filter(library=library)
    candidate_queryset = _apply_relative_path_scope(candidate_queryset, "relative_path", target_path)
    record_groups = {}
    for record in candidate_queryset.only("id", "relative_path").order_by("relative_path", "created_at", "id").iterator(chunk_size=1000):
        record_groups.setdefault(record.relative_path, []).append(record.pk)

    merged_count = 0
    for relative_path, record_ids in record_groups.items():
        if len(record_ids) < 2:
            continue
        with transaction.atomic():
            records = list(
                AccessoryFile.objects
                .select_for_update()
                .filter(pk__in=record_ids)
                .order_by("created_at", "id")
            )
            if len(records) < 2:
                continue
            canonical = max(records, key=_accessory_file_dedupe_score)
            for duplicate in records:
                if duplicate.pk == canonical.pk:
                    continue
                logger.warning(
                    "trive-up merging duplicate accessory file duplicate=%s canonical=%s relative=%s",
                    duplicate.pk,
                    canonical.pk,
                    relative_path,
                )
                duplicate.delete()
                merged_count += 1
    return merged_count


def _process_library_catalog_media_file(job: LibraryDigestJob, media_file_id: str):
    result = _empty_digest_result()
    library = job.library
    media_file = None
    try:
        media_file = (
            MediaFile.objects
            .select_related("source_folder", "library")
            .get(pk=media_file_id, library=library)
        )
        logger.warning(
            "trive-up processing media file id=%s relative=%s kind=%s stage=%s workflow=%s status=%s",
            media_file.pk,
            media_file.relative_path,
            media_file.media_kind,
            media_file.storage_stage,
            media_file.workflow_state,
            media_file.status,
        )
        resolved_media_path = _resolve_existing_media_path(media_file)
        if resolved_media_path is None:
            raise FileNotFoundError(
                f"Unable to resolve media file on disk for {media_file.relative_path}"
            )

        content_hash = _content_hash_for_promotion(media_file, resolved_media_path)
        if media_file.media_kind == "audio":
            _index_media_file_metadata(media_file)
            _sync_triver_interpretation(media_file)
            metadata = _extract_media_metadata(media_file)
        else:
            MediaFileMetaValue.objects.filter(media_file=media_file).exclude(source_family="user").delete()
            _apply_video_path_metadata(media_file)
            metadata = _extract_video_metadata(media_file)
        promotion_result = _promote_media_file(media_file, content_hash)

        if promotion_result["workflow_state"] == MediaFile.WORKFLOW_EXACT_DUPLICATE:
            media_file.content_hash = content_hash
            media_file.absolute_path = promotion_result["absolute_path"]
            media_file.digest_relative_path = promotion_result["digest_relative_path"]
            media_file.storage_stage = MediaFile.STORAGE_STAGE_TRIV_UP
            media_file.workflow_state = MediaFile.WORKFLOW_EXACT_DUPLICATE
            media_file.status = MediaFile.STATUS_SYNCED
            media_file.last_error = ""
            media_file.save(update_fields=[
                "absolute_path",
                "content_hash",
                "digest_relative_path",
                "storage_stage",
                "workflow_state",
                "status",
                "last_error",
                "last_seen_at",
                "updated_at",
            ])
            result["processed_count"] = 1
            result["reused_track_count"] = 1
            logger.warning(
                "trive-up exact duplicate media file id=%s relative=%s",
                media_file.pk,
                media_file.relative_path,
            )
            return result

        with transaction.atomic():
            album = _get_or_create_album(metadata["album_title"], metadata["release_year"])
            primary_artist_name = (metadata.get("artist_names") or [metadata["artist_name"]])[0]
            artist = _get_or_create_artist(primary_artist_name)

            track, created = Track.objects.get_or_create(
                primary_file=media_file,
                defaults={
                    "album": album,
                    "canonical_title": metadata["canonical_title"],
                    "canonical_sort_title": metadata["canonical_title"].lower(),
                    "release_year": metadata["release_year"],
                    "disc_number": metadata["disc_number"],
                    "track_number": metadata["track_number"],
                    "duration_seconds": metadata["duration_seconds"],
                    "metadata_state": Track.STATE_CLEAN,
                    "last_error": "",
                },
            )
            if created:
                result["created_track_count"] = 1
            else:
                result["reused_track_count"] = 1

            track.album = album
            track.canonical_title = metadata["canonical_title"]
            track.canonical_sort_title = metadata["canonical_title"].lower()
            track.release_year = metadata["release_year"]
            track.disc_number = metadata["disc_number"]
            track.track_number = metadata["track_number"]
            track.duration_seconds = metadata["duration_seconds"]
            track.metadata_state = Track.STATE_CLEAN
            track.last_error = ""
            track.save()

            TrackSourceMetadata.objects.update_or_create(
                track=track,
                media_file=media_file,
                defaults={
                    "extractor_name": "ffprobe" if media_file.media_kind == "video" else "mutagen",
                    "extractor_version": "",
                    "raw_title": metadata["raw_title"],
                    "raw_album": metadata["raw_album"],
                    "raw_year": metadata["raw_year"],
                    "raw_track_number": metadata["raw_track_number"],
                    "raw_disc_number": metadata["raw_disc_number"],
                    "raw_artists_display": metadata["raw_artists_display"],
                    "raw_payload": metadata["raw_payload"],
                },
            )

            artist_names = metadata.get("artist_names") or [metadata["artist_name"]]
            artists = []
            for artist_name in artist_names:
                catalog_artist = _get_or_create_artist(artist_name)
                if catalog_artist:
                    artists.append(catalog_artist)

            if not artists:
                artists = [artist]

            TrackArtistCredit.objects.filter(track=track, role=TrackArtistCredit.ROLE_PRIMARY).exclude(
                artist__in=artists
            ).delete()
            for index, catalog_artist in enumerate(artists):
                TrackArtistCredit.objects.update_or_create(
                    track=track,
                    artist=catalog_artist,
                    role=TrackArtistCredit.ROLE_PRIMARY,
                    credit_order=index,
                    defaults={
                        "credited_name": catalog_artist.name,
                        "is_primary": index == 0,
                    },
                )

            for role, contributor_names in (metadata.get("contributor_names_by_role") or {}).items():
                TrackArtistCredit.objects.filter(track=track, role=role).exclude(
                    artist__name__in=contributor_names
                ).delete()
                for index, contributor_name in enumerate(contributor_names):
                    catalog_artist = _get_or_create_artist(contributor_name)
                    if not catalog_artist:
                        continue
                    TrackArtistCredit.objects.update_or_create(
                        track=track,
                        artist=catalog_artist,
                        role=role,
                        credit_order=index,
                        defaults={
                            "credited_name": catalog_artist.name,
                            "is_primary": False,
                        },
                    )

            media_file.content_hash = content_hash
            media_file.absolute_path = promotion_result["absolute_path"]
            media_file.digest_relative_path = promotion_result["digest_relative_path"]
            media_file.storage_stage = MediaFile.STORAGE_STAGE_TRIV_UP
            media_file.workflow_state = promotion_result["workflow_state"]
            media_file.status = (
                MediaFile.STATUS_SYNCED
                if promotion_result["workflow_state"] == MediaFile.WORKFLOW_EXACT_DUPLICATE
                else MediaFile.STATUS_INDEXED
            )
            media_file.last_error = ""
            media_file.save(update_fields=[
                "absolute_path",
                "content_hash",
                "digest_relative_path",
                "storage_stage",
                "workflow_state",
                "status",
                "last_error",
                "last_seen_at",
                "updated_at",
            ])

        result["processed_count"] = 1
        logger.info(
            "trive-up indexed media file id=%s relative=%s track_title=%s kind=%s",
            media_file.pk,
            media_file.relative_path,
            metadata["canonical_title"],
            media_file.media_kind,
        )
    except Exception as exc:  # pragma: no cover - runtime path
        last_error = str(exc)
        result["error_count"] = 1
        result["last_error"] = last_error
        if media_file is not None:
            logger.exception(
                "trive-up failed media file id=%s relative=%s kind=%s",
                media_file.pk,
                media_file.relative_path,
                media_file.media_kind,
            )
            media_file.status = MediaFile.STATUS_ERROR
            media_file.last_error = last_error
            try:
                media_file.save(update_fields=["status", "last_error", "last_seen_at", "updated_at"])
            except IntegrityError:
                logger.exception(
                    "trive-up failed to mark media file error id=%s relative=%s",
                    media_file.pk,
                    media_file.relative_path,
                )
            LibraryDigestError.objects.create(
                digest_job=job,
                library=library,
                media_file=media_file,
                relative_path=media_file.relative_path,
                absolute_path=media_file.absolute_path,
                filename=media_file.filename,
                message=last_error,
                error_type=exc.__class__.__name__,
            )
        else:
            logger.exception("trive-up failed before media file load id=%s", media_file_id)
            LibraryDigestError.objects.create(
                digest_job=job,
                library=library,
                media_file=None,
                relative_path="",
                absolute_path="",
                filename=str(media_file_id),
                message=last_error,
                error_type=exc.__class__.__name__,
            )
    return result


def _process_library_digest_batch(job_id: int, media_file_ids):
    batch_result = _empty_digest_result()
    pending_progress = _empty_digest_result()
    progress_interval = _digest_progress_interval()
    try:
        job = LibraryDigestJob.objects.select_related("library").get(pk=job_id)
    except LibraryDigestJob.DoesNotExist:
        batch_result["error_count"] = 1
        batch_result["last_error"] = f"Digest job not found: {job_id}"
        return batch_result

    if job.status == LibraryDigestJob.STATUS_CANCELED:
        return batch_result

    for media_file_id in media_file_ids:
        if LibraryDigestJob.objects.filter(pk=job_id, status=LibraryDigestJob.STATUS_CANCELED).exists():
            break
        result = _process_library_catalog_media_file(job, media_file_id)
        _merge_digest_result(batch_result, result)
        _merge_digest_result(pending_progress, result)
        _sleep_if_configured("TRIVER_DIGEST_ITEM_SLEEP_SECONDS", 0.35)
        finished_delta = pending_progress["processed_count"] + pending_progress["error_count"]
        if finished_delta >= progress_interval:
            _record_digest_progress(job_id, pending_progress)
            pending_progress = _empty_digest_result()

    if _has_digest_delta(pending_progress):
        _record_digest_progress(job_id, pending_progress)

    batch_result["job_id"] = job_id
    batch_result["batch_size"] = len(media_file_ids)
    return batch_result


@shared_task(bind=True)
def process_library_digest_batch(self, job_id: int, media_file_ids):
    return _process_library_digest_batch(job_id, media_file_ids)


def _finalize_library_catalog(job_id: int, target_path: str, batch_results=None):
    job = LibraryDigestJob.objects.select_related("library").get(pk=job_id)
    library = job.library
    normalized_target_path = _normalize_scope_path(target_path)

    if job.status == LibraryDigestJob.STATUS_CANCELED:
        job.finished_at = timezone.now()
        job.save(update_fields=["finished_at", "updated_at"])
        return {"library_id": library.id, "job_id": job.id, "status": job.status}

    promoted_accessory_count = 0
    dumped_leftover_count = 0
    last_error = ""
    merged_accessory_duplicate_count = _dedupe_accessory_file_records(library, normalized_target_path)
    if merged_accessory_duplicate_count:
        logger.warning(
            "trive-up merged duplicate accessory file records job=%s count=%s",
            job.id,
            merged_accessory_duplicate_count,
        )

    accessory_queryset = AccessoryFile.objects.filter(library=library, removed_at__isnull=True).order_by("relative_path")
    accessory_queryset = _apply_relative_path_scope(accessory_queryset, "relative_path", normalized_target_path)
    for accessory_file in accessory_queryset:
        try:
            if _promote_accessory_file(accessory_file):
                promoted_accessory_count += 1
        except Exception as exc:  # pragma: no cover - runtime path
            last_error = str(exc)
            LibraryDigestError.objects.create(
                digest_job=job,
                library=library,
                media_file=None,
                relative_path=accessory_file.relative_path,
                absolute_path=accessory_file.absolute_path,
                filename=accessory_file.filename,
                message=last_error,
                error_type=exc.__class__.__name__,
            )
            _record_digest_progress(job.pk, {"error_count": 1, "last_error": last_error})

    try:
        dumped_leftover_count = _dump_remaining_ingest_files(library, normalized_target_path)
    except Exception as exc:  # pragma: no cover - runtime path
        last_error = str(exc)
        _record_digest_progress(job.pk, {"error_count": 1, "last_error": last_error})

    library.last_digest_sync_at = timezone.now()
    library.save(update_fields=["last_digest_sync_at", "updated_at"])

    job.refresh_from_db()
    if job.last_error:
        last_error = job.last_error
    job.status = LibraryDigestJob.STATUS_DONE if job.error_count == 0 else LibraryDigestJob.STATUS_ERROR
    job.finished_at = timezone.now()
    job.save(update_fields=[
        "status",
        "finished_at",
        "updated_at",
    ])

    return {
        "library_id": library.id,
        "job_id": job.id,
        "target_count": job.target_count,
        "processed_count": job.processed_count,
        "created_track_count": job.created_track_count,
        "reused_track_count": job.reused_track_count,
        "promoted_accessory_count": promoted_accessory_count,
        "merged_accessory_duplicate_count": merged_accessory_duplicate_count,
        "dumped_leftover_count": dumped_leftover_count,
        "error_count": job.error_count,
        "last_error": last_error,
        "target_path": normalized_target_path,
        "batch_count": len(batch_results or []),
    }


@shared_task(bind=True)
def finalize_library_catalog(self, batch_results, job_id: int, target_path: str = ""):
    return _finalize_library_catalog(job_id, target_path, batch_results)


def _run_library_catalog_batches_sync(job_id: int, normalized_target_path: str, media_file_ids):
    batch_results = []
    for media_file_batch in _chunked(media_file_ids, _digest_batch_size()):
        batch_results.append(_process_library_digest_batch(job_id, media_file_batch))
        _sleep_if_configured("TRIVER_DIGEST_BATCH_SLEEP_SECONDS", 0.0)
    return _finalize_library_catalog(job_id, normalized_target_path, batch_results)


def _run_classic_import_catalog(job_id: int, source_keys):
    job = LibraryDigestJob.objects.select_related("library").get(pk=job_id)
    library = job.library
    try:
        selected_sources = _selected_classic_import_sources(source_keys)
    except ValueError as exc:
        job.status = LibraryDigestJob.STATUS_ERROR
        job.started_at = timezone.now()
        job.finished_at = timezone.now()
        job.last_error = str(exc)
        job.save(update_fields=["status", "started_at", "finished_at", "last_error", "updated_at"])
        return {"job_id": job.id, "status": job.status, "error": job.last_error}

    prefixes = [source["relative_prefix"] for source in selected_sources]
    media_file_ids = [
        str(media_file_id)
        for media_file_id in (
            MediaFile.objects
            .filter(library=library, storage_stage=MediaFile.STORAGE_STAGE_EXTERNAL)
            .exclude(status=MediaFile.STATUS_MISSING)
            .filter(_relative_prefix_q("relative_path", prefixes))
            .order_by("relative_path")
            .values_list("pk", flat=True)
        )
    ]
    target_label = CLASSIC_IMPORT_PREFIX
    _initialise_library_digest_job(job, len(media_file_ids))
    if not media_file_ids:
        return _finalize_library_catalog(job.id, target_label, [])

    if not _bool_setting("TRIVER_DIGEST_PARALLEL_BATCHES", False):
        logger.warning(
            "classic-import running in conservative serial mode job=%s target_count=%s batch_size=%s",
            job.id,
            len(media_file_ids),
            _digest_batch_size(),
        )
        return _run_library_catalog_batches_sync(job.id, target_label, media_file_ids)

    batches = list(_chunked(media_file_ids, _digest_batch_size()))
    workflow = chord(
        group([process_library_digest_batch.s(job.id, media_file_batch) for media_file_batch in batches]),
        finalize_library_catalog.s(job.id, target_label),
    )
    try:
        finalizer_result = workflow.apply_async()
    except Exception:  # pragma: no cover - local fallback path
        logger.exception("classic-import failed to schedule parallel digest; running synchronously job=%s", job.id)
        return _run_library_catalog_batches_sync(job.id, target_label, media_file_ids)

    return {
        "library_id": library.id,
        "job_id": job.id,
        "target_count": len(media_file_ids),
        "batch_count": len(batches),
        "batch_size": _digest_batch_size(),
        "finalizer_task_id": finalizer_result.id,
        "status": job.status,
        "sources": [source["key"] for source in selected_sources],
    }


@shared_task(bind=True)
def run_classic_import(self, scan_job_id: int, digest_job_id: int, source_keys):
    scan_result = _discover_classic_import_sources(scan_job_id, source_keys)
    if scan_result.get("status") != LibraryScanJob.STATUS_DONE:
        LibraryDigestJob.objects.filter(pk=digest_job_id).update(
            status=LibraryDigestJob.STATUS_ERROR,
            started_at=timezone.now(),
            finished_at=timezone.now(),
            last_error=scan_result.get("error") or "Classic import discovery failed.",
            updated_at=timezone.now(),
        )
        return {
            "scan": scan_result,
            "digest": {"job_id": digest_job_id, "status": LibraryDigestJob.STATUS_ERROR},
        }
    digest_result = _run_classic_import_catalog(digest_job_id, source_keys)
    return {"scan": scan_result, "digest": digest_result}


@shared_task(bind=True)
def discover_classic_import_sources(self, scan_job_id: int, source_keys):
    return _discover_classic_import_sources(scan_job_id, source_keys)


@shared_task(bind=True)
def run_trive_import(self, scan_job_id: int, digest_job_id: int, target_path: str = ""):
    scan_result = discover_library.run(scan_job_id, target_path)
    if scan_result.get("status") != LibraryScanJob.STATUS_DONE:
        LibraryDigestJob.objects.filter(pk=digest_job_id).update(
            status=LibraryDigestJob.STATUS_ERROR,
            started_at=timezone.now(),
            finished_at=timezone.now(),
            last_error=scan_result.get("error") or "TriveImport discovery failed.",
            updated_at=timezone.now(),
        )
        return {
            "scan": scan_result,
            "digest": {"job_id": digest_job_id, "status": LibraryDigestJob.STATUS_ERROR},
        }
    digest_result = build_library_catalog.run(digest_job_id, target_path)
    return {"scan": scan_result, "digest": digest_result}


@shared_task(bind=True)
def run_auto_import_monitor(self, force: bool = False):
    library = _get_or_create_default_library()
    settings_obj, _created = AutoImportSettings.objects.get_or_create(library=library)
    now = timezone.now()

    if not force and not settings_obj.enabled:
        settings_obj.last_checked_at = now
        settings_obj.last_result = {"action": "disabled"}
        settings_obj.last_error = ""
        settings_obj.save(update_fields=["last_checked_at", "last_result", "last_error", "updated_at"])
        return settings_obj.last_result

    if _io_job_is_active(library):
        settings_obj.last_checked_at = now
        settings_obj.last_result = {"action": "skipped_active_job"}
        settings_obj.last_error = ""
        settings_obj.save(update_fields=["last_checked_at", "last_result", "last_error", "updated_at"])
        return settings_obj.last_result

    results = []
    try:
        if settings_obj.trive_scan_enabled or settings_obj.trive_up_enabled:
            trive_result = _schedule_trive_auto_import(settings_obj, force)
            results.append(trive_result)
            if trive_result.get("celery_task_id"):
                settings_obj.last_checked_at = now
                settings_obj.last_result = {"action": "triggered", "results": results}
                settings_obj.last_error = ""
                settings_obj.save(update_fields=[
                    "last_checked_at",
                    "last_triggered_at",
                    "last_trive_signature",
                    "last_classic_signatures",
                    "last_result",
                    "last_error",
                    "updated_at",
                ])
                return settings_obj.last_result

        if settings_obj.classic_scan_enabled or settings_obj.classic_up_enabled:
            classic_result = _schedule_classic_auto_import(settings_obj, force)
            results.append(classic_result)

        settings_obj.last_checked_at = now
        settings_obj.last_result = {"action": "checked", "results": results}
        settings_obj.last_error = ""
        settings_obj.save(update_fields=[
            "last_checked_at",
            "last_triggered_at",
            "last_trive_signature",
            "last_classic_signatures",
            "last_result",
            "last_error",
            "updated_at",
        ])
        return settings_obj.last_result
    except Exception as exc:
        logger.exception("auto-import monitor failed")
        settings_obj.last_checked_at = now
        settings_obj.last_result = {"action": "error"}
        settings_obj.last_error = str(exc)
        settings_obj.save(update_fields=["last_checked_at", "last_result", "last_error", "updated_at"])
        return {"action": "error", "error": str(exc)}


@shared_task(bind=True)
def build_library_catalog(self, job_id: int, target_path: str = ""):
    job = LibraryDigestJob.objects.select_related("library").get(pk=job_id)
    library = job.library
    try:
        normalized_target_path = _normalize_scope_path(target_path)
    except ValueError as exc:
        job.status = LibraryDigestJob.STATUS_ERROR
        job.finished_at = timezone.now()
        job.last_error = str(exc)
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        return {"job_id": job.id, "status": job.status, "error": job.last_error, "target_path": target_path}

    merged_media_duplicate_count = _dedupe_media_file_records(library, normalized_target_path)
    merged_track_duplicate_count = _dedupe_track_records(library, normalized_target_path)
    merged_track_source_duplicate_count = _dedupe_track_source_metadata_records(library, normalized_target_path)
    merged_accessory_duplicate_count = _dedupe_accessory_file_records(library, normalized_target_path)
    merged_source_folder_duplicate_count = _dedupe_source_folder_records(library, normalized_target_path)
    if merged_source_folder_duplicate_count:
        logger.warning(
            "trive-up merged duplicate source folder records job=%s count=%s",
            job.id,
            merged_source_folder_duplicate_count,
        )
    if merged_media_duplicate_count:
        logger.warning(
            "trive-up merged duplicate media file records job=%s count=%s",
            job.id,
            merged_media_duplicate_count,
        )
    if merged_accessory_duplicate_count:
        logger.warning(
            "trive-up merged duplicate accessory file records job=%s count=%s",
            job.id,
            merged_accessory_duplicate_count,
        )
    if merged_track_duplicate_count:
        logger.warning(
            "trive-up merged duplicate track records job=%s count=%s",
            job.id,
            merged_track_duplicate_count,
        )
    if merged_track_source_duplicate_count:
        logger.warning(
            "trive-up merged duplicate track source metadata records job=%s count=%s",
            job.id,
            merged_track_source_duplicate_count,
        )
    media_file_ids = [
        str(media_file_id)
        for media_file_id in _library_digest_media_queryset(library, normalized_target_path).values_list("pk", flat=True)
    ]
    _initialise_library_digest_job(job, len(media_file_ids))

    try:
        if not media_file_ids:
            return _finalize_library_catalog(job.id, normalized_target_path, [])

        if not _bool_setting("TRIVER_DIGEST_PARALLEL_BATCHES", False):
            logger.warning(
                "trive-up running in conservative serial mode job=%s target_count=%s batch_size=%s",
                job.id,
                len(media_file_ids),
                _digest_batch_size(),
            )
            return _run_library_catalog_batches_sync(job.id, normalized_target_path, media_file_ids)

        batches = list(_chunked(media_file_ids, _digest_batch_size()))
        workflow = chord(
            group([process_library_digest_batch.s(job.id, media_file_batch) for media_file_batch in batches]),
            finalize_library_catalog.s(job.id, normalized_target_path),
        )

        try:
            finalizer_result = workflow.apply_async()
        except Exception:  # pragma: no cover - local fallback path
            logger.exception("trive-up failed to schedule parallel digest; running synchronously job=%s", job.id)
            return _run_library_catalog_batches_sync(job.id, normalized_target_path, media_file_ids)

        return {
            "library_id": library.id,
            "job_id": job.id,
            "target_count": len(media_file_ids),
            "batch_count": len(batches),
            "batch_size": _digest_batch_size(),
            "finalizer_task_id": finalizer_result.id,
            "status": job.status,
            "target_path": normalized_target_path,
        }
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("trive-up failed job=%s", job.id)
        LibraryDigestJob.objects.filter(pk=job.id).update(
            status=LibraryDigestJob.STATUS_ERROR,
            finished_at=timezone.now(),
            last_error=str(exc),
            updated_at=timezone.now(),
        )
        return {"job_id": job.id, "status": LibraryDigestJob.STATUS_ERROR, "error": str(exc)}
