import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AudioContentNavigation from './AudioContentNavigation';
import HomeView from './views/HomeView';
import TracksView from './views/TracksView';
import VideosView from './views/VideosView';
import VideoCurationView from './views/VideoCurationView';
import AlbumsView from './views/AlbumsView';
import ArtistsView from './views/ArtistsView';
import SourceFoldersView from './views/SourceFoldersView';
import MetadataView from './views/MetadataView';
import SettingsView from './views/SettingsView';
import TriveIoView from './views/TriveIoView';
import UsersView from './views/UsersView';
import CreditsView from './views/CreditsView';
import useAudioLibraryData from '../../../hooks/useAudioLibraryData';
import ArtistDetailModal from '../artist/ArtistDetailModal';
import AlbumDetailModal from '../album/AlbumDetailModal';
import VideoSeriesDetailModal from '../video/VideoSeriesDetailModal';
import { fetchArtistByName } from '../../../api/library';
import ContextMenu from '../../../shared/ui/ContextMenu';

const viewRegistry = {
  home: HomeView,
  tracks: TracksView,
  videos: VideosView,
  'video-curation': VideoCurationView,
  albums: AlbumsView,
  artists: ArtistsView,
  'source-folders': SourceFoldersView,
  metadata: MetadataView,
  settings: (props) => <SettingsView {...props} mode="app" />,
  'dedup-manager': (props) => <SettingsView {...props} mode="dedup" />,
  'metadata-settings': (props) => <SettingsView {...props} mode="metadata" />,
  credits: CreditsView,
  users: UsersView,
  'trive-io': TriveIoView,
};

const pathLabels = {
  home: 'Audio / Home',
  tracks: 'Audio / Tracks',
  videos: 'Audio / Videos',
  'video-curation': 'Audio / Video Curation',
  albums: 'Audio / Albums',
  artists: 'Audio / Artists',
  'source-folders': 'Audio / File Explorer',
  metadata: 'Audio / Metadata',
  settings: 'Audio / App Settings',
  'dedup-manager': 'Audio / Dedup Manager',
  'metadata-settings': 'Audio / Metadata Settings',
  credits: 'Audio / Credits',
  users: 'Audio / Users',
  'trive-io': 'Audio / Trive-IO',
};

const artistRoleOptions = [
  { value: 'all', label: 'All credits' },
  { value: 'primary', label: 'Artists' },
  { value: 'featured', label: 'Featured' },
  { value: 'performer', label: 'Executors' },
  { value: 'composer', label: 'Authors' },
  { value: 'conductor', label: 'Conductors' },
];

function tagFilterFromSummary(tag) {
  if (tag?.value_id) {
    return `value:${tag.value_id}`;
  }
  if (tag?.definition && tag?.normalized_key) {
    return `${tag.definition}:${tag.normalized_key}`;
  }
  return '';
}

export default function AppContent({ currentView = 'tracks', playerActions = {}, playerState = {} }) {
  const CurrentView = viewRegistry[currentView] || TracksView;
  const [artistTrayArtist, setArtistTrayArtist] = useState(null);
  const [artistTrayError, setArtistTrayError] = useState('');
  const [albumTrayAlbum, setAlbumTrayAlbum] = useState(null);
  const [videoSeriesTray, setVideoSeriesTray] = useState(null);
  const [contentContextMenu, setContentContextMenu] = useState(null);
  const contentViewportRef = useRef(null);
  const contentScrollbarTrackRef = useRef(null);
  const contentScrollbarDragRef = useRef(null);
  const [contentScrollState, setContentScrollState] = useState({
    top: 0,
    height: 1,
    visibleHeight: 1,
  });
  const {
    libraryId,
    loading,
    pageError,
    searchTerm,
    setSearchTerm,
    activeJumpKey,
    setActiveJumpKey,
    artistRoleFilter,
    setArtistRoleFilter,
    selectedTagKeys,
    setSelectedTagKeys,
    tagDefinitions,
    quickSearchResults,
    pagination,
    data,
    refreshToken,
    refreshCurrent,
    refreshGlobal,
    loadMoreVideoRow,
  } = useAudioLibraryData(currentView);

  const openArtistTray = useCallback((artistOrId) => {
    if (!artistOrId) {
      return;
    }
    setArtistTrayError('');
    if (typeof artistOrId === 'string') {
      setArtistTrayArtist({ id: artistOrId, name: 'Artist' });
      return;
    }
    setArtistTrayArtist(artistOrId);
  }, []);

  const openArtistTrayByName = useCallback(async (artistName) => {
    if (!libraryId || !artistName) {
      return;
    }
    setArtistTrayError('');
    try {
      const artistPayload = await fetchArtistByName(libraryId, artistName);
      if (artistPayload?.id) {
        setArtistTrayArtist(artistPayload);
      }
    } catch (error) {
      setArtistTrayError(error.message || 'Unable to open artist');
    }
  }, [libraryId]);

  const closeArtistTray = useCallback(() => {
    setArtistTrayArtist(null);
    setArtistTrayError('');
  }, []);

  const closeAlbumTray = useCallback(() => {
    setAlbumTrayAlbum(null);
  }, []);

  const closeVideoSeriesTray = useCallback(() => {
    setVideoSeriesTray(null);
  }, []);

  const handleArtistUpdated = useCallback((updatedArtist) => {
    if (updatedArtist?.id) {
      setArtistTrayArtist(updatedArtist);
    }
    if (currentView === 'artists') {
      refreshCurrent();
    }
  }, [currentView, refreshCurrent]);

  const handleContentTagClick = useCallback((tag) => {
    const filterValue = tagFilterFromSummary(tag);
    if (filterValue) {
      setSelectedTagKeys([filterValue]);
    }
  }, [setSelectedTagKeys]);

  useEffect(() => {
    if (currentView !== 'albums') {
      setAlbumTrayAlbum(null);
    }
  }, [currentView]);

  useEffect(() => {
    if (currentView !== 'videos') {
      setVideoSeriesTray(null);
    }
    setContentContextMenu(null);
  }, [currentView]);

  const syncContentScrollState = useCallback(() => {
    const node = contentViewportRef.current;
    if (!node) {
      return;
    }
    const nextState = {
      top: Math.max(node.scrollTop || 0, 0),
      height: Math.max(node.scrollHeight || 1, 1),
      visibleHeight: Math.max(node.clientHeight || 1, 1),
    };
    setContentScrollState((currentState) => (
      currentState.top === nextState.top
        && currentState.height === nextState.height
        && currentState.visibleHeight === nextState.visibleHeight
        ? currentState
        : nextState
    ));
  }, []);

  useEffect(() => {
    const node = contentViewportRef.current;
    if (!node) {
      return undefined;
    }

    syncContentScrollState();

    function handleScroll() {
      syncContentScrollState();
    }

    function handleWheel(event) {
      if (event.defaultPrevented) {
        return;
      }
      const currentNode = contentViewportRef.current;
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
      syncContentScrollState();
    }

    const observer = new ResizeObserver(() => syncContentScrollState());
    observer.observe(node);
    node.addEventListener('scroll', handleScroll, { passive: true });
    node.addEventListener('wheel', handleWheel, { passive: false });
    window.addEventListener('resize', syncContentScrollState);
    return () => {
      observer.disconnect();
      node.removeEventListener('scroll', handleScroll);
      node.removeEventListener('wheel', handleWheel);
      window.removeEventListener('resize', syncContentScrollState);
    };
  }, [syncContentScrollState]);

  useEffect(() => {
    syncContentScrollState();
  }, [currentView, data, loading, pageError, syncContentScrollState]);

  useEffect(() => {
    function handlePointerMove(event) {
      if (!contentScrollbarDragRef.current) {
        return;
      }
      const node = contentViewportRef.current;
      const trackBounds = contentScrollbarTrackRef.current?.getBoundingClientRect();
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
        Math.min((event.clientY - trackBounds.top) - contentScrollbarDragRef.current.pointerOffsetPx, maxThumbTopPx),
      );
      node.scrollTop = (desiredThumbTopPx / maxThumbTopPx) * scrollableHeight;
      syncContentScrollState();
    }

    function handlePointerUp() {
      contentScrollbarDragRef.current = null;
      document.body.classList.remove('is-dragging-content-scrollbar');
    }

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    window.addEventListener('pointercancel', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('pointercancel', handlePointerUp);
    };
  }, [syncContentScrollState]);

  const currentViewProps = useMemo(() => {
    if (currentView === 'home') {
      return { libraryId, loading, pageError, playerActions, onOpenArtist: openArtistTray, onOpenAlbum: setAlbumTrayAlbum };
    }
    if (currentView === 'tracks') {
      return { tracks: data.tracks, loading, pageError, playerActions, playerState, libraryId, onOpenArtist: openArtistTray, onOpenArtistName: openArtistTrayByName, onRefresh: refreshCurrent, onTagClick: handleContentTagClick };
    }
    if (currentView === 'videos') {
      return { seriesGroups: data.videoSeriesGroups, curationRows: data.videoCurationRows, loading, pageError, playerActions, playerState, libraryId, onRefresh: refreshCurrent, onOpenSeries: setVideoSeriesTray, onTagClick: handleContentTagClick, onLoadMoreRow: loadMoreVideoRow };
    }
    if (currentView === 'video-curation') {
      return { loading, pageError, libraryId, searchTerm, refreshToken };
    }
    if (currentView === 'albums') {
      return { albums: data.albums, loading, pageError, playerActions, libraryId, onOpenArtistName: openArtistTrayByName, onOpenAlbum: setAlbumTrayAlbum, onRefresh: refreshCurrent, onTagClick: handleContentTagClick };
    }
    if (currentView === 'artists') {
      return { artists: data.artists, loading, pageError, playerActions, libraryId, onOpenArtist: openArtistTray, onRefresh: refreshCurrent, onTagClick: handleContentTagClick };
    }
    if (currentView === 'source-folders') {
      return { libraryId, loading, pageError, onRefresh: refreshCurrent };
    }
    if (currentView === 'trive-io') {
      return { loading, pageError, searchTerm };
    }
    return { loading, pageError };
  }, [currentView, data, loading, pageError, playerActions, playerState, libraryId, searchTerm, refreshToken, openArtistTray, openArtistTrayByName, refreshCurrent, handleContentTagClick, loadMoreVideoRow]);

  const contentTrackHeightPx = Math.max(contentScrollbarTrackRef.current?.clientHeight || contentScrollState.visibleHeight - 24, 1);
  const contentScrollableHeight = Math.max(contentScrollState.height - contentScrollState.visibleHeight, 0);
  const contentVisibleRatio = contentScrollState.height > 0 ? contentScrollState.visibleHeight / contentScrollState.height : 1;
  const contentThumbHeightPx = Math.min(
    contentTrackHeightPx,
    Math.max(contentTrackHeightPx * contentVisibleRatio, 36),
  );
  const contentThumbTopPx = contentScrollableHeight > 0
    ? (contentScrollState.top / contentScrollableHeight) * Math.max(contentTrackHeightPx - contentThumbHeightPx, 0)
    : 0;
  const contentHasOverflow = contentScrollState.height > contentScrollState.visibleHeight + 2;

  return (
    <section
      className="app-content"
      onContextMenuCapture={(event) => {
        event.preventDefault();
      }}
      onContextMenu={(event) => {
        event.preventDefault();
        if (event.target.closest('.app-content-tray, button, a, input, textarea, select, [role="dialog"]')) {
          return;
        }
        setContentContextMenu({ x: event.clientX, y: event.clientY });
      }}
    >
      <AudioContentNavigation
        pathLabel={pathLabels[currentView] || 'Audio / Tracks'}
        pagination={pagination}
        searchTerm={searchTerm}
        activeJumpKey={activeJumpKey}
        domainFilterLabel={currentView === 'artists' ? 'Role' : ''}
        domainFilterValue={currentView === 'artists' ? artistRoleFilter : ''}
        domainFilterOptions={currentView === 'artists' ? artistRoleOptions : []}
        selectedTagKeys={selectedTagKeys}
        tagOptions={tagDefinitions}
        onSearchTermChange={setSearchTerm}
        searchResults={quickSearchResults}
        onSelectSearchResult={(result) => {
          setSearchTerm(result.label);
          if (result.kind === 'artist') {
            if (result.id) {
              openArtistTray({ id: result.id, name: result.label });
              return;
            }
            openArtistTrayByName(result.label);
          }
        }}
        onJumpToKey={setActiveJumpKey}
        onClearJumpKey={() => setActiveJumpKey('')}
        onDomainFilterChange={setArtistRoleFilter}
        onTagChange={setSelectedTagKeys}
        onRefreshCurrent={refreshCurrent}
        onRefreshGlobal={refreshGlobal}
      />
      <div className="app-content-scroll-shell">
        <div ref={contentViewportRef} className="app-content-scroll">
          <CurrentView {...currentViewProps} />
          {pagination?.hasMore ? (
            <div className="app-content-load-more">
              <button
                type="button"
                onClick={() => pagination.onLoadMore?.()}
                disabled={loading}
              >
                Load more
              </button>
              <span>{pagination.visibleCount || 0} / {pagination.totalCount || 0}</span>
            </div>
          ) : null}
        </div>
        {contentHasOverflow ? (
          <div
            ref={contentScrollbarTrackRef}
            className="app-content-scrollbar"
            aria-hidden="true"
            onPointerDown={(event) => {
              const node = contentViewportRef.current;
              const trackBounds = contentScrollbarTrackRef.current?.getBoundingClientRect();
              if (!node || !trackBounds?.height) {
                return;
              }
              const nextThumbHeightPx = Math.max((node.clientHeight / Math.max(node.scrollHeight, 1)) * trackBounds.height, 36);
              const maxThumbTopPx = Math.max(trackBounds.height - nextThumbHeightPx, 1);
              const clickedPx = Math.max(0, Math.min(event.clientY - trackBounds.top, trackBounds.height));
              const desiredThumbTopPx = Math.max(0, Math.min(clickedPx - (nextThumbHeightPx / 2), maxThumbTopPx));
              const nextScrollableHeight = Math.max(node.scrollHeight - node.clientHeight, 0);
              node.scrollTop = (desiredThumbTopPx / maxThumbTopPx) * nextScrollableHeight;
              syncContentScrollState();
            }}
          >
            <span
              className="app-content-scrollbar-thumb"
              style={{ height: `${contentThumbHeightPx}px`, transform: `translateY(${contentThumbTopPx}px)` }}
              onPointerDown={(event) => {
                event.stopPropagation();
                const thumbBounds = event.currentTarget.getBoundingClientRect();
                contentScrollbarDragRef.current = {
                  pointerOffsetPx: event.clientY - thumbBounds.top,
                };
                document.body.classList.add('is-dragging-content-scrollbar');
              }}
            />
          </div>
        ) : null}
      </div>
      {artistTrayError ? <div className="app-content-tray-error">{artistTrayError}</div> : null}
      <AlbumDetailModal
        album={albumTrayAlbum}
        libraryId={libraryId}
        playerActions={playerActions}
        onOpenArtistName={openArtistTrayByName}
        onClose={closeAlbumTray}
      />
      <VideoSeriesDetailModal
        series={videoSeriesTray}
        libraryId={libraryId}
        playerActions={playerActions}
        onRefresh={refreshCurrent}
        onClose={closeVideoSeriesTray}
      />
      <ArtistDetailModal
        artist={artistTrayArtist}
        libraryId={libraryId}
        playerActions={playerActions}
        onArtistUpdated={handleArtistUpdated}
        onOpenArtist={openArtistTray}
        onOpenArtistName={openArtistTrayByName}
        onClose={closeArtistTray}
      />
      {contentContextMenu ? (
        <ContextMenu
          x={contentContextMenu.x}
          y={contentContextMenu.y}
          onClose={() => setContentContextMenu(null)}
          items={[
            {
              key: 'refresh',
              label: 'Refresh View',
              onSelect: () => refreshCurrent(),
            },
            {
              key: 'clear-filters',
              label: 'Clear Search And Filters',
              onSelect: () => {
                setSearchTerm('');
                setActiveJumpKey('');
                setSelectedTagKeys(null);
                setArtistRoleFilter(['all']);
              },
            },
          ]}
        />
      ) : null}
    </section>
  );
}
