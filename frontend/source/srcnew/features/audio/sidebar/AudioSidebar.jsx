import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from '../../../app/simpleRouter';
import { useOptionalAuth } from '../../../app/AuthProvider';
import { PlayerPlayIcon } from '../../../shared/ui/TablerIcons';
import TrueRiverBrand from '../../../shared/ui/TrueRiverBrand';
import SidebarAccordion from './SidebarAccordion';

const NAV_ITEMS = [
  { key: 'home', label: 'Home', section: 'Library', path: '/audio/home' },
  { key: 'tracks', label: 'Tracks', section: 'Library', path: '/audio/tracks' },
  { key: 'videos', label: 'Videos', section: 'Library', path: '/audio/videos' },
  { key: 'albums', label: 'Albums', section: 'Library', path: '/audio/albums' },
  { key: 'artists', label: 'Artists', section: 'Library', path: '/audio/artists' },
  { key: 'users', label: 'Users', section: 'Settings', path: '/audio/users', adminOnly: true },
  { key: 'settings', label: 'App Settings', section: 'Settings', path: '/audio/settings' },
  { key: 'metadata-settings', label: 'Metadata Settings', section: 'Settings', path: '/audio/metadata-settings' },
  { key: 'dedup-manager', label: 'Dedup Manager', section: 'Settings', path: '/audio/dedup-manager' },
  { key: 'trive-io', label: 'Trive-IO', section: 'Settings', path: '/audio/trive-io' },
  { key: 'source-folders', label: 'File Explorer', section: 'Settings', path: '/audio/source-folders' },
  { key: 'metadata', label: 'Metadata', section: 'Settings', path: '/audio/metadata' },
  { key: 'credits', label: 'Credits', section: 'Settings', path: '/audio/credits' },
  { key: 'video-curation', label: 'Video Curation', section: 'Settings', path: '/audio/video-curation' },
];

function QueueList({ tracks, currentTrackId, onSelectTrack, onRemoveTrack }) {
  if (!tracks.length) {
    return <p className="sidebar-queue-empty">Queue is empty.</p>;
  }

  return (
    <ul className="nav-list">
      {tracks.map((track, index) => (
        <li key={track.id} className="sidebar-queue-item">
          <button
            type="button"
            className={`nav-item${currentTrackId === track.id ? ' is-active' : ''}`}
            onClick={() => onSelectTrack(index)}
          >
            <span className="sidebar-queue-item-meta">
              <span className="sidebar-queue-item-index">{index + 1}</span>
              <span className={`sidebar-queue-item-now${currentTrackId === track.id ? ' is-active' : ''}`} aria-hidden="true">
                <PlayerPlayIcon />
              </span>
            </span>
            <span className="sidebar-queue-item-copy">
              <span className="sidebar-queue-item-title">{track.canonical_title || track.title || 'Untitled Track'}</span>
              <span className="sidebar-queue-item-subtitle">
                {track.artist_summary?.map((artist) => artist.name).join(', ') || track.subtitle || track.album_title || 'Unknown Artist'}
              </span>
            </span>
          </button>
          <button
            type="button"
            className="sidebar-queue-remove"
            aria-label={`Remove ${track.title}`}
            onClick={() => onRemoveTrack(track.id)}
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}

export default function AudioSidebar({
  currentView,
  queue = [],
  queueIndex = -1,
  playerActions = {},
}) {
  const router = useRouter();
  const auth = useOptionalAuth();
  const sidebarInnerRef = useRef(null);
  const sidebarContainerRef = useRef(null);
  const navbarContentInnerRef = useRef(null);
  const playlistViewportRef = useRef(null);
  const playlistScrollbarTrackRef = useRef(null);
  const splitterDragRef = useRef(null);
  const playlistScrollbarDragRef = useRef(null);
  const [navPanelHeight, setNavPanelHeight] = useState(360);
  const [sidebarHeight, setSidebarHeight] = useState(900);
  const [accordionState, setAccordionState] = useState({
    Library: true,
    Settings: true,
    Playlist: true,
  });
  const [playlistScrollState, setPlaylistScrollState] = useState({
    top: 0,
    height: 1,
    visibleHeight: 1,
  });

  const groups = useMemo(() => NAV_ITEMS.filter((item) => (
    !item.adminOnly || auth?.user?.is_staff || auth?.user?.is_superuser
  )).reduce((accumulator, item) => {
    if (!accumulator[item.section]) {
      accumulator[item.section] = [];
    }
    accumulator[item.section].push(item);
    return accumulator;
  }, {}), [auth?.user?.is_staff, auth?.user?.is_superuser]);

  useEffect(() => {
    const node = sidebarContainerRef.current;
    if (!node) {
      return undefined;
    }
    const updateHeight = () => {
      setSidebarHeight(Math.ceil(node.getBoundingClientRect().height));
    };
    updateHeight();
    const observer = new ResizeObserver(() => updateHeight());
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const navNode = sidebarInnerRef.current;
    const navInnerNode = navbarContentInnerRef.current;
    const containerNode = sidebarContainerRef.current;
    if (!navNode || !navInnerNode || !containerNode) {
      return undefined;
    }

    const growNavPanelIfNeeded = () => {
      const maxNavHeight = Math.max(180, containerNode.clientHeight - 220);
      const requiredHeight = Math.ceil(navInnerNode.getBoundingClientRect().height);
      if (requiredHeight > navPanelHeight && navPanelHeight < maxNavHeight) {
        setNavPanelHeight(Math.min(requiredHeight, maxNavHeight));
      }
    };

    growNavPanelIfNeeded();

    const observer = new ResizeObserver(() => growNavPanelIfNeeded());
    observer.observe(navInnerNode);
    return () => observer.disconnect();
  }, [accordionState, navPanelHeight]);

  const syncPlaylistScrollState = useCallback(() => {
    const node = playlistViewportRef.current;
    if (!node) {
      return;
    }
    setPlaylistScrollState({
      top: Math.max(node.scrollTop || 0, 0),
      height: Math.max(node.scrollHeight || 1, 1),
      visibleHeight: Math.max(node.clientHeight || 1, 1),
    });
  }, []);

  useEffect(() => {
    const node = playlistViewportRef.current;
    if (!node) {
      return undefined;
    }

    syncPlaylistScrollState();

    function handleScroll() {
      syncPlaylistScrollState();
    }

    function handleWheel(event) {
      const currentNode = playlistViewportRef.current;
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
      syncPlaylistScrollState();
    }

    node.addEventListener('scroll', handleScroll, { passive: true });
    node.addEventListener('wheel', handleWheel, { passive: false });
    window.addEventListener('resize', syncPlaylistScrollState);
    return () => {
      node.removeEventListener('scroll', handleScroll);
      node.removeEventListener('wheel', handleWheel);
      window.removeEventListener('resize', syncPlaylistScrollState);
    };
  }, [queue, syncPlaylistScrollState]);

  useEffect(() => {
    function handlePointerMove(event) {
      if (splitterDragRef.current) {
        const containerBounds = sidebarContainerRef.current?.getBoundingClientRect();
        if (containerBounds?.height) {
          const nextHeight = Math.max(
            180,
            Math.min(event.clientY - containerBounds.top, containerBounds.height - 220),
          );
          setNavPanelHeight(nextHeight);
        }
      }

      if (playlistScrollbarDragRef.current) {
        const node = playlistViewportRef.current;
        const trackBounds = playlistScrollbarTrackRef.current?.getBoundingClientRect();
        if (!node || !trackBounds?.height) {
          return;
        }
        const scrollableHeight = Math.max(node.scrollHeight - node.clientHeight, 0);
        if (scrollableHeight <= 0) {
          return;
        }
        const thumbHeightPx = Math.max((node.clientHeight / Math.max(node.scrollHeight, 1)) * trackBounds.height, 32);
        const maxThumbTopPx = Math.max(trackBounds.height - thumbHeightPx, 1);
        const desiredThumbTopPx = Math.max(
          0,
          Math.min((event.clientY - trackBounds.top) - playlistScrollbarDragRef.current.pointerOffsetPx, maxThumbTopPx),
        );
        node.scrollTop = (desiredThumbTopPx / maxThumbTopPx) * scrollableHeight;
        syncPlaylistScrollState();
      }
    }

    function handlePointerUp() {
      splitterDragRef.current = null;
      playlistScrollbarDragRef.current = null;
      document.body.classList.remove('is-resizing-sidebar-panels');
    }

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [syncPlaylistScrollState]);

  const playlistTrackHeightPx = Math.max(playlistScrollbarTrackRef.current?.clientHeight || 0, 1);
  const playlistScrollableHeight = Math.max(playlistScrollState.height - playlistScrollState.visibleHeight, 0);
  const playlistVisibleRatio = playlistScrollState.height > 0 ? playlistScrollState.visibleHeight / playlistScrollState.height : 1;
  const playlistThumbHeightPx = Math.min(
    playlistTrackHeightPx,
    Math.max(playlistTrackHeightPx * playlistVisibleRatio, 32),
  );
  const playlistThumbTopPx = playlistScrollableHeight > 0
    ? (playlistScrollState.top / playlistScrollableHeight) * Math.max(playlistTrackHeightPx - playlistThumbHeightPx, 0)
    : 0;
  const playlistHasOverflow = playlistScrollState.height > playlistScrollState.visibleHeight + 2;
  const playlistExpandedMaxHeight = `${Math.max(220, sidebarHeight - navPanelHeight - 96)}px`;

  return (
    <aside className="container-sidebar" ref={sidebarContainerRef}>
      <div className="navbar-content" ref={sidebarInnerRef} style={{ height: `${navPanelHeight}px` }}>
        <div className="navbar-content-inner" ref={navbarContentInnerRef}>
          <div className="brand-block">
            <TrueRiverBrand mode="audio" />
          </div>

          <nav className="sidebar-nav" aria-label="Main Navigation">
            {Object.entries(groups).map(([section, items]) => (
              <SidebarAccordion
                key={section}
                title={section}
                expanded={Boolean(accordionState[section])}
                onToggle={() => {
                  setAccordionState((current) => ({
                    ...current,
                    [section]: !current[section],
                  }));
                }}
              >
                <ul className="nav-list">
                  {items.map((item) => (
                    <li key={item.key}>
                      <button
                        type="button"
                        className={`nav-item${currentView === item.key ? ' is-active' : ''}`}
                        onClick={() => router.navigate(item.path)}
                      >
                        {item.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </SidebarAccordion>
            ))}
          </nav>
        </div>
      </div>

      <button
        type="button"
        className="sidebar-panel-resize-handle"
        aria-label="Resize sidebar panels"
        onPointerDown={() => {
          splitterDragRef.current = true;
          document.body.classList.add('is-resizing-sidebar-panels');
        }}
      />

      <div className="playlist-content">
        <SidebarAccordion
          title="Playlist"
          expanded={Boolean(accordionState.Playlist)}
          expandedMaxHeight={playlistExpandedMaxHeight}
          onToggle={() => {
            setAccordionState((current) => ({
              ...current,
              Playlist: !current.Playlist,
            }));
          }}
        >
          <div className="sidebar-queue-actions">
            <button type="button" className="sidebar-queue-action">Save</button>
            <button type="button" className="sidebar-queue-action">Load</button>
            <button type="button" className="sidebar-queue-action" onClick={() => playerActions.clearQueue?.()}>Clear</button>
            <button type="button" className="sidebar-queue-action">Manage</button>
            <span className="sidebar-queue-count">{queue.length}</span>
          </div>
          <div className="playlist-scroll-shell">
            <div ref={playlistViewportRef} className="playlist-scroll-viewport">
              <QueueList
                tracks={queue}
                currentTrackId={queue[queueIndex]?.id || null}
                onSelectTrack={(nextIndex) => playerActions.playQueueIndex?.(nextIndex)}
                onRemoveTrack={(trackId) => {
                  playerActions.removeQueueTrack?.(trackId);
                }}
              />
            </div>
            {playlistHasOverflow ? (
              <div
                ref={playlistScrollbarTrackRef}
                className="playlist-scrollbar"
                aria-hidden="true"
                onPointerDown={(event) => {
                  const node = playlistViewportRef.current;
                  const trackBounds = playlistScrollbarTrackRef.current?.getBoundingClientRect();
                  if (!node || !trackBounds?.height) {
                    return;
                  }
                  const nextThumbHeightPx = Math.max((node.clientHeight / Math.max(node.scrollHeight, 1)) * trackBounds.height, 32);
                  const maxThumbTopPx = Math.max(trackBounds.height - nextThumbHeightPx, 1);
                  const clickedPx = Math.max(0, Math.min(event.clientY - trackBounds.top, trackBounds.height));
                  const desiredThumbTopPx = Math.max(0, Math.min(clickedPx - (nextThumbHeightPx / 2), maxThumbTopPx));
                  const nextScrollableHeight = Math.max(node.scrollHeight - node.clientHeight, 0);
                  node.scrollTop = (desiredThumbTopPx / maxThumbTopPx) * nextScrollableHeight;
                  syncPlaylistScrollState();
                }}
              >
                <span
                  className="playlist-scrollbar-thumb"
                  style={{ height: `${playlistThumbHeightPx}px`, transform: `translateY(${playlistThumbTopPx}px)` }}
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    const thumbBounds = event.currentTarget.getBoundingClientRect();
                    playlistScrollbarDragRef.current = {
                      pointerOffsetPx: event.clientY - thumbBounds.top,
                    };
                  }}
                />
              </div>
            ) : null}
          </div>
        </SidebarAccordion>
      </div>
    </aside>
  );
}
