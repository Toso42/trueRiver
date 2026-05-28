import { useEffect, useMemo, useState } from 'react';
import CoverThumb from '../../../shared/ui/CoverThumb';
import InlineArtistLinks from '../../../shared/ui/InlineArtistLinks';
import { CheckIcon, PlayerPlayIcon, PlusIcon, SparklesIcon, UploadIcon } from '../../../shared/ui/TablerIcons';
import ContextMenu from '../../../shared/ui/ContextMenu';
import {
  fetchArtistBioSuggestion,
  fetchArtistById,
  fetchArtistCoverCandidates,
  fetchAlbumTracks,
  fetchArtistTracks,
  selectArtistCover,
  updateArtist,
  uploadArtistProfileImage,
} from '../../../api/library';
import { buildArtistDiscography } from '../metadata/trackMetadataAggregation';
import MultiTrackMetadataEditorModal from '../metadata/MultiTrackMetadataEditorModal';
import { useI18n } from '../../../i18n/I18nProvider';

function withImageVersion(url, version) {
  if (!url || !version) {
    return url || '';
  }
  const joiner = url.includes('?') ? '&' : '?';
  return `${url}${joiner}_triver_img=${version}`;
}

function candidateSelectionPayload(candidate) {
  if (!candidate) {
    return null;
  }
  if (candidate.kind === 'album') {
    return { mode: 'album', album_id: candidate.album_id };
  }
  if (candidate.kind === 'upload') {
    return { mode: 'upload', profile_image_id: candidate.profile_image_id };
  }
  return { mode: 'auto' };
}

function ArtistTrayAlbumRow({ title, items = [], onPlayAlbum, onQueueAlbum, onOpenArtist, onOpenArtistName, onContextMenu }) {
  if (!items.length) {
    return null;
  }

  return (
    <section className="artist-tray-section">
      <div className="artist-tray-section-head">
        <h3>{title}</h3>
        <span>{items.length}</span>
      </div>
      <div className="artist-tray-row">
        {items.map((item) => (
          <article
            key={`${title}-${item.id}`}
            className="artist-tray-album-card"
            onContextMenuCapture={(event) => onContextMenu?.(event, item)}
          >
            <div className="artist-tray-album-cover-shell">
              <div className="artist-tray-album-cover">
                <CoverThumb coverUrl={item.cover_url} alt="" kind="album" />
              </div>
              <button type="button" className="album-play-pill" onClick={() => onPlayAlbum?.(item)} aria-label={`Play ${item.title}`}>
                <PlayerPlayIcon />
              </button>
              <button type="button" className="album-queue-pill" onClick={() => onQueueAlbum?.(item)} aria-label={`Add ${item.title} to queue`}>
                <PlusIcon />
              </button>
            </div>
            <div className="artist-tray-album-copy">
              <h4>{item.title}</h4>
              <InlineArtistLinks
                className="artist-tray-album-artists"
                artists={item.artists || []}
                onOpenArtistId={(_artistId, artistLink) => onOpenArtist?.(artistLink)}
                onOpenArtistName={onOpenArtistName}
              />
              <span>{item.release_year || 'n/a'} · {item.track_count} tracks</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export default function ArtistDetailModal({
  artist = null,
  libraryId = '',
  playerActions = {},
  onClose = () => {},
  onArtistUpdated = null,
  onOpenArtist = null,
  onOpenArtistName = null,
}) {
  const { language } = useI18n();
  const [artistPayload, setArtistPayload] = useState(artist);
  const [tracks, setTracks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [coverCandidates, setCoverCandidates] = useState({ candidates: [] });
  const [activeCoverId, setActiveCoverId] = useState('');
  const [coverSaving, setCoverSaving] = useState(false);
  const [coverError, setCoverError] = useState('');
  const [coverVersion, setCoverVersion] = useState(0);
  const [notesDraft, setNotesDraft] = useState('');
  const [notesSaving, setNotesSaving] = useState(false);
  const [bioLoading, setBioLoading] = useState(false);
  const [bioSources, setBioSources] = useState([]);
  const [notesStatus, setNotesStatus] = useState('');
  const [isImageChanging, setIsImageChanging] = useState(false);
  const [isBioEditing, setIsBioEditing] = useState(false);
  const [contextMenu, setContextMenu] = useState(null);
  const [metadataSelection, setMetadataSelection] = useState(null);
  const [metadataError, setMetadataError] = useState('');

  useEffect(() => {
    if (!artist) {
      setArtistPayload(null);
      setTracks([]);
      setLoading(false);
      setError('');
      setCoverCandidates({ candidates: [] });
      setActiveCoverId('');
      setCoverError('');
      setNotesDraft('');
      setBioSources([]);
      setNotesStatus('');
      setIsImageChanging(false);
      setIsBioEditing(false);
      setContextMenu(null);
      setMetadataSelection(null);
      setMetadataError('');
      return undefined;
    }

    let cancelled = false;
    setArtistPayload(artist);
    setTracks([]);
    setLoading(false);
    setError('');
    setCoverCandidates({ candidates: [] });
    setActiveCoverId('');
    setCoverError('');
    setNotesDraft(artist?.triver_notes || '');
    setBioSources([]);
    setNotesStatus('');
    setIsImageChanging(false);
    setIsBioEditing(false);
    setMetadataError('');

    async function load() {
      if (!artist?.id || !libraryId) {
        return;
      }
      setLoading(true);
      try {
        const [detailPayload, trackPayload, coverPayload] = await Promise.all([
          fetchArtistById(artist.id),
          fetchArtistTracks(libraryId, artist.id),
          fetchArtistCoverCandidates(artist.id, libraryId),
        ]);
        if (!cancelled) {
          setArtistPayload(detailPayload);
          setTracks(trackPayload);
          setCoverCandidates(coverPayload || { candidates: [] });
          setActiveCoverId((coverPayload?.candidates || []).find((candidate) => candidate.selected)?.id || '');
          setNotesDraft(detailPayload?.triver_notes || '');
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError.message || 'Artist detail unavailable');
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
  }, [artist, artist?.id, libraryId]);

  useEffect(() => {
    if (!artist) {
      return undefined;
    }

    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        onClose();
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [artist, onClose]);

  useEffect(() => {
    if (!artist) {
      return undefined;
    }
    function dismissContextMenu() {
      setContextMenu(null);
    }

    window.addEventListener('click', dismissContextMenu);
    window.addEventListener('keydown', dismissContextMenu);
    window.addEventListener('resize', dismissContextMenu);
    return () => {
      window.removeEventListener('click', dismissContextMenu);
      window.removeEventListener('keydown', dismissContextMenu);
      window.removeEventListener('resize', dismissContextMenu);
    };
  }, [artist]);

  const discography = useMemo(
    () => buildArtistDiscography(artistPayload || artist || {}, tracks),
    [artist, artistPayload, tracks],
  );

  if (!artist) {
    return null;
  }

  const currentArtist = artistPayload || artist;
  const fallbackCoverItems = [...discography.albums, ...discography.features].filter((item, index, list) => (
    item.cover_url && index === list.findIndex((entry) => entry.id === item.id)
  ));
  const coverCandidateItems = (coverCandidates?.candidates || []).length
    ? coverCandidates.candidates
    : fallbackCoverItems.map((item) => ({
      id: item.id,
      kind: 'album',
      album_id: item.id,
      profile_image_id: '',
      title: item.title,
      subtitle: String(item.release_year || ''),
      cover_url: item.cover_url,
      selected: false,
    }));
  const activeCover = coverCandidateItems.find((candidate) => candidate.id === activeCoverId)
    || coverCandidateItems.find((candidate) => candidate.selected)
    || coverCandidateItems[0]
    || null;
  const selectedCover = coverCandidateItems.find((candidate) => candidate.selected) || null;
  const activeCoverUrl = withImageVersion(activeCover?.cover_url || currentArtist?.cover_url || artist.cover_url, coverVersion);
  const notesChanged = notesDraft !== (currentArtist?.triver_notes || '');

  async function handleSelectActiveCover() {
    const payload = candidateSelectionPayload(activeCover);
    if (!payload || !currentArtist?.id || activeCover?.selected) {
      return;
    }
    setCoverSaving(true);
    setCoverError('');
    try {
      const response = await selectArtistCover(currentArtist.id, payload);
      setArtistPayload(response.artist || currentArtist);
      setCoverCandidates(response.cover_candidates || { candidates: [] });
      setActiveCoverId(activeCover.id);
      setCoverVersion(Date.now());
      setIsImageChanging(false);
      onArtistUpdated?.(response.artist || currentArtist);
    } catch (nextError) {
      setCoverError(nextError.message || 'Unable to select artist image');
    } finally {
      setCoverSaving(false);
    }
  }

  async function handleUploadImage(event) {
    const file = event.target.files?.[0];
    if (!file || !currentArtist?.id) {
      return;
    }
    setCoverSaving(true);
    setCoverError('');
    try {
      const response = await uploadArtistProfileImage(currentArtist.id, file);
      setArtistPayload(response.artist || currentArtist);
      setCoverCandidates(response.cover_candidates || { candidates: [] });
      setActiveCoverId(response.image?.id || '');
      setCoverVersion(Date.now());
      setIsImageChanging(false);
      onArtistUpdated?.(response.artist || currentArtist);
    } catch (nextError) {
      setCoverError(nextError.message || 'Unable to upload artist image');
    } finally {
      event.target.value = '';
      setCoverSaving(false);
    }
  }

  async function handleSaveNotes() {
    if (!currentArtist?.id || !notesChanged) {
      return;
    }
    setNotesSaving(true);
    setNotesStatus('');
    try {
      const response = await updateArtist(currentArtist.id, { triver_notes: notesDraft });
      setArtistPayload(response || currentArtist);
      setNotesStatus('Saved');
      setIsBioEditing(false);
      onArtistUpdated?.(response || currentArtist);
    } catch (nextError) {
      setNotesStatus(nextError.message || 'Unable to save artist bio');
    } finally {
      setNotesSaving(false);
    }
  }

  async function handleSuggestBio() {
    if (!currentArtist?.id) {
      return;
    }
    setBioLoading(true);
    setNotesStatus('');
    try {
      const suggestion = await fetchArtistBioSuggestion(currentArtist.id, language);
      setNotesDraft(suggestion.draft || '');
      setBioSources(suggestion.sources || []);
      setNotesStatus('Draft ready');
      setIsBioEditing(true);
    } catch (nextError) {
      setNotesStatus(nextError.message || 'No online bio found');
    } finally {
      setBioLoading(false);
    }
  }

  function openAlbumContextMenu(event, albumItem) {
    event.preventDefault();
    event.stopPropagation();
    setContextMenu({
      x: event.clientX,
      y: event.clientY,
      album: albumItem,
    });
  }

  async function openAlbumMetadata(albumItem) {
    if (!libraryId || !albumItem?.id) {
      setMetadataError('Unable to open album metadata: library is not ready.');
      return;
    }
    setMetadataError('');
    try {
      const albumTracks = await fetchAlbumTracks(libraryId, albumItem.id);
      if (!albumTracks.length) {
        setMetadataError('No indexed tracks for this album.');
        return;
      }
      setMetadataSelection({
        title: `${albumItem.title || 'Album'} Metadata`,
        tracks: albumTracks,
      });
    } catch (nextError) {
      setMetadataError(nextError.message || 'Unable to open album metadata.');
    }
  }

  return (
    <div className="app-content-tray" role="presentation">
      <button type="button" className="modal-close artist-tray-close" onClick={onClose} aria-label="Close artist tray">×</button>
      <section className="artist-detail-tray" role="dialog" aria-modal="false" aria-label={currentArtist?.name || 'Artist'}>
        <div className="artist-detail-head">
          <div>
            <p className="panel-kicker">Artist</p>
            <h2>{currentArtist?.name || artist.name || 'Artist'}</h2>
          </div>
        </div>

        <div className="artist-detail-hero">
          <div className="artist-detail-visual">
            <div className="artist-detail-visual-main">
              <CoverThumb coverUrl={activeCoverUrl} alt="" kind="artist" />
              <button
                type="button"
                className="artist-hover-action artist-image-change-button"
                onClick={() => setIsImageChanging(true)}
              >
                <UploadIcon />
                <span>Change image</span>
              </button>
            </div>
            {isImageChanging ? (
              <div className="artist-cover-tool">
                {coverCandidateItems.length ? (
                  <div className="artist-detail-visual-strip">
                    {coverCandidateItems.slice(0, 18).map((item) => (
                      <button
                        key={`${item.kind}-${item.id}`}
                        type="button"
                        className={`artist-detail-visual-thumb${activeCover?.id === item.id ? ' is-active' : ''}${item.selected ? ' is-selected' : ''}`}
                        onClick={() => setActiveCoverId(item.id)}
                        aria-label={`Show ${item.title}`}
                      >
                        <CoverThumb coverUrl={withImageVersion(item.cover_url, coverVersion)} alt="" kind={item.kind === 'upload' ? 'artist' : 'album'} />
                        {item.selected ? <span className="artist-cover-selected-dot"><CheckIcon /></span> : null}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="artist-cover-actions">
                  <button
                    type="button"
                    className="artist-cover-action"
                    onClick={handleSelectActiveCover}
                    disabled={!activeCover || activeCover.selected || coverSaving}
                  >
                    <CheckIcon />
                    <span>{activeCover?.selected ? 'In use' : 'Use image'}</span>
                  </button>
                  <label className={`artist-cover-action${coverSaving ? ' is-disabled' : ''}`}>
                    <UploadIcon />
                    <span>Upload</span>
                    <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={handleUploadImage} disabled={coverSaving} />
                  </label>
                  <button
                    type="button"
                    className="artist-cover-action"
                    onClick={() => {
                      setIsImageChanging(false);
                      setActiveCoverId(selectedCover?.id || '');
                    }}
                    disabled={coverSaving}
                  >
                    <span>Done</span>
                  </button>
                </div>
                <div className="artist-cover-context">
                  <span>{activeCover?.title || selectedCover?.title || 'Auto'}</span>
                  {activeCover?.subtitle ? <span>{activeCover.subtitle}</span> : null}
                </div>
              </div>
            ) : null}
            {coverError ? <p className="metadata-error">{coverError}</p> : null}
          </div>

          <div className="artist-detail-copy">
            <div className={`artist-detail-bio-block${isBioEditing ? ' is-editing' : ''}`}>
              {isBioEditing ? (
                <div className="artist-detail-bio-editor">
                  <textarea
                    value={notesDraft}
                    onChange={(event) => {
                      setNotesDraft(event.target.value);
                      setNotesStatus('');
                    }}
                    placeholder={`${currentArtist?.name || 'Artist'} appears in ${currentArtist?.track_count || tracks.length || 0} tracks in the library.`}
                    rows={8}
                  />
                  <div className="artist-detail-bio-actions">
                    <button type="button" className="artist-cover-action" onClick={handleSuggestBio} disabled={bioLoading || notesSaving}>
                      <SparklesIcon />
                      <span>{bioLoading ? 'Searching...' : 'Suggest'}</span>
                    </button>
                    <button type="button" className="artist-cover-action" onClick={handleSaveNotes} disabled={!notesChanged || notesSaving || bioLoading}>
                      <CheckIcon />
                      <span>{notesSaving ? 'Saving...' : 'Save'}</span>
                    </button>
                    <button
                      type="button"
                      className="artist-cover-action"
                      onClick={() => {
                        setNotesDraft(currentArtist?.triver_notes || '');
                        setIsBioEditing(false);
                        setNotesStatus('');
                      }}
                      disabled={notesSaving || bioLoading}
                    >
                      <span>Cancel</span>
                    </button>
                    {notesStatus ? <span className="artist-detail-bio-status">{notesStatus}</span> : null}
                  </div>
                </div>
              ) : (
                <>
                  <p className="artist-detail-bio-text">
                    {notesDraft?.trim() || `${currentArtist?.name || 'Artist'} appears in ${currentArtist?.track_count || tracks.length || 0} tracks in the library.`}
                  </p>
                  <div className="artist-detail-bio-hover-actions">
                    <button type="button" className="artist-hover-action" onClick={() => setIsBioEditing(true)}>
                      <span>Edit</span>
                    </button>
                    <button type="button" className="artist-hover-action" onClick={handleSuggestBio} disabled={bioLoading || notesSaving}>
                      <SparklesIcon />
                      <span>{bioLoading ? 'Searching...' : 'Suggest'}</span>
                    </button>
                  </div>
                </>
              )}
              {bioSources.length ? (
                <div className="artist-detail-bio-sources">
                  {bioSources.map((source) => (
                    source.url ? (
                      <a key={`${source.label}-${source.url}`} href={source.url} target="_blank" rel="noreferrer">{source.label}</a>
                    ) : (
                      <span key={source.label}>{source.label}</span>
                    )
                  ))}
                </div>
              ) : null}
            </div>
            <div className="artist-detail-meta">
              <span>{currentArtist?.track_count || tracks.length || 0} tracks</span>
              <span>{discography.albums.length} album</span>
              <span>{discography.features.length} feature</span>
            </div>
          </div>
        </div>

        {error ? <p className="metadata-error">{error}</p> : null}
        {metadataError ? <p className="metadata-error">{metadataError}</p> : null}
        {loading ? <p className="empty-state">Loading artist...</p> : null}

        {!loading ? (
          <div className="artist-detail-sections">
            <ArtistTrayAlbumRow
              title="Albums"
              items={discography.albums}
              onPlayAlbum={playerActions.playAlbum}
              onQueueAlbum={playerActions.queueAlbum}
              onOpenArtist={onOpenArtist}
              onOpenArtistName={onOpenArtistName}
              onContextMenu={openAlbumContextMenu}
            />
            <ArtistTrayAlbumRow
              title="Features"
              items={discography.features}
              onPlayAlbum={playerActions.playAlbum}
              onQueueAlbum={playerActions.queueAlbum}
              onOpenArtist={onOpenArtist}
              onOpenArtistName={onOpenArtistName}
              onContextMenu={openAlbumContextMenu}
            />
          </div>
        ) : null}
      </section>
      {contextMenu ? (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          items={[
            {
              key: 'play',
              label: 'Play Album',
              onSelect: () => playerActions.playAlbum?.(contextMenu.album),
            },
            {
              key: 'queue',
              label: 'Add Album To Queue',
              onSelect: () => playerActions.queueAlbum?.(contextMenu.album),
            },
            {
              key: 'metadata',
              label: 'Metadata',
              onSelect: () => openAlbumMetadata(contextMenu.album),
            },
          ]}
        />
      ) : null}
      {metadataSelection ? (
        <MultiTrackMetadataEditorModal
          tracks={metadataSelection.tracks}
          title={metadataSelection.title}
          kicker="Album Selection Metadata"
          onClose={() => setMetadataSelection(null)}
        />
      ) : null}
    </div>
  );
}
