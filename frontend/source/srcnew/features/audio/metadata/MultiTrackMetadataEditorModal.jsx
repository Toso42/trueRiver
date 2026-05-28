import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchMediaFile, fetchMetadataModel, patchMediaFileMetadata } from '../../../api/metadata';
import { isVideoItem } from '../../media/mediaItem';
import MetadataEditableField from './MetadataEditableField';
import { aggregateTrackMetadata } from './trackMetadataAggregation';
import MetadataFieldAdder from './MetadataFieldAdder';
import { buildMultiVideoMetadataRows } from './videoMetadataFields';

const CANONICAL_TRACK_FIELDS = [
  {
    name: 'TrackName',
    readValues: (track) => [track.canonical_title || track.title || ''].filter(Boolean),
  },
  {
    name: 'Artist',
    readValues: (track) => {
      const names = (track.artist_summary || []).map((artist) => artist.name).filter(Boolean);
      return names.length ? [names.join(', ')] : [];
    },
  },
  {
    name: 'Album',
    readValues: (track) => [track.album_title || ''].filter(Boolean),
  },
  {
    name: 'TrackNumber',
    readValues: (track) => (track.track_number ? [String(track.track_number)] : []),
  },
  {
    name: 'DiscNumber',
    readValues: (track) => (track.disc_number ? [String(track.disc_number)] : []),
  },
  {
    name: 'ReleaseDate',
    readValues: (track) => (track.release_year ? [String(track.release_year)] : []),
  },
];

function buildCanonicalRowsFromTracks(tracks, existingRows) {
  const existingFields = new Set(existingRows.map((row) => row.field));

  return CANONICAL_TRACK_FIELDS
    .filter((field) => !existingFields.has(field.name))
    .map((field) => {
      const valuesByText = new Map();
      for (const track of tracks || []) {
        for (const value of field.readValues(track)) {
          const bucket = valuesByText.get(value) || { value, media_files: [] };
          bucket.media_files.push({
            id: track.primary_file,
            item_id: track.id,
            item_label: track.canonical_title || track.title || 'Media item',
          });
          valuesByText.set(value, bucket);
        }
      }

      return {
        section: 'triver',
        field: field.name,
        display_field: field.name,
        read_only: false,
        values: Array.from(valuesByText.values()).sort((left, right) => left.value.localeCompare(right.value)),
      };
    })
    .filter((row) => row.values.length);
}

export default function MultiTrackMetadataEditorModal({
  tracks = [],
  title = 'Selection Metadata',
  kicker = 'Track Selection Metadata',
  onClose = () => {},
}) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [manifestFields, setManifestFields] = useState([]);
  const [pendingTriverFields, setPendingTriverFields] = useState([]);
  const [activeMetadataMode, setActiveMetadataMode] = useState('standard');

  const effectiveTracks = useMemo(() => {
    const deduped = new Map();
    (tracks || []).forEach((track) => {
      if (track?.id && track?.primary_file) {
        deduped.set(track.id, track);
      }
    });
    return Array.from(deduped.values());
  }, [tracks]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!effectiveTracks.length) {
        setRows([]);
        return;
      }
      setLoading(true);
      setError('');
      try {
        const tracksByMediaFileId = new Map(effectiveTracks.map((track) => [track.primary_file, track]));
        const mediaFiles = await Promise.all(effectiveTracks.map((track) => fetchMediaFile(track.primary_file)));
        if (!cancelled) {
          setRows(aggregateTrackMetadata(mediaFiles, tracksByMediaFileId));
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError.message || 'Metadata selection unavailable');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [effectiveTracks]);

  useEffect(() => {
    let cancelled = false;
    fetchMetadataModel()
      .then((payload) => {
        if (!cancelled) {
          setManifestFields(payload.fields || []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setManifestFields([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setPendingTriverFields([]);
    setActiveMetadataMode('standard');
  }, [tracks]);

  if (!effectiveTracks.length) {
    return null;
  }

  const triverRows = rows.filter((row) => row.section === 'triver');
  const sourceRows = rows.filter((row) => row.section !== 'triver');
  const videoTracks = effectiveTracks.filter((track) => isVideoItem(track));
  const hasVideoTracks = videoTracks.length > 0;
  const canonicalFallbackRows = buildCanonicalRowsFromTracks(effectiveTracks, triverRows);
  const existingTriverFields = new Set([
    ...triverRows.map((row) => row.field),
    ...canonicalFallbackRows.map((row) => row.field),
  ]);
  const mergedTriverRows = [
    ...triverRows.map((row) => ({ ...row, read_only: false })),
    ...canonicalFallbackRows,
    ...pendingTriverFields
      .filter((field) => !existingTriverFields.has(field.name))
      .map((field) => ({
        section: 'triver',
        field: field.name,
        display_field: field.display_name || field.name,
        values: [],
        read_only: false,
      })),
  ];
  const videoMetadataRows = buildMultiVideoMetadataRows(mergedTriverRows, videoTracks);

  async function handleApply(row, nextValues) {
    await Promise.all(effectiveTracks.map((track) => patchMediaFileMetadata(track.primary_file, row.field, nextValues)));
    const tracksByMediaFileId = new Map(effectiveTracks.map((track) => [track.primary_file, track]));
    const mediaFiles = await Promise.all(effectiveTracks.map((track) => fetchMediaFile(track.primary_file)));
    setRows(aggregateTrackMetadata(mediaFiles, tracksByMediaFileId));
    setPendingTriverFields((current) => current.filter((field) => field.name !== row.field));
  }

  async function handleApplyVideo(row, nextValues) {
    await Promise.all(videoTracks.map((track) => patchMediaFileMetadata(track.primary_file, row.field, nextValues)));
    const tracksByMediaFileId = new Map(effectiveTracks.map((track) => [track.primary_file, track]));
    const mediaFiles = await Promise.all(effectiveTracks.map((track) => fetchMediaFile(track.primary_file)));
    setRows(aggregateTrackMetadata(mediaFiles, tracksByMediaFileId));
  }

  return createPortal(
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <section className="track-meta-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <div className="track-meta-head">
          <div>
            <p className="panel-kicker">{kicker}</p>
            <h3>{title}</h3>
          </div>
          <div className="track-meta-actions">
            <button type="button" className="modal-close" onClick={onClose} aria-label="Close selection metadata modal">×</button>
          </div>
        </div>
        <div className="track-meta-layout track-meta-layout-wide">
          <div className="metadata-selection-summary">
            {effectiveTracks.slice(0, 18).map((track) => (
              <span key={track.id}>{track.canonical_title || track.title}</span>
            ))}
            {effectiveTracks.length > 18 ? <span>+{effectiveTracks.length - 18}</span> : null}
          </div>
          <div className="metadata-stack">
            <section className="metadata-section">
              <div className="metadata-section-headline">
                <h4>Selection Metadata</h4>
                {loading ? <span>loading</span> : null}
              </div>
              {hasVideoTracks ? (
                <div className="metadata-mode-switch" role="tablist" aria-label="Metadata mode">
                  <button
                    type="button"
                    className={`metadata-mode-button${activeMetadataMode === 'standard' ? ' is-active' : ''}`}
                    onClick={() => setActiveMetadataMode('standard')}
                  >
                    Standard
                  </button>
                  <button
                    type="button"
                    className={`metadata-mode-button${activeMetadataMode === 'video' ? ' is-active' : ''}`}
                    onClick={() => setActiveMetadataMode('video')}
                  >
                    Video Metadata
                  </button>
                </div>
              ) : null}
              {error ? <p className="metadata-error">{error}</p> : null}
              {!loading && !error && !rows.length && !mergedTriverRows.length ? (
                <p className="empty-state">No metadata available for this selection.</p>
              ) : null}
              {hasVideoTracks && activeMetadataMode === 'video' ? (
                <div className="metadata-edit-section">
                  <dl className="metadata-grid metadata-edit-grid">
                    {videoMetadataRows.map((row) => (
                      <MetadataEditableField
                        key={`selection:video:${row.field}`}
                        row={row}
                        disabled={row.read_only || loading}
                        onApply={(nextValues) => handleApplyVideo(row, nextValues)}
                      />
                    ))}
                  </dl>
                </div>
              ) : mergedTriverRows.length ? (
                <div className="metadata-edit-section">
                  <div className="metadata-section-headline">
                    <h5>trueRiver Keys</h5>
                    <MetadataFieldAdder
                      label="Add trueRiver field"
                      fields={manifestFields}
                      existingFields={mergedTriverRows.map((row) => row.field)}
                      onAddField={(field) => setPendingTriverFields((current) => [...current, field])}
                    />
                  </div>
                  <dl className="metadata-grid metadata-edit-grid">
                    {mergedTriverRows.map((row) => (
                      <MetadataEditableField
                        key={`selection:triver:${row.field}`}
                        row={row}
                        disabled={row.read_only || loading}
                        onApply={(nextValues) => handleApply(row, nextValues)}
                      />
                    ))}
                  </dl>
                </div>
              ) : null}
              {activeMetadataMode === 'standard' && sourceRows.length ? (
                <div className="metadata-edit-section">
                  <h5>Source Metadata</h5>
                  <dl className="metadata-grid metadata-edit-grid">
                    {sourceRows.map((row) => (
                      <MetadataEditableField
                        key={`selection:source:${row.field}`}
                        row={row}
                        disabled={row.read_only || loading}
                        onApply={(nextValues) => handleApply(row, nextValues)}
                      />
                    ))}
                  </dl>
                </div>
              ) : null}
            </section>
          </div>
        </div>
      </section>
    </div>,
    document.body,
  );
}
