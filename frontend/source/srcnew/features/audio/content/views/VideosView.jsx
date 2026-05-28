import { useEffect, useState } from 'react';
import AudioContentScaffold from '../AudioContentScaffold';
import CoverThumb from '../../../../shared/ui/CoverThumb';
import { PlayerPlayIcon, VideoIcon } from '../../../../shared/ui/TablerIcons';
import ContextMenu from '../../../../shared/ui/ContextMenu';
import VideoPosterSelectorModal from '../../video/VideoPosterSelectorModal';
import TrackMetadataEditorModal from '../../metadata/TrackMetadataEditorModal';
import MultiTrackMetadataEditorModal from '../../metadata/MultiTrackMetadataEditorModal';
import RemoteMetadataModal from '../../metadata/RemoteMetadataModal';
import TrackTagAssignmentModal from '../../tags/TrackTagAssignmentModal';
import TagSummary from '../../tags/TagSummary';
import VersionFlag, { openVersionHandling, versionCountForItem } from '../../versions/VersionFlag';
import { fetchVideoSeriesTracks } from '../../../../api/library';

function formatSeriesMeta(group) {
  const parts = [];
  if (group.group_kind === 'series') {
    parts.push(group.season_count === 1 ? '1 season' : `${group.season_count || 0} seasons`);
  }
  parts.push(group.track_count === 1 ? '1 video' : `${group.track_count || 0} videos`);
  return parts.join(' · ');
}

function playbackStatusForGroup(group) {
  return group.playback_status || group.representative_track?.playback_status || { cache_ready: true };
}

function playbackBadgeText(status) {
  if (status?.cache_ready !== false) {
    return 'Ready';
  }
  if (status?.building) {
    return `Preparing ${status?.progress?.percent || 0}%`;
  }
  return 'Needs preparation';
}

const VIDEO_SECTIONS = [
  { key: 'movies', title: 'Movies' },
  { key: 'series', title: 'Series' },
  { key: 'uncategorized', title: 'Uncategorized' },
];
const VIDEO_TAG_DEFINITION_KEYS = ['video-tag'];

export default function VideosView({
  seriesGroups = [],
  curationRows = [],
  loading = false,
  pageError = '',
  playerActions = {},
  libraryId = '',
  onRefresh = null,
  onOpenSeries = null,
  onTagClick = null,
  onLoadMoreRow = null,
}) {
  const [contextMenu, setContextMenu] = useState(null);
  const [posterEditor, setPosterEditor] = useState(null);
  const [metadataTrack, setMetadataTrack] = useState(null);
  const [metadataSelection, setMetadataSelection] = useState(null);
  const [metadataError, setMetadataError] = useState('');
  const [coverOverrides, setCoverOverrides] = useState({});
  const [tagSelection, setTagSelection] = useState(null);
  const [remoteMetadataSelection, setRemoteMetadataSelection] = useState(null);

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

  if (loading && !seriesGroups.length) {
    return <p className="empty-state">Loading videos...</p>;
  }

  if (pageError) {
    return <p className="empty-state">{pageError}</p>;
  }

  if (!seriesGroups.length) {
    return <p className="empty-state">No videos available from `trive-up`.</p>;
  }

  async function openGroupMetadata(group) {
    setMetadataError('');
    if (group.group_kind !== 'series') {
      setMetadataSelection(null);
      setMetadataTrack(group.representative_track || null);
      return;
    }
    if (!libraryId || !group.series_key) {
      setMetadataError('Unable to open series metadata: library is not ready.');
      return;
    }
    try {
      const tracks = await fetchVideoSeriesTracks(libraryId, group.series_key);
      if (!tracks.length) {
        setMetadataError('No indexed episodes for this series.');
        return;
      }
      setMetadataTrack(null);
      setMetadataSelection({
        title: `${group.title || 'Series'} Metadata`,
        tracks,
      });
    } catch (error) {
      setMetadataError(error.message || 'Unable to open series metadata.');
    }
  }

  async function openGroupTags(group) {
    setMetadataError('');
    if (group.group_kind !== 'series') {
      setTagSelection([group.representative_track].filter(Boolean));
      return;
    }
    if (!libraryId || !group.series_key) {
      setMetadataError('Unable to open series tags: library is not ready.');
      return;
    }
    try {
      const tracks = await fetchVideoSeriesTracks(libraryId, group.series_key);
      if (!tracks.length) {
        setMetadataError('No indexed episodes for this series.');
        return;
      }
      setTagSelection(tracks);
    } catch (error) {
      setMetadataError(error.message || 'Unable to open series tags.');
    }
  }

  async function openGroupRemoteMetadata(group) {
    setMetadataError('');
    if (group.group_kind !== 'series') {
      setRemoteMetadataSelection([group.representative_track].filter(Boolean));
      return;
    }
    if (!libraryId || !group.series_key) {
      setMetadataError('Unable to open remote metadata: library is not ready.');
      return;
    }
    try {
      const tracks = await fetchVideoSeriesTracks(libraryId, group.series_key);
      if (!tracks.length) {
        setMetadataError('No indexed episodes for this series.');
        return;
      }
      setRemoteMetadataSelection(tracks);
    } catch (error) {
      setMetadataError(error.message || 'Unable to open remote metadata.');
    }
  }

  const sections = curationRows.length
    ? curationRows.map((row) => ({
      key: row.id,
      title: row.label,
      groups: row.groups || [],
      hasMore: Boolean(row.next),
      rowId: row.id,
      totalCount: row.count || 0,
    })).filter((section) => section.groups.length || section.hasMore)
    : VIDEO_SECTIONS
      .map((section) => ({
        ...section,
        groups: seriesGroups.filter((group) => (group.section || (group.group_kind === 'series' ? 'series' : 'uncategorized')) === section.key),
      }))
      .filter((section) => section.groups.length);

  return (
    <AudioContentScaffold
      title="Videos"
      description="Video library grouped by TV series metadata."
    >
      <div className="video-section-stack">
        {metadataError ? <p className="metadata-error">{metadataError}</p> : null}
        {sections.map((section) => (
          <section key={section.key} className="video-section">
            <header className="video-section-head">
              <h3>{section.title}</h3>
              {section.totalCount ? <span>{section.groups.length} / {section.totalCount}</span> : null}
            </header>
            <div className="video-series-grid">
              {section.groups.map((group) => {
                const playbackStatus = playbackStatusForGroup(group);
                const cacheReady = playbackStatus?.cache_ready !== false;
                return (
                <article
                  key={group.series_key || group.id}
                  className={`video-series-card${group.group_kind === 'series' ? ' is-series' : ' is-standalone'}${cacheReady ? '' : ' is-cache-pending'}${playbackStatus?.building ? ' is-cache-building' : ''}`}
                  onClick={() => onOpenSeries?.(group)}
                  onContextMenuCapture={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    setContextMenu({
                      x: event.clientX,
                      y: event.clientY,
                      group,
                    });
                  }}
                >
                  <button
                    type="button"
                    className="video-series-cover-button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpenSeries?.(group);
                    }}
                    onContextMenu={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                    }}
                    aria-label={`Open ${group.title}`}
                  >
                    <CoverThumb coverUrl={coverOverrides[group.series_key || group.id] || group.cover_url} alt="" kind="album" />
                    <span className="video-cache-badge">{playbackBadgeText(playbackStatus)}</span>
                    <span className="video-series-kind" aria-hidden="true">
                      {group.group_kind === 'series' ? <VideoIcon /> : <PlayerPlayIcon />}
                    </span>
                  </button>
                  <div className="video-series-copy">
                    <TagSummary tags={group.representative_track?.tag_summary || []} onTagClick={onTagClick} />
                    <VersionFlag item={group} />
                    <h3>{group.title}</h3>
                    <span>{formatSeriesMeta(group)}</span>
                    {group.first_episode_title ? <small>{group.first_episode_title}</small> : null}
                  </div>
                  {group.group_kind === 'standalone' ? (
              <button
                type="button"
                className="video-series-play"
                onClick={(event) => {
                  event.stopPropagation();
                  playerActions.playSingleTrack?.(group.representative_track);
                }}
                onContextMenu={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
                aria-label={`Play ${group.title}`}
              >
                <PlayerPlayIcon />
              </button>
                  ) : null}
                </article>
                );
              })}
            </div>
            {section.hasMore ? (
              <div className="video-section-load-more">
                <button type="button" onClick={() => onLoadMoreRow?.(section.rowId)}>
                  Load more
                </button>
              </div>
            ) : null}
          </section>
        ))}
      </div>
      {contextMenu ? (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          items={[
            {
              key: 'open',
              label: contextMenu.group.group_kind === 'series' ? 'Open Series' : 'Open Video',
              onSelect: () => onOpenSeries?.(contextMenu.group),
            },
            {
              key: 'play',
              label: contextMenu.group.group_kind === 'series' ? 'Play First Episode' : 'Play Video',
              onSelect: () => playerActions.playSingleTrack?.(contextMenu.group.representative_track),
            },
            {
              key: 'assign-tags',
              label: 'Assign Tags',
              onSelect: () => openGroupTags(contextMenu.group),
            },
            {
              key: 'remote-metadata',
              label: 'Find Remote Metadata',
              onSelect: () => openGroupRemoteMetadata(contextMenu.group),
            },
            ...(versionCountForItem(contextMenu.group) > 1 ? [{
              key: 'version-handling',
              label: 'Version Handling',
              onSelect: openVersionHandling,
            }] : []),
            {
              key: 'metadata',
              label: 'Metadata',
              onSelect: () => openGroupMetadata(contextMenu.group),
            },
            {
              key: 'poster',
              label: contextMenu.group.group_kind === 'series' ? 'Edit Series Poster' : 'Edit Video Poster',
              onSelect: () => setPosterEditor({
                group: contextMenu.group,
                track: contextMenu.group.representative_track,
                mode: contextMenu.group.group_kind === 'series' ? 'series' : 'track',
              }),
            },
          ]}
        />
      ) : null}
      {posterEditor ? (
        <VideoPosterSelectorModal
          track={posterEditor.track}
          mode={posterEditor.mode}
          seriesKey={posterEditor.group.series_key}
          title={posterEditor.group.title}
          onSelected={(payload) => {
            if (payload?.poster_url) {
              setCoverOverrides((current) => ({
                ...current,
                [posterEditor.group.series_key || posterEditor.group.id]: payload.poster_url,
              }));
            }
            onRefresh?.();
          }}
          onClose={() => setPosterEditor(null)}
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
          kicker="Video Selection Metadata"
          onClose={() => setMetadataSelection(null)}
        />
      ) : null}
      {tagSelection ? (
        <TrackTagAssignmentModal
          tracks={tagSelection}
          definitionKeys={VIDEO_TAG_DEFINITION_KEYS}
          onSaved={() => onRefresh?.()}
          onClose={() => setTagSelection(null)}
        />
      ) : null}
      {remoteMetadataSelection ? (
        <RemoteMetadataModal
          tracks={remoteMetadataSelection}
          mode="find"
          onApplied={() => onRefresh?.()}
          onClose={() => setRemoteMetadataSelection(null)}
        />
      ) : null}
    </AudioContentScaffold>
  );
}
