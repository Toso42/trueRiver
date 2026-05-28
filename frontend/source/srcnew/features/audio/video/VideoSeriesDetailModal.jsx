import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import CoverThumb from '../../../shared/ui/CoverThumb';
import { PlayerPlayIcon, PlusIcon } from '../../../shared/ui/TablerIcons';
import { fetchVideoSeriesTracks } from '../../../api/library';
import { formatClockTime, getArtistLabel } from '../player/playerUtils';
import VideoPosterSelectorModal from './VideoPosterSelectorModal';
import ContextMenu from '../../../shared/ui/ContextMenu';
import TrackMetadataEditorModal from '../metadata/TrackMetadataEditorModal';

function episodeLabel(track) {
  const season = track?.season_number ? `S${String(track.season_number).padStart(2, '0')}` : '';
  const episode = track?.episode_number ? `E${String(track.episode_number).padStart(2, '0')}` : '';
  if (season || episode) {
    return `${season}${episode}` || '--';
  }
  return track?.track_number ? String(track.track_number).padStart(2, '0') : '--';
}

function groupBySeason(tracks) {
  const groups = new Map();
  tracks.forEach((track) => {
    const seasonKey = track.season_number ? String(track.season_number) : 'episodes';
    const label = track.season_number ? `Season ${track.season_number}` : 'Episodes';
    const bucket = groups.get(seasonKey) || { key: seasonKey, label, tracks: [] };
    bucket.tracks.push(track);
    groups.set(seasonKey, bucket);
  });
  return Array.from(groups.values());
}

function playbackBadgeText(track) {
  const status = track?.playback_status || {};
  if (status.cache_ready !== false) {
    return 'Ready';
  }
  if (status.building) {
    return `Preparing ${status?.progress?.percent || 0}%`;
  }
  return 'Needs preparation';
}

export default function VideoSeriesDetailModal({
  series = null,
  libraryId = '',
  playerActions = {},
  onRefresh = null,
  onClose = () => {},
}) {
  const [tracks, setTracks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [seriesCoverOverride, setSeriesCoverOverride] = useState('');
  const [posterEditor, setPosterEditor] = useState(null);
  const [contextMenu, setContextMenu] = useState(null);
  const [metadataTrack, setMetadataTrack] = useState(null);
  const trayRef = useRef(null);
  const scrollbarTrackRef = useRef(null);
  const scrollbarDragRef = useRef(null);
  const [scrollState, setScrollState] = useState({
    top: 0,
    height: 1,
    visibleHeight: 1,
  });

  const syncScrollState = useCallback(() => {
    const node = trayRef.current;
    if (!node) {
      return;
    }
    const nextState = {
      top: Math.max(node.scrollTop || 0, 0),
      height: Math.max(node.scrollHeight || 1, 1),
      visibleHeight: Math.max(node.clientHeight || 1, 1),
    };
    setScrollState((currentState) => (
      currentState.top === nextState.top
        && currentState.height === nextState.height
        && currentState.visibleHeight === nextState.visibleHeight
        ? currentState
        : nextState
    ));
  }, []);

  useEffect(() => {
    if (!series) {
      setTracks([]);
      setError('');
      setLoading(false);
      setSeriesCoverOverride('');
      setPosterEditor(null);
      setContextMenu(null);
      setMetadataTrack(null);
      return undefined;
    }

    let cancelled = false;
    setTracks([]);
    setError('');

    async function loadTracks() {
      if (!libraryId || !series?.series_key) {
        return;
      }
      setLoading(true);
      try {
        const payload = await fetchVideoSeriesTracks(libraryId, series.series_key);
        if (!cancelled) {
          setTracks(payload);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError.message || 'Unable to read video series');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadTracks();
    return () => {
      cancelled = true;
    };
  }, [libraryId, series, series?.series_key]);

  const openPosterEditor = useCallback((track, mode = 'track') => {
    if (!track?.id) {
      return;
    }
    setPosterEditor({ track, mode });
  }, []);

  const handlePosterSelected = useCallback((payload) => {
    if (!posterEditor?.track?.id || !payload?.poster_url) {
      return;
    }
    const posterUrl = payload.poster_url;
    if (posterEditor.mode === 'series') {
      setSeriesCoverOverride(posterUrl);
      onRefresh?.();
      return;
    }

    const posterTrackId = posterEditor.track.id;
    setTracks((currentTracks) => {
      const nextTracks = currentTracks.map((track) => (
        track.id === posterTrackId ? { ...track, cover_url: posterUrl, poster_url: posterUrl } : track
      ));
      const representativeId = series?.representative_track?.id || nextTracks[0]?.id;
      if (!seriesCoverOverride && posterTrackId === representativeId) {
        setSeriesCoverOverride(posterUrl);
      }
      return nextTracks;
    });
    onRefresh?.();
  }, [onRefresh, posterEditor, series?.representative_track?.id, seriesCoverOverride]);

  const closePosterEditor = useCallback(() => {
    setPosterEditor(null);
  }, []);

  useEffect(() => {
    if (!series) {
      return undefined;
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, series]);

  useEffect(() => {
    if (!series) {
      return undefined;
    }
    function dismissContextMenu() {
      setContextMenu(null);
    }

    window.addEventListener('click', dismissContextMenu);
    window.addEventListener('keydown', dismissContextMenu);
    window.addEventListener('resize', dismissContextMenu);
    return () => {
      window.removeEventListener('click', dismissContextMenu);
      window.removeEventListener('keydown', dismissContextMenu);
      window.removeEventListener('resize', dismissContextMenu);
    };
  }, [series]);

  useEffect(() => {
    if (!series) {
      return undefined;
    }
    const node = trayRef.current;
    if (!node) {
      return undefined;
    }
    syncScrollState();

    function handleScroll() {
      syncScrollState();
    }

    function handleWheel(event) {
      const currentNode = trayRef.current;
      if (!currentNode) {
        return;
      }
      const scrollableHeight = Math.max(currentNode.scrollHeight - currentNode.clientHeight, 0);
      if (scrollableHeight <= 0) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const deltaMultiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? currentNode.clientHeight : 1;
      currentNode.scrollTop += event.deltaY * deltaMultiplier;
      syncScrollState();
    }

    const observer = new ResizeObserver(() => syncScrollState());
    observer.observe(node);
    node.addEventListener('scroll', handleScroll, { passive: true });
    node.addEventListener('wheel', handleWheel, { passive: false });
    window.addEventListener('resize', syncScrollState);
    return () => {
      observer.disconnect();
      node.removeEventListener('scroll', handleScroll);
      node.removeEventListener('wheel', handleWheel);
      window.removeEventListener('resize', syncScrollState);
    };
  }, [series, syncScrollState]);

  useEffect(() => {
    if (!series) {
      return undefined;
    }
    function handlePointerMove(event) {
      if (!scrollbarDragRef.current) {
        return;
      }
      const node = trayRef.current;
      const trackBounds = scrollbarTrackRef.current?.getBoundingClientRect();
      if (!node || !trackBounds?.height) {
        return;
      }
      const scrollableHeight = Math.max(node.scrollHeight - node.clientHeight, 0);
      if (scrollableHeight <= 0) {
        return;
      }
      const thumbHeightPx = Math.max((node.clientHeight / Math.max(node.scrollHeight, 1)) * trackBounds.height, 36);
      const maxThumbTopPx = Math.max(trackBounds.height - thumbHeightPx, 1);
      const desiredThumbTopPx = Math.max(
        0,
        Math.min((event.clientY - trackBounds.top) - scrollbarDragRef.current.pointerOffsetPx, maxThumbTopPx),
      );
      node.scrollTop = (desiredThumbTopPx / maxThumbTopPx) * scrollableHeight;
      syncScrollState();
    }

    function handlePointerUp() {
      scrollbarDragRef.current = null;
      document.body.classList.remove('is-dragging-album-scrollbar');
    }

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    window.addEventListener('pointercancel', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('pointercancel', handlePointerUp);
    };
  }, [series, syncScrollState]);

  const seasonGroups = useMemo(() => groupBySeason(tracks), [tracks]);

  if (!series) {
    return null;
  }

  const trackHeightPx = Math.max(scrollbarTrackRef.current?.clientHeight || scrollState.visibleHeight - 24, 1);
  const scrollableHeight = Math.max(scrollState.height - scrollState.visibleHeight, 0);
  const visibleRatio = scrollState.height > 0 ? scrollState.visibleHeight / scrollState.height : 1;
  const thumbHeightPx = Math.min(trackHeightPx, Math.max(trackHeightPx * visibleRatio, 36));
  const thumbTopPx = scrollableHeight > 0
    ? (scrollState.top / scrollableHeight) * Math.max(trackHeightPx - thumbHeightPx, 0)
    : 0;
  const hasOverflow = scrollState.height > scrollState.visibleHeight + 2;
  const firstTrack = tracks[0] || series.representative_track;
  const heroCoverUrl = seriesCoverOverride || firstTrack?.cover_url || firstTrack?.poster_url || series.cover_url;
  const metaItems = [
    `${series.track_count || tracks.length} video`,
    series.group_kind === 'series' ? `${series.season_count || seasonGroups.length || 0} seasons` : '',
    series.duration_seconds ? formatClockTime(series.duration_seconds) : '',
  ].filter(Boolean);

  return (
    <div className="app-content-tray" role="presentation">
      <button type="button" className="modal-close artist-tray-close" onClick={onClose} aria-label="Close video series tray">×</button>
      <section ref={trayRef} className="artist-detail-tray album-detail-tray video-series-detail-tray" role="dialog" aria-modal="false" aria-label={series.title || 'TV Series'}>
        <div className="artist-detail-head">
          <div>
            <p className="panel-kicker">{series.group_kind === 'series' ? 'TV Series' : 'Video'}</p>
            <h2>{series.title || 'Video'}</h2>
          </div>
        </div>

        <div className="album-detail-hero video-series-detail-hero">
          <div className="album-detail-cover-shell">
            <CoverThumb coverUrl={heroCoverUrl} alt="" kind="album" />
            <button type="button" className="album-play-pill" onClick={() => playerActions.playSingleTrack?.(firstTrack)} disabled={!firstTrack} aria-label="Play first video">
              <PlayerPlayIcon />
            </button>
            <button
              type="button"
              className="video-poster-edit-pill"
              onClick={() => openPosterEditor(firstTrack, 'series')}
              disabled={!firstTrack}
            >
              Series Poster
            </button>
          </div>
          <div className="album-detail-copy">
            <div className="artist-detail-meta album-detail-meta">
              {metaItems.map((item) => <span key={item}>{item}</span>)}
            </div>
          </div>
        </div>

        {error ? <p className="metadata-error">{error}</p> : null}
        {loading ? <p className="empty-state">Loading series...</p> : null}

        {!loading ? (
          <section className="album-detail-track-section">
            {seasonGroups.map((seasonGroup) => (
              <div key={seasonGroup.key} className="video-season-block">
                <div className="artist-tray-section-head">
                  <h3>{seasonGroup.label}</h3>
                  <span>{seasonGroup.tracks.length}</span>
                </div>
                <ol className="album-detail-track-list">
                  {seasonGroup.tracks.map((track) => (
                    <li
                      key={track.id}
                      className={`album-detail-track-row video-series-episode-row${track?.playback_status?.cache_ready === false ? ' is-cache-pending' : ''}${track?.playback_status?.building ? ' is-cache-building' : ''}`}
                      onContextMenuCapture={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        setContextMenu({
                          x: event.clientX,
                          y: event.clientY,
                          track,
                        });
                      }}
                    >
                      <span className="album-detail-track-index">{episodeLabel(track)}</span>
                      <button type="button" className="play-trigger" onClick={() => playerActions.playSingleTrack?.(track)} aria-label={`Play ${track.canonical_title}`}>
                        <PlayerPlayIcon />
                      </button>
                      <div className="album-detail-track-copy">
                        <strong>{track.episode_title || track.canonical_title || 'Untitled'}</strong>
                        <span>{getArtistLabel(track)}</span>
                      </div>
                      <span className="video-cache-row-badge">{playbackBadgeText(track)}</span>
                      <span className="album-detail-track-duration">{formatClockTime(track.duration_seconds)}</span>
                      <button type="button" className="album-detail-track-poster" onClick={() => openPosterEditor(track)}>
                        Poster
                      </button>
                      <button type="button" className="album-detail-track-queue" onClick={() => playerActions.queueTrack?.(track)} aria-label={`Add ${track.canonical_title} to queue`}>
                        <PlusIcon />
                      </button>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </section>
        ) : null}
      </section>
      {hasOverflow ? (
        <div
          ref={scrollbarTrackRef}
          className="album-detail-scrollbar"
          aria-hidden="true"
          onPointerDown={(event) => {
            const node = trayRef.current;
            const trackBounds = scrollbarTrackRef.current?.getBoundingClientRect();
            if (!node || !trackBounds?.height) {
              return;
            }
            const nextThumbHeightPx = Math.max((node.clientHeight / Math.max(node.scrollHeight, 1)) * trackBounds.height, 36);
            const maxThumbTopPx = Math.max(trackBounds.height - nextThumbHeightPx, 1);
            const clickedPx = Math.max(0, Math.min(event.clientY - trackBounds.top, trackBounds.height));
            const desiredThumbTopPx = Math.max(0, Math.min(clickedPx - (nextThumbHeightPx / 2), maxThumbTopPx));
            const nextScrollableHeight = Math.max(node.scrollHeight - node.clientHeight, 0);
            node.scrollTop = (desiredThumbTopPx / maxThumbTopPx) * nextScrollableHeight;
            syncScrollState();
          }}
        >
          <span
            className="album-detail-scrollbar-thumb"
            style={{ height: `${thumbHeightPx}px`, transform: `translateY(${thumbTopPx}px)` }}
            onPointerDown={(event) => {
              event.stopPropagation();
              const thumbBounds = event.currentTarget.getBoundingClientRect();
              scrollbarDragRef.current = {
                pointerOffsetPx: event.clientY - thumbBounds.top,
              };
              document.body.classList.add('is-dragging-album-scrollbar');
            }}
          />
        </div>
      ) : null}
      {posterEditor ? (
        <VideoPosterSelectorModal
          track={posterEditor.track}
          mode={posterEditor.mode}
          seriesKey={series.series_key}
          title={posterEditor.mode === 'series' ? series.title : posterEditor.track.episode_title || posterEditor.track.canonical_title}
          onSelected={handlePosterSelected}
          onClose={closePosterEditor}
        />
      ) : null}
      {contextMenu ? (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          items={[
            {
              key: 'play',
              label: 'Play',
              onSelect: () => playerActions.playSingleTrack?.(contextMenu.track),
            },
            {
              key: 'queue',
              label: 'Add To Queue',
              onSelect: () => playerActions.queueTrack?.(contextMenu.track),
            },
            {
              key: 'metadata',
              label: 'Metadata',
              onSelect: () => setMetadataTrack(contextMenu.track),
            },
            {
              key: 'poster',
              label: 'Edit Video Poster',
              onSelect: () => openPosterEditor(contextMenu.track),
            },
          ]}
        />
      ) : null}
      {metadataTrack ? (
        <TrackMetadataEditorModal
          track={metadataTrack}
          onClose={() => setMetadataTrack(null)}
        />
      ) : null}
    </div>
  );
}
