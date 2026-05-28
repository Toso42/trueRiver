import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchMediaFile, fetchMetadataModel, patchMediaFileMetadata } from '../../../api/metadata';
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

function formatTimestamp(value) {
  if (!value) {
    return 'n/a';
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

export default function MediaFileMetadataEditorModal({
  mediaFileId = '',
  fileEntry = null,
  onClose = () => {},
}) {
  const [mediaFile, setMediaFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [manifestFields, setManifestFields] = useState([]);
  const [pendingTriverFields, setPendingTriverFields] = useState([]);
  const [activeMetadataMode, setActiveMetadataMode] = useState('standard');

  useEffect(() => {
    let cancelled = false;
    if (!mediaFileId) {
      return undefined;
    }
    setLoading(true);
    setError('');
    fetchMediaFile(mediaFileId)
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
  }, [mediaFileId]);

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
  }, [mediaFileId]);

  const source = mediaFile?.editable_metadata || {};
  const triverRows = source.triver || [];
  const sourceRows = source.source || source.raw || [];
  const mergedTriverRows = useMemo(() => ([
    ...triverRows,
    ...pendingTriverFields
      .filter((field) => !triverRows.some((row) => row.field === field.name))
      .map((field) => ({
        section: 'triver',
        field: field.name,
        display_field: field.display_name || field.name,
        values: [],
        read_only: false,
      })),
  ]), [pendingTriverFields, triverRows]);

  if (!mediaFileId) {
    return null;
  }

  const isVideo = String(mediaFile?.media_kind || fileEntry?.media_kind || '').toLowerCase() === 'video';
  const videoMetadataRows = buildSingleVideoMetadataRows(mergedTriverRows, null);
  const title = mediaFile?.filename || fileEntry?.name || 'Media file';
  const relevantMetadata = mediaFile?.relevant_metadata || [];
  const technicalEntries = [
    ['Format', mediaFile?.extension || fileEntry?.extension || 'n/a'],
    ['Type', mediaFile?.media_kind || fileEntry?.media_kind || 'n/a'],
    ['MIME', mediaFile?.mime_type || 'n/a'],
    ['Size', mediaFile?.size ? formatBytes(mediaFile.size) : fileEntry?.size ? formatBytes(fileEntry.size) : 'n/a'],
    ['Status', mediaFile?.status || 'n/a'],
    ['Workflow', mediaFile?.workflow_state || 'n/a'],
    ['Storage', mediaFile?.storage_stage || 'n/a'],
    ['Modified', formatTimestamp(mediaFile?.mtime || fileEntry?.modified_at)],
    ['Path', mediaFile?.display_path || fileEntry?.relative_path || 'n/a'],
    ['trive-Up path', mediaFile?.digest_relative_path || 'n/a'],
  ];

  async function handleApply(row, nextValues) {
    const payload = await patchMediaFileMetadata(mediaFileId, row.field, nextValues);
    setMediaFile(payload.media_file);
    setPendingTriverFields((current) => current.filter((field) => field.name !== row.field));
  }

  return createPortal(
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <section className="track-meta-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <div className="track-meta-head">
          <div>
            <p className="panel-kicker">File Metadata</p>
            <h3>{title}</h3>
          </div>
          <div className="track-meta-actions">
            <button type="button" className="modal-close" onClick={onClose} aria-label="Close metadata modal">×</button>
          </div>
        </div>
        <div className="track-meta-layout track-meta-layout-wide">
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

            {relevantMetadata.length ? (
              <section className="metadata-section">
                <h4>trueRiver Snapshot</h4>
                <dl className="metadata-grid">
                  {relevantMetadata.map((entry) => (
                    <div key={entry.field} className="metadata-row">
                      <dt>{entry.field}</dt>
                      <dd>{entry.display_value || entry.value || 'n/a'}</dd>
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
                        disabled={row.read_only || loading}
                        onApply={(nextValues) => handleApply(row, nextValues)}
                      />
                    ))}
                  </dl>
                </div>
              ) : (
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
                  {mergedTriverRows.length ? (
                    <dl className="metadata-grid metadata-edit-grid">
                      {mergedTriverRows.map((row) => (
                        <MetadataEditableField
                          key={`file:triver:${row.field}`}
                          row={row}
                          disabled={row.read_only || loading}
                          onApply={(nextValues) => handleApply(row, nextValues)}
                        />
                      ))}
                    </dl>
                  ) : (
                    <p className="empty-state">No trueRiver keys set yet.</p>
                  )}
                </div>
              )}
              {activeMetadataMode === 'standard' && sourceRows.length ? (
                <div className="metadata-edit-section">
                  <h5>Source Metadata</h5>
                  <dl className="metadata-grid metadata-edit-grid">
                    {sourceRows.map((row) => (
                      <MetadataEditableField
                        key={`file:source:${row.field}`}
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
