import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import CoverThumb from '../../../shared/ui/CoverThumb';
import InlineArtistLinks from '../../../shared/ui/InlineArtistLinks';
import { PlayerPlayIcon, PlusIcon } from '../../../shared/ui/TablerIcons';
import { fetchAlbumTracks } from '../../../api/library';
import { formatClockTime, getArtistLabel } from '../player/playerUtils';
import ContextMenu from '../../../shared/ui/ContextMenu';
import TrackMetadataEditorModal from '../metadata/TrackMetadataEditorModal';

function albumTrackNumber(track) {
  const disc = track?.disc_number ? `${track.disc_number}.` : '';
  const number = track?.track_number ? String(track.track_number).padStart(2, '0') : '--';
  return `${disc}${number}`;
}

export default function AlbumDetailModal({
  album = null,
  libraryId = '',
  playerActions = {},
  onClose = () => {},
  onOpenArtistName = null,
}) {
  const [tracks, setTracks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
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
    if (!album) {
      setTracks([]);
      setLoading(false);
      setError('');
      setContextMenu(null);
      setMetadataTrack(null);
      return undefined;
    }

    let cancelled = false;
    setTracks([]);
    setError('');

    async function loadTracks() {
      if (!libraryId || !album?.id) {
        return;
      }
      setLoading(true);
      try {
        const payload = await fetchAlbumTracks(libraryId, album.id);
        if (!cancelled) {
          setTracks(payload);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError.message || 'Unable to read album');
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
  }, [album, album?.id, libraryId]);

  useEffect(() => {
    if (!album) {
      return undefined;
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [album, onClose]);

  useEffect(() => {
    if (!album) {
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
  }, [album]);

  useEffect(() => {
    if (!album) {
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
  }, [album, syncScrollState]);

  useEffect(() => {
    if (!album) {
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
  }, [album, syncScrollState]);

  const albumArtists = useMemo(() => (
    album?.lead_artist_names?.length
      ? album.lead_artist_names.map((name) => ({ name }))
      : Array.from(new Set(tracks.flatMap((track) => (
        track.artist_summary?.filter((artist) => artist.role === 'primary').map((artist) => artist.name) || []
      )))).map((name) => ({ name }))
  ), [album?.lead_artist_names, tracks]);

  if (!album) {
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

  return (
    <div className="app-content-tray" role="presentation">
      <button type="button" className="modal-close artist-tray-close" onClick={onClose} aria-label="Close album tray">×</button>
      <section ref={trayRef} className="artist-detail-tray album-detail-tray" role="dialog" aria-modal="false" aria-label={album.title || 'Album'}>
        <div className="artist-detail-head">
          <div>
            <p className="panel-kicker">Album</p>
            <h2>{album.title || 'Album'}</h2>
          </div>
        </div>

        <div className="album-detail-hero">
          <div className="album-detail-cover-shell">
            <CoverThumb coverUrl={album.cover_url} alt="" kind="album" />
            <button type="button" className="album-play-pill" onClick={() => playerActions.playAlbum?.(album)} aria-label="Play album">
              <PlayerPlayIcon />
            </button>
            <button type="button" className="album-queue-pill" onClick={() => playerActions.queueAlbum?.(album)} aria-label="Add album to queue">
              <PlusIcon />
            </button>
          </div>
          <div className="album-detail-copy">
            <InlineArtistLinks
              className="album-detail-artists"
              artists={albumArtists}
              onOpenArtistName={onOpenArtistName}
            />
            <div className="artist-detail-meta album-detail-meta">
              <span>{album.release_year || 'n/a'}</span>
              <span>{tracks.length || album.track_count || 0} tracks</span>
            </div>
          </div>
        </div>

        {error ? <p className="metadata-error">{error}</p> : null}
        {loading ? <p className="empty-state">Loading album...</p> : null}

        {!loading ? (
          <section className="album-detail-track-section">
            <div className="artist-tray-section-head">
              <h3>Tracks</h3>
              <span>{tracks.length}</span>
            </div>
            <ol className="album-detail-track-list">
              {tracks.map((track) => (
                <li
                  key={track.id}
                  className="album-detail-track-row"
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
                  <span className="album-detail-track-index">{albumTrackNumber(track)}</span>
                  <button type="button" className="play-trigger" onClick={() => playerActions.playSingleTrack?.(track)} aria-label={`Play ${track.canonical_title}`}>
                    <PlayerPlayIcon />
                  </button>
                  <div className="album-detail-track-copy">
                    <strong>{track.canonical_title || 'Untitled'}</strong>
                    <span>{getArtistLabel(track)}</span>
                  </div>
                  <span className="album-detail-track-duration">{formatClockTime(track.duration_seconds)}</span>
                  <button type="button" className="album-detail-track-queue" onClick={() => playerActions.queueTrack?.(track)} aria-label={`Add ${track.canonical_title} to queue`}>
                    <PlusIcon />
                  </button>
                </li>
              ))}
            </ol>
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
