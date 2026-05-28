import { useEffect, useRef, useState } from 'react';
import AudioContentScaffold from '../AudioContentScaffold';
import CoverThumb from '../../../../shared/ui/CoverThumb';
import InlineArtistLinks from '../../../../shared/ui/InlineArtistLinks';
import MarqueeText from '../../../../shared/ui/MarqueeText';
import { PlayerPauseIcon, PlayerPlayIcon, PlusIcon, PlusPlayIcon, SettingsIcon } from '../../../../shared/ui/TablerIcons';
import ContextMenu from '../../../../shared/ui/ContextMenu';
import TrackMetadataEditorModal from '../../metadata/TrackMetadataEditorModal';
import MultiTrackMetadataEditorModal from '../../metadata/MultiTrackMetadataEditorModal';
import AutoMetadataModal from '../../metadata/AutoMetadataModal';
import RemoteMetadataModal from '../../metadata/RemoteMetadataModal';
import TrackTagAssignmentModal from '../../tags/TrackTagAssignmentModal';
import TagSummary from '../../tags/TagSummary';
import { getMediaKind, isVideoItem } from '../../../media/mediaItem';
import VersionFlag, { openVersionHandling, versionCountForItem } from '../../versions/VersionFlag';

const TRACK_TAG_DEFINITION_KEYS = ['audio-tag'];

export default function TracksView({ tracks = [], loading = false, pageError = '', playerActions = {}, playerState = {}, onOpenArtist = null, onOpenArtistName = null, onRefresh = null, onTagClick = null }) {
  const [selectedTrackIds, setSelectedTrackIds] = useState(new Set());
  const selectionAnchorIndexRef = useRef(null);
  const [contextMenu, setContextMenu] = useState(null);
  const [metadataTrack, setMetadataTrack] = useState(null);
  const [metadataSelection, setMetadataSelection] = useState(null);
  const [autoMetadataSelection, setAutoMetadataSelection] = useState(null);
  const [remoteMetadataSelection, setRemoteMetadataSelection] = useState(null);
  const [tagSelection, setTagSelection] = useState(null);
  const currentTrackId = playerState.currentTrack?.id || null;
  const isPlaying = Boolean(playerState.isPlaying);

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

  function onSelectTrackRow(track, index, event) {
    const multiSelect = event.metaKey || event.ctrlKey;
    const rangeSelect = event.shiftKey;
    const anchorIndex = selectionAnchorIndexRef.current;
    setSelectedTrackIds((current) => {
      if (rangeSelect && Number.isInteger(anchorIndex)) {
        if (anchorIndex >= 0 && index >= 0) {
          const rangeStart = Math.min(anchorIndex, index);
          const rangeEnd = Math.max(anchorIndex, index);
          const rangeIds = tracks.slice(rangeStart, rangeEnd + 1).map((entry) => entry.id);
          if (multiSelect) {
            const next = new Set(current);
            rangeIds.forEach((id) => next.add(id));
            return next;
          }
          return new Set(rangeIds);
        }
      }
      if (!multiSelect) {
        return new Set([track.id]);
      }
      const next = new Set(current);
      if (next.has(track.id)) {
        next.delete(track.id);
      } else {
        next.add(track.id);
      }
      return next;
    });
    if (!rangeSelect || !Number.isInteger(anchorIndex)) {
      selectionAnchorIndexRef.current = index;
    }
  }

  if (loading && !tracks.length) {
    return <p className="empty-state">Loading tracks...</p>;
  }

  if (pageError) {
    return <p className="empty-state">{pageError}</p>;
  }

  if (!tracks.length) {
    return <p className="empty-state">No tracks available from `trive-up`.</p>;
  }

  return (
    <AudioContentScaffold
      title="Tracks"
      description="Track list carried into the new shell from the old interface."
    >
      <ul className="library-track-list">
        {tracks.map((track, index) => {
          const isVideo = getMediaKind(track) === 'video';
          return (
          <li
            key={track.id}
            className={`library-track-row${selectedTrackIds.has(track.id) ? ' is-selected' : ''}`}
            onPointerDownCapture={(event) => {
              if (event.button !== 0) {
                return;
              }
              const interactiveTarget = event.target.closest('button, a, input, textarea, select');
              if (interactiveTarget) {
                return;
              }
              if (event.shiftKey) {
                event.preventDefault();
              }
              onSelectTrackRow(track, index, event);
            }}
            onContextMenuCapture={(event) => {
              event.preventDefault();
              event.stopPropagation();
              if (!selectedTrackIds.has(track.id)) {
                onSelectTrackRow(track, index, event);
              }
              setContextMenu({
                x: event.clientX,
                y: event.clientY,
                track,
              });
            }}
          >
            <button
              type="button"
              className={`play-trigger${currentTrackId === track.id ? ' is-active' : ''}`}
              onClick={(event) => {
                event.stopPropagation();
                playerActions.playSingleTrack?.(track);
              }}
              onContextMenu={(event) => {
                event.preventDefault();
                event.stopPropagation();
              }}
              aria-label={currentTrackId === track.id && isPlaying ? 'Pause track' : 'Play track'}
            >
              {currentTrackId === track.id && isPlaying ? <PlayerPauseIcon /> : <PlayerPlayIcon />}
            </button>
            <button
              type="button"
              className="play-trigger play-trigger-ghost"
              onClick={(event) => {
                event.stopPropagation();
                playerActions.queueTrack?.(track);
              }}
              onContextMenu={(event) => {
                event.preventDefault();
                event.stopPropagation();
              }}
              aria-label="Add track to queue"
            >
              <PlusIcon />
            </button>
            <button
              type="button"
              className="play-trigger play-trigger-ghost"
              onClick={(event) => {
                event.stopPropagation();
                playerActions.queueAndPlayTrack?.(track);
              }}
              onContextMenu={(event) => {
                event.preventDefault();
                event.stopPropagation();
              }}
              aria-label="Add track to queue and play"
            >
              <PlusPlayIcon />
            </button>
            <button
              type="button"
              className="play-trigger play-trigger-ghost"
              onClick={(event) => {
                event.stopPropagation();
                setMetadataTrack(track);
              }}
              onContextMenu={(event) => {
                event.preventDefault();
                event.stopPropagation();
              }}
              aria-label="Open track metadata"
            >
              <SettingsIcon />
            </button>
            <div className="library-track-art">
              <CoverThumb coverUrl={track.cover_url} alt="" kind="track" />
            </div>
            <div className="library-track-copy">
              <MarqueeText className="library-track-title" text={track.canonical_title} />
              <div className="library-track-badges">
                {isVideo ? <span className="media-kind-badge is-video">VIDEO</span> : null}
                <TagSummary tags={track.tag_summary || []} onTagClick={onTagClick} />
                <VersionFlag item={track} />
              </div>
              <InlineArtistLinks
                className="library-track-subtitle"
                artists={(track.artist_summary || []).map((artist) => ({ id: artist.artist_id, name: artist.name }))}
                onOpenArtistId={(_artistId, artistLink) => onOpenArtist?.(artistLink)}
                onOpenArtistName={onOpenArtistName}
              />
            </div>
            <div className="library-track-side">
              <span className="library-track-album">{track.album_title || 'Unknown Album'}</span>
              <span className="library-track-extra">
                {track.track_number ? `#${track.track_number}` : isVideo ? 'video item' : 'track'}
                {track.duration_seconds ? ` · ${Math.round(track.duration_seconds)}s` : ''}
              </span>
            </div>
          </li>
          );
        })}
      </ul>
      {contextMenu ? (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          items={[
            {
              key: 'play',
              label: isVideoItem(contextMenu.track) ? 'Play Video Item' : 'Play',
              onSelect: () => playerActions.playSingleTrack?.(contextMenu.track),
            },
            {
              key: 'queue',
              label: 'Add To Queue',
              onSelect: () => playerActions.queueTrack?.(contextMenu.track),
            },
            {
              key: 'queue-play',
              label: 'Add And Play',
              onSelect: () => playerActions.queueAndPlayTrack?.(contextMenu.track),
            },
            {
              key: 'assign-tags',
              label: 'Assign Tags',
              onSelect: () => {
                const selectedTracks = selectedTrackIds.has(contextMenu.track.id)
                  ? tracks.filter((track) => selectedTrackIds.has(track.id))
                  : [contextMenu.track];
                setTagSelection(selectedTracks);
              },
            },
            ...(versionCountForItem(contextMenu.track) > 1 ? [{
              key: 'version-handling',
              label: 'Version Handling',
              onSelect: openVersionHandling,
            }] : []),
            {
              key: 'remote-metadata',
              label: 'Find Remote Metadata',
              onSelect: () => {
                const selectedTracks = selectedTrackIds.has(contextMenu.track.id)
                  ? tracks.filter((track) => selectedTrackIds.has(track.id))
                  : [contextMenu.track];
                setRemoteMetadataSelection(selectedTracks);
              },
            },
            {
              key: 'try-auto-metadata',
              label: 'Try Auto Metadata',
              onSelect: () => {
                const selectedTracks = selectedTrackIds.has(contextMenu.track.id)
                  ? tracks.filter((track) => selectedTrackIds.has(track.id))
                  : [contextMenu.track];
                setAutoMetadataSelection(selectedTracks);
              },
            },
            {
              key: 'metadata',
              label: 'Metadata',
              onSelect: () => {
                const selectedTracks = selectedTrackIds.has(contextMenu.track.id)
                  ? tracks.filter((track) => selectedTrackIds.has(track.id))
                  : [contextMenu.track];
                if (selectedTracks.length > 1) {
                  setMetadataSelection(selectedTracks);
                  return;
                }
                setMetadataTrack(contextMenu.track);
              },
            },
          ]}
        />
      ) : null}
      {metadataTrack ? <TrackMetadataEditorModal track={metadataTrack} onClose={() => setMetadataTrack(null)} /> : null}
      {metadataSelection ? (
        <MultiTrackMetadataEditorModal
          tracks={metadataSelection}
          title={`${metadataSelection.length} selected tracks`}
          kicker="Track Selection Metadata"
          onClose={() => setMetadataSelection(null)}
        />
      ) : null}
      {autoMetadataSelection ? (
        <AutoMetadataModal
          tracks={autoMetadataSelection}
          onApplied={() => onRefresh?.()}
          onClose={() => setAutoMetadataSelection(null)}
        />
      ) : null}
      {remoteMetadataSelection ? (
        <RemoteMetadataModal
          tracks={remoteMetadataSelection}
          onApplied={() => onRefresh?.()}
          onClose={() => setRemoteMetadataSelection(null)}
        />
      ) : null}
      {tagSelection ? (
        <TrackTagAssignmentModal
          tracks={tagSelection}
          definitionKeys={TRACK_TAG_DEFINITION_KEYS}
          onSaved={() => onRefresh?.()}
          onClose={() => setTagSelection(null)}
        />
      ) : null}
    </AudioContentScaffold>
  );
}
