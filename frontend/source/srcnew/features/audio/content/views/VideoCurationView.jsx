import { useCallback, useEffect, useMemo, useState } from 'react';
import AudioContentScaffold from '../AudioContentScaffold';
import {
  ensureCoreTrackTagDefinitions,
  fetchTagValues,
  fetchVideoCurationSettings,
  updateVideoCurationSettings,
} from '../../../../api/tags';

function compareTagValues(left, right) {
  const displayOrderDiff = (Number(left?.display_order) || 0) - (Number(right?.display_order) || 0);
  if (displayOrderDiff !== 0) {
    return displayOrderDiff;
  }
  return String(left?.value_text || '').localeCompare(String(right?.value_text || ''), undefined, { sensitivity: 'base' });
}

function normalizeOrderedValues(values = []) {
  return [...values]
    .sort(compareTagValues)
    .map((value, index) => ({
      ...value,
      display_order: index,
    }));
}

function moveInArray(items, index, delta) {
  const nextIndex = index + delta;
  if (index < 0 || nextIndex < 0 || nextIndex >= items.length) {
    return items;
  }
  const next = [...items];
  const [moved] = next.splice(index, 1);
  next.splice(nextIndex, 0, moved);
  return next;
}

function filterValues(values = [], searchTerm = '') {
  const needle = String(searchTerm || '').trim().toLowerCase();
  if (!needle) {
    return values;
  }
  return values.filter((value) => String(value?.value_text || '').toLowerCase().includes(needle));
}

export default function VideoCurationView({ loading = false, pageError = '', libraryId = null, searchTerm = '', refreshToken = 0 }) {
  const [definitions, setDefinitions] = useState({ audioTagDefinition: null, videoTagDefinition: null });
  const [audioTagValues, setAudioTagValues] = useState([]);
  const [videoTagValues, setVideoTagValues] = useState([]);
  const [curationRows, setCurationRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadState = useCallback(async () => {
    if (!libraryId) {
      return;
    }
    setBusy(true);
    setError('');
    try {
      const ensuredDefinitions = await ensureCoreTrackTagDefinitions();
      const [audioValues, videoValues, curationSettings] = await Promise.all([
        fetchTagValues(ensuredDefinitions.audioTagDefinition.id),
        fetchTagValues(ensuredDefinitions.videoTagDefinition.id),
        fetchVideoCurationSettings(),
      ]);
      setDefinitions(ensuredDefinitions);
      setAudioTagValues(normalizeOrderedValues(audioValues));
      setVideoTagValues(normalizeOrderedValues(videoValues));
      setCurationRows(Array.isArray(curationSettings?.rows) ? curationSettings.rows : []);
    } catch (loadError) {
      setError(loadError.message || 'Unable to load tag curation state.');
    } finally {
      setBusy(false);
    }
  }, [libraryId]);

  useEffect(() => {
    loadState();
  }, [loadState, refreshToken]);

  const filteredAudioValues = useMemo(() => filterValues(audioTagValues, searchTerm), [audioTagValues, searchTerm]);
  const filteredVideoValues = useMemo(() => filterValues(videoTagValues, searchTerm), [videoTagValues, searchTerm]);

  async function moveCurationRow(index, delta) {
    const nextRows = moveInArray(curationRows, index, delta).map((row, nextIndex) => ({
      ...row,
      display_order: nextIndex,
    }));
    setCurationRows(nextRows);
    try {
      setBusy(true);
      await updateVideoCurationSettings({ row_order: nextRows.map((row) => row.id) });
      await loadState();
    } catch (saveError) {
      setError(saveError.message || 'Unable to update landing order.');
      await loadState();
    } finally {
      setBusy(false);
    }
  }

  if (loading && !audioTagValues.length && !videoTagValues.length) {
    return <p className="empty-state">Loading tag curation...</p>;
  }

  if (pageError) {
    return <p className="empty-state">{pageError}</p>;
  }

  return (
    <AudioContentScaffold>
      <section className="video-curation-shell">
        <header className="video-curation-header">
          <div>
            <strong>Tag Types</strong>
            <span>Two global track tag definitions drive assignment across audio and video content.</span>
          </div>
          {busy ? <span className="video-curation-status">Syncing…</span> : null}
        </header>

        {error ? <div className="video-curation-error">{error}</div> : null}

        <section className="video-curation-grid">
          <article className="video-curation-card">
            <header className="video-curation-card-header">
              <strong>{definitions.audioTagDefinition?.label || 'Audio Tag'}</strong>
              <span>{filteredAudioValues.length} visible · {audioTagValues.length} total</span>
            </header>
            <p className="video-curation-card-copy">
              Assignable to any media content from the right-click action. Use this for audio-facing grouping and future listening surfaces.
            </p>
            <ul className="video-curation-value-list">
              {filteredAudioValues.length ? filteredAudioValues.map((value) => (
                <li key={value.id} className="video-curation-value-row">
                  <span>{value.value_text}</span>
                </li>
              )) : <li className="video-curation-empty-inline">No audio tags defined yet.</li>}
            </ul>
          </article>

          <article className="video-curation-card">
            <header className="video-curation-card-header">
              <strong>{definitions.videoTagDefinition?.label || 'Video Tag'}</strong>
              <span>{filteredVideoValues.length} visible · {videoTagValues.length} total</span>
            </header>
            <p className="video-curation-card-copy">
              Assignable to any media content. These values also drive curated rails on the TV landing.
            </p>
            <ul className="video-curation-value-list">
              {filteredVideoValues.length ? filteredVideoValues.map((value) => (
                <li key={value.id} className="video-curation-value-row">
                  <span>{value.value_text}</span>
                </li>
              )) : <li className="video-curation-empty-inline">No video tags defined yet.</li>}
            </ul>
          </article>
        </section>

        <section className="video-curation-card">
          <header className="video-curation-card-header">
            <strong>Landing Order</strong>
            <span>Server order used by the web app and Android TV.</span>
          </header>

          <ul className="video-curation-order-list">
            {curationRows.map((row, index) => (
              <li key={row.id} className="video-curation-order-row">
                <span className="video-curation-order-position">{String(index + 1).padStart(2, '0')}</span>
                <span className="video-curation-order-label">{row.label}</span>
                <span className="video-curation-order-actions">
                  <button type="button" onClick={() => moveCurationRow(index, -1)} disabled={busy || index === 0}>Up</button>
                  <button type="button" onClick={() => moveCurationRow(index, 1)} disabled={busy || index === curationRows.length - 1}>Down</button>
                </span>
              </li>
            ))}
            {!curationRows.length ? <li className="video-curation-empty-inline">No video rows available yet.</li> : null}
          </ul>
        </section>
      </section>
    </AudioContentScaffold>
  );
}
