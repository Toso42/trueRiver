import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchVideoPosterCandidates, selectVideoPosterFrame, selectVideoSeriesPosterFrame } from '../../../api/library';

export default function VideoPosterSelectorModal({
  track = null,
  seriesKey = '',
  mode = 'track',
  title = '',
  onSelected = null,
  onClose = () => {},
}) {
  const [candidates, setCandidates] = useState([]);
  const [timecode, setTimecode] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  const trackId = track?.id || '';
  const isSeriesMode = mode === 'series';

  const loadCandidates = useCallback(async () => {
    if (!trackId) {
      return;
    }
    setCandidates([]);
    setError('');
    setLoading(true);
    try {
      const payload = await fetchVideoPosterCandidates(trackId, 8);
      setCandidates(payload.candidates || []);
    } catch (nextError) {
      setError(nextError.message || 'Unable to read video frames');
    } finally {
      setLoading(false);
    }
  }, [trackId]);

  useEffect(() => {
    loadCandidates();
  }, [loadCandidates, reloadKey]);

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const previewUrl = useMemo(() => {
    const trimmed = timecode.trim();
    if (!trackId || !trimmed) {
      return '';
    }
    return `/api/tracks/${trackId}/poster/frame/?seconds=${encodeURIComponent(trimmed)}`;
  }, [timecode, trackId]);

  async function saveSelection(seconds) {
    if (!trackId) {
      return;
    }
    setSaving(true);
    setError('');
    try {
      const payload = isSeriesMode
        ? await selectVideoSeriesPosterFrame(seriesKey, trackId, seconds)
        : await selectVideoPosterFrame(trackId, seconds);
      const rawPosterUrl = payload.poster_url || (isSeriesMode ? '' : `/api/tracks/${trackId}/poster/`);
      const posterUrl = rawPosterUrl
        ? `${rawPosterUrl}${rawPosterUrl.includes('?') ? '&' : '?'}_triver_ts=${Date.now()}`
        : '';
      onSelected?.({ ...payload, poster_url: posterUrl });
      onClose();
    } catch (nextError) {
      setError(nextError.message || 'Unable to save video poster');
    } finally {
      setSaving(false);
    }
  }

  if (!trackId) {
    return null;
  }

  return createPortal(
    <div
      className="video-poster-modal"
      role="presentation"
      onContextMenu={(event) => event.preventDefault()}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="video-poster-panel" role="dialog" aria-modal="true" aria-label="Video poster frame">
        <button type="button" className="modal-close video-poster-close" onClick={onClose} aria-label="Close poster selector">x</button>
        <div className="video-poster-head">
          <p className="panel-kicker">{isSeriesMode ? 'Series poster' : 'Video poster'}</p>
          <h3>{title || track.episode_title || track.canonical_title || 'Untitled'}</h3>
        </div>
        {error ? <p className="metadata-error">{error}</p> : null}
        <div className="video-poster-manual">
          <label>
            <span>min:sec</span>
            <input
              value={timecode}
              onChange={(event) => setTimecode(event.target.value)}
              placeholder="1:23"
            />
          </label>
          <button type="button" onClick={() => saveSelection(timecode)} disabled={saving || !timecode.trim()}>
            Save frame
          </button>
          <button type="button" onClick={() => setReloadKey((current) => current + 1)} disabled={loading || saving}>
            Random frames
          </button>
        </div>
        {previewUrl ? (
          <button type="button" className="video-poster-preview" onClick={() => saveSelection(timecode)} disabled={saving}>
            <img src={previewUrl} alt="" />
            <span>Use custom frame</span>
          </button>
        ) : null}
        {loading ? <p className="empty-state">Loading frames...</p> : null}
        <div className="video-poster-candidates">
          {candidates.map((candidate) => (
            <button
              key={`${candidate.seconds}-${candidate.url}`}
              type="button"
              className="video-poster-candidate"
              onClick={() => saveSelection(candidate.seconds)}
              disabled={saving}
            >
              <img src={candidate.url} alt="" />
              <span>{candidate.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
