import { useCallback, useEffect, useMemo, useState } from 'react';
import AudioContentScaffold from '../AudioContentScaffold';
import { acceptDedupCandidateAsVersions, cancelDedupJob, fetchDedupState, fullThrottleDedupJob, rejectDedupCandidate, startDedupScan } from '../../../../api/dedup';
import { acceptVersionCandidate, deleteVersionTrack, fetchVersionHandlingState, rejectVersionCandidate } from '../../../../api/versions';
import { fetchRemoteMetadataSettings, updateRemoteMetadataSettings } from '../../../../api/metadata';
import { LanguageSelector, useT } from '../../../../i18n/I18nProvider';

function formatDuration(seconds) {
  const numeric = Number(seconds);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return '';
  }
  const minutes = Math.floor(numeric / 60);
  const remaining = Math.round(numeric % 60).toString().padStart(2, '0');
  return `${minutes}:${remaining}`;
}

function trackArtists(track) {
  return (track.artist_summary || []).map((artist) => artist.name).filter(Boolean).join(', ');
}

function VersionCandidateCard({ candidate, expanded, onToggle, onAccept, onReject, onDeleteTrack, busy }) {
  const score = Math.round(Number(candidate.score || 0) * 100);
  return (
    <article className="version-candidate-card">
      <button type="button" className="version-candidate-summary" onClick={onToggle}>
        <span>
          <strong>{candidate.title || 'Possible Versions'}</strong>
          <small>{candidate.track_count || candidate.tracks?.length || 0} tracks · {score}% match</small>
        </span>
        <span className="version-candidate-reasons">{(candidate.reasons || []).slice(0, 3).join(' · ')}</span>
      </button>
      {expanded ? (
        <div className="version-candidate-detail">
          <div className="version-track-list">
            {(candidate.tracks || []).map((track) => (
              <div key={track.id} className="version-track-row">
                <div>
                  <strong>{track.canonical_title}</strong>
                  <span>{track.album_title || 'Unknown album'}{trackArtists(track) ? ` · ${trackArtists(track)}` : ''}</span>
                </div>
                <small>{formatDuration(track.duration_seconds)}</small>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onDeleteTrack(track)}
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
          <div className="version-candidate-actions">
            <button type="button" disabled={busy} onClick={onAccept}>Accept Versions</button>
            <button type="button" disabled={busy} onClick={onReject}>Not Versions</button>
          </div>
        </div>
      ) : null}
    </article>
  );
}

function ExistingVersionGroup({ group }) {
  const members = group.memberships || [];
  return (
    <article className="version-existing-card">
      <strong>{group.title}</strong>
      <span>{members.length} versions · {group.serving_mode}</span>
      <div className="version-existing-members">
        {members.slice(0, 4).map((membership) => (
          <small key={membership.id}>{membership.track_title}</small>
        ))}
      </div>
    </article>
  );
}

function DedupCandidateCard({ candidate, expanded, onToggle, onAccept, onReject, busy }) {
  const score = Math.round(Number(candidate.score || 0) * 100);
  const tracks = candidate.tracks || [];
  return (
    <article className="version-candidate-card">
      <button type="button" className="version-candidate-summary" onClick={onToggle}>
        <span>
          <strong>{candidate.title || 'Possible duplicates'}</strong>
          <small>{candidate.track_count || tracks.length || 0} files · {score}% match</small>
        </span>
        <span className="version-candidate-reasons">{(candidate.reasons || []).slice(0, 3).join(' · ')}</span>
      </button>
      {expanded ? (
        <div className="version-candidate-detail">
          <div className="version-track-list">
            {tracks.map((track) => (
              <div key={track.id} className="version-track-row">
                <div>
                  <strong>{track.canonical_title}</strong>
                  <span>{track.album_title || 'Unknown album'}{trackArtists(track) ? ` · ${trackArtists(track)}` : ''}</span>
                </div>
                <small>{formatDuration(track.duration_seconds)}</small>
                <span>{track.media_kind || 'media'}</span>
              </div>
            ))}
          </div>
          <div className="version-candidate-actions">
            <button type="button" disabled={busy} onClick={onAccept}>Mark as Versions</button>
            <button type="button" disabled={busy} onClick={onReject}>Not Duplicates</button>
          </div>
        </div>
      ) : null}
    </article>
  );
}

export default function SettingsView({ mode = 'app' }) {
  const t = useT();
  const [versionState, setVersionState] = useState({ candidates: [], existing_groups: [] });
  const [dedupState, setDedupState] = useState({ latest_job: null, candidates: [] });
  const [remoteMetadataSettings, setRemoteMetadataSettings] = useState(null);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [dedupLoading, setDedupLoading] = useState(false);
  const [remoteMetadataLoading, setRemoteMetadataLoading] = useState(false);
  const [remoteMetadataSaving, setRemoteMetadataSaving] = useState(false);
  const [versionsError, setVersionsError] = useState('');
  const [dedupError, setDedupError] = useState('');
  const [remoteMetadataError, setRemoteMetadataError] = useState('');
  const [versionsNotice, setVersionsNotice] = useState('');
  const [dedupNotice, setDedupNotice] = useState('');
  const [remoteMetadataNotice, setRemoteMetadataNotice] = useState('');
  const [expandedFingerprint, setExpandedFingerprint] = useState('');
  const [expandedDedupId, setExpandedDedupId] = useState('');
  const [busyFingerprint, setBusyFingerprint] = useState('');
  const [busyDedupId, setBusyDedupId] = useState('');

  const candidates = useMemo(() => versionState.candidates || [], [versionState]);
  const existingGroups = useMemo(() => versionState.existing_groups || [], [versionState]);
  const dedupCandidates = useMemo(() => dedupState.candidates || [], [dedupState]);
  const latestDedupJob = dedupState.latest_job;
  const remoteProviders = remoteMetadataSettings?.providers || [];
  const pageTitle = mode === 'dedup'
    ? 'Dedup Manager'
    : mode === 'metadata'
      ? 'Metadata Settings'
      : 'App Settings';

  const loadVersions = useCallback(async () => {
    setVersionsLoading(true);
    setVersionsError('');
    try {
      const payload = await fetchVersionHandlingState();
      setVersionState(payload || { candidates: [], existing_groups: [] });
      setExpandedFingerprint((current) => current || payload?.candidates?.[0]?.fingerprint || '');
    } catch (error) {
      setVersionsError(error.message || 'Unable to read version candidates.');
    } finally {
      setVersionsLoading(false);
    }
  }, []);

  const loadDedup = useCallback(async () => {
    setDedupLoading(true);
    setDedupError('');
    try {
      const payload = await fetchDedupState();
      setDedupState(payload || { latest_job: null, candidates: [] });
      setExpandedDedupId((current) => current || payload?.candidates?.[0]?.id || '');
    } catch (error) {
      setDedupError(error.message || 'Unable to read dedup candidates.');
    } finally {
      setDedupLoading(false);
    }
  }, []);

  const loadRemoteMetadataSettings = useCallback(async () => {
    setRemoteMetadataLoading(true);
    setRemoteMetadataError('');
    try {
      const payload = await fetchRemoteMetadataSettings();
      setRemoteMetadataSettings(payload);
    } catch (error) {
      setRemoteMetadataError(error.message || 'Unable to read remote metadata settings.');
    } finally {
      setRemoteMetadataLoading(false);
    }
  }, []);

  useEffect(() => {
    if (mode === 'app') {
      loadVersions();
    }
    if (mode === 'dedup') {
      loadDedup();
    }
    if (mode === 'metadata') {
      loadRemoteMetadataSettings();
    }
  }, [loadDedup, loadRemoteMetadataSettings, loadVersions, mode]);

  useEffect(() => {
    if (window.location.hash === '#version-handling' || window.location.hash === '#dedup-manager') {
      document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ block: 'start' });
    }
  }, []);

  async function acceptCandidate(candidate) {
    setBusyFingerprint(candidate.fingerprint);
    setVersionsNotice('');
    try {
      await acceptVersionCandidate(candidate);
      setVersionsNotice('Version group saved.');
      setExpandedFingerprint('');
      await loadVersions();
    } catch (error) {
      setVersionsError(error.message || 'Unable to accept versions.');
    } finally {
      setBusyFingerprint('');
    }
  }

  async function rejectCandidate(candidate) {
    setBusyFingerprint(candidate.fingerprint);
    setVersionsNotice('');
    try {
      await rejectVersionCandidate(candidate);
      setVersionsNotice('Candidate hidden.');
      setExpandedFingerprint('');
      await loadVersions();
    } catch (error) {
      setVersionsError(error.message || 'Unable to reject versions.');
    } finally {
      setBusyFingerprint('');
    }
  }

  async function deleteTrackFromCandidate(track) {
    if (!window.confirm(`Delete "${track.canonical_title}" and its media file?`)) {
      return;
    }
    setVersionsNotice('');
    try {
      await deleteVersionTrack(track.id);
      setVersionsNotice('Track deleted.');
      await loadVersions();
    } catch (error) {
      setVersionsError(error.message || 'Unable to delete track.');
    }
  }

  async function startDedup() {
    setDedupNotice('');
    setDedupError('');
    try {
      await startDedupScan();
      setDedupNotice('Dedup scan started.');
      await loadDedup();
    } catch (error) {
      setDedupError(error.message || 'Unable to start dedup scan.');
    }
  }

  async function cancelDedup() {
    if (!latestDedupJob?.id) {
      return;
    }
    setDedupNotice('');
    try {
      await cancelDedupJob(latestDedupJob.id);
      setDedupNotice('Dedup job canceled.');
      await loadDedup();
    } catch (error) {
      setDedupError(error.message || 'Unable to cancel dedup job.');
    }
  }

  async function boostDedup() {
    if (!latestDedupJob?.id) {
      return;
    }
    setDedupNotice('');
    try {
      await fullThrottleDedupJob(latestDedupJob.id, 600);
      setDedupNotice('Dedup full throttle enabled for 10 minutes.');
      await loadDedup();
    } catch (error) {
      setDedupError(error.message || 'Unable to update dedup throttle.');
    }
  }

  async function acceptDedup(candidate) {
    setBusyDedupId(candidate.id);
    setDedupNotice('');
    try {
      await acceptDedupCandidateAsVersions(candidate.id);
      setDedupNotice('Dedup candidate saved as versions.');
      await loadDedup();
    } catch (error) {
      setDedupError(error.message || 'Unable to accept dedup candidate.');
    } finally {
      setBusyDedupId('');
    }
  }

  async function rejectDedup(candidate) {
    setBusyDedupId(candidate.id);
    setDedupNotice('');
    try {
      await rejectDedupCandidate(candidate.id);
      setDedupNotice('Dedup candidate rejected.');
      await loadDedup();
    } catch (error) {
      setDedupError(error.message || 'Unable to reject dedup candidate.');
    } finally {
      setBusyDedupId('');
    }
  }

  async function saveRemoteMetadataSettings(patch) {
    setRemoteMetadataSaving(true);
    setRemoteMetadataError('');
    setRemoteMetadataNotice('');
    try {
      const payload = await updateRemoteMetadataSettings(patch);
      setRemoteMetadataSettings(payload);
      setRemoteMetadataNotice(t('Remote metadata settings saved.'));
    } catch (error) {
      setRemoteMetadataError(error.message || 'Unable to save remote metadata settings.');
    } finally {
      setRemoteMetadataSaving(false);
    }
  }

  function updateProviderOrder(scope, rawValue) {
    const providerOrder = {
      ...(remoteMetadataSettings?.provider_order || {}),
      [scope]: String(rawValue || '')
        .split(',')
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean),
    };
    setRemoteMetadataSettings((current) => ({ ...current, provider_order: providerOrder }));
  }

  return (
    <AudioContentScaffold title={pageTitle}>
      {mode === 'app' ? (
      <section className="settings-control-panel" aria-label={t('App Settings')}>
        <div className="settings-card-head">
          <strong>{t('App Settings')}</strong>
        </div>
        <div className="settings-form-grid">
          <LanguageSelector />
        </div>
      </section>
      ) : null}

      {mode === 'metadata' ? (
      <section id="remote-metadata" className="settings-control-panel version-handling-panel" aria-label={t('Remote Metadata')}>
        <div className="settings-card-head">
          <strong>{t('Remote Metadata')}</strong>
          <button type="button" className="settings-inline-button" disabled={remoteMetadataLoading} onClick={loadRemoteMetadataSettings}>
            {t('Refresh')}
          </button>
        </div>
        {remoteMetadataError ? <p className="metadata-error">{remoteMetadataError}</p> : null}
        {remoteMetadataNotice ? <p className="file-explorer-notice">{remoteMetadataNotice}</p> : null}
        {remoteMetadataLoading && !remoteMetadataSettings ? <p className="empty-state">{t('Loading remote metadata settings...')}</p> : null}
        {remoteMetadataSettings ? (
          <>
            <div className="settings-form-grid">
              <label>
                <span>{t('Lookup mode')}</span>
                <select
                  value={remoteMetadataSettings.lookup_mode || 'manual'}
                  disabled={remoteMetadataSaving}
                  onChange={(event) => {
                    const nextValue = event.target.value === 'auto' ? 'auto' : 'manual';
                    setRemoteMetadataSettings((current) => ({ ...current, lookup_mode: nextValue, enabled: true }));
                    saveRemoteMetadataSettings({ lookup_mode: nextValue, enabled: true });
                  }}
                >
                  <option value="manual">{t('Manual')}</option>
                  <option value="auto">{t('Auto')}</option>
                </select>
              </label>
            </div>
            <p className="remote-metadata-mode-note">
              {remoteMetadataSettings.lookup_mode === 'auto'
                ? t('Opening this page never starts a lookup; Auto only applies to configured automation.')
                : t('Manual lookup only runs after a content action.')}
            </p>
            <div className="settings-toggle-grid remote-metadata-toggle-grid">
              {[
                ['video_enabled', 'Video metadata'],
                ['audio_enabled', 'Audio metadata'],
                ['allow_remote_artwork', 'Remote artwork'],
              ].map(([field, label]) => (
                <label key={field} className="settings-toggle-row">
                  <span>{t(label)}</span>
                  <input
                    type="checkbox"
                    checked={Boolean(remoteMetadataSettings[field])}
                    disabled={remoteMetadataSaving}
                    onChange={(event) => {
                      const nextValue = event.target.checked;
                      setRemoteMetadataSettings((current) => ({ ...current, [field]: nextValue }));
                      saveRemoteMetadataSettings({ [field]: nextValue });
                    }}
                  />
                </label>
              ))}
            </div>
            <div className="settings-form-grid">
              <label>
                <span>{t('Language')}</span>
                <input
                  value={remoteMetadataSettings.preferred_language || ''}
                  disabled={remoteMetadataSaving}
                  onChange={(event) => setRemoteMetadataSettings((current) => ({ ...current, preferred_language: event.target.value }))}
                  onBlur={(event) => saveRemoteMetadataSettings({ preferred_language: event.target.value })}
                />
              </label>
              <label>
                <span>{t('Region')}</span>
                <input
                  value={remoteMetadataSettings.preferred_region || ''}
                  disabled={remoteMetadataSaving}
                  onChange={(event) => setRemoteMetadataSettings((current) => ({ ...current, preferred_region: event.target.value }))}
                  onBlur={(event) => saveRemoteMetadataSettings({ preferred_region: event.target.value })}
                />
              </label>
              <label>
                <span>{t('Overwrite policy')}</span>
                <select
                  value={remoteMetadataSettings.overwrite_policy || 'missing_only'}
                  disabled={remoteMetadataSaving}
                  onChange={(event) => {
                    const nextValue = event.target.value;
                    setRemoteMetadataSettings((current) => ({ ...current, overwrite_policy: nextValue }));
                    saveRemoteMetadataSettings({ overwrite_policy: nextValue });
                  }}
                >
                  <option value="missing_only">{t('Missing fields only')}</option>
                  <option value="ask">{t('Ask before overwrite')}</option>
                  <option value="replace_unlocked">{t('Replace unlocked fields')}</option>
                </select>
              </label>
            </div>
            <div className="settings-form-grid">
              <label>
                <span>{t('Video provider order')}</span>
                <input
                  value={(remoteMetadataSettings.provider_order?.video || []).join(', ')}
                  disabled={remoteMetadataSaving}
                  onChange={(event) => updateProviderOrder('video', event.target.value)}
                  onBlur={() => saveRemoteMetadataSettings({ provider_order: remoteMetadataSettings.provider_order })}
                />
              </label>
              <label>
                <span>{t('Audio provider order')}</span>
                <input
                  value={(remoteMetadataSettings.provider_order?.audio || []).join(', ')}
                  disabled={remoteMetadataSaving}
                  onChange={(event) => updateProviderOrder('audio', event.target.value)}
                  onBlur={() => saveRemoteMetadataSettings({ provider_order: remoteMetadataSettings.provider_order })}
                />
              </label>
            </div>
            <div className="remote-metadata-provider-grid">
              {remoteProviders.map((provider) => (
                <article key={provider.key} className="remote-metadata-provider-card">
                  <strong>{provider.label}</strong>
                  <span>{provider.media_scope}</span>
                  <small>{provider.implemented ? 'available' : 'prepared'}</small>
                  <small>{provider.configured ? 'configured' : `set ${provider.credential_env?.[0] || 'no key required'}`}</small>
                </article>
              ))}
            </div>
          </>
        ) : null}
      </section>
      ) : null}

      {mode === 'app' ? (
      <section id="version-handling" className="settings-control-panel version-handling-panel" aria-label="Version Handling">
        <div className="settings-card-head">
          <strong>Version Handling</strong>
          <button type="button" className="settings-inline-button" disabled={versionsLoading} onClick={loadVersions}>
            Refresh
          </button>
        </div>
        {versionsError ? <p className="metadata-error">{versionsError}</p> : null}
        {versionsNotice ? <p className="file-explorer-notice">{versionsNotice}</p> : null}
        {versionsLoading && !candidates.length ? <p className="empty-state">Loading version candidates...</p> : null}

        <div className="version-layout">
          <div className="version-column">
            <div className="version-column-head">
              <strong>Possible Versions</strong>
              <span>{candidates.length}</span>
            </div>
            {candidates.length ? candidates.map((candidate) => (
              <VersionCandidateCard
                key={candidate.fingerprint}
                candidate={candidate}
                expanded={expandedFingerprint === candidate.fingerprint}
                busy={busyFingerprint === candidate.fingerprint}
                onToggle={() => setExpandedFingerprint((current) => (current === candidate.fingerprint ? '' : candidate.fingerprint))}
                onAccept={() => acceptCandidate(candidate)}
                onReject={() => rejectCandidate(candidate)}
                onDeleteTrack={deleteTrackFromCandidate}
              />
            )) : <p className="file-explorer-empty">No pending version candidates.</p>}
          </div>

          <div className="version-column">
            <div className="version-column-head">
              <strong>Accepted Groups</strong>
              <span>{existingGroups.length}</span>
            </div>
            {existingGroups.length ? existingGroups.map((group) => (
              <ExistingVersionGroup key={group.id} group={group} />
            )) : <p className="file-explorer-empty">No accepted version groups yet.</p>}
          </div>
        </div>
      </section>
      ) : null}

      {mode === 'dedup' ? (
      <section id="dedup-manager" className="settings-control-panel version-handling-panel" aria-label="Dedup Manager">
        <div className="settings-card-head">
          <strong>Dedup Manager</strong>
          <span>{latestDedupJob?.status || 'idle'}</span>
        </div>
        <div className="version-candidate-actions">
          <button type="button" disabled={dedupLoading || latestDedupJob?.status === 'running' || latestDedupJob?.status === 'pending'} onClick={startDedup}>
            Start Candidate Scan
          </button>
          <button type="button" disabled={!latestDedupJob?.id || !['running', 'pending'].includes(latestDedupJob.status)} onClick={cancelDedup}>
            Stop
          </button>
          <button type="button" disabled={!latestDedupJob?.id || latestDedupJob.status !== 'running'} onClick={boostDedup}>
            Full Throttle 10m
          </button>
          <button type="button" disabled={dedupLoading} onClick={loadDedup}>
            Refresh
          </button>
        </div>
        {latestDedupJob ? (
          <div className="settings-deployment-grid dedup-status-grid">
            <article className="settings-deployment-card">
              <dl>
                <div><dt>Scanned</dt><dd>{latestDedupJob.scanned_count || 0}</dd></div>
                <div><dt>Candidates</dt><dd>{latestDedupJob.candidate_count || 0}</dd></div>
              </dl>
            </article>
            <article className="settings-deployment-card">
              <dl>
                <div><dt>Started</dt><dd>{latestDedupJob.started_at ? new Date(latestDedupJob.started_at).toLocaleString() : 'n/a'}</dd></div>
                <div><dt>Finished</dt><dd>{latestDedupJob.finished_at ? new Date(latestDedupJob.finished_at).toLocaleString() : 'n/a'}</dd></div>
              </dl>
            </article>
          </div>
        ) : null}
        {dedupError ? <p className="metadata-error">{dedupError}</p> : null}
        {dedupNotice ? <p className="file-explorer-notice">{dedupNotice}</p> : null}
        {dedupLoading && !dedupCandidates.length ? <p className="empty-state">Loading dedup candidates...</p> : null}
        <div className="version-column">
          <div className="version-column-head">
            <strong>Pending Candidates</strong>
            <span>{dedupCandidates.length}</span>
          </div>
          {dedupCandidates.length ? dedupCandidates.map((candidate) => (
            <DedupCandidateCard
              key={candidate.id}
              candidate={candidate}
              expanded={expandedDedupId === candidate.id}
              busy={busyDedupId === candidate.id}
              onToggle={() => setExpandedDedupId((current) => (current === candidate.id ? '' : candidate.id))}
              onAccept={() => acceptDedup(candidate)}
              onReject={() => rejectDedup(candidate)}
            />
          )) : <p className="file-explorer-empty">No pending dedup candidates.</p>}
        </div>
      </section>
      ) : null}
    </AudioContentScaffold>
  );
}
