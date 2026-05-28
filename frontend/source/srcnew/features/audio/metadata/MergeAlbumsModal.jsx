import { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';

export default function MergeAlbumsModal({
  albums = [],
  onClose = () => {},
  onApply = () => Promise.resolve(),
}) {
  const albumOptions = useMemo(() => {
    const seen = new Set();
    return (albums || [])
      .map((album) => ({
        id: album.id,
        title: album.title || 'Untitled Album',
      }))
      .filter((album) => {
        const key = album.title.toLowerCase();
        if (seen.has(key)) {
          return false;
        }
        seen.add(key);
        return true;
      });
  }, [albums]);
  const [selectedTitle, setSelectedTitle] = useState(albumOptions[0]?.title || '');
  const [customTitle, setCustomTitle] = useState('');
  const [useCustomTitle, setUseCustomTitle] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState('');
  const [releaseConflict, setReleaseConflict] = useState(null);
  const [releaseDateResolution, setReleaseDateResolution] = useState('');

  if (!albums.length) {
    return null;
  }

  const targetTitle = (useCustomTitle ? customTitle : selectedTitle).trim();

  async function applyMerge() {
    if (!targetTitle) {
      return;
    }
    setIsApplying(true);
    setError('');
    try {
      await onApply(targetTitle, releaseConflict ? { releaseDateResolution } : {});
      setReleaseConflict(null);
    } catch (applyError) {
      if (applyError.status === 409 && applyError.payload?.conflict_type === 'release_date') {
        const payload = applyError.payload;
        setReleaseConflict(payload);
        setReleaseDateResolution(payload.options?.[0]?.value ?? '');
      } else {
        setError(applyError.message || 'Album merge failed.');
      }
    } finally {
      setIsApplying(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <section className="track-meta-modal merge-albums-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <div className="track-meta-head">
          <div>
            <p className="panel-kicker">Merge Albums</p>
            <h3>{albums.length} selected albums</h3>
          </div>
          <div className="track-meta-actions">
            <button type="button" className="modal-close" onClick={onClose} aria-label="Close merge albums modal">×</button>
          </div>
        </div>
        <div className="metadata-stack">
          <section className="metadata-section">
            <h4>Choose target album title</h4>
            <div className="merge-albums-options">
              {albumOptions.map((album) => (
                <label key={album.id} className="merge-albums-option">
                  <input
                    type="radio"
                    name="merge-albums-title"
                    checked={!useCustomTitle && selectedTitle === album.title}
                    onChange={() => {
                      setUseCustomTitle(false);
                      setSelectedTitle(album.title);
                      setReleaseConflict(null);
                    }}
                  />
                  <span>{album.title}</span>
                </label>
              ))}
              <label className="merge-albums-option">
                <input
                  type="radio"
                  name="merge-albums-title"
                  checked={useCustomTitle}
                  onChange={() => {
                    setUseCustomTitle(true);
                    setReleaseConflict(null);
                  }}
                />
                <span>Custom title</span>
              </label>
              {useCustomTitle ? (
                <input
                  type="text"
                  className="merge-albums-custom-input"
                  value={customTitle}
                  placeholder="Enter album title"
                  onChange={(event) => {
                    setCustomTitle(event.target.value);
                    setReleaseConflict(null);
                  }}
                />
              ) : null}
            </div>
          </section>

          {releaseConflict ? (
            <section className="metadata-section merge-conflict-section">
              <h4>Release date conflict</h4>
              <p>{releaseConflict.message || 'Some tracks have different release dates.'}</p>
              <div className="merge-albums-options">
                {(releaseConflict.options || []).map((option) => (
                  <label key={`${option.value}:${option.label}`} className="merge-albums-option">
                    <input
                      type="radio"
                      name="merge-release-date"
                      checked={releaseDateResolution === option.value}
                      onChange={() => setReleaseDateResolution(option.value)}
                    />
                    <span>{option.label || 'Clear release date'} · {option.track_count} tracks</span>
                  </label>
                ))}
              </div>
            </section>
          ) : null}

          {error ? <p className="metadata-error">{error}</p> : null}
          <div className="track-meta-actions">
            <button type="button" className="metadata-inline-button is-muted" onClick={onClose} disabled={isApplying}>Cancel</button>
            <button
              type="button"
              className="metadata-inline-button"
              disabled={isApplying || !targetTitle}
              onClick={applyMerge}
            >
              {isApplying ? 'Applying' : (releaseConflict ? 'Apply With Date Fix' : 'Apply Merge')}
            </button>
          </div>
        </div>
      </section>
    </div>,
    document.body,
  );
}
