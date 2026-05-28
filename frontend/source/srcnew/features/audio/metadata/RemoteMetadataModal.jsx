import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { applyRemoteMetadataJob, fetchRemoteMetadataJob, startRemoteMetadataPreview } from '../../../api/metadata';

const TERMINAL_STATUSES = new Set(['done', 'error', 'canceled']);

function normalizeTracks(tracks) {
  const deduped = new Map();
  (tracks || []).forEach((track) => {
    if (track?.id) {
      deduped.set(track.id, track);
    }
  });
  return Array.from(deduped.values());
}

function statusText(status) {
  const labels = {
    remote_lookup_disabled: 'Remote lookup disabled in Settings',
    video_lookup_disabled: 'Video lookup disabled in Settings',
    audio_lookup_disabled: 'Audio lookup disabled in Settings',
    unsupported_media: 'Unsupported media type',
    provider_unconfigured: 'Provider API key missing',
    provider_prepared: 'Provider prepared, not implemented yet',
    provider_error: 'Provider error',
    no_query: 'Not enough data to search',
    no_match: 'No match found',
    ready: 'Ready',
  };
  return labels[status] || status || 'Waiting';
}

function candidateFields(candidate) {
  return Object.entries(candidate?.metadata || {})
    .filter(([field]) => field)
    .map(([field, value]) => ({ field, value }));
}

function valueText(value) {
  if (Array.isArray(value)) {
    return value.join(', ');
  }
  return String(value ?? '');
}

function bestCandidate(row) {
  return (row?.candidates || [])[0] || null;
}

export default function RemoteMetadataModal({
  tracks = [],
  mode = 'find',
  providerKey = '',
  overwritePolicy = '',
  onClose = () => {},
  onApplied = () => {},
}) {
  const effectiveTracks = useMemo(() => normalizeTracks(tracks), [tracks]);
  const [job, setJob] = useState(null);
  const [rows, setRows] = useState([]);
  const [selectedMatches, setSelectedMatches] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (!effectiveTracks.length) {
      return undefined;
    }

    setLoading(true);
    setError('');
    setNotice('');
    setRows([]);
    setSelectedMatches({});
    startRemoteMetadataPreview({
      trackIds: effectiveTracks.map((track) => track.id),
      mode,
      providerKey,
      overwritePolicy,
    })
      .then((createdJob) => {
        if (cancelled) {
          return;
        }
        setJob(createdJob);
      })
      .catch((nextError) => {
        if (!cancelled) {
          setError(nextError.message || 'Remote metadata lookup failed.');
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [effectiveTracks, mode, overwritePolicy, providerKey]);

  useEffect(() => {
    if (!job?.id || TERMINAL_STATUSES.has(job.status)) {
      return undefined;
    }
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const payload = await fetchRemoteMetadataJob(job.id);
        if (cancelled) {
          return;
        }
        setJob(payload);
        if (TERMINAL_STATUSES.has(payload.status)) {
          window.clearInterval(timer);
          const nextRows = payload.result_payload?.items || [];
          setRows(nextRows);
          setSelectedMatches(nextRows.reduce((matches, row) => {
            const candidate = bestCandidate(row);
            if (candidate?.match_id) {
              matches[row.track_id] = candidate.match_id;
            }
            return matches;
          }, {}));
          setLoading(false);
        }
      } catch (nextError) {
        if (!cancelled) {
          window.clearInterval(timer);
          setError(nextError.message || 'Unable to read remote metadata job.');
          setLoading(false);
        }
      }
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job]);

  if (!effectiveTracks.length) {
    return null;
  }

  const selectedItems = rows
    .map((row) => {
      const matchId = selectedMatches[row.track_id];
      const candidate = (row.candidates || []).find((item) => item.match_id === matchId);
      return candidate ? {
        track_id: row.track_id,
        match_id: candidate.match_id,
        metadata: candidate.metadata || {},
        overwrite_policy: overwritePolicy || job?.overwrite_policy || 'missing_only',
      } : null;
    })
    .filter(Boolean);

  async function handleApply() {
    if (!job?.id || !selectedItems.length) {
      setNotice('No remote matches selected.');
      return;
    }
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const payload = await applyRemoteMetadataJob(job.id, selectedItems);
      setNotice(`${payload.updated_count || 0} items updated.`);
      await onApplied?.(payload);
    } catch (nextError) {
      setError(nextError.message || 'Applying remote metadata failed.');
    } finally {
      setSaving(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <section className="track-meta-modal auto-metadata-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <div className="track-meta-head">
          <div>
            <p className="panel-kicker">Remote Metadata</p>
            <h3>{effectiveTracks.length === 1 ? '1 selected item' : `${effectiveTracks.length} selected items`}</h3>
          </div>
          <div className="track-meta-actions">
            <button type="button" className="modal-close" onClick={onClose} aria-label="Close remote metadata modal">x</button>
          </div>
        </div>

        <div className="auto-metadata-summary">
          <span>{job?.status || 'starting'}</span>
          <span>{job?.candidate_count || selectedItems.length || 0} matches</span>
          {loading ? <span>searching</span> : null}
          {saving ? <span>saving</span> : null}
        </div>

        {error ? <p className="metadata-error">{error}</p> : null}
        {notice ? <p className="metadata-success">{notice}</p> : null}
        {job?.last_error ? <p className="metadata-error">{job.last_error}</p> : null}
        {loading ? <p className="empty-state">Searching configured metadata providers...</p> : null}

        {!loading && !rows.length ? (
          <p className="empty-state">No remote metadata results available.</p>
        ) : null}

        <div className="auto-metadata-list">
          {rows.map((row) => {
            const selectedMatch = selectedMatches[row.track_id] || '';
            return (
              <article key={row.track_id} className={`auto-metadata-row${selectedMatch ? ' is-selected' : ''}`}>
                <div className="auto-metadata-row-head">
                  <label className="auto-metadata-row-toggle">
                    <input
                      type="checkbox"
                      checked={Boolean(selectedMatch)}
                      onChange={() => {
                        setSelectedMatches((current) => {
                          if (current[row.track_id]) {
                            const next = { ...current };
                            delete next[row.track_id];
                            return next;
                          }
                          const candidate = bestCandidate(row);
                          return candidate?.match_id ? { ...current, [row.track_id]: candidate.match_id } : current;
                        });
                      }}
                      disabled={saving || !(row.candidates || []).length}
                    />
                    <span>{row.track_title || row.filename || 'Untitled item'}</span>
                  </label>
                  <span className={`auto-metadata-confidence${(row.candidates || []).length ? ' is-ready' : ''}`}>
                    {statusText(row.status)}
                  </span>
                </div>
                <p className="auto-metadata-path">{row.display_path || row.filename || 'n/a'}</p>
                {(row.candidates || []).length ? (
                  <div className="remote-metadata-candidates">
                    {(row.candidates || []).map((candidate) => (
                      <label key={candidate.match_id} className="remote-metadata-candidate">
                        <input
                          type="radio"
                          name={`remote-match-${row.track_id}`}
                          checked={selectedMatch === candidate.match_id}
                          onChange={() => setSelectedMatches((current) => ({ ...current, [row.track_id]: candidate.match_id }))}
                          disabled={saving}
                        />
                        <span>
                          <strong>{candidate.label}</strong>
                          <small>{candidate.provider_label || candidate.provider} · {Math.round((candidate.confidence || 0) * 100)}%{candidate.subtitle ? ` · ${candidate.subtitle}` : ''}</small>
                        </span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <p className="auto-metadata-missing">{row.detail || statusText(row.status)}</p>
                )}
                {selectedMatch ? (
                  <div className="auto-metadata-fields">
                    {candidateFields((row.candidates || []).find((candidate) => candidate.match_id === selectedMatch)).map(({ field, value }) => (
                      <label key={`${row.track_id}:${selectedMatch}:${field}`} className="auto-metadata-field">
                        <span>{field}</span>
                        <input value={valueText(value)} readOnly />
                      </label>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>

        <div className="auto-metadata-footer">
          <button type="button" className="metadata-inline-button is-muted" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="button" className="metadata-inline-button auto-metadata-apply" onClick={handleApply} disabled={loading || saving || !selectedItems.length}>
            Apply Selected
          </button>
        </div>
      </section>
    </div>,
    document.body,
  );
}
