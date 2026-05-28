import { useEffect, useRef, useState } from 'react';
import AudioContentScaffold from '../AudioContentScaffold';
import CoverThumb from '../../../../shared/ui/CoverThumb';
import InlineArtistLinks from '../../../../shared/ui/InlineArtistLinks';
import { PlayerPlayIcon, PlusIcon } from '../../../../shared/ui/TablerIcons';
import ContextMenu from '../../../../shared/ui/ContextMenu';
import MultiTrackMetadataEditorModal from '../../metadata/MultiTrackMetadataEditorModal';
import RemoteMetadataModal from '../../metadata/RemoteMetadataModal';
import TrackTagAssignmentModal from '../../tags/TrackTagAssignmentModal';
import TagSummary from '../../tags/TagSummary';
import VersionFlag, { openVersionHandling, versionCountForItem } from '../../versions/VersionFlag';
import { fetchAlbumTracks } from '../../../../api/library';
import { mergeAlbums } from '../../../../api/metadata';
import MergeAlbumsModal from '../../metadata/MergeAlbumsModal';

export default function AlbumsView({ albums = [], loading = false, pageError = '', playerActions = {}, libraryId = '', onOpenArtistName = null, onOpenAlbum = null, onRefresh = null, onTagClick = null }) {
  const [selectedAlbumIds, setSelectedAlbumIds] = useState(new Set());
  const selectionAnchorIndexRef = useRef(null);
  const [contextMenu, setContextMenu] = useState(null);
  const [metadataTracks, setMetadataTracks] = useState(null);
  const [metadataTitle, setMetadataTitle] = useState('Album Metadata');
  const [mergeAlbumsSelection, setMergeAlbumsSelection] = useState(null);
  const [tagSelection, setTagSelection] = useState(null);
  const [remoteMetadataTracks, setRemoteMetadataTracks] = useState(null);

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

  function onSelectAlbum(album, index, event) {
    const multiSelect = event.metaKey || event.ctrlKey;
    const rangeSelect = event.shiftKey;
    const anchorIndex = selectionAnchorIndexRef.current;
    setSelectedAlbumIds((current) => {
      if (rangeSelect && Number.isInteger(anchorIndex)) {
        const rangeStart = Math.min(anchorIndex, index);
        const rangeEnd = Math.max(anchorIndex, index);
        const rangeIds = albums.slice(rangeStart, rangeEnd + 1).map((entry) => entry.id);
        if (multiSelect) {
          const next = new Set(current);
          rangeIds.forEach((id) => next.add(id));
          return next;
        }
        return new Set(rangeIds);
      }
      if (!multiSelect) {
        return new Set([album.id]);
      }
      const next = new Set(current);
      if (next.has(album.id)) {
        next.delete(album.id);
      } else {
        next.add(album.id);
      }
      return next;
    });
    if (!rangeSelect || !Number.isInteger(anchorIndex)) {
      selectionAnchorIndexRef.current = index;
    }
  }

  if (loading && !albums.length) {
    return <p className="empty-state">Loading albums...</p>;
  }

  if (pageError) {
    return <p className="empty-state">{pageError}</p>;
  }

  if (!albums.length) {
    return <p className="empty-state">No albums available from `trive-up`.</p>;
  }

  return (
    <AudioContentScaffold
      title="Albums"
      description="Album browser in the new shell, with cards and cover actions from the historic UI."
    >
      <div className="album-grid">
        {albums.map((album, index) => (
          <article
            key={album.id}
            className={`album-card${selectedAlbumIds.has(album.id) ? ' is-selected' : ''}`}
            onClick={(event) => {
              onSelectAlbum(album, index, event);
              if (!event.metaKey && !event.ctrlKey && !event.shiftKey) {
                onOpenAlbum?.(album);
              }
            }}
            onContextMenuCapture={(event) => {
              event.preventDefault();
              event.stopPropagation();
              if (!selectedAlbumIds.has(album.id)) {
                onSelectAlbum(album, index, event);
              }
              setContextMenu({
                x: event.clientX,
                y: event.clientY,
                album,
              });
            }}
          >
            <div className="album-card-media">
              <button
                type="button"
                className="album-artwork-button"
                onClick={(event) => {
                  event.stopPropagation();
                  onOpenAlbum?.(album);
                }}
                onContextMenu={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
                aria-label={`Open ${album.title}`}
              >
                <span className="album-artwork-ring" aria-hidden="true" />
                <span className="album-artwork-frame">
                  <CoverThumb coverUrl={album.cover_url} alt="" kind="album" />
                </span>
              </button>
              <button
                type="button"
                className="album-play-pill"
                onClick={(event) => {
                  event.stopPropagation();
                  playerActions.playAlbum?.(album);
                }}
                onContextMenu={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
                aria-label="Play album"
              >
                <PlayerPlayIcon />
              </button>
              <button
                type="button"
                className="album-queue-pill"
                onClick={(event) => {
                  event.stopPropagation();
                  playerActions.queueAlbum?.(album);
                }}
                onContextMenu={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
                aria-label="Add album to queue"
              >
                <PlusIcon />
              </button>
            </div>
            <div className="album-copy">
              <TagSummary tags={album.tag_summary || []} onTagClick={onTagClick} />
              <VersionFlag item={album} />
              <h3>{album.title}</h3>
              <InlineArtistLinks
                className="album-copy-artists"
                artists={(album.lead_artist_names || []).map((name) => ({ name }))}
                onOpenArtistName={onOpenArtistName}
              />
              <span>{album.release_year || 'n/a'} · {album.track_count} tracks</span>
            </div>
          </article>
        ))}
      </div>
      {contextMenu ? (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          items={[
            {
              key: 'play-album',
              label: 'Play Album',
              onSelect: () => playerActions.playAlbum?.(contextMenu.album),
            },
            {
              key: 'queue-album',
              label: 'Add Album To Queue',
              onSelect: () => playerActions.queueAlbum?.(contextMenu.album),
            },
            {
              key: 'assign-tags',
              label: 'Assign Tags',
              onSelect: () => {
                const selectedAlbums = selectedAlbumIds.has(contextMenu.album.id)
                  ? albums.filter((album) => selectedAlbumIds.has(album.id))
                  : [contextMenu.album];
                setTagSelection(selectedAlbums);
              },
            },
            ...(versionCountForItem(contextMenu.album) > 1 ? [{
              key: 'version-handling',
              label: 'Version Handling',
              onSelect: openVersionHandling,
            }] : []),
            {
              key: 'remote-metadata-album',
              label: 'Find Remote Metadata',
              onSelect: async () => {
                const selectedAlbums = selectedAlbumIds.has(contextMenu.album.id)
                  ? albums.filter((album) => selectedAlbumIds.has(album.id))
                  : [contextMenu.album];
                if (!libraryId) {
                  return;
                }
                const trackGroups = await Promise.all(selectedAlbums.map((album) => fetchAlbumTracks(libraryId, album.id)));
                const dedupedTracks = Array.from(new Map(trackGroups.flat().map((track) => [track.id, track])).values());
                setRemoteMetadataTracks(dedupedTracks);
              },
            },
            {
              key: 'metadata-album',
              label: 'Metadata',
              onSelect: async () => {
                const selectedAlbums = selectedAlbumIds.has(contextMenu.album.id)
                  ? albums.filter((album) => selectedAlbumIds.has(album.id))
                  : [contextMenu.album];
                if (!libraryId) {
                  return;
                }
                const trackGroups = await Promise.all(selectedAlbums.map((album) => fetchAlbumTracks(libraryId, album.id)));
                const dedupedTracks = Array.from(new Map(trackGroups.flat().map((track) => [track.id, track])).values());
                setMetadataTitle(selectedAlbums.length === 1
                  ? `${selectedAlbums[0].title || 'Album'} Metadata`
                  : `${selectedAlbums.length} albums metadata`);
                setMetadataTracks(dedupedTracks);
              },
            },
            ...(selectedAlbumIds.size > 1 ? [{
              key: 'merge-albums',
              label: 'Merge Albums',
              onSelect: () => {
                const selectedAlbums = selectedAlbumIds.has(contextMenu.album.id)
                  ? albums.filter((album) => selectedAlbumIds.has(album.id))
                  : [contextMenu.album];
                setMergeAlbumsSelection(selectedAlbums);
              },
            }] : []),
          ]}
        />
      ) : null}
      {metadataTracks ? (
        <MultiTrackMetadataEditorModal
          tracks={metadataTracks}
          title={metadataTitle}
          kicker="Album Selection Metadata"
          onClose={() => setMetadataTracks(null)}
        />
      ) : null}
      {mergeAlbumsSelection ? (
        <MergeAlbumsModal
          albums={mergeAlbumsSelection}
          onClose={() => setMergeAlbumsSelection(null)}
          onApply={async (targetAlbumTitle, options = {}) => {
            if (!libraryId || !targetAlbumTitle) {
              setMergeAlbumsSelection(null);
              return;
            }
            await mergeAlbums({
              albumIds: mergeAlbumsSelection.map((album) => album.id),
              targetTitle: targetAlbumTitle,
              releaseDateResolution: options.releaseDateResolution,
            });
            setMergeAlbumsSelection(null);
            onRefresh?.();
          }}
        />
      ) : null}
      {remoteMetadataTracks ? (
        <RemoteMetadataModal
          tracks={remoteMetadataTracks}
          onApplied={() => onRefresh?.()}
          onClose={() => setRemoteMetadataTracks(null)}
        />
      ) : null}
      {tagSelection ? (
        <TrackTagAssignmentModal
          scope="album"
          items={tagSelection}
          onSaved={() => onRefresh?.()}
          onClose={() => setTagSelection(null)}
        />
      ) : null}
    </AudioContentScaffold>
  );
}
