import { useEffect, useRef, useState } from 'react';
import AudioContentScaffold from '../AudioContentScaffold';
import CoverThumb from '../../../../shared/ui/CoverThumb';
import { PlayerPlayIcon, PlusIcon } from '../../../../shared/ui/TablerIcons';
import ContextMenu from '../../../../shared/ui/ContextMenu';
import { fetchArtistTracks } from '../../../../api/library';
import MultiTrackMetadataEditorModal from '../../metadata/MultiTrackMetadataEditorModal';
import RemoteMetadataModal from '../../metadata/RemoteMetadataModal';
import TrackTagAssignmentModal from '../../tags/TrackTagAssignmentModal';
import TagSummary from '../../tags/TagSummary';
import VersionFlag, { openVersionHandling, versionCountForItem } from '../../versions/VersionFlag';

function withArtistCoverVersion(url, version) {
  if (!url || !version) {
    return url || '';
  }
  const joiner = url.includes('?') ? '&' : '?';
  return `${url}${joiner}_triver_artist=${encodeURIComponent(version)}`;
}

export default function ArtistsView({ artists = [], loading = false, pageError = '', playerActions = {}, libraryId = '', onOpenArtist = null, onRefresh = null, onTagClick = null }) {
  const [selectedArtistIds, setSelectedArtistIds] = useState(new Set());
  const selectionAnchorIndexRef = useRef(null);
  const [contextMenu, setContextMenu] = useState(null);
  const [metadataTracks, setMetadataTracks] = useState(null);
  const [remoteMetadataTracks, setRemoteMetadataTracks] = useState(null);
  const [tagSelection, setTagSelection] = useState(null);

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

  function onSelectArtist(artist, index, event) {
    const multiSelect = event.metaKey || event.ctrlKey;
    const rangeSelect = event.shiftKey;
    const anchorIndex = selectionAnchorIndexRef.current;
    setSelectedArtistIds((current) => {
      if (rangeSelect && Number.isInteger(anchorIndex)) {
        const rangeStart = Math.min(anchorIndex, index);
        const rangeEnd = Math.max(anchorIndex, index);
        const rangeIds = artists.slice(rangeStart, rangeEnd + 1).map((entry) => entry.id);
        if (multiSelect) {
          const next = new Set(current);
          rangeIds.forEach((id) => next.add(id));
          return next;
        }
        return new Set(rangeIds);
      }
      if (!multiSelect) {
        return new Set([artist.id]);
      }
      const next = new Set(current);
      if (next.has(artist.id)) {
        next.delete(artist.id);
      } else {
        next.add(artist.id);
      }
      return next;
    });
    if (!rangeSelect || !Number.isInteger(anchorIndex)) {
      selectionAnchorIndexRef.current = index;
    }
  }

  if (loading && !artists.length) {
    return <p className="empty-state">Loading artists...</p>;
  }

  if (pageError) {
    return <p className="empty-state">{pageError}</p>;
  }

  if (!artists.length) {
    return <p className="empty-state">No artists available from `trive-up`.</p>;
  }

  return (
    <AudioContentScaffold
      title="Artists"
      description="Artist cards carried into the new shell with album-style cards."
    >
      <div className="album-grid artist-grid">
        {artists.map((artist, index) => (
          <article
            key={artist.id}
            className={`album-card artist-card${selectedArtistIds.has(artist.id) ? ' is-selected' : ''}`}
            onClick={(event) => {
              onSelectArtist(artist, index, event);
              if (!event.metaKey && !event.ctrlKey && !event.shiftKey) {
                onOpenArtist?.(artist);
              }
            }}
            onContextMenuCapture={(event) => {
              event.preventDefault();
              event.stopPropagation();
              if (!selectedArtistIds.has(artist.id)) {
                onSelectArtist(artist, index, event);
              }
              setContextMenu({
                x: event.clientX,
                y: event.clientY,
                artist,
              });
            }}
          >
            <div className="album-card-media">
              <button
                type="button"
                className="album-artwork-button"
                onClick={(event) => {
                  event.stopPropagation();
                  onOpenArtist?.(artist);
                }}
                onContextMenu={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
                aria-label={`Open ${artist.name}`}
              >
                <span className="album-artwork-ring" aria-hidden="true" />
                <span className="album-artwork-frame">
                  <CoverThumb coverUrl={withArtistCoverVersion(artist.cover_url, artist.updated_at)} alt="" kind="artist" />
                </span>
              </button>
              <button
                type="button"
                className="album-play-pill"
                onClick={(event) => {
                  event.stopPropagation();
                  playerActions.playArtist?.(artist);
                }}
                onContextMenu={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
                aria-label="Play artist"
              >
                <PlayerPlayIcon />
              </button>
              <button
                type="button"
                className="album-queue-pill"
                onClick={(event) => {
                  event.stopPropagation();
                  playerActions.queueArtist?.(artist);
                }}
                onContextMenu={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
                aria-label="Add artist to queue"
              >
                <PlusIcon />
              </button>
            </div>
            <div className="album-copy">
              <TagSummary tags={artist.tag_summary || []} onTagClick={onTagClick} />
              <VersionFlag item={artist} />
              <h3>{artist.name}</h3>
              <p>Artist index</p>
              <span>{artist.track_count} linked tracks</span>
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
              key: 'play-artist',
              label: 'Play Artist',
              onSelect: () => playerActions.playArtist?.(contextMenu.artist),
            },
            {
              key: 'queue-artist',
              label: 'Add Artist To Queue',
              onSelect: () => playerActions.queueArtist?.(contextMenu.artist),
            },
            {
              key: 'assign-tags',
              label: 'Assign Tags',
              onSelect: () => {
                const selectedArtists = selectedArtistIds.has(contextMenu.artist.id)
                  ? artists.filter((artist) => selectedArtistIds.has(artist.id))
                  : [contextMenu.artist];
                setTagSelection(selectedArtists);
              },
            },
            ...(versionCountForItem(contextMenu.artist) > 1 ? [{
              key: 'version-handling',
              label: 'Version Handling',
              onSelect: openVersionHandling,
            }] : []),
            {
              key: 'remote-metadata-artist',
              label: 'Find Remote Metadata',
              onSelect: async () => {
                if (!libraryId) {
                  return;
                }
                const selectedArtists = selectedArtistIds.has(contextMenu.artist.id)
                  ? artists.filter((artist) => selectedArtistIds.has(artist.id))
                  : [contextMenu.artist];
                const trackGroups = await Promise.all(selectedArtists.map((artist) => fetchArtistTracks(libraryId, artist.id)));
                const dedupedTracks = Array.from(new Map(trackGroups.flat().map((track) => [track.id, track])).values());
                setRemoteMetadataTracks(dedupedTracks);
              },
            },
            {
              key: 'metadata-artist',
              label: 'Metadata',
              onSelect: async () => {
                if (!libraryId) {
                  return;
                }
                const selectedArtists = selectedArtistIds.has(contextMenu.artist.id)
                  ? artists.filter((artist) => selectedArtistIds.has(artist.id))
                  : [contextMenu.artist];
                const trackGroups = await Promise.all(selectedArtists.map((artist) => fetchArtistTracks(libraryId, artist.id)));
                const dedupedTracks = Array.from(new Map(trackGroups.flat().map((track) => [track.id, track])).values());
                setMetadataTracks(dedupedTracks);
              },
            },
          ]}
        />
      ) : null}
      {metadataTracks ? (
        <MultiTrackMetadataEditorModal
          tracks={metadataTracks}
          title={metadataTracks.length > 1 ? `${metadataTracks.length} tracks from artist selection` : 'Artist Metadata'}
          kicker="Artist Selection Metadata"
          onClose={() => setMetadataTracks(null)}
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
          scope="artist"
          items={tagSelection}
          onSaved={() => onRefresh?.()}
          onClose={() => setTagSelection(null)}
        />
      ) : null}
    </AudioContentScaffold>
  );
}
