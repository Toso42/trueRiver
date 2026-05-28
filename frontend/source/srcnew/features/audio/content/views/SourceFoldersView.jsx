import { useEffect, useMemo, useRef, useState } from 'react';
import AudioContentScaffold from '../AudioContentScaffold';
import { assignArtistFromFolderName, deleteExplorerEntry, fetchExplorerMetadataTargets, fetchFileExplorer, uploadTriveInFile } from '../../../../api/io';
import { fetchTrackById } from '../../../../api/library';
import ContextMenu from '../../../../shared/ui/ContextMenu';
import MediaFileMetadataEditorModal from '../../metadata/MediaFileMetadataEditorModal';
import MultiTrackMetadataEditorModal from '../../metadata/MultiTrackMetadataEditorModal';
import TrackMetadataEditorModal from '../../metadata/TrackMetadataEditorModal';

const ROOTS = [
  { key: 'trive-In', label: 'trive-In' },
  { key: 'trive-Up', label: 'trive-Up' },
  { key: 'trive-Out', label: 'trive-Out' },
];

function FolderGlyph() {
  return (
    <svg className="tree-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 7.5C3 6.12 4.12 5 5.5 5h4.08l1.9 2H18.5C19.88 7 21 8.12 21 9.5v7c0 1.38-1.12 2.5-2.5 2.5h-13A2.5 2.5 0 0 1 3 16.5z" fill="currentColor" />
    </svg>
  );
}

function FileGlyph() {
  return (
    <svg className="tree-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" fill="currentColor" />
    </svg>
  );
}

function formatFileSize(size) {
  if (size == null || Number.isNaN(Number(size))) {
    return '';
  }
  const value = Number(size);
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatTimestamp(value) {
  if (!value) {
    return '';
  }
  try {
    return new Date(value).toLocaleString();
  } catch (_error) {
    return value;
  }
}

function formatUploadStatus(item) {
  if (item.status === 'complete') {
    return 'Complete';
  }
  if (item.status === 'failed') {
    return item.error || 'Failed';
  }
  if (item.status === 'scanning') {
    return 'Scanning';
  }
  if (item.status === 'uploading') {
    return 'Uploading';
  }
  return 'Queued';
}

export default function SourceFoldersView({ loading = false, pageError = '', onRefresh = null }) {
  const [currentRoot, setCurrentRoot] = useState('trive-In');
  const [currentPath, setCurrentPath] = useState('');
  const [selectedPath, setSelectedPath] = useState('');
  const [browserLoading, setBrowserLoading] = useState(false);
  const [browserError, setBrowserError] = useState('');
  const [browserState, setBrowserState] = useState(null);
  const [contextMenu, setContextMenu] = useState(null);
  const [metadataEntry, setMetadataEntry] = useState(null);
  const [metadataTrack, setMetadataTrack] = useState(null);
  const [folderMetadataSelection, setFolderMetadataSelection] = useState(null);
  const [browserNotice, setBrowserNotice] = useState('');
  const [browserRefreshToken, setBrowserRefreshToken] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploadQueue, setUploadQueue] = useState([]);
  const [deleteBusyPath, setDeleteBusyPath] = useState('');
  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setBrowserLoading(true);
    setBrowserError('');

    fetchFileExplorer(currentRoot, currentPath)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setBrowserState(payload);
      })
      .catch((error) => {
        if (!cancelled) {
          setBrowserError(error.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setBrowserLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [currentRoot, currentPath, browserRefreshToken]);

  useEffect(() => {
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
  }, []);

  const selectedEntry = useMemo(
    () => (browserState?.entries || []).find((entry) => entry.relative_path === selectedPath) || null,
    [browserState?.entries, selectedPath],
  );

  const roots = browserState?.roots?.length ? browserState.roots : ROOTS;
  const effectiveError = browserError || pageError;

  async function openMetadataForEntry(entry) {
    if (entry?.track_id) {
      setBrowserError('');
      try {
        const track = await fetchTrackById(entry.track_id);
        setMetadataTrack(track);
        setMetadataEntry(null);
      } catch (error) {
        setBrowserError(error.message || 'Unable to open track metadata editor.');
      }
      return;
    }
    if (!entry?.media_file_id) {
      setBrowserError('This file is not indexed yet: run scan or rescan before editing its metadata.');
      return;
    }
    setBrowserError('');
    setMetadataEntry(entry);
    setMetadataTrack(null);
  }

  async function openMetadataForFolder(entry) {
    setBrowserError('');
    try {
      const payload = await fetchExplorerMetadataTargets(currentRoot, entry?.relative_path || '');
      const tracks = Array.isArray(payload.tracks) ? payload.tracks : [];
      if (!tracks.length) {
        setBrowserError(`No indexed tracks found inside ${entry?.name || 'this folder'}.`);
        return;
      }
      setFolderMetadataSelection({
        title: `${entry?.name || 'Folder'} Metadata`,
        tracks,
        truncated: Boolean(payload.truncated),
        trackCount: payload.track_count || tracks.length,
      });
    } catch (error) {
      setBrowserError(error.message || 'Unable to open folder metadata.');
    }
  }

  async function assignArtistFromFolder(entry) {
    if (!entry || entry.entry_type !== 'directory') {
      return;
    }
    setBrowserError('');
    setBrowserNotice('');
    try {
      const payload = await assignArtistFromFolderName(currentRoot, entry.relative_path || '');
      const artistName = payload.artist || entry.name || 'folder';
      const trackCount = Number(payload.updated_track_count) || 0;
      const fileCount = Number(payload.updated_media_file_count) || 0;
      setBrowserNotice(`Artist "${artistName}" assigned to ${trackCount} tracks from ${fileCount} files.`);
      onRefresh?.();
    } catch (error) {
      setBrowserError(error.message || 'Unable to assign artist from folder name.');
    }
  }

  function updateUploadQueueItem(index, updates) {
    setUploadQueue((items) => items.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...updates } : item
    )));
  }

  async function uploadFilesFromInput(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (!files.length) {
      return;
    }
    const entries = files.map((file) => ({
      file,
      relativePath: file.webkitRelativePath || file.name,
    }));
    const targetPath = currentPath;
    setUploadQueue(entries.map((entry) => ({
      name: entry.relativePath || entry.file.name,
      loaded: 0,
      total: entry.file.size || 0,
      status: 'queued',
      error: '',
    })));
    setUploading(true);
    setBrowserError('');
    setBrowserNotice('');
    let uploadedCount = 0;
    let failedCount = 0;
    try {
      for (let index = 0; index < entries.length; index += 1) {
        const entry = entries[index];
        updateUploadQueueItem(index, { status: 'uploading', loaded: 0, total: entry.file.size || 0, error: '' });
        try {
          const payload = await uploadTriveInFile(targetPath, entry, ({ loaded, total }) => {
            const safeTotal = total || entry.file.size || 0;
            updateUploadQueueItem(index, {
              loaded,
              total: safeTotal,
              status: safeTotal > 0 && loaded >= safeTotal ? 'scanning' : 'uploading',
            });
          });
          uploadedCount += Number(payload?.uploaded_count) || 1;
          updateUploadQueueItem(index, {
            loaded: entry.file.size || 1,
            total: entry.file.size || 1,
            status: 'complete',
          });
        } catch (error) {
          failedCount += 1;
          updateUploadQueueItem(index, {
            status: 'failed',
            error: error.message || 'Upload failed.',
          });
        }
      }
      if (uploadedCount > 0) {
        setBrowserRefreshToken((token) => token + 1);
        onRefresh?.();
      }
      if (failedCount > 0) {
        setBrowserError(`Upload completed with ${failedCount} failed file${failedCount === 1 ? '' : 's'}.`);
      }
      setBrowserNotice(`Uploaded ${uploadedCount} of ${entries.length} file${entries.length === 1 ? '' : 's'} after antivirus scan.`);
    } finally {
      setUploading(false);
    }
  }

  async function deleteEntryFromBrowser(entry) {
    if (!entry?.relative_path || uploading || deleteBusyPath) {
      return;
    }
    const kind = entry.entry_type === 'directory' ? 'folder' : 'file';
    if (!window.confirm(`Delete ${kind} "${entry.name}" from ${currentRoot}?`)) {
      return;
    }
    setContextMenu(null);
    setBrowserError('');
    setBrowserNotice('');
    setDeleteBusyPath(entry.relative_path);
    try {
      const payload = await deleteExplorerEntry(currentRoot, entry.relative_path);
      const cleanup = payload?.catalog_cleanup || {};
      const cleaned = Number(cleanup.tracks || 0) + Number(cleanup.media_files || 0) + Number(cleanup.accessory_files || 0);
      setBrowserNotice(cleaned > 0
        ? `Deleted ${entry.name} and cleaned ${cleaned} catalog record${cleaned === 1 ? '' : 's'}.`
        : `Deleted ${entry.name}.`);
      setSelectedPath('');
      setBrowserRefreshToken((token) => token + 1);
      onRefresh?.();
    } catch (error) {
      setBrowserError(error.message || 'Unable to delete item.');
    } finally {
      setDeleteBusyPath('');
    }
  }

  return (
    <AudioContentScaffold
      title="File Explorer"
      description="Classic browser for the trive-In, trive-Up, and trive-Out roots. Double-click folders to navigate."
    >
      <div className="file-explorer-shell">
        <aside className="file-explorer-sidebar" aria-label="Explorer roots">
          <div className="file-explorer-sidebar-head">Locations</div>
          <ul className="file-explorer-roots">
            {roots.map((root) => (
              <li key={root.key}>
                <button
                  type="button"
                  className={`file-explorer-root${currentRoot === root.key ? ' is-active' : ''}`}
                  onClick={() => {
                    setCurrentRoot(root.key);
                    setCurrentPath('');
                    setSelectedPath('');
                    setBrowserNotice('');
                  }}
                >
                  <FolderGlyph />
                  <span>{root.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="file-explorer-main">
          <div className="file-explorer-toolbar">
            <button
              type="button"
              className="file-explorer-toolbar-button"
              onClick={() => {
                setCurrentPath(browserState?.parent_path || '');
                setSelectedPath('');
                setBrowserNotice('');
              }}
              disabled={!browserState?.parent_path}
            >
              Up
            </button>
            <div className="file-explorer-pathbar" role="navigation" aria-label="Current path">
              {(browserState?.breadcrumbs || [{ label: currentRoot, relative_path: '' }]).map((crumb, index) => (
                <button
                  key={`${crumb.relative_path || 'root'}:${index}`}
                  type="button"
                  className={`file-explorer-path-segment${crumb.relative_path === currentPath ? ' is-active' : ''}`}
                  onClick={() => {
                    setCurrentPath(crumb.relative_path || '');
                    setSelectedPath('');
                    setBrowserNotice('');
                  }}
                >
                  {crumb.label}
                </button>
              ))}
            </div>
            {currentRoot === 'trive-In' ? (
              <div className="file-explorer-upload-actions">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="file-explorer-hidden-input"
                  onChange={uploadFilesFromInput}
                />
                <input
                  ref={folderInputRef}
                  type="file"
                  multiple
                  webkitdirectory=""
                  directory=""
                  className="file-explorer-hidden-input"
                  onChange={uploadFilesFromInput}
                />
                <button
                  type="button"
                  className="file-explorer-toolbar-button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                >
                  Upload Files
                </button>
                <button
                  type="button"
                  className="file-explorer-toolbar-button"
                  onClick={() => folderInputRef.current?.click()}
                  disabled={uploading}
                >
                  Upload Folder
                </button>
              </div>
            ) : null}
          </div>

          {loading || (browserLoading && !browserState) ? <p className="empty-state">Loading file explorer...</p> : null}
          {effectiveError ? <p className="empty-state">{effectiveError}</p> : null}
          {uploading ? <p className="file-explorer-notice">Uploading one file at a time; each file is scanned before placement.</p> : null}
          {browserNotice ? <p className="file-explorer-notice">{browserNotice}</p> : null}
          {uploadQueue.length ? (
            <div className="file-explorer-upload-queue" aria-label="Upload queue">
              {uploadQueue.map((item, index) => {
                const total = Number(item.total) || 0;
                const loaded = Number(item.loaded) || 0;
                const percent = total > 0 ? Math.max(0, Math.min(100, Math.round((loaded / total) * 100))) : 0;
                return (
                  <div key={`${item.name}:${index}`} className={`file-explorer-upload-row is-${item.status}`}>
                    <div className="file-explorer-upload-copy">
                      <span>{item.name}</span>
                      <strong>{formatUploadStatus(item)}</strong>
                    </div>
                    <div className="file-explorer-upload-meter" aria-hidden="true">
                      <span style={{ width: `${item.status === 'complete' ? 100 : percent}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : null}

          {!effectiveError && browserState ? (
            <div className="file-explorer-table-shell">
              <div className="file-explorer-table-head">
                <span>Name</span>
                <span>Modified</span>
                <span>Type</span>
                <span>Size</span>
              </div>
              <div className="file-explorer-table-body">
                {(browserState?.entries || []).map((entry) => {
                  const isDirectory = entry.entry_type === 'directory';
                  return (
                    <button
                      key={entry.relative_path}
                      type="button"
                      className={`file-explorer-row${selectedPath === entry.relative_path ? ' is-selected' : ''}`}
                      onClick={() => {
                        setSelectedPath(entry.relative_path);
                      }}
                      onDoubleClick={() => {
                        if (!isDirectory) {
                          return;
                        }
                        setCurrentPath(entry.relative_path);
                        setSelectedPath('');
                        setBrowserNotice('');
                      }}
                      onContextMenuCapture={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        setSelectedPath(entry.relative_path);
                        setContextMenu({
                          x: event.clientX,
                          y: event.clientY,
                          entry,
                        });
                      }}
                    >
                      <span className="file-explorer-cell is-name">
                        <span className="file-explorer-icon">
                          {isDirectory ? <FolderGlyph /> : <FileGlyph />}
                        </span>
                        <span className="file-explorer-name">{entry.name}</span>
                      </span>
                      <span className="file-explorer-cell">{formatTimestamp(entry.modified_at) || '-'}</span>
                      <span className="file-explorer-cell">{entry.display_type || entry.entry_type}</span>
                      <span className="file-explorer-cell">{formatFileSize(entry.size) || ''}</span>
                    </button>
                  );
                })}
                {!browserState?.entries?.length ? (
                  <div className="file-explorer-empty">This location is empty.</div>
                ) : null}
              </div>
            </div>
          ) : null}
        </section>

        <aside className="file-explorer-preview" aria-label="Selection details">
          <div className="file-explorer-sidebar-head">Selection</div>
          {selectedEntry ? (
            <div className="file-explorer-preview-copy">
              <p><strong>Name</strong><span>{selectedEntry.name}</span></p>
              <p><strong>Path</strong><span>{selectedEntry.relative_path}</span></p>
              <p><strong>Type</strong><span>{selectedEntry.display_type || selectedEntry.entry_type}</span></p>
              {selectedEntry.track_id ? <p><strong>Track</strong><span>{selectedEntry.track_title || selectedEntry.track_id}</span></p> : null}
              <p><strong>Modified</strong><span>{formatTimestamp(selectedEntry.modified_at) || '-'}</span></p>
              <p><strong>Size</strong><span>{formatFileSize(selectedEntry.size) || '-'}</span></p>
              <button
                type="button"
                className="file-explorer-danger-button"
                onClick={() => deleteEntryFromBrowser(selectedEntry)}
                disabled={uploading || Boolean(deleteBusyPath)}
              >
                {deleteBusyPath === selectedEntry.relative_path ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          ) : (
            <p className="file-explorer-empty">Select a file or folder.</p>
          )}
        </aside>
      </div>
      {contextMenu ? (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          items={contextMenu.entry.entry_type === 'directory' ? [
            {
              key: 'metadata',
              label: 'Metadata',
              onSelect: () => openMetadataForFolder(contextMenu.entry),
            },
            {
              key: 'artist-from-folder-name',
              label: 'Artist From Folder Name',
              onSelect: () => assignArtistFromFolder(contextMenu.entry),
            },
            {
              key: 'open-folder',
              label: 'Open Folder',
              onSelect: () => {
                setCurrentPath(contextMenu.entry.relative_path);
                setSelectedPath('');
                setBrowserNotice('');
              },
            },
            {
              key: 'delete',
              label: deleteBusyPath === contextMenu.entry.relative_path ? 'Deleting...' : 'Delete',
              disabled: uploading || Boolean(deleteBusyPath),
              onSelect: () => deleteEntryFromBrowser(contextMenu.entry),
            },
          ] : [
            {
              key: 'metadata',
              label: 'Metadata',
              onSelect: () => openMetadataForEntry(contextMenu.entry),
            },
            {
              key: 'delete',
              label: deleteBusyPath === contextMenu.entry.relative_path ? 'Deleting...' : 'Delete',
              disabled: uploading || Boolean(deleteBusyPath),
              onSelect: () => deleteEntryFromBrowser(contextMenu.entry),
            },
          ]}
        />
      ) : null}
      {metadataEntry ? (
        <MediaFileMetadataEditorModal
          mediaFileId={metadataEntry.media_file_id}
          fileEntry={metadataEntry}
          onClose={() => setMetadataEntry(null)}
        />
      ) : null}
      {metadataTrack ? (
        <TrackMetadataEditorModal
          track={metadataTrack}
          onClose={() => setMetadataTrack(null)}
        />
      ) : null}
      {folderMetadataSelection ? (
        <MultiTrackMetadataEditorModal
          tracks={folderMetadataSelection.tracks}
          title={folderMetadataSelection.truncated
            ? `${folderMetadataSelection.title} (${folderMetadataSelection.tracks.length} / ${folderMetadataSelection.trackCount})`
            : folderMetadataSelection.title}
          kicker="Folder Metadata"
          onClose={() => setFolderMetadataSelection(null)}
        />
      ) : null}
    </AudioContentScaffold>
  );
}
