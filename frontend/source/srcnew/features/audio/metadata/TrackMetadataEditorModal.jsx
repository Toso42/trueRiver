import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import CoverThumb from '../../../shared/ui/CoverThumb';
import { fetchMediaFile, fetchMetadataModel, patchMediaFileMetadata } from '../../../api/metadata';
import { isVideoItem } from '../../media/mediaItem';
import MetadataEditableField from './MetadataEditableField';
import MetadataFieldAdder from './MetadataFieldAdder';
import { buildSingleVideoMetadataRows } from './videoMetadataFields';

function formatBytes(value) {
  const size = Number(value) || 0;
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 ** 2) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  if (size < 1024 ** 3) {
    return `${(size / (1024 ** 2)).toFixed(1)} MB`;
  }
  return `${(size / (1024 ** 3)).toFixed(1)} GB`;
}

export default function TrackMetadataEditorModal({ track = null, onClose = () => {} }) {
  const [mediaFile, setMediaFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [manifestFields, setManifestFields] = useState([]);
  const [pendingTriverFields, setPendingTriverFields] = useState([]);
  const [activeMetadataMode, setActiveMetadataMode] = useState('standard');

  useEffect(() => {
    let cancelled = false;
    if (!track?.primary_file) {
      return undefined;
    }
    setLoading(true);
    setError('');
    setMediaFile(null);
    fetchMediaFile(track.primary_file)
      .then((payload) => {
        if (!cancelled) {
          setMediaFile(payload);
        }
      })
      .catch((nextError) => {
        if (!cancelled) {
          setError(nextError.message || 'Metadata unavailable');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [track?.id, track?.primary_file]);

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
  }, [track?.id]);

  const editableSections = useMemo(() => {
    const source = mediaFile?.editable_metadata || {};
    const triverRows = (source.triver || []).length ? source.triver : [
      track?.canonical_title || track?.title ? {
        section: 'triver',
        field: 'TrackName',
        display_field: 'TrackName',
        values: [{ value: track.canonical_title || track.title }],
        read_only: false,
      } : null,
      track?.artist_summary?.length ? {
        section: 'triver',
        field: 'Artist',
        display_field: 'Artist',
        values: [{ value: track.artist_summary.map((artist) => artist.name).join(', ') }],
        read_only: false,
      } : null,
      track?.album_title ? {
        section: 'triver',
        field: 'Album',
        display_field: 'Album',
        values: [{ value: track.album_title }],
        read_only: false,
      } : null,
      track?.track_number ? {
        section: 'triver',
        field: 'TrackNumber',
        display_field: 'TrackNumber',
        values: [{ value: String(track.track_number) }],
        read_only: false,
      } : null,
      track?.disc_number ? {
        section: 'triver',
        field: 'DiscNumber',
        display_field: 'DiscNumber',
        values: [{ value: String(track.disc_number) }],
        read_only: false,
      } : null,
      track?.release_year ? {
        section: 'triver',
        field: 'ReleaseDate',
        display_field: 'ReleaseDate',
        values: [{ value: String(track.release_year) }],
        read_only: false,
      } : null,
    ].filter(Boolean);
    return [
      ['triver', 'trueRiver Keys', triverRows],
      ['source', 'Source Metadata', source.source || source.raw || []],
    ].filter(([, , rows]) => rows.length);
  }, [mediaFile, track]);

  const relevantMetadata = useMemo(() => mediaFile?.relevant_metadata || [], [mediaFile]);
  const canonicalProjection = useMemo(() => {
    const rows = [];
    if (track?.canonical_title || track?.title) {
      rows.push(['TrackName', track.canonical_title || track.title]);
    }
    if (track?.artist_summary?.length) {
      rows.push(['Artist', track.artist_summary.map((artist) => artist.name).join(', ')]);
    }
    if (track?.album_title) {
      rows.push(['Album', track.album_title]);
    }
    if (track?.track_number) {
      rows.push(['TrackNumber', String(track.track_number)]);
    }
    if (track?.disc_number) {
      rows.push(['DiscNumber', String(track.disc_number)]);
    }
    if (track?.release_year) {
      rows.push(['ReleaseDate', String(track.release_year)]);
    }
    return rows;
  }, [track]);

  if (!track) {
    return null;
  }

  const technicalEntries = [
    ['Format', track.audio_format || mediaFile?.extension || 'n/a'],
    ['Bitrate', track.bitrate_kbps ? `${track.bitrate_kbps} kbps` : 'n/a'],
    ['MIME', mediaFile?.mime_type || 'n/a'],
    ['Size', mediaFile?.size ? formatBytes(mediaFile.size) : 'n/a'],
    ['Duration', track.duration_seconds ? `${Math.round(track.duration_seconds)}s` : 'n/a'],
    ['Status', mediaFile?.status || 'n/a'],
    ['Workflow', mediaFile?.workflow_state || 'n/a'],
    ['Path', mediaFile?.display_path || 'n/a'],
  ];

  const editableProjectionRows = editableSections.find(([sectionKey]) => sectionKey === 'triver')?.[2]
    || canonicalProjection.map(([field, value]) => ({
      section: 'triver',
      field,
      display_field: field,
      values: [{ value }],
      read_only: false,
    }));
  const mergedProjectionRows = [
    ...editableProjectionRows,
    ...pendingTriverFields
      .filter((field) => !editableProjectionRows.some((row) => row.field === field.name))
      .map((field) => ({
        section: 'triver',
        field: field.name,
        display_field: field.display_name || field.name,
        values: [],
        read_only: false,
      })),
  ];
  const isVideo = isVideoItem(track);
  const videoMetadataRows = buildSingleVideoMetadataRows(mergedProjectionRows, track);

  async function handleApply(row, nextValues) {
    const payload = await patchMediaFileMetadata(track.primary_file, row.field, nextValues);
    setMediaFile(payload.media_file);
    setPendingTriverFields((current) => current.filter((field) => field.name !== row.field));
  }

  return createPortal(
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <section className="track-meta-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <div className="track-meta-head">
          <div>
            <p className="panel-kicker">Track Metadata</p>
            <h3>{track.canonical_title || track.title}</h3>
          </div>
          <div className="track-meta-actions">
            <button type="button" className="modal-close" onClick={onClose} aria-label="Close metadata modal">×</button>
          </div>
        </div>
        <div className="track-meta-layout">
          <CoverThumb coverUrl={track.cover_url} alt="" kind="album" />
          <div className="metadata-stack">
            <section className="metadata-section">
              <h4>File</h4>
              <dl className="metadata-grid">
                {technicalEntries.map(([label, value]) => (
                  <div key={label} className="metadata-row">
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </section>
            {relevantMetadata.length || canonicalProjection.length ? (
              <section className="metadata-section">
                <h4>trueRiver Snapshot</h4>
                <dl className="metadata-grid">
                  {relevantMetadata.length ? relevantMetadata.map((entry) => (
                    <div key={entry.field} className="metadata-row">
                      <dt>{entry.field}</dt>
                      <dd>{entry.display_value || entry.value || 'n/a'}</dd>
                    </div>
                  )) : canonicalProjection.map(([field, value]) => (
                    <div key={field} className="metadata-row">
                      <dt>{field}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ) : null}
            <section className="metadata-section">
              <div className="metadata-section-headline">
                <h4>Editable Metadata</h4>
                {loading ? <span>loading</span> : null}
              </div>
              {isVideo ? (
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
              {isVideo && activeMetadataMode === 'video' ? (
                <div className="metadata-edit-section">
                  <dl className="metadata-grid metadata-edit-grid">
                    {videoMetadataRows.map((row) => (
                      <MetadataEditableField
                        key={`video:${row.field}`}
                        row={row}
                        disabled={row.read_only || !track.primary_file || loading}
                        onApply={(nextValues) => handleApply(row, nextValues)}
                      />
                    ))}
                  </dl>
                </div>
              ) : mergedProjectionRows.length ? (
                <div className="metadata-edit-section">
                  <div className="metadata-section-headline">
                    <h5>trueRiver Keys</h5>
                    <MetadataFieldAdder
                      label="Add trueRiver field"
                      fields={manifestFields}
                      existingFields={mergedProjectionRows.map((row) => row.field)}
                      onAddField={(field) => setPendingTriverFields((current) => [...current, field])}
                    />
                  </div>
                  <dl className="metadata-grid metadata-edit-grid">
                    {mergedProjectionRows.map((row) => (
                      <MetadataEditableField
                        key={`projection:${row.field}`}
                        row={row}
                        disabled={row.read_only || !track.primary_file || loading}
                        onApply={(nextValues) => handleApply(row, nextValues)}
                      />
                    ))}
                  </dl>
                </div>
              ) : null}
              {activeMetadataMode === 'standard' && editableSections.filter(([sectionKey]) => sectionKey !== 'triver').length ? editableSections
                .filter(([sectionKey]) => sectionKey !== 'triver')
                .map(([sectionKey, sectionTitle, rows]) => (
                <div key={sectionKey} className="metadata-edit-section">
                  <h5>{sectionTitle}</h5>
                  <dl className="metadata-grid metadata-edit-grid">
                    {rows.map((row) => (
                      <MetadataEditableField
                        key={`${row.section}:${row.field}`}
                        row={row}
                        disabled={row.read_only || !track.primary_file || loading}
                        onApply={(nextValues) => handleApply(row, nextValues)}
                      />
                    ))}
                  </dl>
                </div>
              )) : !mergedProjectionRows.length ? (
                <p className="empty-state">No metadata available for this media file.</p>
              ) : null}
            </section>
          </div>
        </div>
      </section>
    </div>,
    document.body,
  );
}
