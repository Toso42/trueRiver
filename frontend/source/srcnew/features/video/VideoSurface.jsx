import { useEffect, useMemo, useRef, useState } from 'react';
import Hls from 'hls.js';
import { isVideoItem } from '../media/mediaItem';
import { getJson, writeJson } from '../../api/client';

function buildVideoSources(track) {
  if (!track) {
    return { manifestUrl: '', directUrl: '' };
  }
  return {
    manifestUrl: track.hls_manifest_url ? new URL(track.hls_manifest_url, window.location.origin).href : '',
    directUrl: (track.playback_url || track.video_stream_url || track.stream_url || '')
      ? new URL(track.playback_url || track.video_stream_url || track.stream_url || '', window.location.origin).href
      : '',
  };
}

export default function VideoSurface({ track = null }) {
  const isVideo = isVideoItem(track);
  const { manifestUrl, directUrl } = useMemo(() => buildVideoSources(track), [track]);
  const extractableSubtitles = useMemo(
    () => (track?.subtitle_streams || []).filter((subtitle) => subtitle?.extractable && subtitle?.url),
    [track?.subtitle_streams],
  );
  const videoRef = useRef(null);
  const [playbackStatus, setPlaybackStatus] = useState(null);
  const [sourceNonce, setSourceNonce] = useState(0);
  const [switchedToCached, setSwitchedToCached] = useState(false);
  const [pendingResume, setPendingResume] = useState(null);
  const [surfaceMode, setSurfaceMode] = useState('direct');
  const [subtitleIndex, setSubtitleIndex] = useState(0);
  const prepareRequestedTrackRef = useRef('');
  const needsPlaybackPreparation = Boolean(isVideo && track?.playback_strategy && track.playback_strategy !== 'direct');
  const playbackReady = !needsPlaybackPreparation || Boolean(playbackStatus?.cache_ready);
  const playbackProgress = playbackStatus?.progress || track?.playback_status?.progress || null;
  const playbackPreparationMessage = playbackStatus?.queue_busy
    ? 'Another video is being prepared. Selecting this item moves it to the front.'
    : playbackStatus?.message || track?.playback_status?.message || 'The server is preparing a playable copy. Playback will start when it is ready.';
  const activeManifestUrl = playbackReady ? manifestUrl : '';
  const activeDirectUrl = playbackReady ? directUrl : '';

  useEffect(() => {
    setPlaybackStatus(track?.playback_status || null);
    prepareRequestedTrackRef.current = '';
    setSourceNonce(0);
    setSwitchedToCached(false);
    setPendingResume(null);
    setSurfaceMode('direct');
  }, [track?.id]);

  useEffect(() => {
    const defaultIndex = extractableSubtitles.findIndex((subtitle) => subtitle?.default);
    setSubtitleIndex(defaultIndex >= 0 ? defaultIndex + 1 : 0);
  }, [track?.id, extractableSubtitles]);

  useEffect(() => {
    if (!track?.id || !isVideo || !track.playback_strategy || track.playback_strategy === 'direct') {
      setPlaybackStatus(null);
      return undefined;
    }

    let cancelled = false;
    let intervalId = null;

    async function pollStatus() {
      try {
        const payload = await getJson(`/api/tracks/${track.id}/playback-status/`, 'Unable to read playback status');
        if (!cancelled) {
          setPlaybackStatus(payload);
        }
      } catch (_error) {
        if (!cancelled) {
          setPlaybackStatus(null);
        }
      }
    }

    pollStatus();
    intervalId = window.setInterval(pollStatus, 2000);

    return () => {
      cancelled = true;
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [isVideo, track?.id, track?.playback_strategy]);

  useEffect(() => {
    if (
      !track?.id
      || !needsPlaybackPreparation
      || playbackStatus?.cache_ready
      || playbackStatus?.building
      || prepareRequestedTrackRef.current === String(track.id)
    ) {
      return undefined;
    }

    let cancelled = false;
    prepareRequestedTrackRef.current = String(track.id);

    async function preparePlayback() {
      try {
        const payload = await writeJson(
          `/api/tracks/${track.id}/prepare-playback/`,
          'POST',
          {},
          'Unable to prepare video playback',
        );
        if (!cancelled) {
          setPlaybackStatus(payload);
          if (!payload?.cache_ready && !payload?.building) {
            prepareRequestedTrackRef.current = '';
          }
        }
      } catch (_error) {
        if (!cancelled) {
          prepareRequestedTrackRef.current = '';
          setPlaybackStatus((current) => current);
        }
      }
    }

    preparePlayback();
    return () => {
      cancelled = true;
    };
  }, [
    needsPlaybackPreparation,
    playbackStatus?.building,
    playbackStatus?.cache_ready,
    track?.id,
  ]);

  useEffect(() => {
    if (!playbackStatus?.cache_ready || switchedToCached || !videoRef.current || !track?.id) {
      return;
    }

    const video = videoRef.current;
    const resumeTime = Number(video.currentTime) || 0;
    const shouldResumePlayback = !video.paused;

    setPendingResume({
      time: resumeTime,
      autoplay: shouldResumePlayback,
    });
    setSwitchedToCached(true);
    setSourceNonce((current) => current + 1);
    return undefined;
  }, [playbackStatus?.cache_ready, switchedToCached, track?.id]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !track?.id) {
      return undefined;
    }

    const nativeHlsSupported = video.canPlayType('application/vnd.apple.mpegurl');
    const shouldUseHls = Boolean(activeManifestUrl && (nativeHlsSupported || Hls.isSupported()));

    if (!shouldUseHls) {
      setSurfaceMode(playbackReady ? 'direct' : 'preparing');
      if (video.src !== activeDirectUrl) {
        video.src = activeDirectUrl || '';
      }
      return undefined;
    }

    if (nativeHlsSupported) {
      setSurfaceMode('hls-native');
      if (video.src !== activeManifestUrl) {
        video.src = activeManifestUrl;
      }
      return undefined;
    }

    const hls = new Hls({
      enableWorker: true,
      backBufferLength: 90,
    });
    setSurfaceMode('hls-js');
    hls.loadSource(activeManifestUrl);
    hls.attachMedia(video);
    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (data?.fatal) {
        setSurfaceMode('direct');
        hls.destroy();
        if (video.src !== activeDirectUrl) {
          video.src = activeDirectUrl || '';
        }
      }
    });

    return () => {
      hls.destroy();
    };
  }, [activeDirectUrl, activeManifestUrl, playbackReady, sourceNonce, track?.id]);

  const handleLoadedMetadata = () => {
    const video = videoRef.current;
    if (video) {
      const tracks = Array.from(video.textTracks || []);
      tracks.forEach((textTrack, index) => {
        textTrack.mode = subtitleIndex > 0 && index === subtitleIndex - 1 ? 'showing' : 'disabled';
      });
    }

    if (video && pendingResume) {
      try {
        if (pendingResume.time > 0) {
          video.currentTime = pendingResume.time;
        }
      } catch (_error) {
        // no-op
      }
      if (pendingResume.autoplay) {
        video.play().catch(() => {});
      }
      setPendingResume(null);
    }
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    const tracks = Array.from(video.textTracks || []);
    tracks.forEach((textTrack, index) => {
      textTrack.mode = subtitleIndex > 0 && index === subtitleIndex - 1 ? 'showing' : 'disabled';
    });
  }, [subtitleIndex, sourceNonce, track?.id]);

  if (!track || !isVideo) {
    return null;
  }

  return (
    <section className="video-surface-panel" aria-label="Video surface">
      <div className="video-surface-stage">
        {(activeManifestUrl || activeDirectUrl) ? (
          <video
            key={`${track.id || directUrl || manifestUrl}:${sourceNonce}`}
            ref={videoRef}
            className="video-surface-player"
            controls
            preload="metadata"
            poster={track.poster_url || track.cover_url || ''}
            onLoadedMetadata={handleLoadedMetadata}
          >
            {(track.subtitle_streams || []).map((subtitle) => (
              subtitle?.url && subtitle?.extractable ? (
                <track
                  key={subtitle.index ?? subtitle.url}
                  kind="subtitles"
                  src={new URL(subtitle.url, window.location.origin).href}
                  srcLang={subtitle.language || 'und'}
                  label={subtitle.title || subtitle.language || `Subtitle ${subtitle.index}`}
                  default={Boolean(subtitle.default)}
                />
              ) : null
            ))}
          </video>
        ) : (
          <div className="video-surface-empty">
            <strong>{needsPlaybackPreparation ? 'Preparing video playback' : 'No playable video stream'}</strong>
            <span>
              {needsPlaybackPreparation
                ? playbackPreparationMessage
                : 'The item is marked as video, but no stream URL is available yet.'}
            </span>
            {needsPlaybackPreparation ? (
              <div className="video-cache-progress" aria-label="Video preparation progress">
                <span style={{ width: `${Math.max(0, Math.min(100, playbackProgress?.percent || 0))}%` }} />
                <small>{Math.max(0, Math.min(100, playbackProgress?.percent || 0))}% ready</small>
              </div>
            ) : null}
          </div>
        )}
      </div>
      <div className="video-surface-info">
        <div className="video-surface-title-block">
          <h3>{track.canonical_title || track.title || 'Untitled video item'}</h3>
          {track.album_title ? <p>{track.album_title}</p> : null}
        </div>
        <div className="video-surface-controls">
          <label className="video-surface-subtitle-control">
            <span>Subtitles</span>
            <select
              value={subtitleIndex}
              onChange={(event) => setSubtitleIndex(Number(event.target.value) || 0)}
              disabled={!extractableSubtitles.length}
            >
              <option value={0}>Off</option>
              {extractableSubtitles.map((subtitle, index) => (
                <option key={subtitle.selector || subtitle.url || index} value={index + 1}>
                  {subtitle.title || subtitle.language || `Subtitle ${index + 1}`}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="video-surface-meta">
          {track.width && track.height ? <span>{track.width}x{track.height}</span> : null}
          {track.fps ? <span>{track.fps} fps</span> : null}
          {track.video_codec ? <span>video: {track.video_codec}</span> : null}
          {track.audio_codec ? <span>audio: {track.audio_codec}</span> : null}
          {track.playback_strategy ? <span>strategy: {track.playback_strategy}</span> : null}
          {playbackStatus?.mode ? <span>mode: {playbackStatus.mode}</span> : null}
          <span>surface: {surfaceMode}</span>
          {track.subtitle_strategy ? <span>subs: {track.subtitle_strategy}</span> : null}
          {track.subtitle_streams?.length ? <span>subs: {extractableSubtitles.length}/{track.subtitle_streams.length}</span> : null}
          {track.browser_playable === false ? <span>browser decode limited</span> : null}
        </div>
      </div>
      {track.subtitle_strategy === 'burn_required' ? (
        <div className="video-surface-subtitle-warning">
          Embedded subtitles detected, but they are not browser-extractable.
          {(track.subtitle_streams || []).length ? ` Codecs: ${(track.subtitle_streams || []).map((subtitle) => subtitle.codec).filter(Boolean).join(', ')}.` : ''}
          {' '}Burn-in or OCR is required.
        </div>
      ) : null}
    </section>
  );
}
