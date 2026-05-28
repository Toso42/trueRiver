import { useEffect, useMemo, useRef, useState } from 'react';
import AudioContentScaffold from '../AudioContentScaffold';
import CoverThumb from '../../../../shared/ui/CoverThumb';
import { PlayerPlayIcon, PlusIcon, ShuffleIcon, UserIcon } from '../../../../shared/ui/TablerIcons';
import { fetchAlbumTracks, fetchAlbums, fetchArtistTracks, fetchArtists, fetchTracks } from '../../../../api/library';
import { fetchUserDirectory } from '../../../../api/auth';
import ContextMenu from '../../../../shared/ui/ContextMenu';
import MultiTrackMetadataEditorModal from '../../metadata/MultiTrackMetadataEditorModal';
import TrackMetadataEditorModal from '../../metadata/TrackMetadataEditorModal';
import RemoteMetadataModal from '../../metadata/RemoteMetadataModal';
import VersionFlag, { openVersionHandling, versionCountForItem } from '../../versions/VersionFlag';

const HOME_FLAGS = [
  { id: 'all', label: 'All' },
  { id: 'albums', label: 'Albums' },
  { id: 'artists', label: 'Artists' },
  { id: 'tracks', label: 'Tracks' },
  { id: 'others', label: 'Others' },
];

function itemIdentity(item, index) {
  return `${item?.id ?? ''}:${item?.title ?? item?.name ?? item?.canonical_title ?? ''}:${index}`;
}

function seededScore(identity, seed) {
  let hash = 2166136261 ^ seed;
  for (let index = 0; index < identity.length; index += 1) {
    hash ^= identity.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function pickRandomItems(items, limit, seed) {
  return (items || [])
    .filter(Boolean)
    .map((item, index) => ({ item, score: seededScore(itemIdentity(item, index), seed) }))
    .sort((left, right) => left.score - right.score)
    .slice(0, limit)
    .map(({ item }) => item);
}

function withArtistCoverVersion(url, version) {
  if (!url || !version) {
    return url || '';
  }
  const joiner = url.includes('?') ? '&' : '?';
  return `${url}${joiner}_triver_artist=${encodeURIComponent(version)}`;
}

function HomeAlbumCard({ album, playerActions, onOpenAlbum, onContextMenu }) {
  return (
    <article
      className="album-card home-album-card"
      onClick={() => onOpenAlbum?.(album)}
      onContextMenuCapture={(event) => onContextMenu?.(event, album)}
    >
      <div className="album-card-media">
        <button
          type="button"
          className="album-artwork-button"
          onClick={(event) => {
            event.stopPropagation();
            onOpenAlbum?.(album);
          }}
          aria-label={`Open ${album.title}`}
        >
          <span className="album-artwork-ring" aria-hidden="true" />
          <span className="album-artwork-frame">
            <CoverThumb coverUrl={album.cover_url} alt="" kind="album" />
          </span>
        </button>
        <button type="button" className="album-play-pill" onClick={(event) => { event.stopPropagation(); playerActions.playAlbum?.(album); }} aria-label="Play album">
          <PlayerPlayIcon />
        </button>
        <button type="button" className="album-queue-pill" onClick={(event) => { event.stopPropagation(); playerActions.queueAlbum?.(album); }} aria-label="Add album">
          <PlusIcon />
        </button>
      </div>
      <div className="album-copy">
        <VersionFlag item={album} />
        <h3>{album.title || 'Untitled Album'}</h3>
        <p>{(album.lead_artist_names || []).join(', ') || 'Unknown Artist'}</p>
        <span>{album.release_year || 'n/a'} · {album.track_count || 0} tracks</span>
      </div>
    </article>
  );
}

function HomeArtistCard({ artist, playerActions, onOpenArtist, onContextMenu }) {
  return (
    <article
      className="album-card artist-card home-artist-card"
      onClick={() => onOpenArtist?.(artist)}
      onContextMenuCapture={(event) => onContextMenu?.(event, artist)}
    >
      <div className="album-card-media">
        <button
          type="button"
          className="album-artwork-button"
          onClick={(event) => {
            event.stopPropagation();
            onOpenArtist?.(artist);
          }}
          aria-label={`Open ${artist.name}`}
        >
          <span className="album-artwork-ring" aria-hidden="true" />
          <span className="album-artwork-frame">
            <CoverThumb coverUrl={withArtistCoverVersion(artist.cover_url, artist.updated_at)} alt="" kind="artist" />
          </span>
        </button>
        <button type="button" className="album-play-pill" onClick={(event) => { event.stopPropagation(); playerActions.playArtist?.(artist); }} aria-label="Play artist">
          <PlayerPlayIcon />
        </button>
        <button type="button" className="album-queue-pill" onClick={(event) => { event.stopPropagation(); playerActions.queueArtist?.(artist); }} aria-label="Add artist">
          <PlusIcon />
        </button>
      </div>
      <div className="album-copy">
        <VersionFlag item={artist} />
        <h3>{artist.name || 'Unknown Artist'}</h3>
        <p>Artist index</p>
        <span>{artist.track_count || 0} linked tracks</span>
      </div>
    </article>
  );
}

function HomeTrackRow({ track, playerActions, onContextMenu }) {
  return (
    <button
      type="button"
      className="home-track-row"
      onClick={() => playerActions.playTrack?.(track)}
      onContextMenuCapture={(event) => onContextMenu?.(event, track)}
    >
      <CoverThumb coverUrl={track.cover_url} alt="" kind="track" />
      <span>
        <strong>{track.canonical_title || track.title || 'Untitled Track'}</strong>
        <small>{track.album_title || track.artist_summary?.map((artist) => artist.name).join(', ') || 'Track'}</small>
      </span>
      <PlayerPlayIcon />
    </button>
  );
}

function userDisplayName(user) {
  return user?.username || user?.email || 'User';
}

function ScrollableRow({ className, children, ariaLabel }) {
  const rowRef = useRef(null);
  const dragRef = useRef({
    pointerId: null,
    startX: 0,
    startY: 0,
    startScrollLeft: 0,
    dragging: false,
    suppressClick: false,
  });

  const isInteractiveTarget = (target) => Boolean(target?.closest?.('button, a, input, textarea, select, [role="button"]'));

  useEffect(() => {
    const row = rowRef.current;
    if (!row) {
      return undefined;
    }
    const onWheel = (event) => {
      const legacyHorizontal = typeof event.wheelDeltaX === 'number' ? -event.wheelDeltaX : 0;
      const firefoxHorizontal = typeof event.axis === 'number' && event.axis === event.HORIZONTAL_AXIS ? event.detail : 0;
      const rawDeltaX = event.deltaX || legacyHorizontal || firefoxHorizontal || 0;
      const rawDeltaY = event.shiftKey ? event.deltaY : 0;
      let delta = rawDeltaX || rawDeltaY;
      if (!delta) {
        return;
      }
      if (event.deltaMode === 1) {
        delta *= 18;
      } else if (event.deltaMode === 2) {
        delta *= row.clientWidth;
      }
      const nextScrollLeft = Math.max(0, Math.min(row.scrollLeft + delta, row.scrollWidth - row.clientWidth));
      if (nextScrollLeft === row.scrollLeft) {
        return;
      }
      row.scrollLeft = nextScrollLeft;
      event.preventDefault();
      event.stopPropagation();
    };
    row.addEventListener('wheel', onWheel, { passive: false });
    row.addEventListener('mousewheel', onWheel, { passive: false });
    return () => {
      row.removeEventListener('wheel', onWheel);
      row.removeEventListener('mousewheel', onWheel);
    };
  }, []);

  const pointerIsOnScrollbar = (event, row) => {
    const bounds = row.getBoundingClientRect();
    const scrollbarHeight = row.offsetHeight - row.clientHeight;
    const scrollbarZone = Math.max(30, scrollbarHeight + 12);
    return event.clientY >= bounds.bottom - scrollbarZone;
  };

  const finishDrag = (event) => {
    const row = rowRef.current;
    const state = dragRef.current;
    if (!row || state.pointerId === null) {
      return;
    }
    try {
      row.releasePointerCapture(state.pointerId);
    } catch (_error) {
      // Pointer capture may already be gone if the browser cancelled it.
    }
    if (state.dragging) {
      event.preventDefault();
      state.suppressClick = true;
      window.setTimeout(() => {
        dragRef.current.suppressClick = false;
      }, 0);
    }
    row.classList.remove('is-dragging');
    state.pointerId = null;
    state.dragging = false;
  };

  return (
    <div
      ref={rowRef}
      className={className}
      role="list"
      aria-label={ariaLabel}
      onPointerDownCapture={(event) => {
        if (event.button !== 0) return;
        if (isInteractiveTarget(event.target)) return;
        const row = rowRef.current;
        if (!row) return;
        if (row.scrollWidth <= row.clientWidth) return;
        if (pointerIsOnScrollbar(event, row)) {
          dragRef.current.pointerId = null;
          return;
        }
        dragRef.current = {
          pointerId: event.pointerId,
          startX: event.clientX,
          startY: event.clientY,
          startScrollLeft: row.scrollLeft,
          dragging: false,
          suppressClick: false,
        };
        row.setPointerCapture(event.pointerId);
      }}
      onPointerMoveCapture={(event) => {
        const row = rowRef.current;
        const state = dragRef.current;
        if (!row || state.pointerId !== event.pointerId) return;
        const dx = event.clientX - state.startX;
        const dy = event.clientY - state.startY;
        if (!state.dragging && Math.hypot(dx, dy) > 5) {
          state.dragging = true;
          row.classList.add('is-dragging');
        }
        if (!state.dragging) return;
        row.scrollLeft = state.startScrollLeft - dx;
        event.preventDefault();
      }}
      onPointerUpCapture={finishDrag}
      onPointerCancelCapture={finishDrag}
      onDragStartCapture={(event) => {
        event.preventDefault();
      }}
      onClickCapture={(event) => {
        if (!dragRef.current.suppressClick) return;
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      {children}
    </div>
  );
}

function HomeSectionHeader({ title, subtitle, count, onRefresh }) {
  return (
    <div className="home-section-head">
      <div className="home-section-title">
        <div>
          <h3>{title}</h3>
          {typeof count !== 'undefined' ? <span>{count}</span> : null}
        </div>
        <p>{subtitle}</p>
      </div>
      <button type="button" className="home-section-refresh" onClick={onRefresh} aria-label={`Refresh ${title}`}>
        <ShuffleIcon />
        <span>Refresh</span>
      </button>
    </div>
  );
}

function HomeFlagRow({ activeFlag, onChange }) {
  return (
    <div className="home-flag-row" aria-label="Home sections">
      {HOME_FLAGS.map((flag) => (
        <button
          key={flag.id}
          type="button"
          className={activeFlag === flag.id ? 'is-active' : ''}
          onClick={() => onChange(flag.id)}
        >
          {flag.label}
        </button>
      ))}
    </div>
  );
}

function HomeUserFilterBar({ users, selectedUserIds, onToggleUser, onClear }) {
  return (
    <div className="home-listener-filter" aria-label="Recommendation users">
      <button
        type="button"
        className={selectedUserIds.length === 0 ? 'is-active' : ''}
        onClick={onClear}
      >
        All users
      </button>
      {users.map((user) => {
        const isSelected = selectedUserIds.includes(user.id);
        return (
          <button
            key={user.id}
            type="button"
            className={isSelected ? 'home-user-chip is-active' : 'home-user-chip'}
            onClick={() => onToggleUser(user.id)}
          >
            <span className="home-user-avatar">
              {user.avatar_url ? <img src={user.avatar_url} alt="" /> : <UserIcon />}
            </span>
            <span>{userDisplayName(user)}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function HomeView({ libraryId = '', loading = false, pageError = '', playerActions = {}, onOpenArtist = null, onOpenAlbum = null }) {
  const [homeLoading, setHomeLoading] = useState(true);
  const [homeError, setHomeError] = useState('');
  const [albums, setAlbums] = useState([]);
  const [artists, setArtists] = useState([]);
  const [tracks, setTracks] = useState([]);
  const [users, setUsers] = useState([]);
  const [activeFlag, setActiveFlag] = useState('all');
  const [selectedListenerIds, setSelectedListenerIds] = useState([]);
  const [contextMenu, setContextMenu] = useState(null);
  const [metadataTrack, setMetadataTrack] = useState(null);
  const [metadataSelection, setMetadataSelection] = useState(null);
  const [remoteMetadataTracks, setRemoteMetadataTracks] = useState(null);
  const [metadataError, setMetadataError] = useState('');
  const [sectionSeeds, setSectionSeeds] = useState({
    albums: 11,
    artists: 23,
    tracks: 37,
    recommendations: 53,
  });

  useEffect(() => {
    if (!libraryId) {
      setHomeLoading(false);
      return undefined;
    }
    let cancelled = false;
    setHomeLoading(true);
    setHomeError('');
    Promise.all([
      fetchAlbums(libraryId, 1),
      fetchArtists(libraryId, 1),
      fetchTracks(libraryId, 1),
      fetchUserDirectory().catch(() => []),
    ])
      .then(([albumPayload, artistPayload, trackPayload, userPayload]) => {
        if (cancelled) return;
        setAlbums(albumPayload.items || []);
        setArtists(artistPayload.items || []);
        setTracks(trackPayload.items || []);
        setUsers(Array.isArray(userPayload) ? userPayload : []);
      })
      .catch((error) => {
        if (!cancelled) {
          setHomeError(error.message || 'Unable to load home.');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setHomeLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [libraryId]);

  useEffect(() => {
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
  }, []);

  const listenerSeed = useMemo(
    () => selectedListenerIds.reduce((seed, userId, index) => seed + seededScore(`${userId}`, index + 1), 0),
    [selectedListenerIds]
  );
  const featuredAlbums = useMemo(() => pickRandomItems(albums, 8, sectionSeeds.albums), [albums, sectionSeeds.albums]);
  const featuredArtists = useMemo(() => pickRandomItems(artists, 8, sectionSeeds.artists), [artists, sectionSeeds.artists]);
  const starterTracks = useMemo(() => pickRandomItems(tracks, 10, sectionSeeds.tracks), [tracks, sectionSeeds.tracks]);
  const recommendationTracks = useMemo(() => pickRandomItems(tracks, 10, sectionSeeds.recommendations + listenerSeed), [tracks, sectionSeeds.recommendations, listenerSeed]);
  const otherUsers = useMemo(() => pickRandomItems(users, 18, 5), [users]);
  const selectedListenerNames = useMemo(
    () => selectedListenerIds
      .map((userId) => users.find((user) => user.id === userId))
      .filter(Boolean)
      .map(userDisplayName),
    [selectedListenerIds, users]
  );

  const refreshSection = (section) => {
    setSectionSeeds((current) => ({
      ...current,
      [section]: (current[section] || 0) + 1,
    }));
  };

  const showSection = (section) => activeFlag === 'all' || activeFlag === section;

  const toggleListener = (userId) => {
    setSelectedListenerIds((current) => (
      current.includes(userId)
        ? current.filter((id) => id !== userId)
        : [...current, userId]
    ));
  };

  function openHomeContextMenu(event, kind, item) {
    event.preventDefault();
    event.stopPropagation();
    setContextMenu({
      x: event.clientX,
      y: event.clientY,
      kind,
      item,
    });
  }

  async function openHomeMetadata() {
    if (!contextMenu?.item) {
      return;
    }
    setMetadataError('');
    if (contextMenu.kind === 'album') {
      if (!libraryId || !contextMenu.item.id) {
        setMetadataError('Unable to open album metadata: library is not ready.');
        return;
      }
      try {
        const albumTracks = await fetchAlbumTracks(libraryId, contextMenu.item.id);
        if (!albumTracks.length) {
          setMetadataError('No indexed tracks for this album.');
          return;
        }
        setMetadataTrack(null);
        setMetadataSelection({
          title: `${contextMenu.item.title || 'Album'} Metadata`,
          tracks: albumTracks,
          kicker: 'Album Selection Metadata',
        });
      } catch (error) {
        setMetadataError(error.message || 'Unable to open album metadata.');
      }
      return;
    }
    if (contextMenu.kind === 'track') {
      setMetadataSelection(null);
      setMetadataTrack(contextMenu.item);
      return;
    }
    if (contextMenu.kind === 'artist') {
      if (!libraryId || !contextMenu.item.id) {
        setMetadataError('Unable to open artist metadata: library is not ready.');
        return;
      }
      try {
        const artistTracks = await fetchArtistTracks(libraryId, contextMenu.item.id);
        if (!artistTracks.length) {
          setMetadataError('No indexed tracks for this artist.');
          return;
        }
        setMetadataTrack(null);
        setMetadataSelection({
          title: `${contextMenu.item.name || 'Artist'} Metadata`,
          tracks: artistTracks,
          kicker: 'Artist Selection Metadata',
        });
      } catch (error) {
        setMetadataError(error.message || 'Unable to open artist metadata.');
      }
    }
  }

  async function openHomeRemoteMetadata() {
    if (!contextMenu?.item) {
      return;
    }
    setMetadataError('');
    if (contextMenu.kind === 'track') {
      setRemoteMetadataTracks([contextMenu.item]);
      return;
    }
    if (contextMenu.kind === 'album') {
      if (!libraryId || !contextMenu.item.id) {
        setMetadataError('Unable to open remote metadata: library is not ready.');
        return;
      }
      try {
        const albumTracks = await fetchAlbumTracks(libraryId, contextMenu.item.id);
        setRemoteMetadataTracks(albumTracks);
      } catch (error) {
        setMetadataError(error.message || 'Unable to open remote metadata.');
      }
      return;
    }
    if (contextMenu.kind === 'artist') {
      if (!libraryId || !contextMenu.item.id) {
        setMetadataError('Unable to open remote metadata: library is not ready.');
        return;
      }
      try {
        const artistTracks = await fetchArtistTracks(libraryId, contextMenu.item.id);
        setRemoteMetadataTracks(artistTracks);
      } catch (error) {
        setMetadataError(error.message || 'Unable to open remote metadata.');
      }
    }
  }

  if ((loading || homeLoading) && !albums.length && !artists.length) {
    return <p className="empty-state">Loading home...</p>;
  }

  if (pageError || homeError) {
    return <p className="empty-state">{pageError || homeError}</p>;
  }

  return (
    <AudioContentScaffold
      title="Home"
      description="Mixed music view for returning to the library quickly."
    >
      <div className="home-dashboard">
        <div className="home-main">
          {metadataError ? <p className="metadata-error">{metadataError}</p> : null}
          <HomeFlagRow activeFlag={activeFlag} onChange={setActiveFlag} />
          {showSection('albums') ? <section className="home-section">
            <HomeSectionHeader
              title="Albums in library"
              subtitle="Random album selection from the library."
              count={featuredAlbums.length}
              onRefresh={() => refreshSection('albums')}
            />
            <ScrollableRow className="home-card-row" ariaLabel="Albums in library">
              {featuredAlbums.map((album) => (
                <HomeAlbumCard
                  key={album.id}
                  album={album}
                  playerActions={playerActions}
                  onOpenAlbum={onOpenAlbum}
                  onContextMenu={(event, item) => openHomeContextMenu(event, 'album', item)}
                />
              ))}
            </ScrollableRow>
          </section> : null}
          {showSection('artists') ? <section className="home-section">
            <HomeSectionHeader
              title="Artists"
              subtitle="Artists picked from the catalog, using the same cards as the dedicated page."
              count={featuredArtists.length}
              onRefresh={() => refreshSection('artists')}
            />
            <ScrollableRow className="home-card-row artist-grid" ariaLabel="Artists">
              {featuredArtists.map((artist) => (
                <HomeArtistCard
                  key={artist.id}
                  artist={artist}
                  playerActions={playerActions}
                  onOpenArtist={onOpenArtist}
                  onContextMenu={(event, item) => openHomeContextMenu(event, 'artist', item)}
                />
              ))}
            </ScrollableRow>
          </section> : null}
          {showSection('tracks') ? <section className="home-section">
            <HomeSectionHeader
              title="From the catalog"
              subtitle="Ready-to-play tracks from the general list."
              count={starterTracks.length}
              onRefresh={() => refreshSection('tracks')}
            />
            <ScrollableRow className="home-track-grid" ariaLabel="Tracks from the catalog">
              {starterTracks.map((track) => (
                <HomeTrackRow
                  key={track.id}
                  track={track}
                  playerActions={playerActions}
                  onContextMenu={(event, item) => openHomeContextMenu(event, 'track', item)}
                />
              ))}
            </ScrollableRow>
          </section> : null}
          {showSection('others') ? <section className="home-section">
            <HomeSectionHeader
              title="Listened by others"
              subtitle={selectedListenerNames.length ? `Selection prepared for ${selectedListenerNames.join(', ')}.` : 'Selection ready to become social recommendations when play history is recorded.'}
              count={recommendationTracks.length}
              onRefresh={() => refreshSection('recommendations')}
            />
            <HomeUserFilterBar
              users={otherUsers}
              selectedUserIds={selectedListenerIds}
              onToggleUser={toggleListener}
              onClear={() => setSelectedListenerIds([])}
            />
            <ScrollableRow className="home-track-grid" ariaLabel="Listened by others">
              {recommendationTracks.map((track) => (
                <HomeTrackRow
                  key={track.id}
                  track={track}
                  playerActions={playerActions}
                  onContextMenu={(event, item) => openHomeContextMenu(event, 'track', item)}
                />
              ))}
            </ScrollableRow>
          </section> : null}
        </div>
        <aside className="home-users-panel">
          <div className="home-section-head">
            <h3>Users</h3>
            <span>{otherUsers.length}</span>
          </div>
          <ul>
            {otherUsers.map((user) => (
              <li key={user.id}>
                <span className="home-user-avatar">
                  {user.avatar_url ? <img src={user.avatar_url} alt="" /> : <UserIcon />}
                </span>
                <span>
                  <strong>{userDisplayName(user)}</strong>
                  <small>{user.is_staff ? 'admin' : 'listener'}</small>
                </span>
              </li>
            ))}
          </ul>
        </aside>
      </div>
      {contextMenu ? (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          items={[
            ...(contextMenu.kind === 'album' ? [{
              key: 'open',
              label: 'Open Album',
              onSelect: () => onOpenAlbum?.(contextMenu.item),
            }] : []),
            ...(contextMenu.kind === 'artist' ? [{
              key: 'open',
              label: 'Open Artist',
              onSelect: () => onOpenArtist?.(contextMenu.item),
            }] : []),
            ...(contextMenu.kind === 'track' ? [{
              key: 'play',
              label: 'Play',
              onSelect: () => (playerActions.playSingleTrack || playerActions.playTrack)?.(contextMenu.item),
            }] : []),
            ...(versionCountForItem(contextMenu.item) > 1 ? [{
              key: 'version-handling',
              label: 'Version Handling',
              onSelect: openVersionHandling,
            }] : []),
            {
              key: 'remote-metadata',
              label: 'Find Remote Metadata',
              onSelect: openHomeRemoteMetadata,
            },
            {
              key: 'metadata',
              label: 'Metadata',
              onSelect: openHomeMetadata,
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
      {metadataSelection ? (
        <MultiTrackMetadataEditorModal
          tracks={metadataSelection.tracks}
          title={metadataSelection.title}
          kicker={metadataSelection.kicker}
          onClose={() => setMetadataSelection(null)}
        />
      ) : null}
      {remoteMetadataTracks ? (
        <RemoteMetadataModal
          tracks={remoteMetadataTracks}
          onApplied={() => {
            refreshSection('albums');
            refreshSection('artists');
            refreshSection('tracks');
          }}
          onClose={() => setRemoteMetadataTracks(null)}
        />
      ) : null}
    </AudioContentScaffold>
  );
}
