import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AudioContentScaffold from '../AudioContentScaffold';
import {
  fetchAutoImportSettings,
  fetchClassicImportSources,
  fetchIoAccessoryFiles,
  fetchDigestErrors,
  fetchIoMediaFiles,
  fetchIoSourceFolders,
  fetchLatestDigestJob,
  fetchLatestScanJob,
  fetchScanSkips,
  cancelDigestJob,
  runAutoImportCheckNow,
  startRescanJob,
  startClassicImport,
  startDigestJob,
  startScanJob,
  updateAutoImportSettings,
} from '../../../../api/io';

function formatDateTime(value) {
  if (!value) {
    return 'n/a';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString();
}

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

const SCAN_ACTIVE_STATUSES = new Set(['pending', 'discovering', 'processing']);
const DIGEST_ACTIVE_STATUSES = new Set(['pending', 'running']);

function normalizeJobStatus(job) {
  return String(job?.status || '').toLowerCase();
}

function isScanJobActive(job) {
  return SCAN_ACTIVE_STATUSES.has(normalizeJobStatus(job));
}

function isDigestJobActive(job) {
  return DIGEST_ACTIVE_STATUSES.has(normalizeJobStatus(job));
}

function StatusCard({ title, rows = [], action = null }) {
  return (
    <section className="trive-io-card">
      <div className="trive-io-card-head">
        <h3>{title}</h3>
        {action}
      </div>
      <dl className="trive-io-stats">
        {rows.map(([label, value]) => (
          <div key={label} className="trive-io-stat">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function FileList({ title, items = [], totalCount = null, renderMeta, loading = false }) {
  return (
    <section className="trive-io-card">
      <div className="trive-io-card-head">
        <h3>{title}</h3>
        <span>{loading ? 'Loading…' : totalCount == null ? items.length : `${items.length} / ${totalCount}`}</span>
      </div>
      {!items.length ? (
        <p className="empty-state">No items available.</p>
      ) : (
        <ul className="trive-io-file-list">
          {items.map((item) => (
            <li key={item.id} className="trive-io-file-row">
              <span className="trive-io-file-path">{item.display_path || item.relative_path || item.name || item.filename}</span>
              <span className="trive-io-file-meta">{renderMeta(item)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ClassicImportSources({
  sources = [],
  selectedKeys = [],
  onToggle,
  onSelectAll,
  onSelectNone,
  onStart,
  disabled = false,
  submitting = false,
}) {
  const selectableSources = sources.filter((source) => source.exists && source.is_dir && source.readable);
  return (
    <section className="trive-io-card trive-io-card-wide">
      <div className="trive-io-card-head">
        <h3>Classic Import Folders</h3>
        <div className="trive-io-actions">
          <button type="button" className="metadata-inline-button" onClick={onSelectAll} disabled={disabled || !selectableSources.length}>
            All folders
          </button>
          <button type="button" className="metadata-inline-button" onClick={onSelectNone} disabled={disabled || !selectedKeys.length}>
            No folders
          </button>
          <button type="button" className="metadata-inline-button" onClick={onStart} disabled={disabled || submitting || !selectedKeys.length}>
            {submitting ? 'Starting…' : 'Start Classic Indexing'}
          </button>
        </div>
      </div>
      {!sources.length ? (
        <p className="empty-state">No classic import folders configured. Run the Classic Import configuration script on the server first.</p>
      ) : (
        <ul className="trive-io-source-list">
          {sources.map((source) => {
            const available = source.exists && source.is_dir && source.readable;
            const checked = selectedKeys.includes(source.key);
            return (
              <li key={source.key} className={available ? 'trive-io-source-row' : 'trive-io-source-row is-unavailable'}>
                <label>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={disabled || !available}
                    onChange={() => onToggle(source.key)}
                  />
                  <span>
                    <strong>{source.label || source.key}</strong>
                    <small>{source.container_path || source.relative_prefix}</small>
                  </span>
                </label>
                <em>{available ? 'Ready' : 'Unavailable'}</em>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function AutoImportPanel({
  settings = null,
  disabled = false,
  savingKey = '',
  checking = false,
  onToggle = () => {},
  onCheckNow = () => {},
}) {
  const lastResult = settings?.last_result || {};
  const resultLabel = lastResult.action || 'n/a';
  const triggeredAt = formatDateTime(settings?.last_triggered_at);
  const checkedAt = formatDateTime(settings?.last_checked_at);
  const toggles = [
    ['enabled', 'AutoImport daemon'],
    ['trive_scan_enabled', 'TriveImport autoscan'],
    ['trive_up_enabled', 'TriveImport auto Trive-Up'],
    ['classic_scan_enabled', 'Classic autoscan'],
    ['classic_up_enabled', 'Classic auto catalog'],
  ];

  return (
    <section className="trive-io-card trive-io-card-wide">
      <div className="trive-io-card-head">
        <h3>AutoImport</h3>
        <div className="trive-io-actions">
          <button type="button" className="metadata-inline-button" onClick={onCheckNow} disabled={disabled || checking}>
            {checking ? 'Checking…' : 'Check now'}
          </button>
        </div>
      </div>
      <div className="trive-io-toggle-grid">
        {toggles.map(([key, label]) => (
          <label key={key} className="settings-toggle-row">
            <span>{label}</span>
            <input
              type="checkbox"
              checked={Boolean(settings?.[key])}
              disabled={disabled || savingKey === key}
              onChange={() => onToggle(key)}
            />
          </label>
        ))}
      </div>
      <dl className="trive-io-stats">
        <div className="trive-io-stat">
          <dt>Last check</dt>
          <dd>{checkedAt}</dd>
        </div>
        <div className="trive-io-stat">
          <dt>Last trigger</dt>
          <dd>{triggeredAt}</dd>
        </div>
        <div className="trive-io-stat">
          <dt>Status</dt>
          <dd>{settings?.last_error || resultLabel}</dd>
        </div>
        <div className="trive-io-stat">
          <dt>Latest item</dt>
          <dd>{settings?.last_trive_signature?.latest_path || 'n/a'}</dd>
        </div>
      </dl>
    </section>
  );
}

export default function TriveIoView({ searchTerm = '' }) {
  const [loading, setLoading] = useState(true);
  const reloadInFlightRef = useRef(false);
  const jobsReloadInFlightRef = useRef(false);
  const jobWasActiveRef = useRef(false);
  const [importMode, setImportMode] = useState('trive');
  const [submittingScan, setSubmittingScan] = useState(false);
  const [submittingRescan, setSubmittingRescan] = useState(false);
  const [submittingUp, setSubmittingUp] = useState(false);
  const [submittingClassic, setSubmittingClassic] = useState(false);
  const [checkingAutoImport, setCheckingAutoImport] = useState(false);
  const [savingAutoImportKey, setSavingAutoImportKey] = useState('');
  const [cancelingUp, setCancelingUp] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [autoImportError, setAutoImportError] = useState('');
  const [scanJob, setScanJob] = useState(null);
  const [digestJob, setDigestJob] = useState(null);
  const [mediaFiles, setMediaFiles] = useState([]);
  const [accessoryFiles, setAccessoryFiles] = useState([]);
  const [sourceFolders, setSourceFolders] = useState([]);
  const [autoImportSettings, setAutoImportSettings] = useState(null);
  const [classicSources, setClassicSources] = useState([]);
  const [selectedClassicSourceKeys, setSelectedClassicSourceKeys] = useState([]);
  const [scanSkips, setScanSkips] = useState([]);
  const [digestErrors, setDigestErrors] = useState([]);

  const reloadJobs = useCallback(async (options = {}) => {
    const { background = false } = options;
    if (jobsReloadInFlightRef.current) {
      return null;
    }
    jobsReloadInFlightRef.current = true;
    if (!background) {
      setLoading(true);
    }
    try {
      const [latestScan, latestDigest] = await Promise.all([
        fetchLatestScanJob(),
        fetchLatestDigestJob(),
      ]);
      setScanJob(latestScan);
      setDigestJob(latestDigest);
      return { latestScan, latestDigest };
    } catch (nextError) {
      setError(nextError.message || 'Unable to load trive-IO job status');
      return null;
    } finally {
      jobsReloadInFlightRef.current = false;
      if (!background) {
        setLoading(false);
      }
    }
  }, []);

  const reload = useCallback(async (options = {}) => {
    const { background = false } = options;
    if (reloadInFlightRef.current) {
      return;
    }
    reloadInFlightRef.current = true;
    if (!background) {
      setLoading(true);
    }
    setError('');
    try {
      const [latestScan, latestDigest, classicPayload] = await Promise.all([
        fetchLatestScanJob(),
        fetchLatestDigestJob(),
        fetchClassicImportSources(),
      ]);
      setScanJob(latestScan);
      setDigestJob(latestDigest);
      const nextClassicSources = classicPayload?.sources || [];
      setClassicSources(nextClassicSources);
      setSelectedClassicSourceKeys((previous) => {
        const selectable = nextClassicSources
          .filter((source) => source.exists && source.is_dir && source.readable)
          .map((source) => source.key);
        const kept = previous.filter((key) => selectable.includes(key));
        return kept.length ? kept : selectable;
      });
      const libraryId = latestScan?.library || latestDigest?.library || null;
      const [nextMediaFiles, nextAccessoryFiles, nextSourceFolders, nextScanSkips, nextDigestErrors] = await Promise.all([
        fetchIoMediaFiles(libraryId),
        fetchIoAccessoryFiles(libraryId),
        fetchIoSourceFolders(libraryId),
        fetchScanSkips(latestScan?.id),
        fetchDigestErrors(latestDigest?.id),
      ]);
      setMediaFiles(nextMediaFiles);
      setAccessoryFiles(nextAccessoryFiles);
      setSourceFolders(nextSourceFolders);
      setScanSkips(nextScanSkips);
      setDigestErrors(nextDigestErrors);
      try {
        setAutoImportSettings(await fetchAutoImportSettings());
        setAutoImportError('');
      } catch (nextAutoImportError) {
        setAutoImportSettings(null);
        setAutoImportError(nextAutoImportError.message || 'Unable to read auto import settings');
      }
    } catch (nextError) {
      setError(nextError.message || 'Unable to load trive-IO data');
    } finally {
      reloadInFlightRef.current = false;
      if (!background) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const scanActive = isScanJobActive(scanJob);
  const digestActive = isDigestJobActive(digestJob);
  const classicMode = importMode === 'classic';
  const autoMode = importMode === 'auto';
  const classicSelectableKeys = useMemo(() => (
    classicSources
      .filter((source) => source.exists && source.is_dir && source.readable)
      .map((source) => source.key)
  ), [classicSources]);

  const handleAutoImportToggle = useCallback(async (key) => {
    if (!autoImportSettings) {
      return;
    }
    setSavingAutoImportKey(key);
    setError('');
    setAutoImportError('');
    setMessage('');
    try {
      const payload = await updateAutoImportSettings({ [key]: !autoImportSettings[key] });
      setAutoImportSettings(payload);
    } catch (nextError) {
      setAutoImportError(nextError.message || 'Unable to update auto import settings');
    } finally {
      setSavingAutoImportKey('');
    }
  }, [autoImportSettings]);

  const handleAutoImportCheckNow = useCallback(async () => {
    setCheckingAutoImport(true);
    setError('');
    setAutoImportError('');
    setMessage('');
    try {
      const payload = await runAutoImportCheckNow();
      setAutoImportSettings(payload);
      setMessage('AutoImport check started.');
      window.setTimeout(() => {
        reload({ background: true });
      }, 650);
    } catch (nextError) {
      setAutoImportError(nextError.message || 'Unable to start auto import check');
    } finally {
      setCheckingAutoImport(false);
    }
  }, [reload]);

  useEffect(() => {
    if (!scanActive && !digestActive) {
      if (jobWasActiveRef.current) {
        jobWasActiveRef.current = false;
        reload({ background: true });
      }
      return undefined;
    }
    jobWasActiveRef.current = true;
    const timer = window.setInterval(() => {
      reloadJobs({ background: true });
    }, 650);
    return () => window.clearInterval(timer);
  }, [digestActive, reload, reloadJobs, scanActive]);

  const scanRows = useMemo(() => ([
    ['Status', scanJob?.status || 'n/a'],
    ['Library', scanJob?.library || 'n/a'],
    ['Total Seen', String((scanJob?.discovered_count ?? 0) + (scanJob?.skipped_count ?? 0) + (scanJob?.error_count ?? 0))],
    ['Discovered', String(scanJob?.discovered_count ?? 0)],
    ['Processed', String(scanJob?.processed_count ?? 0)],
    ['Skipped', String(scanJob?.skipped_count ?? 0)],
    ['Errors', String(scanJob?.error_count ?? 0)],
    ['Started', formatDateTime(scanJob?.started_at)],
    ['Finished', formatDateTime(scanJob?.finished_at)],
  ]), [scanJob]);

  const digestRows = useMemo(() => ([
    ['Status', digestJob?.status || 'n/a'],
    ['Library', digestJob?.library || 'n/a'],
    ['Total', String(digestJob?.target_count ?? 0)],
    ['Processed', String(digestJob?.processed_count ?? 0)],
    ['Created', String(digestJob?.created_track_count ?? 0)],
    ['Reused', String(digestJob?.reused_track_count ?? 0)],
    ['Errors', String(digestJob?.error_count ?? 0)],
    ['Started', formatDateTime(digestJob?.started_at)],
    ['Finished', formatDateTime(digestJob?.finished_at)],
  ]), [digestJob]);

  const normalizedFilterTerm = String(searchTerm || '').trim().toLowerCase();

  const filteredMediaFiles = useMemo(() => {
    if (!normalizedFilterTerm) {
      return mediaFiles;
    }
    return mediaFiles.filter((item) => {
      const haystack = [
        item.display_path,
        item.relative_path,
        item.filename,
        item.extension,
        item.media_kind,
        item.mime_type,
      ].filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(normalizedFilterTerm);
    });
  }, [mediaFiles, normalizedFilterTerm]);

  const filteredAccessoryFiles = useMemo(() => {
    if (!normalizedFilterTerm) {
      return accessoryFiles;
    }
    return accessoryFiles.filter((item) => {
      const haystack = [
        item.display_path,
        item.relative_path,
        item.filename,
        item.extension,
        item.asset_kind,
      ].filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(normalizedFilterTerm);
    });
  }, [accessoryFiles, normalizedFilterTerm]);

  const filteredSourceFolders = useMemo(() => {
    if (!normalizedFilterTerm) {
      return sourceFolders;
    }
    return sourceFolders.filter((item) => {
      const haystack = [
        item.display_path,
        item.relative_path,
        item.name,
      ].filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(normalizedFilterTerm);
    });
  }, [sourceFolders, normalizedFilterTerm]);

  const filteredScanSkips = useMemo(() => {
    if (!normalizedFilterTerm) {
      return scanSkips;
    }
    return scanSkips.filter((item) => {
      const haystack = [
        item.display_path,
        item.relative_path,
        item.filename,
        item.extension,
        item.reason_code,
        item.reason_detail,
      ].filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(normalizedFilterTerm);
    });
  }, [scanSkips, normalizedFilterTerm]);

  const filteredDigestErrors = useMemo(() => {
    if (!normalizedFilterTerm) {
      return digestErrors;
    }
    return digestErrors.filter((item) => {
      const haystack = [
        item.display_path,
        item.relative_path,
        item.filename,
        item.error_type,
        item.message,
      ].filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(normalizedFilterTerm);
    });
  }, [digestErrors, normalizedFilterTerm]);

  return (
    <AudioContentScaffold
      title="Trive-IO"
      description="Operational view for TriveImport and Classic Import jobs, media files, and source folders."
    >
      <div className="trive-io-mode-switch" role="group" aria-label="Import mode">
        <button
          type="button"
          className={importMode === 'trive' ? 'is-active' : ''}
          onClick={() => setImportMode('trive')}
        >
          TriveImport
        </button>
        <button
          type="button"
          className={classicMode ? 'is-active' : ''}
          onClick={() => setImportMode('classic')}
        >
          Classic Import
        </button>
        <button
          type="button"
          className={autoMode ? 'is-active' : ''}
          onClick={() => setImportMode('auto')}
        >
          AutoImport
        </button>
      </div>
      {message ? <p className="trive-io-message">{message}</p> : null}
      {error ? <p className="metadata-error">{error}</p> : null}
      <div className="trive-io-grid">
          {autoMode ? (
            <>
              {autoImportError ? <p className="metadata-error trive-io-card-wide">{autoImportError}</p> : null}
              <AutoImportPanel
                settings={autoImportSettings}
                disabled={scanActive || digestActive || !autoImportSettings}
                savingKey={savingAutoImportKey}
                checking={checkingAutoImport}
                onToggle={handleAutoImportToggle}
                onCheckNow={handleAutoImportCheckNow}
              />
            </>
          ) : null}
          {classicMode ? (
            <ClassicImportSources
              sources={classicSources}
              selectedKeys={selectedClassicSourceKeys}
              disabled={scanActive || digestActive}
              submitting={submittingClassic}
              onToggle={(key) => {
                setSelectedClassicSourceKeys((previous) => (
                  previous.includes(key)
                    ? previous.filter((item) => item !== key)
                    : [...previous, key]
                ));
              }}
              onSelectAll={() => setSelectedClassicSourceKeys(classicSelectableKeys)}
              onSelectNone={() => setSelectedClassicSourceKeys([])}
              onStart={async () => {
                setSubmittingClassic(true);
                setError('');
                setMessage('');
                try {
                  const payload = await startClassicImport(selectedClassicSourceKeys);
                  setScanJob(payload.scan_job);
                  setDigestJob(payload.digest_job);
                  setMessage(`Classic import started: scan #${payload.scan_job?.id}, catalog #${payload.digest_job?.id}`);
                  window.setTimeout(() => {
                    reloadJobs({ background: true });
                  }, 80);
                } catch (nextError) {
                  setError(nextError.message || 'Failed to start classic import');
                } finally {
                  setSubmittingClassic(false);
                }
              }}
            />
          ) : null}
        {!autoMode ? (
          <>
          <StatusCard
            title="Latest Scan"
            rows={scanRows}
            action={classicMode ? null : (
              <div className="trive-io-actions">
                <button
                  type="button"
                  className="metadata-inline-button"
                  disabled={submittingScan || scanActive}
                  onClick={async () => {
                    setSubmittingScan(true);
                    setError('');
                    setMessage('');
                    try {
                      const payload = await startScanJob('');
                      setScanJob(payload);
                      setMessage(`Scan started: job #${payload.id}`);
                      window.setTimeout(() => {
                        reloadJobs({ background: true });
                      }, 80);
                    } catch (nextError) {
                      setError(nextError.message || 'Failed to start scan');
                    } finally {
                      setSubmittingScan(false);
                    }
                  }}
                >
                  {submittingScan ? 'Starting…' : 'Start Scan'}
                </button>
                <button
                  type="button"
                  className="metadata-inline-button"
                  disabled={submittingRescan || scanActive}
                  onClick={async () => {
                    setSubmittingRescan(true);
                    setError('');
                    setMessage('');
                    try {
                      const payload = await startRescanJob();
                      setScanJob(payload);
                      setMessage(`Library rescan started: job #${payload.id}`);
                      window.setTimeout(() => {
                        reloadJobs({ background: true });
                      }, 80);
                    } catch (nextError) {
                      setError(nextError.message || 'Failed to start library rescan');
                    } finally {
                      setSubmittingRescan(false);
                    }
                  }}
                >
                  {submittingRescan ? 'Starting…' : 'Rescan Library'}
                </button>
              </div>
            )}
          />
          <StatusCard
            title={classicMode ? 'Latest Catalog Indexing' : 'Latest Trive-Up'}
            rows={digestRows}
            action={classicMode ? null : (
              <div className="trive-io-actions">
                <button
                  type="button"
                  className="metadata-inline-button"
                  disabled={submittingUp || digestActive}
                  onClick={async () => {
                    setSubmittingUp(true);
                    setError('');
                    setMessage('');
                    try {
                      const payload = await startDigestJob();
                      setDigestJob(payload);
                      setMessage(`Trive-up started: job #${payload.id}`);
                      window.setTimeout(() => {
                        reloadJobs({ background: true });
                      }, 80);
                    } catch (nextError) {
                      setError(nextError.message || 'Failed to start trive-up');
                    } finally {
                      setSubmittingUp(false);
                    }
                  }}
                >
                  {submittingUp ? 'Starting…' : 'Start Trive-Up'}
                </button>
                {digestActive ? (
                  <button
                    type="button"
                    className="metadata-inline-button"
                    disabled={cancelingUp}
                    onClick={async () => {
                      setCancelingUp(true);
                      setError('');
                      setMessage('');
                      try {
                        const payload = await cancelDigestJob(digestJob?.id);
                        setDigestJob(payload);
                        setMessage(`Trive-up canceled: job #${payload.id}`);
                        window.setTimeout(() => {
                          reload({ background: true });
                        }, 80);
                      } catch (nextError) {
                        setError(nextError.message || 'Failed to cancel trive-up');
                      } finally {
                        setCancelingUp(false);
                      }
                    }}
                  >
                    {cancelingUp ? 'Canceling…' : 'Cancel'}
                  </button>
                ) : null}
              </div>
            )}
          />
          <FileList
            title="Media Files"
            items={filteredMediaFiles}
            totalCount={mediaFiles.length}
            loading={loading}
            renderMeta={(file) => [
              file.media_kind || 'unknown',
              file.extension || 'n/a',
              formatBytes(file.size),
              file.storage_stage || 'n/a',
              file.workflow_state || 'n/a',
              file.status || 'n/a',
              file.mime_type || '',
              file.last_error ? `error=${file.last_error}` : '',
            ].filter(Boolean).join(' · ')}
          />
          <FileList
            title="Source Folders"
            items={filteredSourceFolders}
            totalCount={sourceFolders.length}
            loading={loading}
            renderMeta={(folder) => `${folder.audio_file_count ?? 0} audio · ${folder.accessory_file_count ?? 0} accessories · ${folder.file_count ?? 0} files`}
          />
          <FileList
            title="Accessory Files"
            items={filteredAccessoryFiles}
            totalCount={accessoryFiles.length}
            loading={loading}
            renderMeta={(file) => [
              file.asset_kind || 'unknown',
              file.extension || '',
              formatBytes(file.size),
            ].filter(Boolean).join(' · ')}
          />
          <FileList
            title="Skipped / Noise"
            items={filteredScanSkips}
            totalCount={scanSkips.length}
            loading={loading}
            renderMeta={(skip) => `${skip.reason_code || 'skip'}${skip.extension ? ` · ${skip.extension}` : ''}${skip.reason_detail ? ` · ${skip.reason_detail}` : ''}`}
          />
          <FileList
            title="Digest Errors"
            items={filteredDigestErrors}
            totalCount={digestErrors.length}
            loading={loading}
            renderMeta={(entry) => `${entry.error_type || 'error'}${entry.message ? ` · ${entry.message}` : ''}`}
          />
          </>
        ) : null}
      </div>
    </AudioContentScaffold>
  );
}
