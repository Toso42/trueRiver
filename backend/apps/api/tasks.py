from __future__ import annotations

import logging
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="playback", acks_late=True)
def build_cached_video_playback(
    self,
    track_id,
    file_path,
    playback_strategy,
    lock_path,
    global_lock_path,
):
    from apps.api.views import (
        _ensure_cached_video_playback,
        _release_playback_build_lock,
    )

    lock_path = Path(lock_path)
    global_lock_path = Path(global_lock_path)
    try:
        _ensure_cached_video_playback(
            track_id,
            Path(file_path),
            playback_strategy,
            acquired_lock_path=lock_path,
            acquired_global_lock_path=global_lock_path,
        )
    except Exception as exc:
        logger.warning(
            "trive-playback queued-build-failed track_id=%s strategy=%s task_id=%s error=%s",
            track_id,
            playback_strategy,
            self.request.id,
            str(exc),
        )
        raise
    finally:
        _release_playback_build_lock(lock_path)
        _release_playback_build_lock(global_lock_path)
