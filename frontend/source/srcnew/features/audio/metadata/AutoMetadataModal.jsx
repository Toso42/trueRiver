import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { applyTrackAutoMetadata, previewTrackAutoMetadata } from '../../../api/metadata';

const AUTO_FIELDS = [
  { key: 'SeriesTitle', label: 'Series title', inputMode: 'text' },
  { key: 'SeasonNumber', label: 'Season', inputMode: 'numeric' },
  { key: 'EpisodeNumber', label: 'Episode', inputMode: 'numeric' },
  { key: 'EpisodeTitle', label: 'Episode title', inputMode: 'text' },
];

function normalizeValue(value) {
  return String(value ?? '').trim();
}

function buildDraft(item) {
  return AUTO_FIELDS.reduce((draft, field) => {
    draft[field.key] = normalizeValue(item?.suggested?.[field.key]) || normalizeValue(item?.existing?.[field.key]);
    return draft;
  }, {});
}

function buildApplyMetadata(row) {
  return AUTO_FIELDS.reduce((metadata, field) => {
    const value = normalizeValue(row.draft?.[field.key]);
    const existingValue = normalizeValue(row.existing?.[field.key]);
    if (value && value !== existingValue) {
      metadata[field.key] = value;
    } else if (value && !existingValue) {
      metadata[field.key] = value;
    }
    return metadata;
  }, {});
}

function existingSummary(row) {
  return AUTO_FIELDS
    .map((field) => {
      const value = normalizeValue(row.existing?.[field.key]);
      return value ? `${field.key}: ${value}` : '';
    })
    .filter(Boolean)
    .join(' · ');
}

export default function AutoMetadataModal({
  tracks = [],
  onClose = () => {},
  onApplied = () => {},
}) {
  const effectiveTracks = useMemo(() => {
    const deduped = new Map();
    (tracks || []).forEach((track) => {
      if (track?.id) {
        deduped.set(track.id, track);
      }
    });
    return Array.from(deduped.values());
  }, [tracks]);

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (!effectiveTracks.length) {
      setRows([]);
      return undefined;
    }

    setLoading(true);
    setSaving(false);
    setError('');
    setNotice('');
    previewTrackAutoMetadata(effectiveTracks.map((track) => track.id))
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setRows((payload.items || []).map((item) => ({
          ...item,
          selected: Boolean(item.has_suggestion),
          draft: buildDraft(item),
        })));
      })
      .catch((nextError) => {
        if (!cancelled) {
          setError(nextError.message || 'Auto metadata unavailable.');
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
  }, [effectiveTracks]);

  if (!effectiveTracks.length) {
    return null;
  }

  const selectedCount = rows.filter((row) => row.selected).length;
  const suggestedCount = rows.filter((row) => row.has_suggestion).length;

  function updateDraft(rowTrackId, fieldKey, value) {
    setRows((currentRows) => currentRows.map((row) => (
      row.track_id === rowTrackId
        ? { ...row, draft: { ...row.draft, [fieldKey]: value } }
        : row
    )));
  }

  function toggleRow(rowTrackId) {
    setRows((currentRows) => currentRows.map((row) => (
      row.track_id === rowTrackId ? { ...row, selected: !row.selected } : row
    )));
  }

  function selectSuggestedRows() {
    setRows((currentRows) => currentRows.map((row) => ({ ...row, selected: Boolean(row.has_suggestion) })));
  }

  async function handleApply() {
    const items = rows
      .filter((row) => row.selected)
      .map((row) => ({
        track_id: row.track_id,
        metadata: buildApplyMetadata(row),
      }))
      .filter((item) => Object.keys(item.metadata).length);

    if (!items.length) {
      setNotice('No new or changed metadata to apply.');
      return;
    }

    setSaving(true);
    setError('');
    setNotice('');
    try {
      const payload = await applyTrackAutoMetadata(items);
      const appliedIds = new Set(items.map((item) => item.track_id));
      setRows((currentRows) => currentRows.map((row) => (
        appliedIds.has(row.track_id)
          ? {
            ...row,
            selected: false,
            existing: { ...row.existing, ...buildApplyMetadata(row) },
            missing_fields: [],
            has_suggestion: false,
          }
          : row
      )));
      setNotice(`${payload.updated_count || 0} files updated.`);
      await onApplied?.(payload);
    } catch (nextError) {
      setError(nextError.message || 'Applying auto metadata failed.');
    } finally {
      setSaving(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <section className="track-meta-modal auto-metadata-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <div className="track-meta-head">
          <div>
            <p className="panel-kicker">Try Auto Metadata</p>
            <h3>{effectiveTracks.length === 1 ? '1 selected file' : `${effectiveTracks.length} selected files`}</h3>
          </div>
          <div className="track-meta-actions">
            <button type="button" className="metadata-inline-button is-muted" onClick={selectSuggestedRows} disabled={loading || saving}>
              Select suggested
            </button>
            <button type="button" className="modal-close" onClick={onClose} aria-label="Close auto metadata modal">x</button>
          </div>
        </div>

        <div className="auto-metadata-summary">
          <span>{suggestedCount} with suggestions</span>
          <span>{selectedCount} selected</span>
          {loading ? <span>loading</span> : null}
          {saving ? <span>saving</span> : null}
        </div>

        {error ? <p className="metadata-error">{error}</p> : null}
        {notice ? <p className="metadata-success">{notice}</p> : null}

        {!loading && !rows.length ? (
          <p className="empty-state">No files available for auto metadata.</p>
        ) : null}

        <div className="auto-metadata-list">
          {rows.map((row) => {
            const existing = existingSummary(row);
            return (
              <article key={row.track_id} className={`auto-metadata-row${row.selected ? ' is-selected' : ''}`}>
                <div className="auto-metadata-row-head">
                  <label className="auto-metadata-row-toggle">
                    <input
                      type="checkbox"
                      checked={row.selected}
                      onChange={() => toggleRow(row.track_id)}
                      disabled={saving}
                    />
                    <span>{row.track_title || row.filename || 'Untitled file'}</span>
                  </label>
                  <span className={`auto-metadata-confidence${row.has_suggestion ? ' is-ready' : ''}`}>
                    {row.has_suggestion ? `regex ${Math.round((row.confidence || 0) * 100)}%` : 'no suggestion'}
                  </span>
                </div>
                <p className="auto-metadata-path">{row.display_path || row.filename || 'n/a'}</p>
                <div className="auto-metadata-fields">
                  {AUTO_FIELDS.map((field) => (
                    <label key={`${row.track_id}:${field.key}`} className="auto-metadata-field">
                      <span>{field.label}</span>
                      <input
                        value={row.draft?.[field.key] || ''}
                        inputMode={field.inputMode}
                        onChange={(event) => updateDraft(row.track_id, field.key, event.target.value)}
                        disabled={saving}
                      />
                    </label>
                  ))}
                </div>
                {existing ? <p className="auto-metadata-existing">Existing: {existing}</p> : null}
                {row.missing_fields?.length ? (
                  <p className="auto-metadata-missing">Will fill: {row.missing_fields.join(', ')}</p>
                ) : null}
              </article>
            );
          })}
        </div>

        <div className="auto-metadata-footer">
          <button type="button" className="metadata-inline-button is-muted" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="button" className="metadata-inline-button auto-metadata-apply" onClick={handleApply} disabled={loading || saving || !rows.length}>
            Apply Approved
          </button>
        </div>
      </section>
    </div>,
    document.body,
  );
}
