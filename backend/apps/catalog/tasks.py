from __future__ import annotations

import hashlib
import re
import time
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Track, TrackDedupCandidate, TrackDedupJob
from apps.catalog.remote_metadata import run_metadata_enrichment_job_sync


def _positive_int_setting(name: str, default: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return max(1, default)
    return max(1, value)


def _non_negative_float_setting(name: str, default: float) -> float:
    try:
        value = float(getattr(settings, name, default))
    except (TypeError, ValueError):
        return max(0.0, default)
    return max(0.0, value)


def _dedup_base_text(value: str) -> str:
    normalized = re.sub(r"\b(remaster(?:ed)?|remix|mono|stereo|live|edit|version|bonus|demo)\b", " ", str(value or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _duration_bucket(track: Track):
    if track.duration_seconds is None:
        return None
    try:
        return round(float(track.duration_seconds) / 2) * 2
    except (TypeError, ValueError):
        return None


def _artist_names(track: Track):
    return {
        credit.artist.name.lower()
        for credit in track.artist_credits.all()
        if credit.artist and credit.artist.name
    }


def _candidate_fingerprint(track_ids, reason_key: str):
    stable = "|".join(sorted(str(track_id) for track_id in track_ids))
    digest = hashlib.sha1(f"{reason_key}:{stable}".encode("utf-8")).hexdigest()
    return f"dedup:{digest}"


def _candidate_payload(bucket_tracks, reason_key: str, base_score: float, reasons):
    unique_tracks = list({str(track.pk): track for track in bucket_tracks}.values())
    if len(unique_tracks) < 2:
        return None

    durations = []
    for track in unique_tracks:
        if track.duration_seconds is not None:
            try:
                durations.append(float(track.duration_seconds))
            except (TypeError, ValueError):
                pass

    score = base_score
    reason_list = list(reasons)
    if len(durations) == len(unique_tracks):
        spread = max(durations) - min(durations)
        if spread <= 1:
            score += 0.1
            reason_list.append("duration within 1 second")
        elif spread <= 3:
            score += 0.06
            reason_list.append("duration within 3 seconds")

    sizes = [
        int(track.primary_file.size)
        for track in unique_tracks
        if track.primary_file and track.primary_file.size
    ]
    if len(sizes) == len(unique_tracks) and len(set(sizes)) == 1:
        score += 0.12
        reason_list.append("same file size")

    artist_sets = [_artist_names(track) for track in unique_tracks]
    if artist_sets and set.intersection(*artist_sets):
        score += 0.08
        reason_list.append("artist overlap")

    sorted_tracks = sorted(unique_tracks, key=lambda item: (str(item.canonical_sort_title or item.canonical_title).lower(), str(item.pk)))
    return {
        "fingerprint": _candidate_fingerprint([track.pk for track in sorted_tracks], reason_key),
        "title": sorted_tracks[0].canonical_title or "Possible duplicates",
        "score": min(score, 0.99),
        "reasons": reason_list,
        "track_ids": [str(track.pk) for track in sorted_tracks],
    }


def _job_full_throttle(job: TrackDedupJob) -> bool:
    return bool(job.full_throttle_until and job.full_throttle_until > timezone.now())


def _dedup_pause(job: TrackDedupJob, scanned_count: int):
    if _job_full_throttle(job):
        return
    every = _positive_int_setting("TRIVER_DEDUP_SCAN_SLEEP_EVERY", 25)
    if scanned_count % every == 0:
        seconds = _non_negative_float_setting("TRIVER_DEDUP_SCAN_SLEEP_SECONDS", 0.05)
        if seconds > 0:
            time.sleep(seconds)


@shared_task(bind=True)
def run_dedup_candidate_scan(self, job_id: str):
    job = TrackDedupJob.objects.select_related("library").get(pk=job_id)
    job.status = TrackDedupJob.STATUS_RUNNING
    job.started_at = timezone.now()
    job.finished_at = None
    job.scanned_count = 0
    job.candidate_count = 0
    job.last_error = ""
    job.save(update_fields=["status", "started_at", "finished_at", "scanned_count", "candidate_count", "last_error", "updated_at"])

    try:
        tracks = list(
            Track.objects
            .filter(primary_file__library=job.library, primary_file__removed_at__isnull=True)
            .select_related("album", "primary_file")
            .prefetch_related("artist_credits__artist")
            .order_by("canonical_sort_title", "canonical_title", "id")
        )
        buckets = {}
        scanned_count = 0

        for track in tracks:
            if TrackDedupJob.objects.filter(pk=job.pk, status=TrackDedupJob.STATUS_CANCELED).exists():
                job.refresh_from_db()
                return {"job_id": str(job.pk), "status": job.status, "scanned_count": scanned_count}

            scanned_count += 1
            title_key = _dedup_base_text(track.canonical_title)
            media_kind = track.primary_file.media_kind if track.primary_file else ""
            if len(title_key) >= 4:
                duration_bucket = _duration_bucket(track)
                if duration_bucket is not None:
                    buckets.setdefault(("title_duration", media_kind, title_key, duration_bucket), []).append(track)
                if track.primary_file and track.primary_file.size:
                    buckets.setdefault(("title_size", media_kind, title_key, int(track.primary_file.size)), []).append(track)

            if track.primary_file and track.primary_file.content_hash:
                buckets.setdefault(("content_hash", media_kind, track.primary_file.content_hash), []).append(track)

            if scanned_count % 25 == 0:
                TrackDedupJob.objects.filter(pk=job.pk).update(scanned_count=scanned_count, updated_at=timezone.now())
            _dedup_pause(job, scanned_count)

        candidates_by_fingerprint = {}
        for bucket_key, bucket_tracks in buckets.items():
            if len(bucket_tracks) < 2:
                continue
            reason_type = bucket_key[0]
            if reason_type == "content_hash":
                payload = _candidate_payload(bucket_tracks, "content_hash", 0.9, ["same existing content hash"])
            elif reason_type == "title_size":
                payload = _candidate_payload(bucket_tracks, "title_size", 0.62, ["similar title", "same file size"])
            else:
                payload = _candidate_payload(bucket_tracks, "title_duration", 0.58, ["similar title", "similar duration"])
            if not payload:
                continue
            existing = candidates_by_fingerprint.get(payload["fingerprint"])
            if not existing or payload["score"] > existing["score"]:
                candidates_by_fingerprint[payload["fingerprint"]] = payload

        candidate_limit = _positive_int_setting("TRIVER_DEDUP_MAX_CANDIDATES", 200)
        candidates = sorted(
            candidates_by_fingerprint.values(),
            key=lambda item: (-item["score"], item["title"].lower()),
        )[:candidate_limit]

        created_or_updated_count = 0
        with transaction.atomic():
            for payload in candidates:
                existing = TrackDedupCandidate.objects.filter(fingerprint=payload["fingerprint"]).first()
                if existing and existing.status != TrackDedupCandidate.STATUS_PENDING:
                    continue
                TrackDedupCandidate.objects.update_or_create(
                    fingerprint=payload["fingerprint"],
                    defaults={
                        "library": job.library,
                        "job": job,
                        "status": TrackDedupCandidate.STATUS_PENDING,
                        "title": payload["title"],
                        "score": Decimal(str(round(payload["score"], 2))),
                        "reasons": payload["reasons"],
                        "track_ids": payload["track_ids"],
                    },
                )
                created_or_updated_count += 1

        job.status = TrackDedupJob.STATUS_DONE
        job.finished_at = timezone.now()
        job.scanned_count = scanned_count
        job.candidate_count = created_or_updated_count
        job.save(update_fields=["status", "finished_at", "scanned_count", "candidate_count", "updated_at"])
        return {
            "job_id": str(job.pk),
            "status": job.status,
            "scanned_count": scanned_count,
            "candidate_count": created_or_updated_count,
        }
    except Exception as exc:
        job.status = TrackDedupJob.STATUS_ERROR
        job.finished_at = timezone.now()
        job.last_error = str(exc)
        job.save(update_fields=["status", "finished_at", "last_error", "updated_at"])
        raise


@shared_task(bind=True)
def run_metadata_enrichment_job(self, job_id: str):
    return run_metadata_enrichment_job_sync(job_id)
