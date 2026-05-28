import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import CoverThumb from '../../../shared/ui/CoverThumb';
import { fetchAlbumMetadata, patchAlbumMetadata } from '../../../api/metadata';
import MetadataEditableField from './MetadataEditableField';

export default function AlbumMetadataEditorModal({ album = null, onClose = () => {} }) {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (!album?.id) {
      return undefined;
    }
    setLoading(true);
    setError('');
    setPayload(null);
    fetchAlbumMetadata(album.id)
      .then((nextPayload) => {
        if (!cancelled) {
          setPayload(nextPayload);
        }
      })
      .catch((nextError) => {
        if (!cancelled) {
          setError(nextError.message || 'Album metadata unavailable');
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
  }, [album?.id]);

  if (!album) {
    return null;
  }

  const rows = payload?.metadata || [];

  async function handleApply(row, nextValues) {
    await patchAlbumMetadata(album.id, row.field, nextValues);
    const nextPayload = await fetchAlbumMetadata(album.id);
    setPayload(nextPayload);
  }

  return createPortal(
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <section className="track-meta-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <div className="track-meta-head">
          <div>
            <p className="panel-kicker">Album Metadata</p>
            <h3>{album.title}</h3>
          </div>
          <div className="track-meta-actions">
            <button type="button" className="modal-close" onClick={onClose} aria-label="Close album metadata modal">×</button>
          </div>
        </div>
        <div className="track-meta-layout">
          <CoverThumb coverUrl={album.cover_url} alt="" kind="album" />
          <div className="metadata-stack">
            <section className="metadata-section">
              <div className="metadata-section-headline">
                <h4>Editable Metadata</h4>
                {loading ? <span>loading</span> : null}
              </div>
              {error ? <p className="metadata-error">{error}</p> : null}
              {!loading && !error && !rows.length ? (
                <p className="empty-state">No metadata available for this album.</p>
              ) : null}
              {rows.length ? (
                <dl className="metadata-grid metadata-edit-grid">
                  {rows.map((row) => (
                    <MetadataEditableField
                      key={row.field}
                      row={row}
                      disabled={row.read_only || loading}
                      onApply={(nextValues) => handleApply(row, nextValues)}
                    />
                  ))}
                </dl>
              ) : null}
            </section>
          </div>
        </div>
      </section>
    </div>,
    document.body,
  );
}
