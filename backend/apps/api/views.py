import mimetypes
import errno
import hashlib
import logging
import os
from pathlib import Path
import random
import re
import json
import datetime
import math
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import time
import threading
import uuid
from array import array
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.views.decorators.csrf import ensure_csrf_cookie, get_token
from django.http import FileResponse, Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as APIValidationError
from rest_framework.response import Response

from apps.api.serializers import (
    AccessoryFileSerializer,
    AlbumCardSerializer,
    AlbumSerializer,
    ArtistCardSerializer,
    ArtistSerializer,
    ArtistProfileImageSerializer,
    AutoImportSettingsSerializer,
    LibraryDigestErrorSerializer,
    LibrarySerializer,
    LibraryDigestJobSerializer,
    LibraryScanJobSerializer,
    LibraryScanSkipSerializer,
    MediaFileSerializer,
    MediaFileMetaValueSerializer,
    MetadataEnrichmentJobSerializer,
    MetaFieldDefinitionSerializer,
    MetaNormalizationRuleSerializer,
    RemoteMetadataSettingsSerializer,
    SourceFolderSerializer,
    SavedPlaylistSerializer,
    TrackDedupCandidateSerializer,
    TrackDedupJobSerializer,
    TrackCardSerializer,
    TrackSerializer,
    _enumerate_track_subtitle_streams,
    AlbumTagAssignmentSerializer,
    ArtistTagAssignmentSerializer,
    RegisterSerializer,
    TagDefinitionSerializer,
    TagValueSerializer,
    TrackTagAssignmentSerializer,
    TrackVersionGroupSerializer,
    TrackVersionMembershipSerializer,
    UserSerializer,
)
from apps.catalog.models import Album, Artist, ArtistProfileImage, MetadataEnrichmentJob, RemoteMetadataSettings, Track, TrackArtistCredit, TrackDedupCandidate, TrackDedupJob, TrackVersionCandidateDecision, TrackVersionGroup, TrackVersionMembership
from apps.catalog.models import MediaTransformJob, MetadataWritebackJob, TrackMetadataOverride, TrackSourceMetadata
from apps.catalog.remote_metadata import provider_settings_payload, settings_snapshot_from_env
from apps.catalog.tasks import run_dedup_candidate_scan, run_metadata_enrichment_job
from apps.core.models import OperationLog
from apps.library.models import AccessoryFile, AutoImportSettings, Library, LibraryDigestError, LibraryDigestJob, LibraryScanJob, LibraryScanSkip, MediaFile, SourceFolder
from apps.library.models import DEFAULT_META_SEARCH_GROUPS, MediaFileMetaValue, MetaFieldDefinition, MetaNormalizationRule
from apps.library.models import SUPPORTED_AUDIO_EXTENSIONS, SUPPORTED_VIDEO_EXTENSIONS
from apps.library.models import SavedPlaylist, SavedPlaylistEntry
from apps.library.tasks import _bootstrap_default_meta_registry, _get_or_create_default_library, _infer_video_path_metadata, _resolve_existing_media_path, _sync_triver_interpretation, build_library_catalog, classic_import_sources_payload, discover_library, rescan_library_catalog, run_auto_import_monitor, run_classic_import
from apps.tags.models import AlbumTagAssignment, ArtistTagAssignment, TagDefinition, TagValue, TrackTagAssignment, VideoCurationSettings
from utils.drf_extensions import BidirectionalRelationMixin, LoggedViewSetMixin

logger = logging.getLogger(__name__)


EXPLORER_SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa", ".ttml", ".dfxp", ".smi", ".sub", ".idx", ".sup"}
FILE_EXPLORER_ROOTS = ("trive-In", "trive-Up", "trive-Out")
CLASSIC_EXPLORER_ROOT_PREFIX = "classic:"
USER_AVATAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
USER_AVATAR_MAX_BYTES = 5 * 1024 * 1024


def _wants_card_payload(request):
    view = str(request.query_params.get("view") or request.query_params.get("payload") or "").strip().lower()
    lite = str(request.query_params.get("lite") or "").strip().lower()
    return view in {"card", "cards", "tv"} or lite in {"1", "true", "yes", "on"}


def _user_avatar_root():
    root = Path(getattr(settings, "TRIVER_USER_AVATAR_ROOT", "")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _user_avatar_file(user):
    if not getattr(user, "pk", None):
        return None
    root = _user_avatar_root()
    for candidate in root.glob(f"{user.pk}.*"):
        if candidate.is_file():
            return candidate
    return None


def _delete_user_avatar(user):
    if not getattr(user, "pk", None):
        return
    root = _user_avatar_root()
    for candidate in root.glob(f"{user.pk}.*"):
        if candidate.is_file():
            candidate.unlink(missing_ok=True)


def _normalize_relative_target_path(raw_path):
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


def _normalize_upload_relative_path(raw_path):
    normalized = _normalize_relative_target_path(raw_path)
    if not normalized:
        raise ValueError("Invalid upload filename.")
    return normalized


def _upload_quarantine_root():
    root = Path(settings.TRIVER_DUMP_ROOT).resolve() / "upload-quarantine"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _clamav_scan_file(file_path):
    if not getattr(settings, "TRIVER_CLAMAV_ENABLED", True):
        return {"status": "skipped", "scanner": "clamav"}

    host = getattr(settings, "TRIVER_CLAMAV_HOST", "triver-clamav")
    port = int(getattr(settings, "TRIVER_CLAMAV_PORT", 3310))
    chunk_size = int(getattr(settings, "TRIVER_UPLOAD_SCAN_CHUNK_BYTES", 1024 * 1024))

    try:
        with socket.create_connection((host, port), timeout=45) as sock:
            sock.settimeout(120)
            sock.sendall(b"zINSTREAM\0")
            with open(file_path, "rb") as handle:
                while True:
                    chunk = handle.read(chunk_size)
                    if not chunk:
                        break
                    sock.sendall(struct.pack(">I", len(chunk)))
                    sock.sendall(chunk)
            sock.sendall(struct.pack(">I", 0))
            response = sock.recv(4096).decode("utf-8", errors="replace").strip()
    except OSError as exc:
        raise RuntimeError(f"Antivirus scan unavailable: {exc}") from exc

    if " FOUND" in response or response.endswith("FOUND"):
        raise ValueError(f"Antivirus blocked upload: {response}")
    if " OK" in response or response.endswith("OK"):
        return {"status": "ok", "scanner": "clamav", "response": response}
    raise RuntimeError(f"Antivirus scan failed: {response or 'empty response'}")


def _move_scanned_upload(source_path, destination_path):
    try:
        os.replace(source_path, destination_path)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise

    try:
        shutil.copy2(source_path, destination_path)
    except Exception:
        if destination_path.exists() and destination_path.is_file():
            destination_path.unlink(missing_ok=True)
        raise
    source_path.unlink(missing_ok=True)


def _resolve_scoped_root_path(root_path, target_path=""):
    resolved_root = Path(root_path).resolve()
    if not target_path:
        return resolved_root

    scoped_path = (resolved_root / target_path).resolve()
    if scoped_path != resolved_root and resolved_root not in scoped_path.parents:
        raise ValueError("Target path escapes library root.")
    return scoped_path


def _path_matches_scope(relative_path, target_path=""):
    if not target_path:
        return True
    normalized_relative = str(relative_path or "")
    return normalized_relative == target_path or normalized_relative.startswith(f"{target_path}/")


def _request_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _requested_target_path(request):
    payload = getattr(request, "data", {}) or {}
    return _normalize_relative_target_path(payload.get("target_path") or "")


def _isoformat_timestamp(stat_result):
    try:
        return datetime.datetime.fromtimestamp(stat_result.st_mtime, tz=datetime.timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return ""


def _classify_browser_entry(path):
    extension = path.suffix.lower()
    if path.is_dir():
        return {"entry_type": "directory", "media_kind": "", "is_subtitle": False, "display_type": "Folder"}
    if extension in SUPPORTED_VIDEO_EXTENSIONS:
        return {"entry_type": "file", "media_kind": "video", "is_subtitle": False, "display_type": "Video File"}
    if extension in SUPPORTED_AUDIO_EXTENSIONS:
        return {"entry_type": "file", "media_kind": "audio", "is_subtitle": False, "display_type": "Audio File"}
    if extension in EXPLORER_SUBTITLE_EXTENSIONS:
        return {"entry_type": "file", "media_kind": "", "is_subtitle": True, "display_type": "Subtitle File"}
    return {"entry_type": "file", "media_kind": "", "is_subtitle": False, "display_type": "File"}


def _file_explorer_roots_payload():
    roots = [{"key": name, "label": name, "kind": "trive"} for name in FILE_EXPLORER_ROOTS]
    for source in classic_import_sources_payload().get("sources", []):
        roots.append({
            "key": f"{CLASSIC_EXPLORER_ROOT_PREFIX}{source.get('key')}",
            "label": f"Classic: {source.get('label') or source.get('key')}",
            "kind": "classic",
            "exists": bool(source.get("exists")),
            "readable": bool(source.get("readable")),
        })
    return roots


def _classic_explorer_source(root_name):
    source_key = str(root_name or "")[len(CLASSIC_EXPLORER_ROOT_PREFIX):].strip()
    if not source_key:
        return None
    for source in classic_import_sources_payload().get("sources", []):
        if source.get("key") == source_key:
            return source
    return None


def _classic_catalog_relative_path(root_name, relative_path=""):
    source = _classic_explorer_source(root_name)
    if not source:
        return ""
    prefix = str(source.get("relative_prefix") or "").strip().strip("/")
    normalized_path = str(relative_path or "").strip().strip("/")
    return f"{prefix}/{normalized_path}" if normalized_path else prefix


def _resolve_file_explorer_root(library, root_name="trive-In"):
    normalized_root = str(root_name or "trive-In").strip()
    if normalized_root.startswith(CLASSIC_EXPLORER_ROOT_PREFIX):
        source = _classic_explorer_source(normalized_root)
        if not source:
            raise ValueError("Invalid classic import root.")
        return normalized_root, Path(source.get("container_path") or "")

    if normalized_root not in FILE_EXPLORER_ROOTS:
        raise ValueError("Invalid explorer root.")

    if normalized_root == "trive-In":
        return normalized_root, Path(library.ingest_path)
    if normalized_root == "trive-Up":
        return normalized_root, Path(library.digest_path)
    return normalized_root, Path(library.normalize_path)


def _build_file_explorer_payload(library, root_name="trive-In", relative_path=""):
    normalized_root, root_path = _resolve_file_explorer_root(library, root_name)
    current_path = _resolve_scoped_root_path(root_path, relative_path)
    root_exists = root_path.exists() and root_path.is_dir()
    if not root_exists and not relative_path:
        return {
            "library_id": library.id,
            "root": normalized_root,
            "roots": _file_explorer_roots_payload(),
            "relative_path": "",
            "parent_path": "",
            "breadcrumbs": [{"label": normalized_root, "relative_path": ""}],
            "entries": [],
        }
    if not current_path.exists():
        raise FileNotFoundError(f"Path not found inside {normalized_root}: {relative_path or '/'}")
    if not current_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {relative_path}")

    entries = []
    with os.scandir(current_path) as iterator:
        for entry in iterator:
            entry_path = Path(entry.path)
            entry_relative_path = entry_path.relative_to(root_path).as_posix()
            entry_kind = _classify_browser_entry(entry_path)
            try:
                stat_result = entry.stat(follow_symlinks=False)
            except OSError:
                continue

            entries.append({
                "name": entry.name,
                "entry_type": entry_kind["entry_type"],
                "relative_path": entry_relative_path,
                "extension": entry_path.suffix.lower().lstrip("."),
                "size": None if entry.is_dir(follow_symlinks=False) else stat_result.st_size,
                "modified_at": _isoformat_timestamp(stat_result),
                "media_kind": entry_kind["media_kind"],
                "is_subtitle": entry_kind["is_subtitle"],
                "display_type": entry_kind["display_type"],
            })

    entries.sort(key=lambda item: (0 if item["entry_type"] == "directory" else 1, item["name"].lower()))
    _attach_catalog_matches_to_explorer_entries(library, normalized_root, entries)

    breadcrumbs = [{"label": normalized_root, "relative_path": ""}]
    if relative_path:
        parts = Path(relative_path).parts
        current_parts = []
        for part in parts:
            current_parts.append(part)
            breadcrumbs.append({
                "label": part,
                "relative_path": Path(*current_parts).as_posix(),
            })

    parent_path = ""
    if relative_path:
        parent_path = Path(relative_path).parent.as_posix()
        if parent_path == ".":
            parent_path = ""

    return {
        "library_id": library.id,
        "root": normalized_root,
        "roots": _file_explorer_roots_payload(),
        "relative_path": relative_path,
        "parent_path": parent_path,
        "breadcrumbs": breadcrumbs,
        "entries": entries,
    }


def _attach_catalog_matches_to_explorer_entries(library, root_name, entries):
    file_entries = [entry for entry in entries if entry.get("entry_type") == "file"]
    if not file_entries:
        return

    relative_paths = [entry["relative_path"] for entry in file_entries if entry.get("relative_path")]
    if not relative_paths:
        return

    media_files = MediaFile.objects.filter(library=library, removed_at__isnull=True)
    if root_name == "trive-Up":
        media_files = media_files.filter(Q(digest_relative_path__in=relative_paths) | Q(relative_path__in=relative_paths))
    elif root_name == "trive-In":
        media_files = media_files.filter(relative_path__in=relative_paths)
    elif root_name.startswith(CLASSIC_EXPLORER_ROOT_PREFIX):
        prefixed_paths = [_classic_catalog_relative_path(root_name, path) for path in relative_paths]
        media_files = media_files.filter(relative_path__in=prefixed_paths)
    else:
        return

    media_by_path = {}
    media_by_id = {}
    for media_file in media_files:
        if media_file.relative_path:
            media_by_path.setdefault(media_file.relative_path, media_file)
        if media_file.digest_relative_path:
            media_by_path.setdefault(media_file.digest_relative_path, media_file)
        media_by_id[media_file.pk] = media_file

    tracks_by_media_id = {
        track.primary_file_id: track
        for track in Track.objects.filter(primary_file_id__in=media_by_id.keys()).select_related("primary_file")
    }

    for entry in file_entries:
        lookup_path = entry.get("relative_path")
        if root_name.startswith(CLASSIC_EXPLORER_ROOT_PREFIX):
            lookup_path = _classic_catalog_relative_path(root_name, lookup_path)
        media_file = media_by_path.get(lookup_path)
        if not media_file:
            entry["media_file_id"] = ""
            entry["track_id"] = ""
            entry["track_title"] = ""
            continue
        track = tracks_by_media_id.get(media_file.pk)
        entry["media_file_id"] = str(media_file.pk)
        entry["track_id"] = str(track.pk) if track else ""
        entry["track_title"] = track.canonical_title if track else ""


def _explorer_media_files_for_path(library, root_name, relative_path):
    normalized_path = str(relative_path or "").strip().strip("/")
    queryset = MediaFile.objects.filter(library=library, removed_at__isnull=True)

    if root_name == "trive-Up":
        if normalized_path:
            prefix = f"{normalized_path}/"
            queryset = queryset.filter(
                Q(digest_relative_path=normalized_path)
                | Q(digest_relative_path__startswith=prefix)
                | Q(relative_path=normalized_path)
                | Q(relative_path__startswith=prefix)
            )
        return queryset

    if root_name == "trive-In":
        if normalized_path:
            prefix = f"{normalized_path}/"
            queryset = queryset.filter(Q(relative_path=normalized_path) | Q(relative_path__startswith=prefix))
        return queryset

    if root_name.startswith(CLASSIC_EXPLORER_ROOT_PREFIX):
        catalog_path = _classic_catalog_relative_path(root_name, normalized_path)
        if catalog_path:
            prefix = f"{catalog_path}/"
            queryset = queryset.filter(Q(relative_path=catalog_path) | Q(relative_path__startswith=prefix))
        else:
            queryset = queryset.none()
        return queryset

    return queryset.none()


def _path_match_query(field_name, relative_path):
    normalized_path = str(relative_path or "").strip().strip("/")
    if not normalized_path:
        return Q(pk__in=[])
    return Q(**{field_name: normalized_path}) | Q(**{f"{field_name}__startswith": f"{normalized_path}/"})


def _cleanup_catalog_after_explorer_delete(library, root_name, relative_path):
    normalized_path = str(relative_path or "").strip().strip("/")
    if not normalized_path:
        return {
            "tracks": 0,
            "media_files": 0,
            "accessory_files": 0,
            "source_folders": 0,
        }

    if root_name == "trive-In":
        media_files = MediaFile.objects.filter(
            library=library,
            storage_stage=MediaFile.STORAGE_STAGE_TRIV_IN,
        ).filter(_path_match_query("relative_path", normalized_path))
        accessory_files = AccessoryFile.objects.filter(library=library).filter(_path_match_query("relative_path", normalized_path))
        source_folders = SourceFolder.objects.filter(library=library).filter(_path_match_query("relative_path", normalized_path))
    elif root_name == "trive-Up":
        media_files = MediaFile.objects.filter(
            library=library,
            storage_stage=MediaFile.STORAGE_STAGE_TRIV_UP,
        ).filter(
            _path_match_query("digest_relative_path", normalized_path)
            | _path_match_query("relative_path", normalized_path)
        )
        accessory_files = AccessoryFile.objects.filter(library=library).filter(_path_match_query("relative_path", normalized_path))
        source_folders = SourceFolder.objects.none()
    elif root_name.startswith(CLASSIC_EXPLORER_ROOT_PREFIX):
        catalog_path = _classic_catalog_relative_path(root_name, normalized_path)
        media_files = MediaFile.objects.filter(library=library).filter(_path_match_query("relative_path", catalog_path))
        accessory_files = AccessoryFile.objects.filter(library=library).filter(_path_match_query("relative_path", catalog_path))
        source_folders = SourceFolder.objects.filter(library=library).filter(_path_match_query("relative_path", catalog_path))
    else:
        media_files = MediaFile.objects.none()
        accessory_files = AccessoryFile.objects.none()
        source_folders = SourceFolder.objects.none()

    media_file_ids = list(media_files.values_list("pk", flat=True))
    with transaction.atomic():
        tracks_deleted = Track.objects.filter(primary_file_id__in=media_file_ids).delete()[0] if media_file_ids else 0
        media_files_deleted = MediaFile.objects.filter(pk__in=media_file_ids).delete()[0] if media_file_ids else 0
        accessory_files_deleted = accessory_files.delete()[0]
        source_folders_deleted = source_folders.delete()[0]

    return {
        "tracks": tracks_deleted,
        "media_files": media_files_deleted,
        "accessory_files": accessory_files_deleted,
        "source_folders": source_folders_deleted,
    }


@ensure_csrf_cookie
def csrf_token_view(request):
    return JsonResponse({"csrfToken": get_token(request)})


class AuthViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        if not getattr(request.user, "is_authenticated", False):
            return Response({"authenticated": False, "user": None})
        return Response({"authenticated": True, "user": UserSerializer(request.user).data})

    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        username = str(request.data.get("username") or "").strip()
        password = str(request.data.get("password") or "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"detail": "Credenziali non valide."}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        return Response({"authenticated": True, "user": UserSerializer(user).data})

    @action(detail=False, methods=["post"], url_path="logout")
    def logout(self, request):
        logout(request)
        return Response({"authenticated": False, "user": None})

    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response({"authenticated": True, "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get", "post"], url_path="users")
    def users(self, request):
        if not getattr(request.user, "is_authenticated", False):
            return Response({"detail": "Credenziali richieste."}, status=status.HTTP_403_FORBIDDEN)
        if not (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)):
            return Response({"detail": "Permessi admin richiesti."}, status=status.HTTP_403_FORBIDDEN)
        if request.method == "POST":
            serializer = RegisterSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            try:
                validate_password(serializer.validated_data["password"])
            except ValidationError as error:
                return Response({"detail": list(error.messages)}, status=status.HTTP_400_BAD_REQUEST)
            is_staff = _request_bool(request.data.get("is_staff"))
            is_superuser = _request_bool(request.data.get("is_superuser"))
            if (is_staff or is_superuser) and not getattr(request.user, "is_superuser", False):
                return Response({"detail": "Solo un superuser puo' creare utenti admin."}, status=status.HTTP_403_FORBIDDEN)
            user = serializer.save()
            update_fields = []
            if is_staff:
                user.is_staff = True
                update_fields.append("is_staff")
            if is_superuser:
                user.is_superuser = True
                user.is_staff = True
                update_fields.extend(["is_superuser", "is_staff"])
            if update_fields:
                user.save(update_fields=sorted(set(update_fields)))
            return Response({"user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)
        users = get_user_model().objects.order_by("username", "id")
        return Response(UserSerializer(users, many=True).data)

    @action(detail=False, methods=["get"], url_path="directory")
    def directory(self, request):
        if not getattr(request.user, "is_authenticated", False):
            return Response({"detail": "Credenziali richieste."}, status=status.HTTP_403_FORBIDDEN)
        users = get_user_model().objects.filter(is_active=True).order_by("username", "id")
        return Response(UserSerializer(users, many=True).data)

    @action(detail=False, methods=["post", "delete"], url_path="me/avatar")
    def avatar(self, request):
        if not getattr(request.user, "is_authenticated", False):
            return Response({"detail": "Credenziali richieste."}, status=status.HTTP_403_FORBIDDEN)

        if request.method.lower() == "delete":
            _delete_user_avatar(request.user)
            return Response({"authenticated": True, "user": UserSerializer(request.user).data})

        upload = request.FILES.get("avatar")
        if upload is None:
            return Response({"detail": "File avatar mancante."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > USER_AVATAR_MAX_BYTES:
            return Response({"detail": "Avatar troppo grande: massimo 5 MB."}, status=status.HTTP_400_BAD_REQUEST)

        extension = Path(upload.name or "").suffix.lower()
        if extension == ".jpeg":
            extension = ".jpg"
        if extension not in USER_AVATAR_EXTENSIONS:
            return Response({"detail": "Formato avatar non supportato."}, status=status.HTTP_400_BAD_REQUEST)

        _delete_user_avatar(request.user)
        target_path = _user_avatar_root() / f"{request.user.pk}{extension}"
        with target_path.open("wb") as destination:
            for chunk in upload.chunks():
                destination.write(chunk)

        return Response({"authenticated": True, "user": UserSerializer(request.user).data})

    @action(detail=False, methods=["get"], url_path="me/avatar/image")
    def avatar_image(self, request):
        if not getattr(request.user, "is_authenticated", False):
            return Response({"detail": "Credenziali richieste."}, status=status.HTTP_403_FORBIDDEN)
        requested_user_id = request.query_params.get("user_id") or getattr(request.user, "pk", None)
        user_model = get_user_model()
        try:
            target_user = user_model.objects.get(pk=requested_user_id, is_active=True)
        except user_model.DoesNotExist:
            raise Http404("Avatar non trovato.")

        avatar_file = _user_avatar_file(target_user)
        if not avatar_file:
            raise Http404("Avatar non trovato.")
        content_type = mimetypes.guess_type(avatar_file.name)[0] or "application/octet-stream"
        return FileResponse(avatar_file.open("rb"), content_type=content_type)

    @action(detail=False, methods=["post"], url_path=r"users/(?P<user_id>[^/.]+)/password")
    def set_user_password(self, request, user_id=None):
        if not getattr(request.user, "is_authenticated", False):
            return Response({"detail": "Credenziali richieste."}, status=status.HTTP_403_FORBIDDEN)
        if not (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)):
            return Response({"detail": "Permessi admin richiesti."}, status=status.HTTP_403_FORBIDDEN)

        user_model = get_user_model()
        try:
            target_user = user_model.objects.get(pk=user_id)
        except user_model.DoesNotExist:
            return Response({"detail": "Utente non trovato."}, status=status.HTTP_404_NOT_FOUND)

        if getattr(target_user, "is_superuser", False) and not getattr(request.user, "is_superuser", False):
            return Response({"detail": "Solo un superuser puo' cambiare la password di un superuser."}, status=status.HTTP_403_FORBIDDEN)

        password = str(request.data.get("password") or "")
        if len(password) < 8:
            return Response({"detail": "La password deve avere almeno 8 caratteri."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(password, user=target_user)
        except ValidationError as error:
            return Response({"detail": list(error.messages)}, status=status.HTTP_400_BAD_REQUEST)

        target_user.set_password(password)
        target_user.save(update_fields=["password"])
        return Response({"user": UserSerializer(target_user).data})


class SystemMaintenanceViewSet(viewsets.ViewSet):

    def _reset_paths(self):
        digest_root = Path(settings.TRIVER_DIGEST_ROOT).resolve()
        ingest_root = Path(settings.TRIVER_INGEST_ROOT).resolve()
        unsafe_roots = {Path("/").resolve(), Path("/srv").resolve(), Path("/srv/triver").resolve()}

        if digest_root.name != "trive-Up":
            raise ValueError(f"Digest root non sicura per reset: {digest_root}")
        if ingest_root.name != "trive-In":
            raise ValueError(f"Ingest root non sicura per reset: {ingest_root}")
        if digest_root in unsafe_roots or ingest_root in unsafe_roots:
            raise ValueError(f"Root non sicura per reset: digest={digest_root}, ingest={ingest_root}")

        moved = []
        digest_root.mkdir(parents=True, exist_ok=True)
        ingest_root.mkdir(parents=True, exist_ok=True)

        for source_path in sorted(digest_root.rglob("*")):
            if source_path.is_dir():
                continue
            relative_path = source_path.relative_to(digest_root)
            destination_relative_path = (
                Path(*relative_path.parts[1:])
                if relative_path.parts and relative_path.parts[0] == "Unrevisioned"
                else relative_path
            )
            if not destination_relative_path.parts:
                destination_relative_path = Path(source_path.name)
            destination_path = ingest_root / destination_relative_path
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            final_destination = destination_path
            if destination_path.exists():
                source_size = source_path.stat().st_size
                destination_size = destination_path.stat().st_size
                if source_size == destination_size:
                    source_path.unlink()
                    moved.append({
                        "source": str(source_path),
                        "destination": str(destination_path),
                        "action": "kept_existing",
                    })
                    continue
                counter = 1
                while True:
                    candidate = destination_path.with_name(
                        f"{destination_path.stem}__reset_{counter:03d}{destination_path.suffix}"
                    )
                    if not candidate.exists():
                        final_destination = candidate
                        break
                    counter += 1
            shutil.move(str(source_path), str(final_destination))
            moved.append({
                "source": str(source_path),
                "destination": str(final_destination),
                "action": "moved",
            })

        removed = []
        for child in digest_root.iterdir():
            removed.append(child.name)
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
        return {
            "root": str(digest_root),
            "rewound_to": str(ingest_root),
            "rewound_count": len(moved),
            "rewound": moved[:200],
            "rewound_truncated": len(moved) > 200,
            "removed_count": len(removed),
            "removed": removed[:200],
            "truncated": len(removed) > 200,
        }

    @action(detail=False, methods=["post"], url_path="reset-database")
    def reset_database(self, request):
        confirmation = str(request.data.get("confirmation", "")).strip()
        if confirmation != "RESET DATABASE":
            return Response(
                {"detail": "Conferma richiesta: RESET DATABASE"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            reset_paths = self._reset_paths()
        except Exception as exc:
            return Response(
                {
                    "detail": "Reset database fallito durante la fase filesystem.",
                    "stage": "filesystem",
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            with transaction.atomic():
                delete_plan = [
                    TrackTagAssignment,
                    TagValue,
                    TagDefinition,
                    SavedPlaylistEntry,
                    SavedPlaylist,
                    TrackVersionMembership,
                    TrackVersionGroup,
                    MetadataWritebackJob,
                    MediaTransformJob,
                    TrackMetadataOverride,
                    TrackSourceMetadata,
                    TrackArtistCredit,
                    Track,
                    Album,
                    ArtistProfileImage,
                    Artist,
                    LibraryDigestError,
                    LibraryScanSkip,
                    AccessoryFile,
                    MediaFileMetaValue,
                    MediaFile,
                    SourceFolder,
                    LibraryScanJob,
                    LibraryDigestJob,
                    Library,
                    MetaNormalizationRule,
                    MetaFieldDefinition,
                    OperationLog,
                ]
                deleted = {}
                for model in delete_plan:
                    deleted[model._meta.label] = model.objects.all().delete()[0]
                _bootstrap_default_meta_registry()
                library = _get_or_create_default_library()
        except Exception as exc:
            return Response(
                {
                    "detail": "Reset database fallito durante la fase database.",
                    "stage": "database",
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                    "cleared_digest_root": reset_paths,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "status": "reset",
            "library": str(library.pk),
            "deleted": deleted,
            "cleared_digest_root": reset_paths,
        })

    @action(detail=False, methods=["post"], url_path="resync-catalog")
    def resync_catalog(self, request):
        library_id = request.data.get("library") or request.query_params.get("library")
        media_files = (
            MediaFile.objects
            .filter(primary_for_tracks__isnull=False)
            .prefetch_related("meta_values__field", "primary_for_tracks")
            .distinct()
            .order_by("pk")
        )
        if library_id:
            media_files = media_files.filter(library_id=library_id)

        synced_media_files = 0
        synced_tracks = 0
        errors = []

        for media_file in media_files.iterator(chunk_size=200):
            try:
                _sync_triver_interpretation(media_file)
                refreshed_media_file = (
                    MediaFile.objects
                    .prefetch_related("meta_values__field", "primary_for_tracks__artist_credits__artist")
                    .get(pk=media_file.pk)
                )
                updated_track_ids = _sync_catalog_from_media_metadata(
                    refreshed_media_file,
                    _metadata_from_media_file(refreshed_media_file),
                    user=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
                    path=request.path,
                    http_method=request.method,
                )
                synced_media_files += 1
                synced_tracks += len(updated_track_ids)
            except Exception as exc:
                errors.append({
                    "media_file_id": str(media_file.pk),
                    "filename": media_file.filename,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                })

        return Response({
            "status": "resynced",
            "library": str(library_id) if library_id else None,
            "synced_media_files": synced_media_files,
            "synced_tracks": synced_tracks,
            "error_count": len(errors),
            "errors": errors[:50],
            "errors_truncated": len(errors) > 50,
        })


def _normalize_meta_name(value):
    return "".join(character for character in str(value or "") if character.isalnum()).lower()


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


def _source_metadata_label(source_family, source_name):
    normalized_source_name = str(source_name or "").upper()
    return (
        SOURCE_METADATA_LABELS.get(str(source_family or "").lower(), {}).get(normalized_source_name)
        or SOURCE_METADATA_LABELS.get("vorbis", {}).get(normalized_source_name)
        or ""
    )


def _metadata_payload_from_request(request):
    payload = request.data or {}
    metadata = payload.get("metadata", payload)
    if not isinstance(metadata, dict):
        raise ValueError("`metadata` deve essere un oggetto campo -> valore/i.")
    return metadata


def _coerce_metadata_values(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _first_metadata_value(metadata, field_name):
    normalized_target = _normalize_meta_name(field_name)
    for key, value in metadata.items():
        if _normalize_meta_name(key) == normalized_target:
            values = _coerce_metadata_values(value)
            return values[0] if values else ""
    return None


def _metadata_values(metadata, field_name):
    normalized_target = _normalize_meta_name(field_name)
    for key, value in metadata.items():
        if _normalize_meta_name(key) == normalized_target:
            return _coerce_metadata_values(value)
    return None


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


def _metadata_from_media_file(media_file):
    by_source = {"user": {}, "triver": {}}
    values = (
        media_file.meta_values
        .select_related("field")
        .filter(source_family__in=["user", "triver"])
        .order_by("field__name", "value_order", "id")
    )
    for value in values:
        bucket = by_source[value.source_family].setdefault(value.field.name, [])
        bucket.append(value.value_text)
    metadata = dict(by_source["triver"])
    metadata.update(by_source["user"])
    return metadata


def _parse_positive_int(value):
    if value in {None, ""}:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _parse_year(value):
    if value in {None, ""}:
        return None
    match = re.search(r"\d{4}", str(value))
    return int(match.group(0)) if match else None


def _get_or_create_meta_field(field_name):
    normalized_name = _normalize_meta_name(field_name)
    if not normalized_name:
        raise ValueError("Nome campo metadata vuoto.")
    field = MetaFieldDefinition.objects.filter(normalized_name=normalized_name).first()
    if field:
        return field
    return MetaFieldDefinition.objects.create(
        name=str(field_name).strip(),
        normalized_name=normalized_name,
        source_family="user",
        is_user_defined=True,
        is_indexed=True,
    )


def _get_or_create_catalog_artist(name):
    clean_name = str(name or "").strip()
    if not clean_name:
        return None
    artist, _created = Artist.objects.get_or_create(
        name=clean_name,
        sort_name=clean_name.lower(),
        defaults={"triver_notes": ""},
    )
    return artist


def _get_or_create_catalog_album(title, *, release_year=None):
    clean_title = str(title or "").strip()
    if not clean_title:
        return None
    queryset = Album.objects.filter(
        title=clean_title,
        sort_title=clean_title.lower(),
    ).order_by("release_year", "created_at", "pk")

    if release_year is not None:
        exact_year_match = queryset.filter(release_year=release_year).first()
        if exact_year_match:
            album = exact_year_match
        else:
            album = queryset.first()
    else:
        album = queryset.first()

    if album is None:
        album = Album.objects.create(
            title=clean_title,
            sort_title=clean_title.lower(),
            release_year=release_year,
        )

    if release_year and album.release_year != release_year:
        album.release_year = release_year
        album.save(update_fields=["release_year", "updated_at"])
    return album


def _sync_track_artist_credit_role(track, role, artist_names):
    TrackArtistCredit.objects.filter(track=track, role=role).delete()
    for index, artist_name in enumerate(artist_names or []):
        artist = _get_or_create_catalog_artist(artist_name)
        if not artist:
            continue
        TrackArtistCredit.objects.update_or_create(
            track=track,
            artist=artist,
            role=role,
            credit_order=index,
            defaults={
                "credited_name": artist.name,
                "is_primary": role == TrackArtistCredit.ROLE_PRIMARY and index == 0,
            },
        )


def _sync_catalog_from_media_metadata(media_file, metadata, *, user=None, path="", http_method=""):
    tracks = list(media_file.primary_for_tracks.select_related("album").prefetch_related("artist_credits__artist").all())
    if not tracks:
        return []

    title = _first_metadata_value(metadata, "TrackName")
    album_title = _first_metadata_value(metadata, "Album")
    artist_names = _split_logical_artists(_metadata_values(metadata, "Artist"))
    contributor_role_fields = {
        TrackArtistCredit.ROLE_COMPOSER: ("Composer",),
        TrackArtistCredit.ROLE_CONDUCTOR: ("Conductor",),
        TrackArtistCredit.ROLE_PERFORMER: ("Executor", "BandName", "EnsembleName", "OrchestraName"),
    }
    contributor_names_by_role = {}
    contributor_roles_present = set()
    for role, field_names in contributor_role_fields.items():
        role_names = []
        for field_name in field_names:
            values = _metadata_values(metadata, field_name)
            if values is None:
                continue
            contributor_roles_present.add(role)
            role_names.extend(_split_logical_artists(values))
        if role in contributor_roles_present:
            contributor_names_by_role[role] = role_names
    track_number = _parse_positive_int(_first_metadata_value(metadata, "TrackNumber"))
    disc_number = _parse_positive_int(_first_metadata_value(metadata, "DiscNumber"))
    release_year = _parse_year(_first_metadata_value(metadata, "ReleaseDate"))
    synced = []

    for track in tracks:
        update_fields = set()
        if title is not None:
            track.canonical_title = title or media_file.filename
            track.canonical_sort_title = track.canonical_title.lower()
            update_fields.update(["canonical_title", "canonical_sort_title"])
        if album_title is not None:
            track.album = _get_or_create_catalog_album(album_title, release_year=release_year) if album_title else None
            update_fields.add("album")
        if track_number is not None:
            track.track_number = track_number
            update_fields.add("track_number")
        if disc_number is not None:
            track.disc_number = disc_number
            update_fields.add("disc_number")
        if release_year is not None:
            track.release_year = release_year
            update_fields.add("release_year")
        if update_fields or artist_names is not None:
            track.metadata_state = Track.STATE_MODIFIED
            update_fields.add("metadata_state")

        if update_fields:
            track.save(
                user=user,
                path=path,
                http_method=http_method,
                update_fields=[*update_fields, "updated_at"],
            )

        if artist_names is not None:
            _sync_track_artist_credit_role(track, TrackArtistCredit.ROLE_PRIMARY, artist_names)

        for role in contributor_roles_present:
            _sync_track_artist_credit_role(track, role, contributor_names_by_role.get(role, []))

        synced.append(str(track.pk))
    return synced


def _set_media_file_metadata(media_file, metadata, *, user=None, path="", http_method=""):
    updated_fields = []
    for field_name, raw_values in metadata.items():
        field_name = str(field_name).strip()
        if not field_name:
            continue
        field = _get_or_create_meta_field(field_name)
        values = _coerce_metadata_values(raw_values)
        MediaFileMetaValue.objects.filter(
            media_file=media_file,
            field=field,
            source_family__in=["user", "triver"],
        ).delete()
        for index, value_text in enumerate(values):
            MediaFileMetaValue.objects.create(
                media_file=media_file,
                field=field,
                source_family="user",
                source_name=field.name,
                source_name_normalized=field.normalized_name,
                value_text=value_text,
                value_order=index,
                is_primary=index == 0,
            )
        updated_fields.append({
            "field": field.name,
            "values": values,
        })

    if updated_fields:
        media_file.status = MediaFile.STATUS_MODIFIED
        media_file.workflow_state = MediaFile.WORKFLOW_REVISED
        media_file.save(
            user=user,
            path=path,
            http_method=http_method,
            update_fields=["status", "workflow_state", "updated_at"],
        )
    _sync_triver_interpretation(media_file)
    media_file = MediaFile.objects.prefetch_related("meta_values__field", "primary_for_tracks").get(pk=media_file.pk)
    synced_tracks = _sync_catalog_from_media_metadata(
        media_file,
        _metadata_from_media_file(media_file),
        user=user,
        path=path,
        http_method=http_method,
    )
    return updated_fields, synced_tracks


def _album_metadata_summary(album):
    rows = {}
    media_files = (
        MediaFile.objects
        .filter(primary_for_tracks__album=album)
        .distinct()
        .prefetch_related("meta_values__field", "primary_for_tracks")
        .order_by("relative_path", "filename")
    )

    for media_file in media_files:
        media_payload = {
            "id": str(media_file.pk),
            "filename": media_file.filename,
            "display_path": media_file.display_path,
            "tracks": [
                {
                    "id": str(track.pk),
                    "canonical_title": track.canonical_title,
                    "primary_file": str(media_file.pk),
                }
                for track in media_file.primary_for_tracks.all()
            ],
        }
        for meta_value in media_file.meta_values.all():
            is_source_metadata = meta_value.source_family not in {"user", "triver"}
            source_label = _source_metadata_label(meta_value.source_family, meta_value.source_name) if is_source_metadata else ""
            field_name = meta_value.source_name if is_source_metadata else meta_value.field.name
            display_field = " / ".join(
                item for item in [
                    meta_value.source_family.upper() if is_source_metadata and meta_value.source_family else "",
                    field_name,
                    source_label,
                ]
                if item
            ) or field_name
            row = rows.setdefault(field_name, {
                "field": field_name,
                "display_field": display_field,
                "read_only": is_source_metadata,
                "source_family": meta_value.source_family if is_source_metadata else "",
                "source_name": meta_value.source_name if is_source_metadata else "",
                "source_label": source_label,
                "values": {},
            })
            value_key = meta_value.value_text or ""
            bucket = row["values"].setdefault(value_key, {
                "value": value_key,
                "media_files": [],
            })
            bucket["media_files"].append(media_payload)

    return [
        {
            "field": row["field"],
            "display_field": row.get("display_field", row["field"]),
            "read_only": row.get("read_only", False),
            "source_family": row.get("source_family", ""),
            "source_name": row.get("source_name", ""),
            "source_label": row.get("source_label", ""),
            "values": sorted(row["values"].values(), key=lambda item: item["value"].lower()),
        }
        for row in sorted(rows.values(), key=lambda item: item["field"].lower())
    ]


AUTO_VIDEO_METADATA_FIELDS = ("SeriesTitle", "SeasonNumber", "EpisodeNumber", "EpisodeTitle")


def _metadata_first_string(metadata, field_name):
    value = _first_metadata_value(metadata, field_name)
    return str(value or "").strip()


def _coerce_auto_metadata_items(raw_items):
    if not isinstance(raw_items, list):
        raise ValueError("`items` deve essere una lista di file con metadata.")

    items = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        track_id = str(raw_item.get("track_id") or "").strip()
        raw_metadata = raw_item.get("metadata") or {}
        if not track_id or not isinstance(raw_metadata, dict):
            continue

        metadata = {}
        for field_name in AUTO_VIDEO_METADATA_FIELDS:
            if field_name not in raw_metadata:
                continue
            values = _coerce_metadata_values(raw_metadata.get(field_name))
            if not values:
                continue
            if field_name in {"SeasonNumber", "EpisodeNumber"}:
                parsed_number = _parse_positive_int(values[0])
                if parsed_number is None:
                    raise ValueError(f"`{field_name}` deve contenere un numero.")
                metadata[field_name] = [str(parsed_number)]
            else:
                metadata[field_name] = [values[0]]

        if metadata:
            items.append({"track_id": track_id, "metadata": metadata})
    return items


def _track_auto_metadata_preview(track):
    media_file = track.primary_file
    existing = {field_name: "" for field_name in AUTO_VIDEO_METADATA_FIELDS}
    suggested = {field_name: "" for field_name in AUTO_VIDEO_METADATA_FIELDS}
    missing_fields = []

    if media_file:
        metadata = _metadata_from_media_file(media_file)
        existing = {
            field_name: _metadata_first_string(metadata, field_name)
            for field_name in AUTO_VIDEO_METADATA_FIELDS
        }
        if getattr(media_file, "media_kind", "audio") == "video":
            inferred = _infer_video_path_metadata(media_file)
            suggested = {
                field_name: str(inferred.get(field_name) or "").strip()
                for field_name in AUTO_VIDEO_METADATA_FIELDS
            }
            missing_fields = [
                field_name
                for field_name in AUTO_VIDEO_METADATA_FIELDS
                if not existing.get(field_name) and suggested.get(field_name)
            ]

    confidence = 0.0
    if suggested.get("SeriesTitle") and suggested.get("EpisodeNumber"):
        confidence = 0.86
    elif suggested.get("SeriesTitle"):
        confidence = 0.62
    elif suggested.get("EpisodeNumber"):
        confidence = 0.48

    return {
        "track_id": str(track.pk),
        "media_file_id": str(media_file.pk) if media_file else "",
        "track_title": track.canonical_title or "",
        "filename": media_file.filename if media_file else "",
        "display_path": media_file.display_path if media_file else "",
        "media_kind": getattr(media_file, "media_kind", "") if media_file else "",
        "existing": existing,
        "suggested": suggested,
        "missing_fields": missing_fields,
        "has_suggestion": bool(missing_fields),
        "confidence": confidence,
        "matched_pattern": "filename/path regex" if confidence else "",
    }


def _metadata_from_prefetched_media_file(media_file):
    if not media_file:
        return {}
    by_source = {"user": {}, "triver": {}}
    for value in media_file.meta_values.all():
        if value.source_family not in by_source:
            continue
        bucket = by_source[value.source_family].setdefault(value.field.name, [])
        bucket.append(value.value_text)
    metadata = dict(by_source["triver"])
    metadata.update(by_source["user"])
    return metadata


def _track_has_tv_series_tag(track):
    return any(
        assignment.tag_value.definition.key == "video-tag"
        and (
            assignment.tag_value.normalized_key == "tv-series"
            or str(assignment.tag_value).strip().lower() == "tv series"
        )
        for assignment in track.tag_assignments.all()
    )


def _query_param_values(query_params, *names):
    values = []
    for name in names:
        for raw_value in query_params.getlist(name):
            values.extend(part.strip() for part in str(raw_value or "").split(",") if part.strip())
    return values


def _tag_filter_q(raw_filter, relation_name):
    if ":" in raw_filter:
        definition_key, normalized_key = raw_filter.split(":", 1)
        definition_key = definition_key.strip()
        normalized_key = normalized_key.strip()
        if definition_key == "value" and normalized_key:
            return Q(**{f"{relation_name}__tag_value_id": normalized_key})
        if definition_key and normalized_key:
            return Q(**{
                f"{relation_name}__tag_value__definition__key": definition_key,
                f"{relation_name}__tag_value__normalized_key": normalized_key,
            })
        return Q(pk__in=[])
    return Q(**{f"{relation_name}__tag_value__definition__key": raw_filter})


def _apply_tag_filters(queryset, request, relation_name="tag_assignments"):
    tag_keys = _query_param_values(request.query_params, "tag_key")
    if tag_keys:
        queryset = queryset.filter(**{f"{relation_name}__tag_value__definition__key__in": tag_keys})

    tag_filters = _query_param_values(request.query_params, "tag_filter", "tag")
    if tag_filters:
        include_q = Q()
        for raw_filter in tag_filters:
            include_q |= _tag_filter_q(raw_filter, relation_name)
        queryset = queryset.filter(include_q)

    exclude_tag_filters = _query_param_values(request.query_params, "exclude_tag_filter", "exclude_tag")
    if exclude_tag_filters:
        exclude_q = Q()
        for raw_filter in exclude_tag_filters:
            exclude_q |= _tag_filter_q(raw_filter, relation_name)
        queryset = queryset.exclude(exclude_q)
    return queryset


def _track_has_video_tag(track, *normalized_keys):
    wanted = {str(key or "").strip().lower() for key in normalized_keys if str(key or "").strip()}
    return any(
        assignment.tag_value.definition.key == "video-tag"
        and (
            assignment.tag_value.normalized_key in wanted
            or str(assignment.tag_value).strip().lower() in wanted
        )
        for assignment in track.tag_assignments.all()
    )


def _video_series_key(kind, title, fallback):
    normalized_title = re.sub(r"[^a-z0-9]+", "-", str(title or "").lower()).strip("-")
    return f"{kind}:{normalized_title or fallback}"


def _video_series_entry(track):
    media_file = track.primary_file
    metadata = _metadata_from_prefetched_media_file(media_file)
    series_title = _metadata_first_string(metadata, "SeriesTitle")
    is_movie = _track_has_video_tag(track, "movie", "movies", "film")
    if is_movie:
        series_title = ""
    if not series_title and _track_has_tv_series_tag(track):
        if track.album and track.album.title:
            series_title = track.album.title
        else:
            source_folder = getattr(media_file, "source_folder", None) if media_file else None
            series_title = getattr(source_folder, "name", "") or ""

    group_kind = "series" if series_title and not is_movie else "standalone"
    title = series_title or track.canonical_title or (media_file.filename if media_file else "") or "Untitled video"
    season_number = _parse_positive_int(_metadata_first_string(metadata, "SeasonNumber"))
    episode_number = _parse_positive_int(_metadata_first_string(metadata, "EpisodeNumber")) or track.track_number
    return {
        "key": _video_series_key(group_kind, title, str(track.pk)),
        "kind": group_kind,
        "title": title,
        "season_number": season_number,
        "episode_number": episode_number,
        "episode_title": _metadata_first_string(metadata, "EpisodeTitle"),
        "track": track,
    }


def _video_series_track_sort_key(entry):
    track = entry["track"]
    return (
        entry.get("season_number") if entry.get("season_number") is not None else 9999,
        entry.get("episode_number") if entry.get("episode_number") is not None else (track.track_number or 9999),
        (entry.get("episode_title") or track.canonical_title or "").lower(),
        str(track.pk),
    )


def _video_section_for_group(group_kind, tracks):
    if group_kind == "series":
        return "series"
    if any(_track_has_video_tag(track, "movie", "movies", "film") for track in tracks):
        return "movies"
    return "uncategorized"


VIDEO_CURATION_SYSTEM_ROWS = {
    "recently": "Recently Added",
    "all": "All Videos",
}


def _video_curation_row_id(row_type, key):
    return f"{row_type}:{key}"


def _video_curation_row_ref(row_id):
    row_id = str(row_id or "").strip()
    if row_id.startswith("system:"):
        key = row_id.split(":", 1)[1]
        if key in VIDEO_CURATION_SYSTEM_ROWS:
            return {"type": "system", "key": key}
    if row_id.startswith("tag:"):
        tag_id = row_id.split(":", 1)[1]
        if tag_id:
            return {"type": "tag", "id": tag_id}
    return None


def _video_curation_available_rows():
    rows = {}
    for key, label in VIDEO_CURATION_SYSTEM_ROWS.items():
        row_id = _video_curation_row_id("system", key)
        rows[row_id] = {
            "id": row_id,
            "type": "system",
            "key": key,
            "label": label,
            "query": {"curation_system": key},
        }

    definition = TagDefinition.objects.filter(scope=TagDefinition.SCOPE_TRACK, key="video-tag").first()
    if definition:
        for value in definition.values.order_by("display_order", "value_text", "id"):
            row_id = _video_curation_row_id("tag", value.pk)
            rows[row_id] = {
                "id": row_id,
                "type": "tag",
                "key": value.normalized_key or str(value.pk),
                "tag_value_id": value.pk,
                "label": value.value_text or str(value),
                "query": {"tag_value": str(value.pk)},
            }
    return rows


def _video_curation_settings_payload(settings_row=None):
    settings_row = settings_row or VideoCurationSettings.load()
    available_rows = _video_curation_available_rows()
    saved_refs = settings_row.row_order if isinstance(settings_row.row_order, list) else []
    ordered_ids = []
    for ref in saved_refs:
        if isinstance(ref, str):
            row_id = ref
        elif isinstance(ref, dict):
            row_type = ref.get("type")
            row_key = ref.get("key") if row_type == "system" else ref.get("id")
            row_id = _video_curation_row_id(row_type, row_key)
        else:
            continue
        if row_id in available_rows and row_id not in ordered_ids:
            ordered_ids.append(row_id)

    if not ordered_ids:
        ordered_ids = ["system:recently", "system:all"]

    for system_id in ["system:recently", "system:all"]:
        if system_id in available_rows and system_id not in ordered_ids:
            ordered_ids.append(system_id)

    missing_tag_ids = [
        row_id
        for row_id, row in available_rows.items()
        if row.get("type") == "tag" and row_id not in ordered_ids
    ]
    if missing_tag_ids:
        try:
            all_index = ordered_ids.index("system:all")
        except ValueError:
            all_index = len(ordered_ids)
        ordered_ids[all_index:all_index] = missing_tag_ids

    rows = [{**available_rows[row_id], "display_order": index} for index, row_id in enumerate(ordered_ids) if row_id in available_rows]
    return {
        "id": settings_row.pk,
        "row_order": [row["id"] for row in rows],
        "rows": rows,
    }


def _video_curation_refs_from_row_order(row_order):
    refs = []
    seen = set()
    for row_id in row_order if isinstance(row_order, list) else []:
        ref = _video_curation_row_ref(row_id)
        if not ref:
            continue
        normalized_id = _video_curation_row_id(ref.get("type"), ref.get("key") if ref.get("type") == "system" else ref.get("id"))
        if normalized_id in seen:
            continue
        seen.add(normalized_id)
        refs.append(ref)
    for row_id in ["system:recently", "system:all"]:
        if row_id not in seen:
            refs.append(_video_curation_row_ref(row_id))
    return [ref for ref in refs if ref]


def _resolve_existing_accessory_path(accessory_file):
    candidates = []

    if accessory_file.absolute_path:
        candidates.append(Path(accessory_file.absolute_path))

    if accessory_file.relative_path:
        relative_path = Path(accessory_file.relative_path)
        candidates.extend([
            Path(accessory_file.library.ingest_path) / relative_path,
            Path(accessory_file.library.digest_path) / relative_path,
            Path(accessory_file.library.digest_path) / "Unrevisioned" / relative_path,
        ])

    seen = set()
    for candidate in candidates:
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


RANGE_HEADER_PATTERN = re.compile(r"bytes=(\d*)-(\d*)$")
WAVEFORM_CACHE_DIR = Path("/tmp/triver-waveforms")
SUBTITLE_CACHE_DIR = Path("/tmp/triver-subtitles")
PLAYBACK_CACHE_DIR = Path("/tmp/triver-playback")
HLS_CACHE_DIR = Path("/tmp/triver-hls")
PLAYBACK_CACHE_VERSION = 3
WAVEFORM_LEVELS = (256, 1024, 4096, 16384)
PLAYBACK_BUILD_LOCK = threading.Lock()
PLAYBACK_BUILD_IN_PROGRESS = set()
PLAYBACK_BUILD_LOCK_TTL_SECONDS = 12 * 60 * 60
PLAYBACK_QUEUE_LOCK_TTL_SECONDS = 30 * 60


class PlaybackBuildInProgress(RuntimeError):
    pass


def _iter_file_chunks(file_handle, remaining_bytes, chunk_size=8192):
    try:
        while remaining_bytes > 0:
            chunk = file_handle.read(min(chunk_size, remaining_bytes))
            if not chunk:
                break
            remaining_bytes -= len(chunk)
            yield chunk
    finally:
        file_handle.close()


def _parse_id3v2_prefix_size(header):
    if len(header) < 10 or not header.startswith(b"ID3"):
        return None
    tag_size = (
        ((header[6] & 0x7F) << 21)
        | ((header[7] & 0x7F) << 14)
        | ((header[8] & 0x7F) << 7)
        | (header[9] & 0x7F)
    )
    footer_size = 10 if (header[5] & 0x10) else 0
    return 10 + tag_size + footer_size


def _inspect_audio_stream_layout(file_path):
    try:
        with file_path.open("rb") as file_handle:
            header = file_handle.read(16)
    except OSError:
        return 0, None

    if header.startswith(b"fLaC"):
        return 0, "audio/flac"
    id3_prefix_size = _parse_id3v2_prefix_size(header[:10])
    if id3_prefix_size:
        try:
            with file_path.open("rb") as file_handle:
                file_handle.seek(id3_prefix_size)
                nested_header = file_handle.read(16)
        except OSError:
            nested_header = b""
        if nested_header.startswith(b"fLaC"):
            return id3_prefix_size, "audio/flac"
        return 0, "audio/mpeg"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return 0, "audio/mpeg"
    if header.startswith(b"OggS"):
        return 0, "audio/ogg"
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return 0, "audio/wav"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return 0, "audio/mp4"
    return 0, None


def _build_audio_stream_response(request, file_path, default_content_type="audio/mpeg"):
    file_size = file_path.stat().st_size
    prefix_skip, sniffed_content_type = _inspect_audio_stream_layout(file_path)
    logical_size = max(file_size - prefix_skip, 0)
    content_type, _ = mimetypes.guess_type(file_path.name)
    content_type = sniffed_content_type or content_type or default_content_type
    range_header = request.headers.get("Range", "").strip()

    if not range_header:
        file_handle = file_path.open("rb")
        if prefix_skip:
            file_handle.seek(prefix_skip)
        response = FileResponse(file_handle, content_type=content_type)
        response["Accept-Ranges"] = "bytes"
        response["Content-Length"] = str(logical_size)
        return response

    match = RANGE_HEADER_PATTERN.match(range_header)
    if not match:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{logical_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    start_text, end_text = match.groups()
    if not start_text and not end_text:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{logical_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else logical_size - 1
    else:
        suffix_length = int(end_text)
        if suffix_length <= 0:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{logical_size}"
            response["Accept-Ranges"] = "bytes"
            return response
        start = max(logical_size - suffix_length, 0)
        end = logical_size - 1

    if start >= logical_size or end < start:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{logical_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    end = min(end, logical_size - 1)
    content_length = end - start + 1
    file_handle = file_path.open("rb")
    file_handle.seek(prefix_skip + start)

    response = StreamingHttpResponse(
        _iter_file_chunks(file_handle, content_length),
        status=206,
        content_type=content_type,
    )
    response["Accept-Ranges"] = "bytes"
    response["Content-Length"] = str(content_length)
    response["Content-Range"] = f"bytes {start}-{end}/{logical_size}"
    return response


def _build_binary_stream_response(request, file_path, default_content_type="application/octet-stream"):
    file_size = file_path.stat().st_size
    content_type, _ = mimetypes.guess_type(file_path.name)
    content_type = content_type or default_content_type
    headers = getattr(request, "headers", {}) if request is not None else {}
    range_header = headers.get("Range", "").strip()

    if not range_header:
        response = FileResponse(file_path.open("rb"), content_type=content_type)
        response["Accept-Ranges"] = "bytes"
        response["Content-Length"] = str(file_size)
        return response

    match = RANGE_HEADER_PATTERN.match(range_header)
    if not match:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{file_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    start_text, end_text = match.groups()
    if not start_text and not end_text:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{file_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else file_size - 1
    else:
        suffix_length = int(end_text)
        if suffix_length <= 0:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{file_size}"
            response["Accept-Ranges"] = "bytes"
            return response
        start = max(file_size - suffix_length, 0)
        end = file_size - 1

    if start >= file_size or end < start:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{file_size}"
        response["Accept-Ranges"] = "bytes"
        return response

    end = min(end, file_size - 1)
    content_length = end - start + 1
    file_handle = file_path.open("rb")
    file_handle.seek(start)

    response = StreamingHttpResponse(
        _iter_file_chunks(file_handle, content_length),
        status=206,
        content_type=content_type,
    )
    response["Accept-Ranges"] = "bytes"
    response["Content-Length"] = str(content_length)
    response["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return response


def _subtitle_cache_path(track_id, stream_selector, file_path):
    SUBTITLE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_selector = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(stream_selector or "subtitle"))
    stat_result = file_path.stat()
    cache_key = f"{track_id}-{safe_selector}-{int(stat_result.st_mtime)}-{stat_result.st_size}.vtt"
    return SUBTITLE_CACHE_DIR / cache_key


def _video_poster_root():
    root = Path(getattr(settings, "TRIVER_DUMP_ROOT", "/tmp")).resolve() / "video-posters"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _video_poster_source_key(track, file_path):
    stat_result = file_path.stat()
    return f"{track.pk}-{int(stat_result.st_mtime)}-{stat_result.st_size}"


def _selected_video_poster_path(track, file_path):
    return _video_poster_root() / "selected" / f"{_video_poster_source_key(track, file_path)}.jpg"


def _default_video_poster_path(track, file_path):
    return _video_poster_root() / "default" / f"{_video_poster_source_key(track, file_path)}.jpg"


def _candidate_video_poster_path(track, file_path, seconds):
    milliseconds = int(round(max(float(seconds), 0.0) * 1000))
    return _video_poster_root() / "candidates" / f"{_video_poster_source_key(track, file_path)}-{milliseconds}.jpg"


def _video_series_poster_token(series_key):
    return hashlib.sha1(str(series_key or "").encode("utf-8")).hexdigest()[:32]


def _selected_video_series_poster_path(series_key):
    return _video_poster_root() / "series" / f"{_video_series_poster_token(series_key)}.jpg"


def _selected_video_series_poster_url(series_key):
    poster_path = _selected_video_series_poster_path(series_key)
    if not poster_path.exists() or poster_path.stat().st_size <= 0:
        return ""
    return f"/api/videos/series-poster/?series_key={quote(str(series_key or ''))}&v={int(poster_path.stat().st_mtime)}"


def _track_duration_seconds(track):
    try:
        duration = float(track.duration_seconds)
    except (TypeError, ValueError):
        duration = 0.0
    return max(duration, 0.0)


def _parse_timecode_seconds(raw_value):
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    text = str(raw_value or "").strip().replace(",", ".")
    if not text:
        return 0.0
    if ":" not in text:
        return float(text)

    parts = [part.strip() for part in text.split(":")]
    if len(parts) > 3 or any(part == "" for part in parts):
        raise ValueError("Formato tempo non valido.")
    seconds = 0.0
    multiplier = 1.0
    for part in reversed(parts):
        seconds += float(part) * multiplier
        multiplier *= 60.0
    return seconds


def _coerce_video_poster_seconds(raw_value, track):
    try:
        seconds = _parse_timecode_seconds(raw_value)
    except (TypeError, ValueError):
        raise ValueError("Tempo frame non valido. Usa secondi oppure min:sec.")
    duration = _track_duration_seconds(track)
    if duration > 0:
        seconds = min(seconds, max(duration - 0.25, 0.0))
    return round(max(seconds, 0.0), 3)


def _default_video_poster_seconds(track):
    duration = _track_duration_seconds(track)
    if duration >= 600:
        return 60.0
    if duration >= 120:
        return 30.0
    if duration > 10:
        return max(3.0, duration * 0.15)
    return 0.0


def _format_video_poster_label(seconds):
    seconds = max(float(seconds or 0), 0.0)
    whole_seconds = int(round(seconds))
    hours = whole_seconds // 3600
    minutes = (whole_seconds % 3600) // 60
    remainder = whole_seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{remainder:02d}"
    return f"{minutes}:{remainder:02d}"


def _ensure_video_poster_frame(track, file_path, seconds, output_path):
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink(missing_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-ss",
        f"{max(float(seconds or 0), 0.0):.3f}",
        "-i",
        str(file_path),
        "-frames:v",
        "1",
        "-an",
        "-q:v",
        "3",
        str(output_path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )
    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError((result.stderr or "").strip() or "Impossibile generare poster video.")
    return output_path


def _video_poster_response(file_path):
    response = FileResponse(file_path.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "no-store"
    response["Content-Length"] = str(file_path.stat().st_size)
    return response


def _video_poster_candidate_seconds(track, count):
    duration = _track_duration_seconds(track)
    if duration <= 0:
        return [0.0]
    lower_bound = min(max(duration * 0.04, 1.0), max(duration - 0.25, 0.0))
    upper_bound = max(duration - max(duration * 0.08, 2.0), lower_bound)
    seconds = set()
    anchor_ratios = [0.12, 0.28, 0.45, 0.62, 0.78, 0.9]
    for ratio in anchor_ratios[:max(count // 2, 1)]:
        seconds.add(round(min(max(duration * ratio, lower_bound), upper_bound), 3))
    while len(seconds) < count:
        seconds.add(round(random.uniform(lower_bound, upper_bound), 3))
    return sorted(seconds)[:count]


def _extract_subtitle_stream_to_vtt(file_path, stream_index, cache_path):
    if cache_path.exists():
        return cache_path
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(file_path),
            "-map",
            f"0:{stream_index}",
            "-f",
            "webvtt",
            str(cache_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not cache_path.exists():
        raise RuntimeError(result.stderr.strip() or "Subtitle extraction failed.")
    return cache_path


def _extract_external_subtitle_to_vtt(subtitle_path, cache_path):
    if subtitle_path.suffix.lower() == ".vtt":
        return subtitle_path
    if cache_path.exists():
        return cache_path
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(subtitle_path),
            "-f",
            "webvtt",
            str(cache_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not cache_path.exists():
        raise RuntimeError(result.stderr.strip() or "Subtitle extraction failed.")
    return cache_path


def _get_track_source_payload(track):
    source_metadata = track.source_metadata.order_by("-created_at").first()
    if not source_metadata:
        return {}
    return source_metadata.raw_payload or {}


def _get_track_probe_streams(track, codec_type=None):
    streams = ((_get_track_source_payload(track).get("ffprobe") or {}).get("streams") or [])
    if codec_type is None:
        return streams
    return [stream for stream in streams if str(stream.get("codec_type") or "").lower() == codec_type]


def _is_browser_friendly_container_for_track(track):
    primary_file = track.primary_file
    extension = str(getattr(primary_file, "extension", "") or "").lower()
    return extension in {"mp4", "m4v", "webm", "ogv"}


def _is_browser_friendly_video_codec(codec_name):
    return str(codec_name or "").lower() in {"h264", "avc1", "vp8", "vp9", "av1", "theora"}


def _is_browser_friendly_audio_codec(codec_name):
    return str(codec_name or "").lower() in {"aac", "mp3", "opus", "vorbis"}


def _get_track_playback_strategy(track):
    primary_file = track.primary_file
    if not primary_file or getattr(primary_file, "media_kind", "audio") != "video":
        return "direct"
    video_codec = next(iter(_get_track_probe_streams(track, "video")), {}).get("codec_name") or ""
    audio_codec = next(iter(_get_track_probe_streams(track, "audio")), {}).get("codec_name") or ""
    container_ok = _is_browser_friendly_container_for_track(track)
    video_ok = _is_browser_friendly_video_codec(video_codec)
    audio_ok = _is_browser_friendly_audio_codec(audio_codec) or not audio_codec
    if container_ok and video_ok and audio_ok:
        return "direct"
    if (not container_ok) and video_ok and audio_ok:
        return "remux"
    if video_ok and not audio_ok:
        return "audio_transcode"
    return "transcode"


def _playback_cache_path(track_id, playback_strategy, file_path):
    PLAYBACK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stat = file_path.stat()
    cache_key = f"v{PLAYBACK_CACHE_VERSION}-{track_id}-{playback_strategy}-{int(stat.st_mtime)}-{stat.st_size}.mp4"
    return PLAYBACK_CACHE_DIR / cache_key


def _playback_build_lock_path(cache_path):
    return cache_path.with_name(f"{cache_path.name}.lock")


def _playback_progress_path(cache_path):
    return cache_path.with_name(f"{cache_path.name}.progress")


def _playback_global_build_lock_path():
    PLAYBACK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return PLAYBACK_CACHE_DIR / ".global-build.lock"


def _coerce_positive_int(value):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _pid_exists(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_playback_lock(lock_path):
    try:
        raw_value = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        payload = {}
        for part in raw_value.replace("\n", " ").split():
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            payload[key] = value
        return payload


def _write_playback_lock(lock_path, **metadata):
    payload = {
        "pid": os.getpid(),
        "started": time.time(),
        **{key: value for key, value in metadata.items() if value not in (None, "")},
    }
    lock_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _is_playback_lock_active(lock_path):
    if not lock_path.exists():
        return False
    payload = _read_playback_lock(lock_path)
    try:
        age_seconds = time.time() - lock_path.stat().st_mtime
    except OSError:
        return True
    lock_pid = _coerce_positive_int(payload.get("ffmpeg_pid") or payload.get("pid"))
    if payload.get("queued"):
        if age_seconds <= PLAYBACK_QUEUE_LOCK_TTL_SECONDS:
            return True
        try:
            lock_path.unlink()
        except OSError:
            return True
        return False
    if lock_pid and not _pid_exists(lock_pid):
        try:
            lock_path.unlink()
        except OSError:
            return True
        return False
    if age_seconds <= PLAYBACK_BUILD_LOCK_TTL_SECONDS:
        return True
    try:
        lock_path.unlink()
    except OSError:
        return True
    return False


def _acquire_playback_lock_path(lock_path, **metadata):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for _attempt in range(2):
        try:
            fd = os.open(str(lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            if _is_playback_lock_active(lock_path):
                return None
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
            payload = {
                "pid": os.getpid(),
                "started": time.time(),
                **{key: value for key, value in metadata.items() if value not in (None, "")},
            }
            json.dump(payload, lock_file, sort_keys=True)
        return lock_path
    return None


def _acquire_playback_build_lock(cache_path, **metadata):
    return _acquire_playback_lock_path(_playback_build_lock_path(cache_path), **metadata)


def _acquire_global_playback_build_lock(**metadata):
    return _acquire_playback_lock_path(_playback_global_build_lock_path(), **metadata)


def _release_playback_build_lock(lock_path):
    if lock_path is not None:
        lock_path.unlink(missing_ok=True)


def _is_playback_building(cache_path):
    build_key = str(cache_path)
    with PLAYBACK_BUILD_LOCK:
        in_memory = build_key in PLAYBACK_BUILD_IN_PROGRESS
    return in_memory or _is_playback_lock_active(_playback_build_lock_path(cache_path))


def _is_global_playback_building():
    return _is_playback_lock_active(_playback_global_build_lock_path())


def _read_playback_progress(cache_path, duration_seconds=None):
    progress_path = _playback_progress_path(cache_path)
    if not progress_path.exists():
        return {
            "percent": 100 if cache_path.exists() else 0,
            "seconds_done": 0,
            "seconds_total": round(float(duration_seconds or 0), 3),
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

    out_time_raw = progress_values.get("out_time_ms") or progress_values.get("out_time_us")
    out_time_value = _coerce_positive_int(out_time_raw) or 0
    seconds_done = out_time_value / 1_000_000 if out_time_value else 0.0
    total_seconds = max(float(duration_seconds or 0), 0.0)
    if cache_path.exists():
        percent = 100
    elif total_seconds > 0:
        percent = max(0, min(99, int(round((seconds_done / total_seconds) * 100))))
    else:
        percent = 0
    return {
        "percent": percent,
        "seconds_done": round(seconds_done, 3),
        "seconds_total": round(total_seconds, 3),
    }


def _playback_status_message(playback_strategy, cache_ready, building, queue_busy):
    if cache_ready:
        return "Ready to play."
    if queue_busy:
        return "Another video is being prepared. Selecting this video will move it to the front."
    if building:
        return "Preparing this video for smooth browser playback."
    if playback_strategy == "remux":
        return "This video needs a quick packaging step before the browser can play it."
    if playback_strategy == "audio_transcode":
        return "This video uses an audio format the browser cannot play yet. trueRiver will prepare a playable copy."
    return "This video needs preparation before the browser can play it smoothly."


def _cancel_active_playback_build(requested_track_id=None):
    global_lock_path = _playback_global_build_lock_path()
    if not _is_playback_lock_active(global_lock_path):
        return False

    lock_payload = _read_playback_lock(global_lock_path)
    active_track_id = str(lock_payload.get("track_id") or "")
    if requested_track_id and active_track_id == str(requested_track_id):
        return False

    ffmpeg_pid = _coerce_positive_int(lock_payload.get("ffmpeg_pid"))
    if not ffmpeg_pid:
        return False

    try:
        os.kill(ffmpeg_pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    except OSError as exc:
        logger.warning("trive-playback cancel-failed pid=%s error=%s", ffmpeg_pid, exc)
        return False

    logger.warning(
        "trive-playback cancel-requested active_track_id=%s requested_track_id=%s pid=%s",
        active_track_id,
        requested_track_id,
        ffmpeg_pid,
    )
    return True


def _wait_for_global_playback_slot(timeout_seconds=2.0):
    deadline = time.time() + max(float(timeout_seconds or 0), 0.0)
    while time.time() < deadline:
        if not _is_global_playback_building():
            return True
        time.sleep(0.1)
    return not _is_global_playback_building()


def _build_ffmpeg_playback_command(file_path, playback_strategy, output_path, progress_path=None):
    ffmpeg_cmd = [
        "ionice",
        "-c",
        "3",
        "nice",
        "-n",
        "15",
        "ffmpeg",
        "-y",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(file_path),
        "-map",
        "0:v:0?",
        "-map",
        "0:a:0?",
        "-threads",
        "1",
    ]

    if playback_strategy == "remux":
        ffmpeg_cmd += ["-c:v", "copy", "-c:a", "copy"]
    elif playback_strategy == "audio_transcode":
        ffmpeg_cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    else:
        ffmpeg_cmd += [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "24",
            "-x264-params",
            "threads=1",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
        ]

    if progress_path is not None:
        ffmpeg_cmd += ["-progress", str(progress_path), "-nostats"]

    ffmpeg_cmd.append(str(output_path))
    return ffmpeg_cmd


def _build_ffmpeg_live_playback_command(file_path, playback_strategy):
    ffmpeg_cmd = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(file_path),
        "-map",
        "0:v:0?",
        "-map",
        "0:a:0?",
        "-movflags",
        "frag_keyframe+empty_moov+faststart",
        "-f",
        "mp4",
        "-threads",
        "1",
    ]

    if playback_strategy == "remux":
        ffmpeg_cmd += ["-c:v", "copy", "-c:a", "copy"]
    elif playback_strategy == "audio_transcode":
        ffmpeg_cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    else:
        ffmpeg_cmd += [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "24",
            "-x264-params",
            "threads=1",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
        ]

    ffmpeg_cmd.append("pipe:1")
    return ffmpeg_cmd


def _iter_ffmpeg_stdout(process):
    try:
        while True:
            chunk = process.stdout.read(8192)
            if not chunk:
                break
            yield chunk
    finally:
        if process.stdout:
            process.stdout.close()
        stderr_output = b""
        if process.stderr:
            stderr_output = process.stderr.read()
            process.stderr.close()
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError((stderr_output or b"").decode("utf-8", errors="ignore").strip() or "ffmpeg stream failed.")


def _build_live_video_playback_response(file_path, playback_strategy):
    ffmpeg_cmd = _build_ffmpeg_live_playback_command(file_path, playback_strategy)
    process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    response = StreamingHttpResponse(
        _iter_ffmpeg_stdout(process),
        content_type="video/mp4",
    )
    response["Cache-Control"] = "no-store"
    return response


def _ensure_cached_video_playback(
    track_id,
    file_path,
    playback_strategy,
    acquired_lock_path=None,
    acquired_global_lock_path=None,
):
    if playback_strategy == "direct":
        logger.warning(
            "trive-playback direct track_id=%s source=%s",
            track_id,
            str(file_path),
        )
        return file_path

    cache_path = _playback_cache_path(track_id, playback_strategy, file_path)
    if cache_path.exists():
        logger.warning(
            "trive-playback cache-hit track_id=%s strategy=%s cache=%s",
            track_id,
            playback_strategy,
            str(cache_path),
        )
        return cache_path

    global_lock_path = acquired_global_lock_path or _acquire_global_playback_build_lock(
        track_id=str(track_id),
        strategy=playback_strategy,
        cache_file=str(cache_path),
    )
    if global_lock_path is None:
        raise PlaybackBuildInProgress("Another playback build is already running.")

    lock_path = acquired_lock_path or _acquire_playback_build_lock(
        cache_path,
        track_id=str(track_id),
        strategy=playback_strategy,
        cache_file=str(cache_path),
    )
    try:
        if lock_path is None:
            raise PlaybackBuildInProgress(f"Playback build already running for {cache_path}")
        if cache_path.exists():
            return cache_path
        temp_path = cache_path.with_suffix(".tmp.mp4")
        progress_path = _playback_progress_path(cache_path)
        progress_path.unlink(missing_ok=True)
        ffmpeg_cmd = _build_ffmpeg_playback_command(file_path, playback_strategy, temp_path, progress_path=progress_path)
        started_at = time.perf_counter()
        logger.warning(
            "trive-playback build-start track_id=%s strategy=%s source=%s cache=%s cmd=%s",
            track_id,
            playback_strategy,
            str(file_path),
            str(cache_path),
            " ".join(ffmpeg_cmd),
        )
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        lock_metadata = {
            "track_id": str(track_id),
            "strategy": playback_strategy,
            "cache_file": str(cache_path),
            "temp_path": str(temp_path),
            "progress_path": str(progress_path),
            "ffmpeg_pid": process.pid,
        }
        _write_playback_lock(global_lock_path, **lock_metadata)
        _write_playback_lock(lock_path, **lock_metadata)
        stdout_text, stderr_text = process.communicate()
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        if process.returncode != 0 or not temp_path.exists():
            temp_path.unlink(missing_ok=True)
            progress_path.unlink(missing_ok=True)
            logger.warning(
                "trive-playback build-failed track_id=%s strategy=%s elapsed_ms=%s stderr=%s",
                track_id,
                playback_strategy,
                elapsed_ms,
                (stderr_text or stdout_text or "").strip(),
            )
            raise RuntimeError((stderr_text or stdout_text or "").strip() or "ffmpeg playback build failed.")

        temp_path.replace(cache_path)
        progress_path.unlink(missing_ok=True)
        logger.warning(
            "trive-playback build-done track_id=%s strategy=%s elapsed_ms=%s cache=%s size=%s",
            track_id,
            playback_strategy,
            elapsed_ms,
            str(cache_path),
            cache_path.stat().st_size if cache_path.exists() else 0,
        )
        return cache_path
    finally:
        _release_playback_build_lock(lock_path)
        _release_playback_build_lock(global_lock_path)


def _spawn_cached_video_playback_build(track_id, file_path, playback_strategy, preempt=False):
    cache_path = _playback_cache_path(track_id, playback_strategy, file_path)
    build_key = str(cache_path)
    if cache_path.exists():
        return cache_path

    with PLAYBACK_BUILD_LOCK:
        if build_key in PLAYBACK_BUILD_IN_PROGRESS:
            logger.warning(
                "trive-playback build-already-running track_id=%s strategy=%s cache=%s",
                track_id,
                playback_strategy,
                build_key,
            )
            return cache_path

    global_lock_path = _acquire_global_playback_build_lock(
        track_id=str(track_id),
        strategy=playback_strategy,
        cache_file=str(cache_path),
        queued=True,
    )
    if global_lock_path is None:
        if preempt and _cancel_active_playback_build(requested_track_id=track_id):
            _wait_for_global_playback_slot(timeout_seconds=2.0)
            global_lock_path = _acquire_global_playback_build_lock(
                track_id=str(track_id),
                strategy=playback_strategy,
                cache_file=str(cache_path),
                queued=True,
            )
        if global_lock_path is not None:
            logger.warning(
                "trive-playback build-preempted-previous track_id=%s strategy=%s cache=%s",
                track_id,
                playback_strategy,
                build_key,
            )
        else:
            logger.warning(
                "trive-playback build-global-busy track_id=%s strategy=%s cache=%s",
                track_id,
                playback_strategy,
                build_key,
            )
            return cache_path

    lock_path = _acquire_playback_build_lock(
        cache_path,
        track_id=str(track_id),
        strategy=playback_strategy,
        cache_file=str(cache_path),
        queued=True,
    )
    if lock_path is None:
        _release_playback_build_lock(global_lock_path)
        logger.warning(
            "trive-playback build-already-running track_id=%s strategy=%s cache=%s",
            track_id,
            playback_strategy,
            build_key,
        )
        return cache_path

    try:
        from apps.api.tasks import build_cached_video_playback

        async_result = build_cached_video_playback.apply_async(
            args=[
                str(track_id),
                str(file_path),
                playback_strategy,
                str(lock_path),
                str(global_lock_path),
            ],
            queue="playback",
        )
    except Exception:
        _release_playback_build_lock(lock_path)
        _release_playback_build_lock(global_lock_path)
        raise

    lock_metadata = {
        "track_id": str(track_id),
        "strategy": playback_strategy,
        "cache_file": str(cache_path),
        "task_id": async_result.id,
        "queued": True,
    }
    _write_playback_lock(global_lock_path, **lock_metadata)
    _write_playback_lock(lock_path, **lock_metadata)
    logger.warning(
        "trive-playback build-queued track_id=%s strategy=%s cache=%s task_id=%s",
        track_id,
        playback_strategy,
        build_key,
        async_result.id,
    )
    return cache_path


def _get_cached_video_playback_status(track_id, file_path, playback_strategy, duration_seconds=None):
    if playback_strategy == "direct":
        return {
            "strategy": playback_strategy,
            "mode": "direct",
            "cache_ready": True,
            "building": False,
            "queue_busy": False,
            "progress": {"percent": 100, "seconds_done": round(float(duration_seconds or 0), 3), "seconds_total": round(float(duration_seconds or 0), 3)},
            "message": "Ready to play.",
            "cache_path": str(file_path),
        }

    cache_path = _playback_cache_path(track_id, playback_strategy, file_path)
    building = _is_playback_building(cache_path)
    cache_ready = cache_path.exists()
    queue_busy = _is_global_playback_building() and not building and not cache_ready
    progress = _read_playback_progress(cache_path, duration_seconds=duration_seconds)
    return {
        "strategy": playback_strategy,
        "mode": "cached" if cache_ready else "preparing",
        "cache_ready": cache_ready,
        "building": building,
        "queue_busy": queue_busy,
        "progress": progress,
        "message": _playback_status_message(playback_strategy, cache_ready, building, queue_busy),
        "cache_path": str(cache_path),
    }


def _hls_cache_dir(track_id, playback_strategy, file_path):
    HLS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stat = file_path.stat()
    cache_key = f"v{PLAYBACK_CACHE_VERSION}-{track_id}-{playback_strategy}-{int(stat.st_mtime)}-{stat.st_size}"
    return HLS_CACHE_DIR / cache_key


def _build_ffmpeg_hls_command(file_path, playback_strategy, cache_dir):
    playlist_path = cache_dir / "index.m3u8"
    segment_pattern = cache_dir / "segment_%03d.ts"
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(file_path),
        "-map",
        "0:v:0?",
        "-map",
        "0:a:0?",
        "-threads",
        "1",
    ]

    if playback_strategy == "audio_transcode":
        ffmpeg_cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    else:
        ffmpeg_cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-c:a", "aac", "-b:a", "160k"]

    ffmpeg_cmd += [
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_playlist_type",
        "vod",
        "-hls_segment_filename",
        str(segment_pattern),
        str(playlist_path),
    ]
    return ffmpeg_cmd


def _ensure_hls_playback_cache(track_id, file_path, playback_strategy):
    cache_dir = _hls_cache_dir(track_id, playback_strategy, file_path)
    playlist_path = cache_dir / "index.m3u8"
    if playlist_path.exists():
        return cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_cmd = _build_ffmpeg_hls_command(file_path, playback_strategy, cache_dir)
    started_at = time.perf_counter()
    logger.warning(
        "trive-hls build-start track_id=%s strategy=%s source=%s playlist=%s cmd=%s",
        track_id,
        playback_strategy,
        str(file_path),
        str(playlist_path),
        " ".join(ffmpeg_cmd),
    )
    result = subprocess.run(
        ffmpeg_cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    if result.returncode != 0 or not playlist_path.exists():
        logger.warning(
            "trive-hls build-failed track_id=%s strategy=%s elapsed_ms=%s stderr=%s",
            track_id,
            playback_strategy,
            elapsed_ms,
            (result.stderr or "").strip(),
        )
        raise RuntimeError(result.stderr.strip() or "ffmpeg hls build failed.")
    logger.warning(
        "trive-hls build-done track_id=%s strategy=%s elapsed_ms=%s playlist=%s",
        track_id,
        playback_strategy,
        elapsed_ms,
        str(playlist_path),
    )
    return cache_dir


def _build_video_playback_response(request, track, file_path, playback_strategy):
    logger.warning(
        "trive-playback serve-start track_id=%s title=%s strategy=%s source=%s",
        str(track.pk),
        track.canonical_title,
        playback_strategy,
        str(file_path),
    )
    if playback_strategy == "direct":
        playback_path = _ensure_cached_video_playback(track.pk, file_path, playback_strategy)
        response = _build_binary_stream_response(request, playback_path, default_content_type="video/mp4")
        response["Cache-Control"] = "no-store"
        logger.warning(
            "trive-playback serve-ready track_id=%s strategy=%s playback=%s",
            str(track.pk),
            playback_strategy,
            str(playback_path),
        )
        return response

    cache_path = _playback_cache_path(track.pk, playback_strategy, file_path)
    if cache_path.exists():
        response = _build_binary_stream_response(request, cache_path, default_content_type="video/mp4")
        response["Cache-Control"] = "no-store"
        logger.warning(
            "trive-playback serve-ready track_id=%s strategy=%s playback=%s",
            str(track.pk),
            playback_strategy,
            str(cache_path),
        )
        return response

    _spawn_cached_video_playback_build(track.pk, file_path, playback_strategy, preempt=True)
    logger.warning(
        "trive-playback cache-miss-preparing track_id=%s strategy=%s source=%s",
        str(track.pk),
        playback_strategy,
        str(file_path),
    )
    return Response(
        {
            "detail": "Playback cache is being prepared. Retry when playback-status reports cache_ready=true.",
            "track_id": str(track.pk),
            **_get_cached_video_playback_status(track.pk, file_path, playback_strategy, duration_seconds=track.duration_seconds),
        },
        status=status.HTTP_202_ACCEPTED,
    )


def _read_audio_sample_rate(file_path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return int((result.stdout or "").strip())
    except (TypeError, ValueError):
        return None


def _decode_audio_samples(file_path):
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(file_path),
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-f",
            "f32le",
            "-c:a",
            "pcm_f32le",
            "-",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or b"ffmpeg decode failed").decode("utf-8", errors="ignore").strip())

    samples = array("f")
    samples.frombytes(result.stdout)
    return samples


def _build_waveform_level(samples, resolution):
    total_samples = len(samples)
    if total_samples <= 0:
      return [{"min": 0.0, "max": 0.0} for _ in range(resolution)]

    bucket_size = max(1, math.ceil(total_samples / resolution))
    level = []

    for index in range(resolution):
        start = index * bucket_size
        end = min(total_samples, start + bucket_size)
        if start >= total_samples:
            level.append({"min": 0.0, "max": 0.0})
            continue

        bucket = samples[start:end]
        level.append(
            {
                "min": round(min(bucket), 6),
                "max": round(max(bucket), 6),
            }
        )

    return level


def _waveform_cache_path(track_id, file_path):
    stat = file_path.stat()
    cache_name = f"{track_id}-{stat.st_size}-{stat.st_mtime_ns}.json"
    return WAVEFORM_CACHE_DIR / cache_name


def _get_or_build_waveform_payload(track, file_path):
    cache_path = _waveform_cache_path(track.pk, file_path)
    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    sample_rate = _read_audio_sample_rate(file_path)
    samples = _decode_audio_samples(file_path)
    duration_seconds = float(track.duration_seconds) if track.duration_seconds is not None else (
        (len(samples) / sample_rate) if sample_rate else 0.0
    )
    payload = {
        "track_id": str(track.pk),
        "duration_seconds": round(duration_seconds, 6),
        "sample_rate": sample_rate,
        "levels": {
            str(level): _build_waveform_level(samples, level)
            for level in WAVEFORM_LEVELS
        },
    }

    WAVEFORM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    return payload


ARTIST_PROFILE_IMAGE_ROOT = "artist-profile-images"
ARTIST_IMAGE_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
ARTIST_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _cacheless_file_response(file_path, content_type="application/octet-stream"):
    response = FileResponse(file_path.open("rb"), content_type=content_type or "application/octet-stream")
    response["Cache-Control"] = "no-store"
    return response


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


def _resolve_artist_profile_image_path(profile_image):
    if not profile_image or not profile_image.relative_path:
        return None
    root_path = Path(settings.TRIVER_DUMP_ROOT).resolve()
    candidate = (root_path / profile_image.relative_path).resolve()
    if candidate != root_path and root_path not in candidate.parents:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _safe_filter_first(queryset, **filters):
    try:
        return queryset.filter(**filters).first()
    except (TypeError, ValueError, ValidationError):
        return None


def _artist_profile_image_extension(uploaded_file):
    content_type = str(getattr(uploaded_file, "content_type", "") or "").split(";")[0].strip().lower()
    name_extension = Path(getattr(uploaded_file, "name", "") or "").suffix.lower()
    if name_extension == ".jpeg":
        name_extension = ".jpg"
    if content_type in ARTIST_IMAGE_CONTENT_TYPES:
        return ARTIST_IMAGE_CONTENT_TYPES[content_type], content_type
    if name_extension in ARTIST_IMAGE_EXTENSIONS:
        guessed_type, _ = mimetypes.guess_type(f"image{name_extension}")
        return name_extension, guessed_type or "application/octet-stream"
    raise ValueError("Il file caricato deve essere un'immagine JPG, PNG, WebP o GIF.")


def _save_artist_profile_image(artist, uploaded_file, user=None, path="", http_method="POST"):
    if not uploaded_file:
        raise ValueError("Nessuna immagine ricevuta.")
    if getattr(uploaded_file, "size", 0) and uploaded_file.size > 12 * 1024 * 1024:
        raise ValueError("L'immagine supera il limite di 12 MB.")

    extension, content_type = _artist_profile_image_extension(uploaded_file)
    image_id = uuid.uuid4()
    relative_path = Path(ARTIST_PROFILE_IMAGE_ROOT) / str(artist.pk) / f"{image_id}{extension}"
    root_path = Path(settings.TRIVER_DUMP_ROOT).resolve()
    destination = (root_path / relative_path).resolve()
    if destination != root_path and root_path not in destination.parents:
        raise ValueError("Percorso upload non valido.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        for chunk in uploaded_file.chunks():
            handle.write(chunk)

    profile_image = ArtistProfileImage(
        id=image_id,
        artist=artist,
        relative_path=relative_path.as_posix(),
        original_filename=Path(getattr(uploaded_file, "name", "") or "").name,
        content_type=content_type,
        size=getattr(uploaded_file, "size", 0) or destination.stat().st_size,
    )
    profile_image.save(user=user, path=path, http_method=http_method)
    return profile_image


def _http_json(url, timeout=4.0):
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "trueRiver/0.1 (artist bio lookup; local library tool)",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = response.read(1024 * 1024)
    return json.loads(payload.decode("utf-8"))


def _fetch_wikipedia_summary(artist_name, language="it"):
    normalized_language = language if language in {"it", "en"} else "it"
    languages = [normalized_language]
    if normalized_language != "en":
        languages.append("en")

    for lang in languages:
        direct_title = quote(str(artist_name or "").strip().replace(" ", "_"))
        if direct_title:
            try:
                summary = _http_json(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{direct_title}")
                extract = str(summary.get("extract") or "").strip()
                if extract and summary.get("type") != "disambiguation":
                    return {
                        "title": summary.get("title") or artist_name,
                        "extract": extract,
                        "url": (summary.get("content_urls") or {}).get("desktop", {}).get("page") or "",
                        "language": lang,
                    }
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
                pass

        search_params = urlencode({
            "action": "query",
            "list": "search",
            "srsearch": f"{artist_name} musician",
            "format": "json",
            "srlimit": "3",
        })
        try:
            search_payload = _http_json(f"https://{lang}.wikipedia.org/w/api.php?{search_params}")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            continue
        for result in (search_payload.get("query") or {}).get("search") or []:
            title = quote(str(result.get("title") or "").replace(" ", "_"))
            if not title:
                continue
            try:
                summary = _http_json(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}")
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
                continue
            extract = str(summary.get("extract") or "").strip()
            if extract and summary.get("type") != "disambiguation":
                return {
                    "title": summary.get("title") or result.get("title") or artist_name,
                    "extract": extract,
                    "url": (summary.get("content_urls") or {}).get("desktop", {}).get("page") or "",
                    "language": lang,
                }
    return None


def _fetch_musicbrainz_artist(artist_name):
    params = urlencode({
        "query": f'artist:"{artist_name}"',
        "fmt": "json",
        "limit": "1",
    })
    try:
        payload = _http_json(f"https://musicbrainz.org/ws/2/artist/?{params}")
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None
    artist = next(iter(payload.get("artists") or []), None)
    if not artist:
        return None
    tags = [
        tag.get("name")
        for tag in sorted(artist.get("tags") or [], key=lambda item: item.get("count") or 0, reverse=True)
        if tag.get("name")
    ][:5]
    return {
        "name": artist.get("name") or artist_name,
        "type": artist.get("type") or "",
        "country": artist.get("country") or "",
        "disambiguation": artist.get("disambiguation") or "",
        "life_span": artist.get("life-span") or {},
        "tags": tags,
        "url": f"https://musicbrainz.org/artist/{artist.get('id')}" if artist.get("id") else "",
    }


def _build_artist_bio_suggestion(artist, language="en"):
    wikipedia = _fetch_wikipedia_summary(artist.name, language=language)
    musicbrainz = _fetch_musicbrainz_artist(artist.name)
    draft = ""
    source_notes = []

    if wikipedia and wikipedia.get("extract"):
        draft = wikipedia["extract"]

    if musicbrainz:
        facts = []
        if musicbrainz.get("type"):
            facts.append(musicbrainz["type"].lower())
        if musicbrainz.get("country"):
            facts.append(f"country: {musicbrainz['country']}")
        life_span = musicbrainz.get("life_span") or {}
        if life_span.get("begin") or life_span.get("end"):
            period = " - ".join(value for value in [life_span.get("begin"), life_span.get("end")] if value)
            facts.append(f"period: {period}")
        if musicbrainz.get("tags"):
            facts.append(f"tag: {', '.join(musicbrainz['tags'])}")
        if facts:
            source_notes.append("; ".join(facts))

    if not draft and source_notes:
        draft = f"{artist.name} appears in online music databases with these references: {source_notes[0]}."
    elif draft and source_notes:
        draft = f"{draft}\n\nMusicBrainz references: {source_notes[0]}."

    sources = []
    if wikipedia:
        sources.append({
            "label": f"Wikipedia ({wikipedia.get('language')})",
            "title": wikipedia.get("title") or "",
            "url": wikipedia.get("url") or "",
        })
    if musicbrainz:
        sources.append({
            "label": "MusicBrainz",
            "title": musicbrainz.get("name") or artist.name,
            "url": musicbrainz.get("url") or "",
        })
    return {
        "draft": draft.strip(),
        "sources": sources,
        "provider": "wikipedia+musicbrainz",
    }


class CoverAssetMixin:
    def default_cover_response(self):
        return HttpResponse(status=404)

    def file_response_from_path(self, file_path, content_type=None):
        resolved_path = Path(file_path)
        guessed_type, _ = mimetypes.guess_type(resolved_path.name)
        return _cacheless_file_response(resolved_path, content_type or guessed_type or "application/octet-stream")

    def cover_response_from_source_folder(self, source_folder):
        if not source_folder:
            return self.default_cover_response()

        cover = source_folder.get_best_cover_accessory()
        if not cover:
            return self.default_cover_response()

        file_path = _resolve_existing_accessory_path(cover)
        if file_path is None:
            return self.default_cover_response()

        return self.file_response_from_path(file_path)


class LibraryViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = Library.objects.all()
    serializer_class = LibrarySerializer
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "created_at", "updated_at"]


class AutoImportSettingsViewSet(viewsets.ViewSet):
    serializer_class = AutoImportSettingsSerializer

    def _settings_object(self):
        library = _get_or_create_default_library()
        settings_obj, _created = AutoImportSettings.objects.get_or_create(library=library)
        return settings_obj

    def list(self, request):
        settings_obj = self._settings_object()
        return Response(self.serializer_class(settings_obj).data)

    @action(detail=False, methods=["get", "patch", "post"], url_path="settings")
    def update_settings(self, request):
        settings_obj = self._settings_object()
        if request.method == "GET":
            return Response(self.serializer_class(settings_obj).data)
        serializer = self.serializer_class(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user if request.user.is_authenticated else None)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="check-now")
    def check_now(self, request):
        settings_obj = self._settings_object()
        try:
            async_result = run_auto_import_monitor.delay(True)
        except Exception:
            async_result = run_auto_import_monitor.apply(args=[True])
        payload = self.serializer_class(settings_obj).data
        payload["celery_task_id"] = async_result.id
        payload["mode"] = "manual"
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class LibraryScanJobViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = LibraryScanJob.objects.select_related("library", "requested_by").all()
    serializer_class = LibraryScanJobSerializer
    filterset_fields = ["library", "status"]
    ordering_fields = ["created_at", "started_at", "finished_at", "status"]

    @action(detail=False, methods=["post"])
    def start_scan(self, request):
        library = _get_or_create_default_library()
        try:
            target_path = _requested_target_path(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        active_job = self.get_queryset().filter(
            library=library,
            status__in=[
                LibraryScanJob.STATUS_PENDING,
                LibraryScanJob.STATUS_DISCOVERING,
                LibraryScanJob.STATUS_PROCESSING,
            ],
        ).first()
        if active_job is not None:
            payload = self.get_serializer(active_job).data
            payload["detail"] = "A scan job is already active. Cancel or finish it before starting another one."
            return Response(payload, status=status.HTTP_409_CONFLICT)
        job = LibraryScanJob.objects.create(
            library=library,
            requested_by=request.user if request.user.is_authenticated else None,
            status=LibraryScanJob.STATUS_PENDING,
        )
        try:
            async_result = discover_library.delay(job.id, target_path)
        except Exception:
            async_result = discover_library.apply(args=[job.id, target_path])
        payload = self.get_serializer(job).data
        payload["celery_task_id"] = async_result.id
        payload["target_path"] = target_path
        payload["scope"] = "path" if target_path else "global"
        return Response(payload, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"])
    def start_rescan(self, request):
        library = _get_or_create_default_library()
        try:
            target_path = _requested_target_path(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        active_job = self.get_queryset().filter(
            library=library,
            status__in=[
                LibraryScanJob.STATUS_PENDING,
                LibraryScanJob.STATUS_DISCOVERING,
                LibraryScanJob.STATUS_PROCESSING,
            ],
        ).first()
        if active_job is not None:
            payload = self.get_serializer(active_job).data
            payload["detail"] = "A scan job is already active. Cancel or finish it before starting another one."
            return Response(payload, status=status.HTTP_409_CONFLICT)
        job = LibraryScanJob.objects.create(
            library=library,
            requested_by=request.user if request.user.is_authenticated else None,
            status=LibraryScanJob.STATUS_PENDING,
        )
        try:
            async_result = rescan_library_catalog.delay(job.id, target_path)
        except Exception:
            async_result = rescan_library_catalog.apply(args=[job.id, target_path])
        payload = self.get_serializer(job).data
        payload["celery_task_id"] = async_result.id
        payload["mode"] = "rescan"
        payload["target_path"] = target_path
        payload["scope"] = "path" if target_path else "global"
        return Response(payload, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["get"], url_path="classic-sources")
    def classic_sources(self, request):
        return Response(classic_import_sources_payload())

    @action(detail=False, methods=["post"], url_path="start-classic-import")
    def start_classic_import(self, request):
        library = _get_or_create_default_library()
        source_keys = request.data.get("source_keys") or request.data.get("sources") or []
        if isinstance(source_keys, str):
            source_keys = [source_keys]
        if not isinstance(source_keys, list):
            return Response({"detail": "source_keys must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        scan_active_job = self.get_queryset().filter(
            library=library,
            status__in=[
                LibraryScanJob.STATUS_PENDING,
                LibraryScanJob.STATUS_DISCOVERING,
                LibraryScanJob.STATUS_PROCESSING,
            ],
        ).first()
        if scan_active_job is not None:
            payload = self.get_serializer(scan_active_job).data
            payload["detail"] = "A scan job is already active. Cancel or finish it before starting another one."
            return Response(payload, status=status.HTTP_409_CONFLICT)
        digest_active_job = LibraryDigestJob.objects.filter(
            library=library,
            status__in=[
                LibraryDigestJob.STATUS_PENDING,
                LibraryDigestJob.STATUS_RUNNING,
            ],
        ).first()
        if digest_active_job is not None:
            payload = LibraryDigestJobSerializer(digest_active_job, context=self.get_serializer_context()).data
            payload["detail"] = "A Trive-Up job is already active. Cancel or finish it before starting another one."
            return Response(payload, status=status.HTTP_409_CONFLICT)

        configured = classic_import_sources_payload()
        configured_keys = {source["key"] for source in configured.get("sources", [])}
        requested_keys = [str(source_key or "").strip() for source_key in source_keys if str(source_key or "").strip()]
        if not configured_keys:
            return Response({"detail": "No classic import folders are configured."}, status=status.HTTP_400_BAD_REQUEST)
        if not requested_keys:
            requested_keys = sorted(configured_keys)
        unknown_keys = [key for key in requested_keys if key not in configured_keys]
        if unknown_keys:
            return Response({"detail": f"Unknown classic import folder: {', '.join(unknown_keys)}"}, status=status.HTTP_400_BAD_REQUEST)

        scan_job = LibraryScanJob.objects.create(
            library=library,
            requested_by=request.user if request.user.is_authenticated else None,
            status=LibraryScanJob.STATUS_PENDING,
        )
        digest_job = LibraryDigestJob.objects.create(
            library=library,
            requested_by=request.user if request.user.is_authenticated else None,
            status=LibraryDigestJob.STATUS_PENDING,
        )
        try:
            async_result = run_classic_import.delay(scan_job.id, digest_job.id, requested_keys)
        except Exception:
            async_result = run_classic_import.apply(args=[scan_job.id, digest_job.id, requested_keys])
        return Response({
            "scan_job": self.get_serializer(scan_job).data,
            "digest_job": LibraryDigestJobSerializer(digest_job, context=self.get_serializer_context()).data,
            "celery_task_id": async_result.id,
            "source_keys": requested_keys,
            "mode": "classic_import",
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["get"])
    def latest(self, request):
        library = _get_or_create_default_library()
        job = self.get_queryset().filter(library=library).first()
        if job is None:
            return Response({"detail": "No scan job found yet."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        job = self.get_object()
        serializer = self.get_serializer(job)
        return Response(serializer.data)


class LibraryDigestJobViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = LibraryDigestJob.objects.select_related("library", "requested_by").all()
    serializer_class = LibraryDigestJobSerializer
    filterset_fields = ["library", "status"]
    ordering_fields = ["created_at", "started_at", "finished_at", "status"]

    @action(detail=False, methods=["post"])
    def start_up(self, request):
        library = _get_or_create_default_library()
        try:
            target_path = _requested_target_path(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        active_job = self.get_queryset().filter(
            library=library,
            status__in=[
                LibraryDigestJob.STATUS_PENDING,
                LibraryDigestJob.STATUS_RUNNING,
            ],
        ).first()
        if active_job is not None:
            payload = self.get_serializer(active_job).data
            payload["detail"] = "A Trive-Up job is already active. Cancel or finish it before starting another one."
            return Response(payload, status=status.HTTP_409_CONFLICT)
        job = LibraryDigestJob.objects.create(
            library=library,
            requested_by=request.user if request.user.is_authenticated else None,
            status=LibraryDigestJob.STATUS_PENDING,
        )
        try:
            async_result = build_library_catalog.delay(job.id, target_path)
        except Exception:
            async_result = build_library_catalog.apply(args=[job.id, target_path])
        payload = self.get_serializer(job).data
        payload["celery_task_id"] = async_result.id
        payload["target_path"] = target_path
        payload["scope"] = "path" if target_path else "global"
        return Response(payload, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        job = self.get_object()
        if job.status in {
            LibraryDigestJob.STATUS_DONE,
            LibraryDigestJob.STATUS_ERROR,
            LibraryDigestJob.STATUS_CANCELED,
        }:
            return Response(self.get_serializer(job).data)
        job.status = LibraryDigestJob.STATUS_CANCELED
        job.finished_at = timezone.now()
        job.last_error = ""
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        return Response(self.get_serializer(job).data)

    @action(detail=False, methods=["get"])
    def latest(self, request):
        library = _get_or_create_default_library()
        job = self.get_queryset().filter(library=library).first()
        if job is None:
            return Response({"detail": "No digest job found yet."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        job = self.get_object()
        return Response(self.get_serializer(job).data)


class LibraryDigestErrorViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = LibraryDigestError.objects.select_related("library", "digest_job", "media_file").all()
    serializer_class = LibraryDigestErrorSerializer
    filterset_fields = ["library", "digest_job", "media_file", "error_type"]
    search_fields = ["relative_path", "filename", "message", "error_type"]
    ordering_fields = ["relative_path", "filename", "created_at"]


class MediaFileViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = MediaFile.objects.select_related("library").prefetch_related("meta_values__field").all()
    serializer_class = MediaFileSerializer
    filterset_fields = ["library", "source_folder", "status", "media_kind", "extension"]
    search_fields = [
        "relative_path",
        "filename",
        "mime_type",
        "meta_values__value_text",
        "meta_values__field__name",
        "meta_values__field__normalized_name",
        "meta_values__source_name",
        "meta_values__source_name_normalized",
    ]
    ordering_fields = ["relative_path", "size", "mtime", "created_at"]

    def get_queryset(self):
        return super().get_queryset().distinct()

    @action(detail=True, methods=["patch"], url_path="metadata")
    def metadata(self, request, pk=None):
        media_file = self.get_object()
        user = request.user if getattr(request.user, "is_authenticated", False) else None
        try:
            metadata = _metadata_payload_from_request(request)
            with transaction.atomic():
                updated_fields, synced_tracks = _set_media_file_metadata(
                    media_file,
                    metadata,
                    user=user,
                    path=request.path,
                    http_method=request.method,
                )
                refreshed = self.get_queryset().get(pk=media_file.pk)
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "media_file": MediaFileSerializer(refreshed, context=self.get_serializer_context()).data,
            "updated_fields": updated_fields,
            "synced_tracks": synced_tracks,
        })


class SourceFolderViewSet(CoverAssetMixin, LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = SourceFolder.objects.select_related("library").all()
    serializer_class = SourceFolderSerializer
    filterset_fields = ["library", "path_depth"]
    search_fields = ["relative_path", "name", "parent_relative_path"]
    ordering_fields = ["relative_path", "name", "file_count", "audio_file_count", "accessory_file_count", "created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        starts_with = (self.request.query_params.get("starts_with") or "").strip()
        if starts_with:
            if starts_with == "#":
                queryset = queryset.filter(name__regex=r"^[^A-Za-z0-9]")
            else:
                queryset = queryset.filter(name__istartswith=starts_with)
        return queryset

    @action(detail=True, methods=["get"], url_path="cover")
    def cover(self, request, pk=None):
        return self.cover_response_from_source_folder(self.get_object())


class IngestBrowserViewSet(viewsets.ViewSet):

    def list(self, request):
        library = _get_or_create_default_library()
        try:
            root_name = (request.query_params.get("root") or "trive-In").strip()
            relative_path = _normalize_relative_target_path(request.query_params.get("path") or "")
            payload = _build_file_explorer_payload(library, root_name=root_name, relative_path=relative_path)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except FileNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except NotADirectoryError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    @action(detail=False, methods=["get"], url_path="metadata-targets")
    def metadata_targets(self, request):
        library = _get_or_create_default_library()
        try:
            root_name = (request.query_params.get("root") or "trive-In").strip()
            relative_path = _normalize_relative_target_path(request.query_params.get("path") or "")
            normalized_root, root_path = _resolve_file_explorer_root(library, root_name)
            target_path = _resolve_scoped_root_path(root_path, relative_path)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if relative_path and not target_path.exists():
            return Response({"detail": f"Path not found inside {normalized_root}: {relative_path}"}, status=status.HTTP_404_NOT_FOUND)

        media_files = _explorer_media_files_for_path(library, normalized_root, relative_path)
        media_file_count = media_files.count()
        tracks = (
            Track.objects
            .filter(primary_file_id__in=media_files.values("pk"))
            .select_related("album", "primary_file")
            .prefetch_related(
                "artist_credits__artist",
                "tag_assignments__tag_value__definition",
                "primary_file__meta_values__field",
                "source_metadata",
            )
            .distinct()
            .order_by("canonical_sort_title", "canonical_title")
        )
        track_count = tracks.count()
        max_items = 500

        return Response({
            "library_id": library.id,
            "root": normalized_root,
            "relative_path": relative_path,
            "media_file_count": media_file_count,
            "track_count": track_count,
            "truncated": track_count > max_items,
            "tracks": TrackSerializer(tracks[:max_items], many=True, context={"request": request}).data,
        })

    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        library = _get_or_create_default_library()
        try:
            root_name = (request.data.get("root") or "trive-In").strip()
            relative_path = _normalize_relative_target_path(request.data.get("path") or "")
            normalized_root, root_path = _resolve_file_explorer_root(library, root_name)
            target_path = _resolve_scoped_root_path(root_path, relative_path)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if normalized_root != "trive-In":
            return Response({"detail": "Browser upload is only enabled for trive-In."}, status=status.HTTP_400_BAD_REQUEST)
        if target_path.exists() and not target_path.is_dir():
            return Response({"detail": "Upload target is not a directory."}, status=status.HTTP_400_BAD_REQUEST)

        upload_files = request.FILES.getlist("files")
        relative_paths = request.data.getlist("relative_paths")
        if not upload_files:
            return Response({"detail": "No files provided."}, status=status.HTTP_400_BAD_REQUEST)

        temp_dir = Path(tempfile.mkdtemp(prefix="triver-upload-", dir=_upload_quarantine_root()))
        staged = []
        try:
            for index, upload_file in enumerate(upload_files):
                upload_relative = relative_paths[index] if index < len(relative_paths) else upload_file.name
                upload_relative = _normalize_upload_relative_path(upload_relative or upload_file.name)
                destination_relative = Path(relative_path) / upload_relative if relative_path else Path(upload_relative)
                destination_relative = _normalize_upload_relative_path(destination_relative.as_posix())
                destination_path = _resolve_scoped_root_path(root_path, destination_relative)
                if destination_path.exists():
                    raise ValueError(f"Upload target already exists: {destination_relative}")

                temp_path = temp_dir / f"{index:05d}-{uuid.uuid4().hex}"
                with open(temp_path, "wb") as handle:
                    for chunk in upload_file.chunks():
                        handle.write(chunk)

                scan_result = _clamav_scan_file(temp_path)
                staged.append({
                    "source": temp_path,
                    "destination": destination_path,
                    "relative_path": destination_relative,
                    "name": upload_file.name,
                    "size": upload_file.size,
                    "scan": scan_result,
                })

            uploaded = []
            for item in staged:
                item["destination"].parent.mkdir(parents=True, exist_ok=True)
                if item["destination"].exists():
                    raise ValueError(f"Upload target already exists: {item['relative_path']}")
                _move_scanned_upload(item["source"], item["destination"])
                uploaded.append({
                    "name": item["name"],
                    "relative_path": item["relative_path"],
                    "size": item["size"],
                    "scan": item["scan"],
                })
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as exc:
            logger.warning("Upload antivirus scan failed: %s", exc)
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return Response({
            "root": normalized_root,
            "relative_path": relative_path,
            "uploaded_count": len(uploaded),
            "uploaded": uploaded[:200],
            "truncated": len(uploaded) > 200,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post", "delete"], url_path="delete-entry")
    def delete_entry(self, request):
        library = _get_or_create_default_library()
        try:
            root_name = (request.data.get("root") or request.query_params.get("root") or "trive-In").strip()
            relative_path = _normalize_upload_relative_path(request.data.get("path") or request.query_params.get("path") or "")
            normalized_root, root_path = _resolve_file_explorer_root(library, root_name)
            target_path = _resolve_scoped_root_path(root_path, relative_path)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not target_path.exists() and not target_path.is_symlink():
            return Response({"detail": f"Path not found inside {normalized_root}: {relative_path}"}, status=status.HTTP_404_NOT_FOUND)

        entry_type = "directory" if target_path.is_dir() and not target_path.is_symlink() else "file"
        try:
            if entry_type == "directory":
                shutil.rmtree(target_path)
            else:
                target_path.unlink()
        except OSError as exc:
            logger.warning("File explorer delete failed root=%s path=%s: %s", normalized_root, relative_path, exc)
            return Response({"detail": f"Unable to delete {relative_path}: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        cleanup = _cleanup_catalog_after_explorer_delete(library, normalized_root, relative_path)
        return Response({
            "root": normalized_root,
            "deleted_path": relative_path,
            "entry_type": entry_type,
            "catalog_cleanup": cleanup,
        })

    @action(detail=False, methods=["post"], url_path="artist-from-folder-name")
    def artist_from_folder_name(self, request):
        library = _get_or_create_default_library()
        try:
            root_name = (request.data.get("root") or "trive-In").strip()
            relative_path = _normalize_relative_target_path(request.data.get("path") or "")
            normalized_root, root_path = _resolve_file_explorer_root(library, root_name)
            target_path = _resolve_scoped_root_path(root_path, relative_path)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not relative_path:
            return Response({"detail": "Seleziona una cartella, non la root."}, status=status.HTTP_400_BAD_REQUEST)
        if not target_path.exists():
            return Response({"detail": f"Path not found inside {normalized_root}: {relative_path}"}, status=status.HTTP_404_NOT_FOUND)
        if not target_path.is_dir():
            return Response({"detail": "Artist from folder name richiede una cartella."}, status=status.HTTP_400_BAD_REQUEST)

        artist_name = Path(relative_path).name.strip()
        if not artist_name:
            return Response({"detail": "Nome cartella non valido."}, status=status.HTTP_400_BAD_REQUEST)

        media_files = (
            _explorer_media_files_for_path(library, normalized_root, relative_path)
            .prefetch_related("primary_for_tracks", "meta_values__field")
            .distinct()
        )
        user = request.user if getattr(request.user, "is_authenticated", False) else None
        updated = []

        with transaction.atomic():
            for media_file in media_files:
                if not media_file.primary_for_tracks.exists():
                    continue
                updated_fields, synced_tracks = _set_media_file_metadata(
                    media_file,
                    {"Artist": [artist_name]},
                    user=user,
                    path=request.path,
                    http_method=request.method,
                )
                updated.append({
                    "media_file": str(media_file.pk),
                    "display_path": media_file.display_path,
                    "updated_fields": updated_fields,
                    "synced_tracks": synced_tracks,
                })

        return Response({
            "root": normalized_root,
            "relative_path": relative_path,
            "artist": artist_name,
            "updated_media_file_count": len(updated),
            "updated_track_count": len({track_id for item in updated for track_id in item["synced_tracks"]}),
            "updated": updated[:200],
            "truncated": len(updated) > 200,
        })


class AccessoryFileViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = AccessoryFile.objects.select_related("library", "source_folder").filter(removed_at__isnull=True)
    serializer_class = AccessoryFileSerializer
    filterset_fields = ["library", "source_folder", "asset_kind", "extension"]
    search_fields = ["relative_path", "filename"]
    ordering_fields = ["relative_path", "filename", "asset_kind", "size", "created_at"]


class MetaFieldDefinitionViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = MetaFieldDefinition.objects.prefetch_related("values").all()
    serializer_class = MetaFieldDefinitionSerializer
    filterset_fields = ["source_family", "is_user_defined", "is_indexed"]
    search_fields = ["name", "normalized_name", "description"]
    ordering_fields = ["name", "normalized_name", "created_at"]

    @action(detail=False, methods=["get"])
    def search_groups(self, request):
        return Response(DEFAULT_META_SEARCH_GROUPS)

    @action(detail=False, methods=["get"], url_path="value-suggestions")
    def value_suggestions(self, request):
        field_name = str(request.query_params.get("field") or "").strip()
        query = str(request.query_params.get("q") or "").strip()
        try:
            limit = max(1, min(25, int(request.query_params.get("limit") or 10)))
        except (TypeError, ValueError):
            limit = 10

        normalized_field = _normalize_meta_name(field_name)
        suggestions = []
        seen = set()

        def add(value, source):
            clean = str(value or "").strip()
            key = clean.lower()
            if not clean or key in seen:
                return
            seen.add(key)
            suggestions.append({"value": clean, "source": source})

        if normalized_field in {"artist", "composer", "conductor", "executor", "bandname", "ensemblename", "orchestraname"}:
            artists = Artist.objects.all()
            if query:
                artists = artists.filter(name__icontains=query)
            for artist in artists.order_by("sort_name", "name")[:limit]:
                add(artist.name, "artist")

        if normalized_field in {"album", "seriestitle"}:
            albums = Album.objects.all()
            if query:
                albums = albums.filter(title__icontains=query)
            for album in albums.order_by("sort_title", "title")[:limit]:
                add(album.title, "album")

        if len(suggestions) < limit and normalized_field:
            values = (
                MediaFileMetaValue.objects
                .filter(field__normalized_name=normalized_field)
                .exclude(value_text="")
            )
            if query:
                values = values.filter(value_text__icontains=query)
            for value_text in values.order_by("value_text").values_list("value_text", flat=True)[:limit * 3]:
                add(value_text, "metadata")
                if len(suggestions) >= limit:
                    break

        return Response({
            "field": field_name,
            "query": query,
            "suggestions": suggestions[:limit],
        })


class MetaNormalizationRuleViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = MetaNormalizationRule.objects.select_related("target_field").all()
    serializer_class = MetaNormalizationRuleSerializer
    filterset_fields = ["source_family", "target_field", "is_active", "is_system"]
    search_fields = ["source_name", "source_name_normalized", "target_field__name"]
    ordering_fields = ["source_family", "source_name", "created_at"]


class QuickSearchViewSet(viewsets.ViewSet):

    def _score_match(self, query, values):
        query = query.lower().strip()
        best = 0
        best_value = ""
        for raw_value in values:
            value = str(raw_value or "").strip()
            if not value:
                continue
            lower_value = value.lower()
            score = 0
            if lower_value == query:
                score = 100
            elif lower_value.startswith(query):
                score = 80
            elif query in lower_value:
                score = 55
            if score > best:
                best = score
                best_value = value
        return best, best_value

    def _metadata_match(self, query, meta_values):
        best = (0, "", "")
        for meta_value in meta_values:
            candidates = [
                ("metadata", meta_value.value_text),
                ("field", getattr(meta_value.field, "name", "")),
                ("field", getattr(meta_value.field, "normalized_name", "")),
                ("source", meta_value.source_name),
                ("source", meta_value.source_name_normalized),
            ]
            for field, value in candidates:
                score, matched_value = self._score_match(query, [value])
                if score > best[0]:
                    best = (score, field, matched_value)
        return best

    def _ranked_results(self, results, limit):
        return [
            payload
            for _score, payload in sorted(results, key=lambda item: (-item[0], item[1]["kind"], item[1]["label"].lower()))
        ][:limit]

    def list(self, request):
        query = (request.query_params.get("q") or "").strip()
        library_id = request.query_params.get("library")
        scope = (request.query_params.get("scope") or "all").strip().lower()
        limit = min(max(int(request.query_params.get("limit", 8) or 8), 1), 25)
        if len(query) < 2:
            return Response({"query": query, "results": []})

        results = []

        if scope in {"all", "tracks"}:
            tracks = Track.objects.select_related("album", "primary_file").prefetch_related(
                "artist_credits__artist",
                "primary_file__meta_values__field",
            )
            if library_id:
                tracks = tracks.filter(primary_file__library_id=library_id)
            tracks = tracks.filter(
                Q(canonical_title__icontains=query)
                | Q(album__title__icontains=query)
                | Q(artist_credits__artist__name__icontains=query)
                | Q(primary_file__meta_values__value_text__icontains=query)
                | Q(primary_file__meta_values__field__name__icontains=query)
                | Q(primary_file__meta_values__field__normalized_name__icontains=query)
                | Q(primary_file__meta_values__source_name__icontains=query)
                | Q(primary_file__meta_values__source_name_normalized__icontains=query)
            ).distinct().order_by("canonical_title")[: limit * 4]
            for track in tracks:
                artist_names = [credit.artist.name for credit in track.artist_credits.all()]
                meta_score, meta_field, meta_value = self._metadata_match(
                    query,
                    track.primary_file.meta_values.all() if track.primary_file else [],
                )
                title_score, title_value = self._score_match(query, [track.canonical_title])
                album_score, album_value = self._score_match(query, [track.album.title if track.album else ""])
                artist_score, artist_value = self._score_match(query, artist_names)
                score, matched_field, matched_value = max(
                    [
                        (title_score, "title", title_value),
                        (album_score, "album", album_value),
                        (artist_score, "artist", artist_value),
                        (meta_score, meta_field or "metadata", meta_value),
                    ],
                    key=lambda item: item[0],
                )
                results.append((
                    score,
                    {
                        "kind": "track",
                        "id": str(track.pk),
                        "label": track.canonical_title,
                        "subtitle": track.album.title if track.album else "",
                        "matched_field": matched_field,
                        "matched_value": matched_value,
                    },
                ))

        if scope in {"all", "albums"}:
            albums = Album.objects.prefetch_related(
                "tracks__artist_credits__artist",
                "tracks__primary_file__meta_values__field",
            )
            if library_id:
                albums = albums.filter(tracks__primary_file__library_id=library_id).distinct()
            albums = albums.filter(
                Q(title__icontains=query)
                | Q(tracks__artist_credits__artist__name__icontains=query)
                | Q(tracks__primary_file__meta_values__value_text__icontains=query)
                | Q(tracks__primary_file__meta_values__field__name__icontains=query)
                | Q(tracks__primary_file__meta_values__field__normalized_name__icontains=query)
                | Q(tracks__primary_file__meta_values__source_name__icontains=query)
                | Q(tracks__primary_file__meta_values__source_name_normalized__icontains=query)
            ).distinct().order_by("title")[: limit * 4]
            for album in albums:
                artist_names = []
                meta_values = []
                for track in album.tracks.all():
                    artist_names.extend(credit.artist.name for credit in track.artist_credits.all())
                    if track.primary_file:
                        meta_values.extend(track.primary_file.meta_values.all())
                meta_score, meta_field, meta_value = self._metadata_match(query, meta_values)
                album_score, album_value = self._score_match(query, [album.title])
                artist_score, artist_value = self._score_match(query, artist_names)
                score, matched_field, matched_value = max(
                    [
                        (album_score, "album", album_value),
                        (artist_score, "artist", artist_value),
                        (meta_score, meta_field or "metadata", meta_value),
                    ],
                    key=lambda item: item[0],
                )
                results.append((
                    score,
                    {
                        "kind": "album",
                        "id": str(album.pk),
                        "label": album.title,
                        "subtitle": str(album.release_year or ""),
                        "matched_field": matched_field,
                        "matched_value": matched_value,
                    },
                ))

        if scope in {"all", "artists"}:
            artists = Artist.objects.prefetch_related("track_credits__track__primary_file__meta_values__field")
            if library_id:
                artists = artists.filter(track_credits__track__primary_file__library_id=library_id).distinct()
            artists = artists.filter(
                Q(name__icontains=query)
                | Q(track_credits__track__primary_file__meta_values__value_text__icontains=query)
                | Q(track_credits__track__primary_file__meta_values__field__name__icontains=query)
                | Q(track_credits__track__primary_file__meta_values__field__normalized_name__icontains=query)
                | Q(track_credits__track__primary_file__meta_values__source_name__icontains=query)
                | Q(track_credits__track__primary_file__meta_values__source_name_normalized__icontains=query)
            ).distinct().order_by("name")[: limit * 4]
            for artist in artists:
                meta_values = []
                for credit in artist.track_credits.all():
                    if credit.track.primary_file:
                        meta_values.extend(credit.track.primary_file.meta_values.all())
                meta_score, meta_field, meta_value = self._metadata_match(query, meta_values)
                artist_score, artist_value = self._score_match(query, [artist.name])
                score, matched_field, matched_value = max(
                    [
                        (artist_score, "artist", artist_value),
                        (meta_score, meta_field or "metadata", meta_value),
                    ],
                    key=lambda item: item[0],
                )
                results.append((
                    score,
                    {
                        "kind": "artist",
                        "id": str(artist.pk),
                        "label": artist.name,
                        "subtitle": "artist",
                        "matched_field": matched_field,
                        "matched_value": matched_value,
                    },
                ))

        return Response({"query": query, "results": self._ranked_results(results, limit)})


class MediaFileMetaValueViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = MediaFileMetaValue.objects.select_related("media_file", "field").all()
    serializer_class = MediaFileMetaValueSerializer
    filterset_fields = ["media_file", "field", "source_family", "is_primary"]
    search_fields = ["value_text", "field__name", "field__normalized_name", "source_name", "media_file__relative_path"]
    ordering_fields = ["field__name", "value_order", "created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        field_name = self.request.query_params.get("field_name")
        if field_name:
            normalized = "".join(character for character in field_name if character.isalnum()).lower()
            group_members = DEFAULT_META_SEARCH_GROUPS.get(normalized)
            if group_members:
                normalized_group_members = [
                    "".join(character for character in member if character.isalnum()).lower()
                    for member in group_members
                ]
                queryset = queryset.filter(field__normalized_name__in=normalized_group_members)
            else:
                queryset = queryset.filter(
                    Q(field__normalized_name=normalized) | Q(field__name__iexact=field_name)
                )
        library_id = self.request.query_params.get("library")
        if library_id:
            queryset = queryset.filter(media_file__library_id=library_id)
        return queryset


class LibraryScanSkipViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = LibraryScanSkip.objects.select_related("library", "scan_job").all()
    serializer_class = LibraryScanSkipSerializer
    filterset_fields = ["library", "scan_job", "reason_code", "extension"]
    search_fields = ["relative_path", "filename", "reason_detail"]
    ordering_fields = ["relative_path", "filename", "created_at"]


class TrackViewSet(CoverAssetMixin, LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = Track.objects.select_related("album", "primary_file").prefetch_related(
        "artist_credits__artist",
        "tag_assignments__tag_value__definition",
        "version_memberships__group__memberships",
        "primary_file__meta_values__field",
        "source_metadata",
    )
    serializer_class = TrackSerializer
    filterset_fields = ["album", "metadata_state", "release_year", "primary_file__source_folder"]
    search_fields = [
        "canonical_title",
        "canonical_sort_title",
        "album__title",
        "artist_credits__artist__name",
        "primary_file__meta_values__value_text",
        "primary_file__meta_values__field__name",
        "primary_file__meta_values__field__normalized_name",
        "primary_file__meta_values__source_name",
        "primary_file__meta_values__source_name_normalized",
    ]
    ordering_fields = ["canonical_title", "release_year", "track_number", "disc_number", "created_at"]

    def get_serializer_class(self):
        if _wants_card_payload(self.request):
            return TrackCardSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        if _wants_card_payload(self.request):
            queryset = Track.objects.select_related(
                "album",
                "primary_file",
                "primary_file__source_folder",
            ).prefetch_related(
                "source_metadata",
            )
        else:
            queryset = super().get_queryset()
        library_id = self.request.query_params.get("library")
        if library_id:
            queryset = queryset.filter(primary_file__library_id=library_id)
        starts_with = (self.request.query_params.get("starts_with") or "").strip()
        series_group_actions = {"series_groups", "series_tracks"}
        if starts_with and getattr(self, "action", "") not in series_group_actions:
            if starts_with == "#":
                queryset = queryset.filter(canonical_title__regex=r"^[^A-Za-z0-9]")
            else:
                queryset = queryset.filter(canonical_title__istartswith=starts_with)
        if self.request.query_params.get("unrevisioned") in {"1", "true", "yes"}:
            queryset = queryset.filter(
                override__isnull=True,
                primary_file__storage_stage="triv_up",
                primary_file__workflow_state="unrevisioned",
            )
        media_kind = (self.request.query_params.get("media_kind") or "").strip().lower()
        if media_kind in {"audio", "video"}:
            queryset = queryset.filter(primary_file__media_kind=media_kind)
        artist_ids = self.request.query_params.getlist("artist")
        if artist_ids:
            queryset = queryset.filter(artist_credits__artist_id__in=artist_ids).distinct()
        queryset = _apply_tag_filters(queryset, self.request)
        return queryset.distinct()

    @action(detail=True, methods=["get"], url_path="stream")
    def stream(self, request, pk=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file:
            raise Http404("Track has no primary media file.")

        file_path = _resolve_existing_media_path(media_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        if getattr(media_file, "media_kind", "audio") == "video":
            return _build_binary_stream_response(request, file_path, default_content_type="video/mp4")
        return _build_audio_stream_response(request, file_path, default_content_type="audio/mpeg")

    @action(detail=True, methods=["get"], url_path="playback")
    def playback(self, request, pk=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file:
            raise Http404("Track has no primary media file.")

        file_path = _resolve_existing_media_path(media_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        if getattr(media_file, "media_kind", "audio") == "video":
            playback_strategy = _get_track_playback_strategy(track)
            subtitle_streams = _get_track_probe_streams(track, "subtitle")
            logger.warning(
                "trive-playback request track_id=%s title=%s strategy=%s video_codec=%s audio_codec=%s subtitle_codecs=%s",
                str(track.pk),
                track.canonical_title,
                playback_strategy,
                next(iter(_get_track_probe_streams(track, "video")), {}).get("codec_name") or "",
                next(iter(_get_track_probe_streams(track, "audio")), {}).get("codec_name") or "",
                ",".join(str(stream.get("codec_name") or "") for stream in subtitle_streams),
            )
            return _build_video_playback_response(request, track, file_path, playback_strategy)
        return _build_audio_stream_response(request, file_path, default_content_type="audio/mpeg")

    @action(detail=True, methods=["get"], url_path="playback-status")
    def playback_status(self, request, pk=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file:
            raise Http404("Track has no primary media file.")

        file_path = _resolve_existing_media_path(media_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        if getattr(media_file, "media_kind", "audio") != "video":
            return Response({
                "track_id": str(track.pk),
                "media_kind": getattr(media_file, "media_kind", "audio"),
                "strategy": "direct",
                "mode": "direct",
                "cache_ready": True,
                "building": False,
            })

        playback_strategy = _get_track_playback_strategy(track)
        status_payload = _get_cached_video_playback_status(track.pk, file_path, playback_strategy, duration_seconds=track.duration_seconds)
        return Response({
            "track_id": str(track.pk),
            "media_kind": "video",
            **status_payload,
        })

    @action(detail=True, methods=["post"], url_path="prepare-playback")
    def prepare_playback(self, request, pk=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file:
            raise Http404("Track has no primary media file.")

        file_path = _resolve_existing_media_path(media_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        if getattr(media_file, "media_kind", "audio") != "video":
            return Response({
                "track_id": str(track.pk),
                "media_kind": getattr(media_file, "media_kind", "audio"),
                "strategy": "direct",
                "mode": "direct",
                "cache_ready": True,
                "building": False,
                "queue_busy": False,
            })

        playback_strategy = _get_track_playback_strategy(track)
        status_payload = _get_cached_video_playback_status(track.pk, file_path, playback_strategy, duration_seconds=track.duration_seconds)
        if (
            playback_strategy != "direct"
            and not status_payload["cache_ready"]
            and not status_payload["building"]
        ):
            _spawn_cached_video_playback_build(track.pk, file_path, playback_strategy, preempt=True)
            status_payload = _get_cached_video_playback_status(track.pk, file_path, playback_strategy, duration_seconds=track.duration_seconds)
        response_status = status.HTTP_200_OK if status_payload.get("cache_ready") else status.HTTP_202_ACCEPTED
        return Response(
            {
                "track_id": str(track.pk),
                "media_kind": "video",
                **status_payload,
            },
            status=response_status,
        )

    @action(detail=True, methods=["get"], url_path="hls/manifest")
    def hls_manifest(self, request, pk=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file:
            raise Http404("Track has no primary media file.")
        if getattr(media_file, "media_kind", "audio") != "video":
            raise Http404("HLS is available only for video items.")

        file_path = _resolve_existing_media_path(media_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        playback_strategy = _get_track_playback_strategy(track)
        if playback_strategy != "direct":
            status_payload = _get_cached_video_playback_status(track.pk, file_path, playback_strategy, duration_seconds=track.duration_seconds)
            return Response(
                {
                    "detail": "HLS generation is disabled for transcoded playback. Use playback-status and playback_url.",
                    "track_id": str(track.pk),
                    "media_kind": "video",
                    **status_payload,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        if playback_strategy == "direct":
            return Response({"detail": "HLS not required for direct playback."}, status=status.HTTP_400_BAD_REQUEST)

        cache_dir = _ensure_hls_playback_cache(track.pk, file_path, playback_strategy)
        playlist_path = cache_dir / "index.m3u8"
        try:
            playlist_text = playlist_path.read_text(encoding="utf-8")
        except OSError as exc:
            return Response({"detail": "Unable to read HLS manifest.", "error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        rewritten_lines = []
        for line in playlist_text.splitlines():
            if line.startswith("#") or not line.strip():
                rewritten_lines.append(line)
                continue
            rewritten_lines.append(f"/api/tracks/{track.pk}/hls/segment/{line.strip()}/")

        response = HttpResponse("\n".join(rewritten_lines) + "\n", content_type="application/vnd.apple.mpegurl")
        response["Cache-Control"] = "no-store"
        return response

    @action(detail=True, methods=["get"], url_path=r"hls/segment/(?P<segment_name>[^/]+)")
    def hls_segment(self, request, pk=None, segment_name=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file:
            raise Http404("Track has no primary media file.")
        if getattr(media_file, "media_kind", "audio") != "video":
            raise Http404("HLS is available only for video items.")

        file_path = _resolve_existing_media_path(media_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        playback_strategy = _get_track_playback_strategy(track)
        cache_dir = _hls_cache_dir(track.pk, playback_strategy, file_path)
        segment_path = (cache_dir / (segment_name or "")).resolve()
        if not str(segment_path).startswith(str(cache_dir.resolve())) or not segment_path.exists():
            raise Http404("HLS segment not found.")

        return FileResponse(segment_path.open("rb"), content_type="video/mp2t")

    @action(detail=True, methods=["get"], url_path=r"subtitles/(?P<stream_index>[^/.]+)")
    def subtitles(self, request, pk=None, stream_index=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file:
            raise Http404("Track has no primary media file.")
        if getattr(media_file, "media_kind", "audio") != "video":
            raise Http404("Subtitles are available only for video items.")

        file_path = _resolve_existing_media_path(media_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        subtitle_stream = next(
            (
                stream
                for stream in _enumerate_track_subtitle_streams(track, include_absolute_path=True)
                if stream.get("selector") == str(stream_index) or str(stream.get("index")) == str(stream_index)
            ),
            None,
        )
        if subtitle_stream is None:
            logger.warning(
                "trive-subtitles invalid-index track_id=%s title=%s requested=%s",
                str(track.pk),
                track.canonical_title,
                stream_index,
            )
            return Response({"detail": "Invalid subtitle stream index."}, status=status.HTTP_400_BAD_REQUEST)

        if not subtitle_stream.get("extractable"):
            return Response(
                {"detail": "Subtitle stream is not browser-extractable."},
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

        selector = subtitle_stream.get("selector") or stream_index
        cache_subject_path = file_path
        if subtitle_stream.get("source") == "external":
            cache_subject_path = Path(subtitle_stream.get("absolute_path") or "")
            if not cache_subject_path.exists() or not cache_subject_path.is_file():
                raise Http404("External subtitle file not found on disk.")

        cache_path = _subtitle_cache_path(track.pk, selector, cache_subject_path)
        logger.warning(
            "trive-subtitles request track_id=%s title=%s stream_index=%s source=%s cache=%s",
            str(track.pk),
            track.canonical_title,
            selector,
            subtitle_stream.get("source"),
            str(cache_path),
        )
        try:
            if subtitle_stream.get("source") == "external":
                extracted_path = _extract_external_subtitle_to_vtt(cache_subject_path, cache_path)
            else:
                extracted_path = _extract_subtitle_stream_to_vtt(file_path, subtitle_stream.get("index"), cache_path)
        except RuntimeError as exc:
            logger.warning(
                "trive-subtitles failed track_id=%s title=%s stream_index=%s error=%s",
                str(track.pk),
                track.canonical_title,
                selector,
                str(exc),
            )
            return Response(
                {
                    "detail": "Subtitle extraction failed.",
                    "error": str(exc),
                },
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

        response = FileResponse(extracted_path.open("rb"), content_type="text/vtt")
        response["Content-Length"] = str(extracted_path.stat().st_size)
        response["Content-Disposition"] = f'inline; filename=\"track-{track.pk}-subtitle-{selector}.vtt\"'
        logger.warning(
            "trive-subtitles ready track_id=%s title=%s stream_index=%s path=%s size=%s",
            str(track.pk),
            track.canonical_title,
            selector,
            str(extracted_path),
            extracted_path.stat().st_size,
        )
        return response

    @action(detail=True, methods=["get"], url_path="waveform")
    def waveform(self, request, pk=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file:
            raise Http404("Track has no primary media file.")

        file_path = _resolve_existing_media_path(media_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        payload = _get_or_build_waveform_payload(track, file_path)
        requested_level = request.query_params.get("level")
        if requested_level:
            level_key = str(requested_level)
            if level_key not in payload["levels"]:
                return JsonResponse(
                    {
                        "detail": "Unsupported waveform level.",
                        "available_levels": list(payload["levels"].keys()),
                    },
                    status=400,
                )
            return JsonResponse(
                {
                    "track_id": payload["track_id"],
                    "duration_seconds": payload["duration_seconds"],
                    "sample_rate": payload["sample_rate"],
                    "level": level_key,
                    "points": payload["levels"][level_key],
                    "available_levels": list(payload["levels"].keys()),
                }
            )

        return JsonResponse(payload)

    @action(detail=True, methods=["get"], url_path="cover")
    def cover(self, request, pk=None):
        track = self.get_object()
        primary_file = track.primary_file
        return self.cover_response_from_source_folder(primary_file.source_folder if primary_file else None)

    @action(detail=True, methods=["get"], url_path="poster")
    def poster(self, request, pk=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file or getattr(media_file, "media_kind", "audio") != "video":
            raise Http404("Poster is available only for video items.")

        file_path = _resolve_existing_media_path(media_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        selected_path = _selected_video_poster_path(track, file_path)
        if selected_path.exists() and selected_path.stat().st_size > 0:
            return _video_poster_response(selected_path)

        seconds = _default_video_poster_seconds(track)
        default_path = _default_video_poster_path(track, file_path)
        try:
            poster_path = _ensure_video_poster_frame(track, file_path, seconds, default_path)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            logger.warning("trive-video-poster failed track_id=%s error=%s", str(track.pk), str(exc))
            raise Http404("Unable to generate video poster.")
        return _video_poster_response(poster_path)

    @action(detail=True, methods=["get"], url_path="poster/frame")
    def poster_frame(self, request, pk=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file or getattr(media_file, "media_kind", "audio") != "video":
            raise Http404("Poster frames are available only for video items.")

        file_path = _resolve_existing_media_path(media_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        try:
            seconds = _coerce_video_poster_seconds(request.query_params.get("seconds", "0"), track)
            poster_path = _ensure_video_poster_frame(track, file_path, seconds, _candidate_video_poster_path(track, file_path, seconds))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            logger.warning("trive-video-poster-frame failed track_id=%s error=%s", str(track.pk), str(exc))
            return Response({"detail": "Impossibile generare il frame richiesto."}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        return _video_poster_response(poster_path)

    @action(detail=True, methods=["get"], url_path="poster/candidates")
    def poster_candidates(self, request, pk=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file or getattr(media_file, "media_kind", "audio") != "video":
            raise Http404("Poster candidates are available only for video items.")

        raw_count = request.query_params.get("count", "6")
        try:
            count = max(1, min(int(raw_count), 12))
        except (TypeError, ValueError):
            count = 6

        candidates = []
        for seconds in _video_poster_candidate_seconds(track, count):
            candidates.append({
                "seconds": seconds,
                "label": _format_video_poster_label(seconds),
                "url": f"/api/tracks/{track.pk}/poster/frame/?seconds={seconds}",
            })
        return Response({
            "track_id": str(track.pk),
            "duration_seconds": _track_duration_seconds(track),
            "candidates": candidates,
        })

    @action(detail=True, methods=["post"], url_path="poster/select")
    def poster_select(self, request, pk=None):
        track = self.get_object()
        media_file = track.primary_file
        if not media_file or getattr(media_file, "media_kind", "audio") != "video":
            raise Http404("Poster selection is available only for video items.")

        file_path = _resolve_existing_media_path(media_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        raw_seconds = request.data.get("seconds", request.data.get("timecode", "0"))
        try:
            seconds = _coerce_video_poster_seconds(raw_seconds, track)
            poster_path = _selected_video_poster_path(track, file_path)
            poster_path.unlink(missing_ok=True)
            poster_path = _ensure_video_poster_frame(track, file_path, seconds, poster_path)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            logger.warning("trive-video-poster-select failed track_id=%s error=%s", str(track.pk), str(exc))
            return Response({"detail": "Impossibile salvare il poster video."}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

        return Response({
            "track_id": str(track.pk),
            "seconds": seconds,
            "label": _format_video_poster_label(seconds),
            "poster_url": f"/api/tracks/{track.pk}/poster/?v={int(poster_path.stat().st_mtime)}",
        })

    @action(detail=False, methods=["get", "post"], url_path="series-poster")
    def series_poster(self, request):
        raw_series_key = request.query_params.get("series_key") if request.method == "GET" else request.data.get("series_key")
        series_key = str(raw_series_key or "").strip()
        if not series_key:
            return Response({"detail": "`series_key` richiesto."}, status=status.HTTP_400_BAD_REQUEST)

        if request.method == "GET":
            poster_path = _selected_video_series_poster_path(series_key)
            if not poster_path.exists() or poster_path.stat().st_size <= 0:
                raise Http404("Series poster not found.")
            return _video_poster_response(poster_path)

        track_id = str(request.data.get("track_id") or "").strip()
        if not track_id:
            return Response({"detail": "`track_id` richiesto."}, status=status.HTTP_400_BAD_REQUEST)

        track = (
            self.get_queryset()
            .filter(pk=track_id, primary_file__media_kind="video")
            .select_related("album", "primary_file")
            .prefetch_related(
                "tag_assignments__tag_value__definition",
                "primary_file__meta_values__field",
                "source_metadata",
            )
            .first()
        )
        if not track:
            raise Http404("Track video non trovata.")
        if _video_series_entry(track)["key"] != series_key:
            return Response({"detail": "La track selezionata non appartiene a questa serie."}, status=status.HTTP_400_BAD_REQUEST)

        file_path = _resolve_existing_media_path(track.primary_file)
        if file_path is None:
            raise Http404("Track media file not found on disk.")

        raw_seconds = request.data.get("seconds", request.data.get("timecode", "0"))
        try:
            seconds = _coerce_video_poster_seconds(raw_seconds, track)
            poster_path = _selected_video_series_poster_path(series_key)
            poster_path.unlink(missing_ok=True)
            poster_path = _ensure_video_poster_frame(track, file_path, seconds, poster_path)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            logger.warning("trive-video-series-poster-select failed series_key=%s track_id=%s error=%s", series_key, str(track.pk), str(exc))
            return Response({"detail": "Impossibile salvare il poster serie."}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

        return Response({
            "series_key": series_key,
            "track_id": str(track.pk),
            "seconds": seconds,
            "label": _format_video_poster_label(seconds),
            "poster_url": f"/api/videos/series-poster/?series_key={quote(series_key)}&v={int(poster_path.stat().st_mtime)}",
        })

    @action(detail=False, methods=["post"], url_path="auto-metadata-preview")
    def auto_metadata_preview(self, request):
        raw_track_ids = request.data.get("track_ids") or []
        if not isinstance(raw_track_ids, list):
            return Response({"detail": "`track_ids` deve essere una lista."}, status=status.HTTP_400_BAD_REQUEST)

        track_ids = [str(track_id).strip() for track_id in raw_track_ids if str(track_id).strip()]
        if not track_ids:
            return Response({"items": []})
        if len(track_ids) > 200:
            return Response({"detail": "Selezione troppo grande: massimo 200 file per preview."}, status=status.HTTP_400_BAD_REQUEST)

        tracks = (
            self.get_queryset()
            .filter(pk__in=track_ids)
            .select_related("album", "primary_file__source_folder")
            .prefetch_related("primary_file__meta_values__field")
        )
        tracks_by_id = {str(track.pk): track for track in tracks}
        items = [
            _track_auto_metadata_preview(tracks_by_id[track_id])
            for track_id in track_ids
            if track_id in tracks_by_id
        ]
        return Response({"items": items})

    @action(detail=False, methods=["post"], url_path="auto-metadata-apply")
    def auto_metadata_apply(self, request):
        try:
            items = _coerce_auto_metadata_items(request.data.get("items") or [])
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        if not items:
            return Response({"updated": [], "updated_count": 0})
        if len(items) > 200:
            return Response({"detail": "Selezione troppo grande: massimo 200 file per apply."}, status=status.HTTP_400_BAD_REQUEST)

        track_ids = [item["track_id"] for item in items]
        tracks = (
            self.get_queryset()
            .filter(pk__in=track_ids)
            .select_related("primary_file__source_folder")
            .prefetch_related("primary_file__meta_values__field")
        )
        tracks_by_id = {str(track.pk): track for track in tracks}
        user = request.user if getattr(request.user, "is_authenticated", False) else None
        updated = []

        with transaction.atomic():
            for item in items:
                track = tracks_by_id.get(item["track_id"])
                media_file = track.primary_file if track else None
                if not media_file:
                    updated.append({
                        "track_id": item["track_id"],
                        "status": "skipped",
                        "detail": "Track senza primary file.",
                    })
                    continue
                updated_fields, synced_tracks = _set_media_file_metadata(
                    media_file,
                    item["metadata"],
                    user=user,
                    path=request.path,
                    http_method=request.method,
                )
                updated.append({
                    "track_id": str(track.pk),
                    "media_file_id": str(media_file.pk),
                    "status": "updated",
                    "updated_fields": updated_fields,
                    "synced_tracks": synced_tracks,
                })

        return Response({"updated": updated, "updated_count": len([item for item in updated if item["status"] == "updated"])})

    @action(detail=False, methods=["get"], url_path="series-groups")
    def series_groups(self, request):
        queryset = (
            self.filter_queryset(self.get_queryset())
            .filter(primary_file__media_kind="video")
            .select_related("album", "primary_file__source_folder")
            .prefetch_related(
                "artist_credits__artist",
                "primary_file__meta_values__field",
                "tag_assignments__tag_value__definition",
                "version_memberships__group__memberships",
                "source_metadata",
            )
        )

        groups = {}
        for track in queryset:
            entry = _video_series_entry(track)
            group = groups.setdefault(entry["key"], {
                "id": entry["key"],
                "series_key": entry["key"],
                "group_kind": entry["kind"],
                "title": entry["title"],
                "entries": [],
                "duration_seconds": 0,
                "season_numbers": set(),
                "episode_count": 0,
            })
            group["entries"].append(entry)
            group["duration_seconds"] += track.duration_seconds or 0
            if entry["season_number"] is not None:
                group["season_numbers"].add(entry["season_number"])
            if entry["episode_number"] is not None:
                group["episode_count"] += 1

        starts_with = (request.query_params.get("starts_with") or "").strip()
        section_filter = (request.query_params.get("section") or "").strip().lower()
        curation_system = (request.query_params.get("curation_system") or "").strip().lower()
        tag_value_filter = str(request.query_params.get("tag_value") or "").strip()
        group_rows = []
        for group in groups.values():
            if starts_with:
                title = str(group["title"] or "")
                if starts_with == "#":
                    if re.match(r"^[A-Za-z0-9]", title):
                        continue
                elif not title.lower().startswith(starts_with.lower()):
                    continue

            entries = sorted(group["entries"], key=_video_series_track_sort_key)
            group_tracks = [entry["track"] for entry in entries]
            section = _video_section_for_group(group["group_kind"], group_tracks)
            if tag_value_filter and not any(
                any(str(assignment.tag_value_id) == tag_value_filter for assignment in track.tag_assignments.all())
                for track in group_tracks
            ):
                continue
            if section_filter and section != section_filter:
                continue
            representative = entries[0]["track"]
            season_numbers = sorted(group["season_numbers"])
            latest_created_at = max([
                getattr(getattr(track, "primary_file", None), "created_at", None) or track.created_at
                for track in group_tracks
            ] or [representative.created_at])
            group_rows.append({
                **group,
                "_entries": entries,
                "_group_tracks": group_tracks,
                "_section": section,
                "_representative": representative,
                "_season_numbers": season_numbers,
                "_latest_created_at": latest_created_at,
            })

        if curation_system == "recently":
            group_rows.sort(key=lambda item: (item["_latest_created_at"] or item["_representative"].created_at, item["title"].lower()), reverse=True)
        else:
            section_order = {"movies": 0, "series": 1, "uncategorized": 2}
            group_rows.sort(key=lambda item: (section_order.get(item.get("_section"), 99), item["title"].lower(), item["id"]))

        card_payload = _wants_card_payload(request)
        serializer_class = TrackCardSerializer if card_payload else TrackSerializer

        def serialize_group(group):
            representative = group["_representative"]
            representative_payload = serializer_class(representative, context=self.get_serializer_context()).data
            representative_playback_status = representative_payload.get("playback_status") or {}
            series_cover_url = _selected_video_series_poster_url(group["series_key"]) or representative_payload.get("cover_url") or ""
            version_groups = {
                membership.group_id: membership.group
                for track in group["_group_tracks"]
                for membership in track.version_memberships.all()
            }
            entries = group["_entries"]
            return {
                "id": group["id"],
                "series_key": group["series_key"],
                "group_kind": group["group_kind"],
                "section": group["_section"],
                "title": group["title"],
                "track_count": len(entries),
                "episode_count": group["episode_count"] or len(entries),
                "season_count": len(group["_season_numbers"]),
                "season_numbers": group["_season_numbers"],
                "duration_seconds": round(group["duration_seconds"], 3),
                "cover_url": series_cover_url,
                "recently_added_at": group["_latest_created_at"].isoformat() if group["_latest_created_at"] else "",
                "playback_cache_ready": bool(representative_playback_status.get("cache_ready", True)),
                "playback_status": representative_playback_status,
                "version_count": max([version_group.memberships.count() for version_group in version_groups.values()] or [0]),
                "representative_track": representative_payload,
                "first_episode_title": entries[0].get("episode_title") or representative.canonical_title or "",
            }

        page = self.paginate_queryset(group_rows)
        if page is not None:
            return self.get_paginated_response([serialize_group(group) for group in page])
        return Response([serialize_group(group) for group in group_rows])

    @action(detail=False, methods=["get"], url_path="series-tracks")
    def series_tracks(self, request):
        series_key = str(request.query_params.get("series_key") or "").strip()
        if not series_key:
            return Response({"detail": "`series_key` richiesto."}, status=status.HTTP_400_BAD_REQUEST)

        queryset = (
            self.filter_queryset(self.get_queryset())
            .filter(primary_file__media_kind="video")
            .select_related("album", "primary_file__source_folder")
            .prefetch_related(
                "artist_credits__artist",
                "primary_file__meta_values__field",
                "tag_assignments__tag_value__definition",
                "source_metadata",
            )
        )
        entries = [
            entry
            for track in queryset
            for entry in [_video_series_entry(track)]
            if entry["key"] == series_key
        ]
        entries.sort(key=_video_series_track_sort_key)
        tracks = [entry["track"] for entry in entries]
        return Response(TrackSerializer(tracks, many=True, context=self.get_serializer_context()).data)


class VideoViewSet(TrackViewSet):
    def get_queryset(self):
        return super().get_queryset().filter(primary_file__media_kind="video")


class AlbumViewSet(CoverAssetMixin, LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = Album.objects.prefetch_related("tracks", "tag_assignments__tag_value__definition").all()
    serializer_class = AlbumSerializer
    filterset_fields = ["release_year"]
    search_fields = [
        "title",
        "sort_title",
        "triver_notes",
        "tracks__artist_credits__artist__name",
        "tracks__primary_file__meta_values__value_text",
        "tracks__primary_file__meta_values__field__name",
        "tracks__primary_file__meta_values__field__normalized_name",
        "tracks__primary_file__meta_values__source_name",
        "tracks__primary_file__meta_values__source_name_normalized",
    ]
    ordering_fields = ["title", "sort_title", "release_year", "created_at"]

    def get_serializer_class(self):
        if _wants_card_payload(self.request):
            return AlbumCardSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        queryset = Album.objects.all() if _wants_card_payload(self.request) else super().get_queryset()
        library_id = self.request.query_params.get("library")
        if library_id:
            queryset = queryset.filter(tracks__primary_file__library_id=library_id).distinct()
        starts_with = (self.request.query_params.get("starts_with") or "").strip()
        if starts_with:
            if starts_with == "#":
                queryset = queryset.filter(title__regex=r"^[^A-Za-z0-9]")
            else:
                queryset = queryset.filter(title__istartswith=starts_with)
        media_kind = (self.request.query_params.get("media_kind") or "").strip().lower()
        if media_kind in {"audio", "video"}:
            queryset = queryset.filter(tracks__primary_file__media_kind=media_kind).distinct()
        queryset = _apply_tag_filters(queryset, self.request)
        return queryset.distinct()

    @action(detail=True, methods=["get"], url_path="cover")
    def cover(self, request, pk=None):
        album = self.get_object()
        track = album.tracks.select_related("primary_file__source_folder").first()
        primary_file = track.primary_file if track else None
        return self.cover_response_from_source_folder(primary_file.source_folder if primary_file else None)

    @action(detail=True, methods=["get", "patch"], url_path="metadata")
    def metadata(self, request, pk=None):
        album = self.get_object()
        if request.method == "GET":
            return Response({
                "album": AlbumSerializer(album, context=self.get_serializer_context()).data,
                "metadata": _album_metadata_summary(album),
            })

        user = request.user if getattr(request.user, "is_authenticated", False) else None
        try:
            metadata = _metadata_payload_from_request(request)
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        media_files = (
            MediaFile.objects
            .filter(primary_for_tracks__album=album)
            .distinct()
            .prefetch_related("meta_values__field")
        )

        with transaction.atomic():
            updated = []
            for media_file in media_files:
                updated_fields, synced_tracks = _set_media_file_metadata(
                    media_file,
                    metadata,
                    user=user,
                    path=request.path,
                    http_method=request.method,
                )
                updated.append({
                    "media_file": str(media_file.pk),
                    "display_path": media_file.display_path,
                    "updated_fields": updated_fields,
                    "synced_tracks": synced_tracks,
                })

        return Response({
            "album": str(album.pk),
            "updated_media_file_count": len(updated),
            "updated": updated,
        })

    @action(detail=False, methods=["post"], url_path="merge")
    def merge(self, request):
        album_ids = request.data.get("album_ids") or []
        target_title = str(request.data.get("target_title") or "").strip()
        release_date_resolution = request.data.get("release_date_resolution", None)
        has_release_date_resolution = "release_date_resolution" in request.data

        if not isinstance(album_ids, list) or len(album_ids) < 2:
            return Response({"detail": "Seleziona almeno due album."}, status=status.HTTP_400_BAD_REQUEST)
        if not target_title:
            return Response({"detail": "Titolo album target mancante."}, status=status.HTTP_400_BAD_REQUEST)

        albums = list(Album.objects.filter(pk__in=album_ids))
        if len(albums) < 2:
            return Response({"detail": "Album selezionati non trovati."}, status=status.HTTP_400_BAD_REQUEST)

        tracks = list(
            Track.objects
            .filter(album_id__in=[album.pk for album in albums], primary_file__isnull=False)
            .select_related("album", "primary_file")
            .prefetch_related("primary_file__meta_values__field")
            .distinct()
        )
        if not tracks:
            return Response({"detail": "Nessuna traccia indicizzata negli album selezionati."}, status=status.HTTP_400_BAD_REQUEST)

        release_buckets = {}
        for track in tracks:
            media_metadata = _metadata_from_media_file(track.primary_file)
            release_value = _first_metadata_value(media_metadata, "ReleaseDate")
            release_year = _parse_year(release_value)
            if release_value in {None, ""} and track.release_year:
                release_value = str(track.release_year)
                release_year = track.release_year
            if release_value in {None, ""} and track.album and track.album.release_year:
                release_value = str(track.album.release_year)
                release_year = track.album.release_year
            key = str(release_year or release_value or "").strip()
            if not key:
                key = ""
            bucket = release_buckets.setdefault(key, {"value": key, "track_count": 0, "tracks": []})
            bucket["track_count"] += 1
            bucket["tracks"].append({
                "id": str(track.pk),
                "title": track.canonical_title,
                "album": track.album.title if track.album else "",
            })

        conflicting_values = [key for key in release_buckets.keys() if key]
        if len(set(conflicting_values)) > 1 and not has_release_date_resolution:
            options = [
                {"value": bucket["value"], "label": bucket["value"], "track_count": bucket["track_count"]}
                for key, bucket in sorted(release_buckets.items(), key=lambda item: (-item[1]["track_count"], item[0]))
                if key
            ]
            options.append({"value": "", "label": "Clear release date", "track_count": len(tracks)})
            return Response({
                "detail": "release_date_conflict",
                "message": "Gli album selezionati hanno ReleaseDate/anno diversi. Scegli come normalizzarli prima del merge.",
                "conflict_type": "release_date",
                "target_title": target_title,
                "options": options,
                "buckets": list(release_buckets.values()),
            }, status=status.HTTP_409_CONFLICT)

        metadata = {"Album": [target_title]}
        if has_release_date_resolution:
            clean_release_date = str(release_date_resolution or "").strip()
            metadata["ReleaseDate"] = [clean_release_date] if clean_release_date else []

        user = request.user if getattr(request.user, "is_authenticated", False) else None
        media_files = []
        seen_media_file_ids = set()
        for track in tracks:
            if track.primary_file_id and track.primary_file_id not in seen_media_file_ids:
                seen_media_file_ids.add(track.primary_file_id)
                media_files.append(track.primary_file)

        updated = []
        with transaction.atomic():
            for media_file in media_files:
                updated_fields, synced_tracks = _set_media_file_metadata(
                    media_file,
                    metadata,
                    user=user,
                    path=request.path,
                    http_method=request.method,
                )
                if has_release_date_resolution and not metadata["ReleaseDate"]:
                    Track.objects.filter(primary_file=media_file).update(release_year=None)
                updated.append({
                    "media_file": str(media_file.pk),
                    "display_path": media_file.display_path,
                    "updated_fields": updated_fields,
                    "synced_tracks": synced_tracks,
                })

        return Response({
            "target_title": target_title,
            "updated_media_file_count": len(updated),
            "updated_track_count": len({track_id for item in updated for track_id in item["synced_tracks"]}),
            "updated": updated[:200],
            "truncated": len(updated) > 200,
        })


class ArtistViewSet(CoverAssetMixin, LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = Artist.objects.select_related("selected_cover_album", "selected_profile_image").prefetch_related("track_credits", "tag_assignments__tag_value__definition").all()
    serializer_class = ArtistSerializer
    search_fields = [
        "name",
        "sort_name",
        "triver_notes",
        "track_credits__track__primary_file__meta_values__value_text",
        "track_credits__track__primary_file__meta_values__field__name",
        "track_credits__track__primary_file__meta_values__field__normalized_name",
        "track_credits__track__primary_file__meta_values__source_name",
        "track_credits__track__primary_file__meta_values__source_name_normalized",
    ]
    ordering_fields = ["name", "sort_name", "created_at"]

    def get_serializer_class(self):
        if _wants_card_payload(self.request):
            return ArtistCardSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        queryset = Artist.objects.all() if _wants_card_payload(self.request) else super().get_queryset()
        library_id = self.request.query_params.get("library")
        if library_id:
            queryset = queryset.filter(track_credits__track__primary_file__library_id=library_id).distinct()
        requested_roles = []
        for raw_role in self.request.query_params.getlist("role"):
            requested_roles.extend(str(raw_role or "").split(","))
        role_aliases = {
            "artist": TrackArtistCredit.ROLE_PRIMARY,
            "artists": TrackArtistCredit.ROLE_PRIMARY,
            "author": TrackArtistCredit.ROLE_COMPOSER,
            "authors": TrackArtistCredit.ROLE_COMPOSER,
            "executor": TrackArtistCredit.ROLE_PERFORMER,
            "executors": TrackArtistCredit.ROLE_PERFORMER,
            "performers": TrackArtistCredit.ROLE_PERFORMER,
        }
        valid_roles = {choice[0] for choice in TrackArtistCredit.ROLE_CHOICES}
        roles = []
        for raw_role in requested_roles:
            role = str(raw_role or "").strip().lower()
            role = role_aliases.get(role, role)
            if role and role != "all" and role in valid_roles:
                roles.append(role)
        if roles:
            queryset = queryset.filter(track_credits__role__in=roles).distinct()
        media_kind = (self.request.query_params.get("media_kind") or "").strip().lower()
        if media_kind in {"audio", "video"}:
            queryset = queryset.filter(track_credits__track__primary_file__media_kind=media_kind).distinct()
        starts_with = (self.request.query_params.get("starts_with") or "").strip()
        if starts_with:
            if starts_with == "#":
                queryset = queryset.filter(name__regex=r"^[^A-Za-z0-9]")
            else:
                queryset = queryset.filter(name__istartswith=starts_with)
        queryset = _apply_tag_filters(queryset, self.request)
        return queryset.distinct()

    def _artist_album_cover_candidates(self, artist):
        library_id = self.request.query_params.get("library")
        tracks = (
            Track.objects
            .filter(artist_credits__artist=artist, album__isnull=False)
            .select_related("album", "primary_file__source_folder")
            .order_by("album__sort_title", "album__title", "disc_number", "track_number")
        )
        if library_id:
            tracks = tracks.filter(primary_file__library_id=library_id)

        candidates = []
        seen_album_ids = set()
        for track in tracks:
            album = track.album
            if not album or album.pk in seen_album_ids:
                continue
            seen_album_ids.add(album.pk)
            source_folder = _album_cover_source_folder(album)
            if not source_folder or not source_folder.get_best_cover_accessory():
                continue
            candidates.append({
                "id": str(album.pk),
                "kind": "album",
                "album_id": str(album.pk),
                "profile_image_id": "",
                "title": album.title,
                "subtitle": str(album.release_year or ""),
                "cover_url": f"/api/albums/{album.pk}/cover/",
                "selected": artist.selected_cover_mode == "album" and artist.selected_cover_album_id == album.pk,
            })
        return candidates

    def _artist_upload_cover_candidates(self, artist):
        return [
            {
                "id": str(profile_image.pk),
                "kind": "upload",
                "album_id": "",
                "profile_image_id": str(profile_image.pk),
                "title": profile_image.original_filename or "Immagine caricata",
                "subtitle": profile_image.created_at.isoformat() if profile_image.created_at else "",
                "cover_url": f"/api/artists/{artist.pk}/profile-images/{profile_image.pk}/",
                "selected": artist.selected_cover_mode == "upload" and artist.selected_profile_image_id == profile_image.pk,
            }
            for profile_image in artist.profile_images.all()
            if _resolve_artist_profile_image_path(profile_image) is not None
        ]

    def _artist_cover_candidates(self, artist):
        auto_source_folder = _artist_auto_cover_source_folder(artist)
        candidates = []
        if auto_source_folder and auto_source_folder.get_best_cover_accessory():
            candidates.append({
                "id": "auto",
                "kind": "auto",
                "album_id": "",
                "profile_image_id": "",
                "title": "Auto",
                "subtitle": "Prima cover disponibile",
                "cover_url": f"/api/artists/{artist.pk}/cover/?mode=auto",
                "selected": artist.selected_cover_mode == "auto",
            })
        candidates.extend(self._artist_album_cover_candidates(artist))
        candidates.extend(self._artist_upload_cover_candidates(artist))
        return {
            "selected_mode": artist.selected_cover_mode,
            "selected_album": str(artist.selected_cover_album_id or ""),
            "selected_profile_image": str(artist.selected_profile_image_id or ""),
            "candidates": candidates,
        }

    def _cover_response_for_selection(self, artist, mode=None, album_id=None, profile_image_id=None):
        selected_mode = mode or artist.selected_cover_mode
        if selected_mode == "upload":
            profile_image = None
            if profile_image_id:
                profile_image = _safe_filter_first(artist.profile_images, pk=profile_image_id)
            elif artist.selected_profile_image_id:
                profile_image = artist.selected_profile_image
            profile_path = _resolve_artist_profile_image_path(profile_image)
            if profile_path:
                return self.file_response_from_path(profile_path, getattr(profile_image, "content_type", "") or None)

        if selected_mode == "album":
            album = None
            if album_id:
                album = _safe_filter_first(Album.objects, pk=album_id)
            elif artist.selected_cover_album_id:
                album = artist.selected_cover_album
            response = self.cover_response_from_source_folder(_album_cover_source_folder(album))
            if response.status_code != 404:
                return response

        return self.cover_response_from_source_folder(_artist_auto_cover_source_folder(artist))

    @action(detail=True, methods=["get"], url_path="cover")
    def cover(self, request, pk=None):
        artist = self.get_object()
        return self._cover_response_for_selection(
            artist,
            mode=request.query_params.get("mode"),
            album_id=request.query_params.get("album"),
            profile_image_id=request.query_params.get("image"),
        )

    @action(detail=True, methods=["get"], url_path="cover-candidates")
    def cover_candidates(self, request, pk=None):
        artist = self.get_object()
        return Response(self._artist_cover_candidates(artist))

    @action(detail=True, methods=["get"], url_path=r"profile-images/(?P<image_id>[^/.]+)")
    def profile_image(self, request, pk=None, image_id=None):
        artist = self.get_object()
        profile_image = _safe_filter_first(artist.profile_images, pk=image_id)
        profile_path = _resolve_artist_profile_image_path(profile_image)
        if not profile_path:
            raise Http404("Artist profile image not found.")
        return self.file_response_from_path(profile_path, profile_image.content_type or None)

    @action(detail=True, methods=["post"], url_path="profile-image")
    def upload_profile_image(self, request, pk=None):
        artist = self.get_object()
        uploaded_file = request.FILES.get("image") or next(iter(request.FILES.values()), None)
        user = request.user if getattr(request.user, "is_authenticated", False) else None
        try:
            profile_image = _save_artist_profile_image(
                artist,
                uploaded_file,
                user=user,
                path=request.path,
                http_method=request.method,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        artist.selected_cover_mode = "upload"
        artist.selected_profile_image = profile_image
        artist.selected_cover_album = None
        artist.save(user=user, path=request.path, http_method=request.method)
        refreshed = self.get_queryset().get(pk=artist.pk)
        return Response({
            "artist": self.get_serializer(refreshed).data,
            "image": ArtistProfileImageSerializer(profile_image, context=self.get_serializer_context()).data,
            "cover_candidates": self._artist_cover_candidates(refreshed),
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="cover-selection")
    def cover_selection(self, request, pk=None):
        artist = self.get_object()
        mode = str(request.data.get("mode") or "auto").strip()
        user = request.user if getattr(request.user, "is_authenticated", False) else None

        if mode == "auto":
            artist.selected_cover_mode = "auto"
            artist.selected_cover_album = None
            artist.selected_profile_image = None
        elif mode == "album":
            album_id = request.data.get("album_id")
            album = _safe_filter_first(Album.objects, pk=album_id)
            if not album or not album.tracks.filter(artist_credits__artist=artist).exists():
                return Response({"detail": "Album non valido per questo artista."}, status=status.HTTP_400_BAD_REQUEST)
            artist.selected_cover_mode = "album"
            artist.selected_cover_album = album
            artist.selected_profile_image = None
        elif mode == "upload":
            profile_image_id = request.data.get("profile_image_id")
            profile_image = _safe_filter_first(artist.profile_images, pk=profile_image_id)
            if not profile_image:
                return Response({"detail": "Immagine caricata non valida per questo artista."}, status=status.HTTP_400_BAD_REQUEST)
            artist.selected_cover_mode = "upload"
            artist.selected_profile_image = profile_image
            artist.selected_cover_album = None
        else:
            return Response({"detail": "Modalita' cover non valida."}, status=status.HTTP_400_BAD_REQUEST)

        artist.save(user=user, path=request.path, http_method=request.method)
        refreshed = self.get_queryset().get(pk=artist.pk)
        return Response({
            "artist": self.get_serializer(refreshed).data,
            "cover_candidates": self._artist_cover_candidates(refreshed),
        })

    @action(detail=True, methods=["post"], url_path="bio-suggestion")
    def bio_suggestion(self, request, pk=None):
        artist = self.get_object()
        language = str(request.data.get("language") or "it").strip().lower()
        suggestion = _build_artist_bio_suggestion(artist, language=language)
        if not suggestion.get("draft"):
            return Response(
                {"detail": "Nessuna bio trovata dai provider online configurati.", **suggestion},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(suggestion)


class VideoCurationSettingsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=["get", "patch"], url_path="current")
    def current(self, request):
        settings_row = VideoCurationSettings.load()
        if request.method == "GET":
            return Response(_video_curation_settings_payload(settings_row))
        if not getattr(request.user, "is_authenticated", False):
            return Response({"detail": "Authentication required."}, status=status.HTTP_403_FORBIDDEN)

        row_order = request.data.get("row_order")
        if row_order is None:
            row_order = request.data.get("rows")
        if not isinstance(row_order, list):
            return Response({"detail": "row_order must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        settings_row.row_order = _video_curation_refs_from_row_order(row_order)
        settings_row.save(
            user=request.user if getattr(request.user, "is_authenticated", False) else None,
            path=request.path,
            http_method=request.method,
        )
        return Response(_video_curation_settings_payload(settings_row))


class TagDefinitionViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = TagDefinition.objects.all()
    serializer_class = TagDefinitionSerializer
    filterset_fields = ["scope", "value_type", "visibility", "owner"]
    search_fields = ["key", "label", "description"]
    ordering_fields = ["scope", "key", "visibility", "created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user if getattr(self.request.user, "is_authenticated", False) else None
        if user:
            return queryset.filter(Q(visibility=TagDefinition.VISIBILITY_GLOBAL) | Q(owner=user))
        return queryset.filter(visibility=TagDefinition.VISIBILITY_GLOBAL)

    def perform_create(self, serializer):
        user = self.request.user if getattr(self.request.user, "is_authenticated", False) else None
        visibility = serializer.validated_data.get("visibility") or TagDefinition.VISIBILITY_GLOBAL
        if visibility == TagDefinition.VISIBILITY_PERSONAL:
            if not user:
                raise APIValidationError("Personal tags require an authenticated user.")
            serializer.save(owner=user, user=user, path=self.request.path, http_method=self.request.method)
            return
        serializer.save(owner=None, user=user, path=self.request.path, http_method=self.request.method)


class TagValueViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = TagValue.objects.select_related("definition").all()
    serializer_class = TagValueSerializer
    filterset_fields = ["definition"]
    search_fields = ["value_text", "normalized_key"]
    ordering_fields = ["display_order", "value_text", "created_at"]


class TrackTagAssignmentViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = TrackTagAssignment.objects.select_related("track", "tag_value__definition").all()
    serializer_class = TrackTagAssignmentSerializer
    filterset_fields = ["track", "tag_value__definition"]


class AlbumTagAssignmentViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = AlbumTagAssignment.objects.select_related("album", "tag_value__definition").all()
    serializer_class = AlbumTagAssignmentSerializer
    filterset_fields = ["album", "tag_value__definition"]


class ArtistTagAssignmentViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = ArtistTagAssignment.objects.select_related("artist", "tag_value__definition").all()
    serializer_class = ArtistTagAssignmentSerializer
    filterset_fields = ["artist", "tag_value__definition"]


def _version_base_text(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"\.[a-z0-9]{2,5}$", "", text)
    text = re.sub(
        r"[\(\[\{][^\)\]\}]{0,96}(remaster|version|edit|mix|live|take|demo|mono|stereo|explicit|clean|extended|radio|instrumental|acoustic|alternate)[^\)\]\}]*[\)\]\}]",
        " ",
        text,
    )
    text = re.sub(
        r"\b(remaster(?:ed)?|version|edit|mix|live|take|demo|mono|stereo|explicit|clean|extended|radio|instrumental|acoustic|alternate)\b",
        " ",
        text,
    )
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"\s+", " ", text)


def _version_duration_bucket(track):
    if track.duration_seconds is None:
        return None
    try:
        return int(round(float(track.duration_seconds) / 2.0) * 2)
    except (TypeError, ValueError):
        return None


def _version_artist_names(track):
    return {
        str(credit.artist.name or "").strip().lower()
        for credit in track.artist_credits.all()
        if getattr(credit, "artist", None) and str(credit.artist.name or "").strip()
    }


def _version_track_fingerprint(track_ids):
    stable_ids = sorted(str(track_id) for track_id in track_ids)
    digest = hashlib.sha1("|".join(stable_ids).encode("utf-8")).hexdigest()
    return f"track-candidate:{digest}"


def _tracks_already_share_version_group(tracks):
    member_sets = []
    for track in tracks:
        group_ids = {membership.group_id for membership in track.version_memberships.all()}
        member_sets.append(group_ids)
    return bool(member_sets and set.intersection(*member_sets))


def _version_candidate_payload(tracks, context):
    unique_tracks = list({track.pk: track for track in tracks}.values())
    if len(unique_tracks) < 2 or _tracks_already_share_version_group(unique_tracks):
        return None

    durations = []
    for track in unique_tracks:
        if track.duration_seconds is not None:
            try:
                durations.append(float(track.duration_seconds))
            except (TypeError, ValueError):
                pass

    score = 0.45
    reasons = ["similar title"]
    if len(durations) == len(unique_tracks):
        spread = max(durations) - min(durations)
        if spread <= 2:
            score += 0.25
            reasons.append("duration within 2 seconds")
        elif spread <= 5:
            score += 0.15
            reasons.append("duration within 5 seconds")

    album_keys = {_version_base_text(track.album.title) for track in unique_tracks if track.album}
    album_keys.discard("")
    if len(album_keys) == 1:
        score += 0.1
        reasons.append("same album name")
    elif len(album_keys) > 1:
        album_values = list(album_keys)
        if any(left in right or right in left for index, left in enumerate(album_values) for right in album_values[index + 1:]):
            score += 0.06
            reasons.append("partially matching album names")

    artist_sets = [_version_artist_names(track) for track in unique_tracks]
    if artist_sets and set.intersection(*artist_sets):
        score += 0.1
        reasons.append("artist overlap")

    hashes = [track.primary_file.content_hash for track in unique_tracks if track.primary_file and track.primary_file.content_hash]
    if len(hashes) != len(set(hashes)):
        score += 0.3
        reasons.append("identical file hash")

    if score < 0.55:
        return None

    sorted_tracks = sorted(unique_tracks, key=lambda item: (str(item.canonical_sort_title or item.canonical_title).lower(), str(item.pk)))
    fingerprint = _version_track_fingerprint([track.pk for track in sorted_tracks])
    title = sorted_tracks[0].canonical_title or "Possible Versions"
    return {
        "fingerprint": fingerprint,
        "title": title,
        "score": round(min(score, 0.99), 2),
        "reasons": reasons,
        "track_count": len(sorted_tracks),
        "tracks": TrackSerializer(sorted_tracks, many=True, context=context).data,
    }


def _build_track_version_candidates(library, context, limit=80):
    tracks = list(
        Track.objects
        .filter(primary_file__library=library, primary_file__removed_at__isnull=True)
        .select_related("album", "primary_file")
        .prefetch_related(
            "artist_credits__artist",
            "tag_assignments__tag_value__definition",
            "version_memberships__group__memberships",
        )
        .order_by("canonical_sort_title", "canonical_title", "id")
    )
    strict_buckets = {}
    title_buckets = {}
    for track in tracks:
        base_title = _version_base_text(track.canonical_title)
        if len(base_title) < 4:
            continue
        media_kind = track.primary_file.media_kind if track.primary_file else ""
        title_buckets.setdefault((media_kind, base_title), []).append(track)
        duration_bucket = _version_duration_bucket(track)
        if duration_bucket is not None:
            strict_buckets.setdefault((media_kind, base_title, duration_bucket), []).append(track)

    ignored_fingerprints = set(TrackVersionCandidateDecision.objects.values_list("fingerprint", flat=True))
    accepted_fingerprints = set(TrackVersionGroup.objects.exclude(fingerprint="").values_list("fingerprint", flat=True))
    ignored_fingerprints.update(accepted_fingerprints)

    candidates_by_fingerprint = {}
    for bucket_tracks in list(strict_buckets.values()) + list(title_buckets.values()):
        if len(bucket_tracks) < 2:
            continue
        candidate = _version_candidate_payload(bucket_tracks, context)
        if not candidate or candidate["fingerprint"] in ignored_fingerprints:
            continue
        existing = candidates_by_fingerprint.get(candidate["fingerprint"])
        if not existing or candidate["score"] > existing["score"]:
            candidates_by_fingerprint[candidate["fingerprint"]] = candidate

    candidates = sorted(
        candidates_by_fingerprint.values(),
        key=lambda item: (-item["score"], -item["track_count"], item["title"].lower()),
    )
    return candidates[:limit]


class TrackDedupJobViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = TrackDedupJob.objects.select_related("library").all()
    serializer_class = TrackDedupJobSerializer
    filterset_fields = ["library", "status", "mode"]
    ordering_fields = ["created_at", "started_at", "finished_at", "status", "candidate_count"]

    @action(detail=False, methods=["post"], url_path="start-scan")
    def start_scan(self, request):
        library = _get_or_create_default_library()
        active_job = self.get_queryset().filter(
            library=library,
            status__in=[TrackDedupJob.STATUS_PENDING, TrackDedupJob.STATUS_RUNNING],
        ).first()
        if active_job is not None:
            payload = self.get_serializer(active_job).data
            payload["detail"] = "A Dedup Worker job is already active."
            return Response(payload, status=status.HTTP_409_CONFLICT)

        job = TrackDedupJob.objects.create(
            library=library,
            status=TrackDedupJob.STATUS_PENDING,
            mode=TrackDedupJob.MODE_CANDIDATE_SCAN,
        )
        try:
            async_result = run_dedup_candidate_scan.delay(str(job.pk))
        except Exception:
            async_result = run_dedup_candidate_scan.apply(args=[str(job.pk)])
        payload = self.get_serializer(job).data
        payload["celery_task_id"] = async_result.id
        return Response(payload, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        job = self.get_object()
        if job.status in {TrackDedupJob.STATUS_DONE, TrackDedupJob.STATUS_ERROR, TrackDedupJob.STATUS_CANCELED}:
            return Response(self.get_serializer(job).data)
        job.status = TrackDedupJob.STATUS_CANCELED
        job.finished_at = timezone.now()
        job.last_error = "Canceled by user."
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post"], url_path="full-throttle")
    def full_throttle(self, request, pk=None):
        job = self.get_object()
        try:
            duration_seconds = int(request.data.get("duration_seconds") or 600)
        except (TypeError, ValueError):
            duration_seconds = 600
        duration_seconds = max(60, min(duration_seconds, 3600))
        job.full_throttle_until = timezone.now() + datetime.timedelta(seconds=duration_seconds)
        job.save(update_fields=["full_throttle_until", "updated_at"])
        return Response(self.get_serializer(job).data)

    @action(detail=False, methods=["get"])
    def latest(self, request):
        library = _get_or_create_default_library()
        job = self.get_queryset().filter(library=library).first()
        if job is None:
            return Response({"detail": "No dedup job found yet."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(job).data)


class TrackDedupCandidateViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = TrackDedupCandidate.objects.select_related("library", "job").all()
    serializer_class = TrackDedupCandidateSerializer
    filterset_fields = ["library", "status", "fingerprint"]
    search_fields = ["title", "fingerprint", "notes"]
    ordering_fields = ["score", "title", "created_at", "updated_at"]

    @action(detail=False, methods=["get"])
    def pending(self, request):
        library = _get_or_create_default_library()
        candidates = self.get_queryset().filter(library=library, status=TrackDedupCandidate.STATUS_PENDING).order_by("-score", "title")[:100]
        return Response(self.get_serializer(candidates, many=True).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        candidate = self.get_object()
        candidate.status = TrackDedupCandidate.STATUS_REJECTED
        candidate.notes = str(request.data.get("notes") or candidate.notes or "")
        candidate.save(update_fields=["status", "notes", "updated_at"])
        return Response(self.get_serializer(candidate).data)

    @action(detail=True, methods=["post"], url_path="accept-as-versions")
    def accept_as_versions(self, request, pk=None):
        candidate = self.get_object()
        track_ids = [str(track_id) for track_id in (candidate.track_ids or [])]
        tracks = list(
            Track.objects
            .filter(pk__in=track_ids)
            .select_related("album", "primary_file")
            .order_by("canonical_sort_title", "canonical_title")
        )
        if len(tracks) < 2:
            return Response({"detail": "Candidate tracks not found."}, status=status.HTTP_400_BAD_REQUEST)

        track_by_id = {str(track.pk): track for track in tracks}
        ordered_tracks = [track_by_id[track_id] for track_id in track_ids if track_id in track_by_id]
        if len(ordered_tracks) < 2:
            ordered_tracks = tracks

        with transaction.atomic():
            group, _created = TrackVersionGroup.objects.get_or_create(
                fingerprint=candidate.fingerprint.replace("dedup:", "dedup-version:"),
                defaults={
                    "title": candidate.title or ordered_tracks[0].canonical_title or "Version Group",
                    "sort_title": _version_base_text(candidate.title or ordered_tracks[0].canonical_title),
                    "serving_mode": TrackVersionGroup.SERVING_PRIMARY,
                },
            )
            for index, track in enumerate(ordered_tracks):
                TrackVersionMembership.objects.update_or_create(
                    group=group,
                    track=track,
                    defaults={
                        "role": TrackVersionMembership.ROLE_PRIMARY if index == 0 else TrackVersionMembership.ROLE_ALTERNATE,
                        "sort_order": index,
                        "is_default": index == 0,
                    },
                )
            candidate.status = TrackDedupCandidate.STATUS_ACCEPTED
            candidate.notes = str(request.data.get("notes") or candidate.notes or "")
            candidate.save(update_fields=["status", "notes", "updated_at"])

        return Response(self.get_serializer(candidate).data)


def _metadata_enrichment_scope_for_tracks(track_ids):
    media_kinds = set(
        Track.objects
        .filter(pk__in=track_ids)
        .select_related("primary_file")
        .values_list("primary_file__media_kind", flat=True)
    )
    media_kinds.discard(None)
    if media_kinds == {"audio"}:
        return MetadataEnrichmentJob.MEDIA_SCOPE_AUDIO
    if media_kinds == {"video"}:
        return MetadataEnrichmentJob.MEDIA_SCOPE_VIDEO
    return MetadataEnrichmentJob.MEDIA_SCOPE_MIXED


def _filter_remote_metadata_for_policy(media_file, metadata, policy):
    incoming = {
        str(field_name).strip(): values
        for field_name, values in (metadata or {}).items()
        if str(field_name).strip()
    }
    if policy != RemoteMetadataSettings.OVERWRITE_MISSING_ONLY:
        return incoming

    existing = _metadata_from_media_file(media_file)
    filtered = {}
    for field_name, values in incoming.items():
        existing_value = _first_metadata_value(existing, field_name)
        existing_values = _metadata_values(existing, field_name)
        if existing_value or existing_values:
            continue
        filtered[field_name] = values
    return filtered


class RemoteMetadataSettingsViewSet(LoggedViewSetMixin):
    serializer_class = RemoteMetadataSettingsSerializer

    def get_queryset(self):
        return RemoteMetadataSettings.objects.all()

    def list(self, request):
        settings_row = RemoteMetadataSettings.load()
        return Response(self.get_serializer(settings_row).data)

    @action(detail=False, methods=["get", "patch"], url_path="current")
    def current(self, request):
        settings_row = RemoteMetadataSettings.load()
        if request.method == "GET":
            payload = self.get_serializer(settings_row).data
            payload["env"] = settings_snapshot_from_env()
            return Response(payload)

        serializer = self.get_serializer(settings_row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            user=request.user if getattr(request.user, "is_authenticated", False) else None,
            path=request.path,
            http_method=request.method,
        )
        payload = serializer.data
        payload["env"] = settings_snapshot_from_env()
        return Response(payload)


class MetadataEnrichmentJobViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = MetadataEnrichmentJob.objects.select_related("library", "requested_by").all()
    serializer_class = MetadataEnrichmentJobSerializer
    filterset_fields = ["library", "status", "mode", "media_scope", "provider_key"]
    ordering_fields = ["created_at", "started_at", "finished_at", "status", "candidate_count", "updated_count"]

    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request):
        raw_track_ids = request.data.get("track_ids") or []
        if not isinstance(raw_track_ids, list):
            return Response({"detail": "`track_ids` must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        track_ids = [str(track_id).strip() for track_id in raw_track_ids if str(track_id).strip()]
        if not track_ids:
            return Response({"detail": "Select at least one item."}, status=status.HTTP_400_BAD_REQUEST)
        if len(track_ids) > 50:
            return Response({"detail": "Remote metadata lookup is limited to 50 items per job."}, status=status.HTTP_400_BAD_REQUEST)

        settings_row = RemoteMetadataSettings.load()
        mode = str(request.data.get("mode") or MetadataEnrichmentJob.MODE_FIND).strip()
        if mode not in {MetadataEnrichmentJob.MODE_FIND, MetadataEnrichmentJob.MODE_REFRESH, MetadataEnrichmentJob.MODE_FIX_MATCH}:
            mode = MetadataEnrichmentJob.MODE_FIND
        provider_key = str(request.data.get("provider_key") or "").strip().lower()
        overwrite_policy = str(request.data.get("overwrite_policy") or settings_row.overwrite_policy).strip()
        if overwrite_policy not in {choice[0] for choice in RemoteMetadataSettings.OVERWRITE_CHOICES}:
            overwrite_policy = settings_row.overwrite_policy

        library = _get_or_create_default_library()
        job = MetadataEnrichmentJob.objects.create(
            library=library,
            requested_by=request.user if getattr(request.user, "is_authenticated", False) else None,
            status=MetadataEnrichmentJob.STATUS_PENDING,
            mode=mode,
            media_scope=_metadata_enrichment_scope_for_tracks(track_ids),
            provider_key=provider_key,
            overwrite_policy=overwrite_policy,
            target_track_ids=track_ids,
        )
        try:
            async_result = run_metadata_enrichment_job.delay(str(job.pk))
        except Exception:
            async_result = run_metadata_enrichment_job.apply(args=[str(job.pk)])
        payload = self.get_serializer(job).data
        payload["celery_task_id"] = async_result.id
        return Response(payload, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        job = self.get_object()
        if job.status in {MetadataEnrichmentJob.STATUS_DONE, MetadataEnrichmentJob.STATUS_ERROR, MetadataEnrichmentJob.STATUS_CANCELED}:
            return Response(self.get_serializer(job).data)
        job.status = MetadataEnrichmentJob.STATUS_CANCELED
        job.finished_at = timezone.now()
        job.last_error = "Canceled by user."
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        job = self.get_object()
        raw_items = request.data.get("items") or []
        if not isinstance(raw_items, list):
            return Response({"detail": "`items` must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        if len(raw_items) > 50:
            return Response({"detail": "Remote metadata apply is limited to 50 items."}, status=status.HTTP_400_BAD_REQUEST)

        track_ids = [str(item.get("track_id") or "").strip() for item in raw_items if isinstance(item, dict)]
        tracks = (
            Track.objects
            .filter(pk__in=track_ids)
            .select_related("primary_file")
            .prefetch_related("primary_file__meta_values__field")
        )
        tracks_by_id = {str(track.pk): track for track in tracks}
        user = request.user if getattr(request.user, "is_authenticated", False) else None
        updated = []
        updated_count = 0

        with transaction.atomic():
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                track_id = str(item.get("track_id") or "").strip()
                track = tracks_by_id.get(track_id)
                media_file = track.primary_file if track else None
                if not media_file:
                    updated.append({"track_id": track_id, "status": "skipped", "detail": "Track has no media file."})
                    continue
                metadata = item.get("metadata") or {}
                if not isinstance(metadata, dict):
                    updated.append({"track_id": track_id, "status": "skipped", "detail": "Invalid metadata payload."})
                    continue
                policy = str(item.get("overwrite_policy") or job.overwrite_policy or RemoteMetadataSettings.OVERWRITE_MISSING_ONLY)
                filtered_metadata = _filter_remote_metadata_for_policy(media_file, metadata, policy)
                if not filtered_metadata:
                    updated.append({"track_id": track_id, "status": "skipped", "detail": "No missing or approved fields to apply."})
                    continue
                updated_fields, synced_tracks = _set_media_file_metadata(
                    media_file,
                    filtered_metadata,
                    user=user,
                    path=request.path,
                    http_method=request.method,
                )
                updated_count += 1
                updated.append({
                    "track_id": track_id,
                    "media_file_id": str(media_file.pk),
                    "status": "updated",
                    "match_id": str(item.get("match_id") or ""),
                    "updated_fields": updated_fields,
                    "synced_tracks": synced_tracks,
                })

        job.updated_count = updated_count
        result_payload = dict(job.result_payload or {})
        result_payload["apply_result"] = updated
        job.result_payload = result_payload
        job.save(update_fields=["updated_count", "result_payload", "updated_at"])
        return Response({"updated": updated, "updated_count": updated_count})

    @action(detail=False, methods=["get"])
    def latest(self, request):
        job = self.get_queryset().first()
        if job is None:
            return Response({"detail": "No metadata enrichment job found yet."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(job).data)


class TrackVersionGroupViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = TrackVersionGroup.objects.prefetch_related("memberships__track").all()
    serializer_class = TrackVersionGroupSerializer
    filterset_fields = ["serving_mode", "fingerprint"]
    search_fields = ["title", "sort_title", "fingerprint", "notes"]
    ordering_fields = ["title", "sort_title", "created_at", "updated_at"]

    @action(detail=False, methods=["get"], url_path="candidates")
    def candidates(self, request):
        library = _get_or_create_default_library()
        candidates = _build_track_version_candidates(library, self.get_serializer_context())
        existing_groups = (
            TrackVersionGroup.objects
            .prefetch_related("memberships__track")
            .exclude(memberships__isnull=True)
            .distinct()
            .order_by("-updated_at")[:80]
        )
        return Response({
            "candidates": candidates,
            "candidate_count": len(candidates),
            "existing_groups": TrackVersionGroupSerializer(existing_groups, many=True, context=self.get_serializer_context()).data,
        })

    @action(detail=False, methods=["post"], url_path="accept-candidate")
    def accept_candidate(self, request):
        fingerprint = str(request.data.get("fingerprint") or "").strip()
        track_ids = request.data.get("track_ids") or []
        title = str(request.data.get("title") or "").strip()
        if not fingerprint:
            return Response({"detail": "Missing candidate fingerprint."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(track_ids, list) or len(track_ids) < 2:
            return Response({"detail": "Select at least two tracks."}, status=status.HTTP_400_BAD_REQUEST)

        tracks = list(
            Track.objects
            .filter(pk__in=track_ids)
            .select_related("album", "primary_file")
            .order_by("canonical_sort_title", "canonical_title")
        )
        if len(tracks) < 2:
            return Response({"detail": "Version candidate tracks not found."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            group, _created = TrackVersionGroup.objects.get_or_create(
                fingerprint=fingerprint,
                defaults={
                    "title": title or tracks[0].canonical_title or "Version Group",
                    "sort_title": _version_base_text(title or tracks[0].canonical_title),
                    "serving_mode": TrackVersionGroup.SERVING_PRIMARY,
                },
            )
            if title and group.title != title:
                group.title = title
                group.sort_title = _version_base_text(title)
                group.save(update_fields=["title", "sort_title", "updated_at"])

            for index, track in enumerate(tracks):
                TrackVersionMembership.objects.update_or_create(
                    group=group,
                    track=track,
                    defaults={
                        "role": TrackVersionMembership.ROLE_PRIMARY if index == 0 else TrackVersionMembership.ROLE_ALTERNATE,
                        "sort_order": index,
                        "is_default": index == 0,
                    },
                )
            TrackVersionCandidateDecision.objects.update_or_create(
                fingerprint=fingerprint,
                defaults={"status": TrackVersionCandidateDecision.STATUS_ACCEPTED, "group": group},
            )

        refreshed = TrackVersionGroup.objects.prefetch_related("memberships__track").get(pk=group.pk)
        return Response(TrackVersionGroupSerializer(refreshed, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["post"], url_path="reject-candidate")
    def reject_candidate(self, request):
        fingerprint = str(request.data.get("fingerprint") or "").strip()
        if not fingerprint:
            return Response({"detail": "Missing candidate fingerprint."}, status=status.HTTP_400_BAD_REQUEST)
        TrackVersionCandidateDecision.objects.update_or_create(
            fingerprint=fingerprint,
            defaults={"status": TrackVersionCandidateDecision.STATUS_REJECTED, "group": None},
        )
        return Response({"fingerprint": fingerprint, "status": "rejected"})

    @action(detail=False, methods=["post"], url_path="delete-track")
    def delete_track(self, request):
        track_id = request.data.get("track_id")
        if not request.data.get("confirm"):
            return Response({"detail": "Deletion requires confirm=true."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            track = Track.objects.select_related("primary_file__library").get(pk=track_id)
        except Track.DoesNotExist:
            return Response({"detail": "Track not found."}, status=status.HTTP_404_NOT_FOUND)

        media_file = track.primary_file
        deleted_path = ""
        with transaction.atomic():
            if media_file:
                existing_path = _resolve_existing_media_path(media_file)
                if existing_path:
                    deleted_path = str(existing_path)
                    existing_path.unlink(missing_ok=True)
                media_file.removed_at = timezone.now()
                media_file.status = MediaFile.STATUS_MISSING
                media_file.save(update_fields=["removed_at", "status", "updated_at"])
            track.delete()

        return Response({"deleted_track_id": str(track_id), "deleted_path": deleted_path})


class TrackVersionMembershipViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = TrackVersionMembership.objects.select_related("group", "track").all()
    serializer_class = TrackVersionMembershipSerializer
    filterset_fields = ["group", "track", "role", "is_default"]
    ordering_fields = ["group", "sort_order", "created_at"]


class SavedPlaylistViewSet(LoggedViewSetMixin, BidirectionalRelationMixin):
    queryset = SavedPlaylist.objects.select_related("library").prefetch_related(
        "entries__track__album",
        "entries__track__primary_file",
        "entries__track__artist_credits__artist",
        "entries__track__tag_assignments__tag_value__definition",
    ).all()
    serializer_class = SavedPlaylistSerializer
    filterset_fields = ["library"]
    search_fields = ["name", "notes"]
    ordering_fields = ["name", "updated_at", "created_at"]
