import { useEffect, useState } from 'react';
import {
  ALBUMS_PAGE_SIZE,
  ARTISTS_PAGE_SIZE,
  SOURCE_FOLDERS_PAGE_SIZE,
  TRACKS_PAGE_SIZE,
  VIDEO_SERIES_PAGE_SIZE,
  fetchAlbums,
  fetchArtists,
  fetchQuickSearch,
  fetchSourceFolders,
  fetchTracks,
  fetchVideoSeriesGroupsFromPath,
  fetchVideoSeriesGroups,
  resolveLibraryId,
} from '../api/library';
import { fetchTagDefinitions, fetchTagValues, fetchVideoCurationSettings, tagFilterValue } from '../api/tags';

const TAG_SELECTION_STORAGE_PREFIX = 'triver.audioContent.tagSelection.';

function scopeForView(currentView) {
  if (currentView === 'albums') {
    return 'album';
  }
  if (currentView === 'artists') {
    return 'artist';
  }
  if (currentView === 'tracks' || currentView === 'videos') {
    return 'track';
  }
  return '';
}

function tagDefinitionKeysForView(currentView) {
  if (currentView === 'tracks') {
    return new Set(['audio-tag']);
  }
  if (currentView === 'videos') {
    return new Set(['video-tag']);
  }
  return null;
}

function readStoredTagSelection(currentView) {
  if (typeof window === 'undefined' || !window.localStorage) {
    return null;
  }
  try {
    const rawValue = window.localStorage.getItem(`${TAG_SELECTION_STORAGE_PREFIX}${currentView}`);
    if (rawValue === null) {
      return null;
    }
    const parsedValue = JSON.parse(rawValue);
    return Array.isArray(parsedValue) ? parsedValue.filter(Boolean) : null;
  } catch (_error) {
    return null;
  }
}

function writeStoredTagSelection(currentView, selection) {
  if (typeof window === 'undefined' || !window.localStorage) {
    return;
  }
  try {
    if (selection === null) {
      window.localStorage.removeItem(`${TAG_SELECTION_STORAGE_PREFIX}${currentView}`);
      return;
    }
    window.localStorage.setItem(`${TAG_SELECTION_STORAGE_PREFIX}${currentView}`, JSON.stringify(Array.isArray(selection) ? selection : []));
  } catch (_error) {
    // Ignore storage errors; the in-memory selection still works for this session.
  }
}

function mergeById(currentItems = [], nextItems = []) {
  const merged = new Map();
  currentItems.forEach((item) => merged.set(item.id, item));
  nextItems.forEach((item) => merged.set(item.id, item));
  return Array.from(merged.values());
}

function pageConfig(page, pageSize, totalCount, visibleCount, onPageChange) {
  return {
    page,
    pageSize,
    totalCount,
    visibleCount,
    hasMore: visibleCount < totalCount,
    onPageChange,
    onLoadMore: () => onPageChange((current) => current + 1),
  };
}

export default function useAudioLibraryData(currentView) {
  const [libraryId, setLibraryId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [activeJumpKey, setActiveJumpKey] = useState('');
  const [artistRoleFilter, setArtistRoleFilter] = useState(['all']);
  const [selectedTagKeys, setSelectedTagKeysState] = useState(() => readStoredTagSelection(currentView));
  const [tagOptions, setTagOptions] = useState([]);
  const [quickSearchResults, setQuickSearchResults] = useState([]);
  const [trackPage, setTrackPage] = useState(1);
  const [videoPage, setVideoPage] = useState(1);
  const [albumPage, setAlbumPage] = useState(1);
  const [artistPage, setArtistPage] = useState(1);
  const [sourceFolderPage, setSourceFolderPage] = useState(1);
  const [refreshTick, setRefreshTick] = useState(0);
  const [tracks, setTracks] = useState([]);
  const [videos, setVideos] = useState([]);
  const [videoSeriesGroups, setVideoSeriesGroups] = useState([]);
  const [videoCurationRows, setVideoCurationRows] = useState([]);
  const [albums, setAlbums] = useState([]);
  const [artists, setArtists] = useState([]);
  const [sourceFolders, setSourceFolders] = useState([]);
  const [trackTotalCount, setTrackTotalCount] = useState(0);
  const [videoTotalCount, setVideoTotalCount] = useState(0);
  const [albumTotalCount, setAlbumTotalCount] = useState(0);
  const [artistTotalCount, setArtistTotalCount] = useState(0);
  const [sourceFolderTotalCount, setSourceFolderTotalCount] = useState(0);

  function setSelectedTagKeys(nextSelection) {
    setSelectedTagKeysState((currentSelection) => {
      const resolvedSelection = typeof nextSelection === 'function'
        ? nextSelection(currentSelection)
        : nextSelection;
      writeStoredTagSelection(currentView, resolvedSelection);
      return resolvedSelection;
    });
  }

  useEffect(() => {
    let mounted = true;

    resolveLibraryId()
      .then((nextLibraryId) => {
        if (!mounted) {
          return;
        }
        setLibraryId(nextLibraryId);
      })
      .catch((error) => {
        if (mounted) {
          setPageError(error.message);
        }
      });

    return () => {
      mounted = false;
    };
  }, [currentView, refreshTick]);

  const activeTagFilter = (() => {
    const optionValues = tagOptions.map((option) => option.value).filter(Boolean);
    if (!optionValues.length || selectedTagKeys === null) {
      return { include: [], exclude: [] };
    }
    const selectedValues = Array.isArray(selectedTagKeys) ? selectedTagKeys : [];
    const selectedSet = new Set(selectedValues);
    if (selectedSet.size >= optionValues.length && optionValues.every((value) => selectedSet.has(value))) {
      return { include: [], exclude: [] };
    }
    return {
      include: optionValues.filter((value) => selectedSet.has(value)),
      exclude: optionValues.filter((value) => !selectedSet.has(value)),
    };
  })();

  useEffect(() => {
    if (currentView === 'tracks') {
      setTrackPage(1);
    } else if (currentView === 'videos' || currentView === 'video-curation') {
      setVideoPage(1);
    } else if (currentView === 'albums') {
      setAlbumPage(1);
    } else if (currentView === 'artists') {
      setArtistPage(1);
    } else if (currentView === 'source-folders') {
      setSourceFolderPage(1);
    }
  }, [currentView, searchTerm, activeJumpKey, artistRoleFilter, selectedTagKeys]);

  useEffect(() => {
    setSelectedTagKeysState(readStoredTagSelection(currentView));
  }, [currentView]);

  useEffect(() => {
    const scope = scopeForView(currentView);
    if (!scope) {
      setTagOptions([]);
      return undefined;
    }
    let cancelled = false;
    fetchTagDefinitions({ scope })
      .then(async (definitions) => {
        const allowedKeys = tagDefinitionKeysForView(currentView);
        const visibleDefinitions = allowedKeys
          ? definitions.filter((definition) => allowedKeys.has(definition.key))
          : definitions;
        const valueGroups = await Promise.all(visibleDefinitions.map(async (definition) => ({
          definition,
          values: await fetchTagValues(definition.id),
        })));
        if (!cancelled) {
          const nextOptions = valueGroups.flatMap(({ definition, values }) => (
            values.map((value) => ({
              value: tagFilterValue(definition.key, value.normalized_key || value.value_text, value.id),
              label: `${definition.label || definition.key}: ${value.value_text}`,
            }))
          ));
          const nextValues = nextOptions.map((option) => option.value).filter(Boolean);
          const nextValueSet = new Set(nextValues);
          const previousValues = tagOptions.map((option) => option.value).filter(Boolean);
          setTagOptions(nextOptions);
          setSelectedTagKeys((current) => {
            if (current === null) {
              return null;
            }
            const currentValues = Array.isArray(current) ? current : [];
            const currentSet = new Set(currentValues);
            const hadAllSelected = previousValues.length > 0
              && previousValues.every((value) => currentSet.has(value));
            if (hadAllSelected) {
              return nextValues;
            }
            return currentValues
              .filter((value) => nextValueSet.has(value));
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTagOptions([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [currentView, refreshTick]);

  useEffect(() => {
    if (!libraryId || searchTerm.trim().length < 2) {
      setQuickSearchResults([]);
      return undefined;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const scope = ['tracks', 'albums', 'artists', 'videos'].includes(currentView)
          ? currentView
          : 'all';
        const results = await fetchQuickSearch(libraryId, searchTerm, scope);
        if (!controller.signal.aborted) {
          setQuickSearchResults(results);
        }
      } catch (_error) {
        if (!controller.signal.aborted) {
          setQuickSearchResults([]);
        }
      }
    }, 160);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [currentView, libraryId, searchTerm]);

  useEffect(() => {
    if (!libraryId) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setPageError('');

    async function run() {
      try {
        if (currentView === 'tracks') {
          const parsed = await fetchTracks(libraryId, trackPage, searchTerm, activeJumpKey, activeTagFilter);
          if (!cancelled) {
            setTracks((current) => (trackPage > 1 ? mergeById(current, parsed.items) : parsed.items));
            setTrackTotalCount(parsed.count);
          }
        } else if (currentView === 'videos') {
          const curationSettings = await fetchVideoCurationSettings();
          const visibleRows = Array.isArray(curationSettings?.rows) ? curationSettings.rows : [];
          const rowPayloads = await Promise.all(visibleRows.map(async (row) => {
            const parsed = await fetchVideoSeriesGroups(libraryId, 1, searchTerm, activeJumpKey, activeTagFilter, row.query || {});
            return {
              ...row,
              groups: parsed.items,
              count: parsed.count,
              next: parsed.next,
            };
          }));
          if (!cancelled) {
            setVideoCurationRows(rowPayloads.filter((row) => row.groups.length || row.count > 0));
            setVideoSeriesGroups(rowPayloads.flatMap((row) => row.groups));
            setVideoTotalCount(rowPayloads.reduce((total, row) => total + (Number(row.count) || 0), 0));
          }
        } else if (currentView === 'albums') {
          const parsed = await fetchAlbums(libraryId, albumPage, searchTerm, activeJumpKey, activeTagFilter);
          if (!cancelled) {
            setAlbums((current) => (albumPage > 1 ? mergeById(current, parsed.items) : parsed.items));
            setAlbumTotalCount(parsed.count);
          }
        } else if (currentView === 'artists') {
          const parsed = await fetchArtists(libraryId, artistPage, searchTerm, activeJumpKey, artistRoleFilter, activeTagFilter);
          if (!cancelled) {
            setArtists((current) => (artistPage > 1 ? mergeById(current, parsed.items) : parsed.items));
            setArtistTotalCount(parsed.count);
          }
        } else if (currentView === 'source-folders') {
          if (!cancelled) {
            setSourceFolders([]);
            setSourceFolderTotalCount(0);
          }
        }
      } catch (error) {
        if (!cancelled) {
          setPageError(error.message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    run();

    return () => {
      cancelled = true;
    };
  }, [currentView, libraryId, trackPage, videoPage, albumPage, artistPage, sourceFolderPage, searchTerm, activeJumpKey, artistRoleFilter, selectedTagKeys, tagOptions, refreshTick]);

  function getPaginationConfig() {
    if (currentView === 'tracks') {
      return pageConfig(trackPage, TRACKS_PAGE_SIZE, trackTotalCount, tracks.length, setTrackPage);
    }
    if (currentView === 'videos') {
      return {
        page: 1,
        pageSize: VIDEO_SERIES_PAGE_SIZE,
        totalCount: videoTotalCount,
        visibleCount: videoCurationRows.reduce((total, row) => total + row.groups.length, 0),
        hasMore: false,
        onPageChange: () => {},
      };
    }
    if (currentView === 'video-curation') {
      return { page: 1, pageSize: 1, totalCount: 1, onPageChange: () => {} };
    }
    if (currentView === 'albums') {
      return pageConfig(albumPage, ALBUMS_PAGE_SIZE, albumTotalCount, albums.length, setAlbumPage);
    }
    if (currentView === 'artists') {
      return pageConfig(artistPage, ARTISTS_PAGE_SIZE, artistTotalCount, artists.length, setArtistPage);
    }
    if (currentView === 'source-folders') {
      return { page: 1, pageSize: SOURCE_FOLDERS_PAGE_SIZE, totalCount: sourceFolderTotalCount, onPageChange: () => {} };
    }
    return { page: 1, pageSize: 1, totalCount: 1, onPageChange: () => {} };
  }

  return {
    libraryId,
    loading,
    pageError,
    searchTerm,
    setSearchTerm,
    activeJumpKey,
    setActiveJumpKey,
    artistRoleFilter,
    setArtistRoleFilter,
    selectedTagKeys: Array.isArray(selectedTagKeys)
      ? selectedTagKeys
      : null,
    setSelectedTagKeys,
    tagDefinitions: tagOptions,
    quickSearchResults,
    pagination: getPaginationConfig(),
    data: {
      tracks,
      videos,
      videoSeriesGroups,
      videoCurationRows,
      albums,
      artists,
      sourceFolders,
    },
    refreshToken: refreshTick,
    refreshCurrent() {
      setRefreshTick((current) => current + 1);
    },
    refreshGlobal() {
      setSearchTerm('');
      setActiveJumpKey('');
      setArtistRoleFilter(['all']);
      setSelectedTagKeys(null);
      setTrackPage(1);
      setVideoPage(1);
      setAlbumPage(1);
      setArtistPage(1);
      setSourceFolderPage(1);
      setRefreshTick((current) => current + 1);
    },
    async loadMoreVideoRow(rowId) {
      const row = videoCurationRows.find((entry) => entry.id === rowId);
      if (!row?.next) {
        return;
      }
      const parsed = await fetchVideoSeriesGroupsFromPath(row.next);
      setVideoCurationRows((currentRows) => currentRows.map((entry) => (
        entry.id === rowId
          ? {
              ...entry,
              groups: mergeById(entry.groups, parsed.items),
              count: parsed.count,
              next: parsed.next,
            }
          : entry
      )));
      setVideoSeriesGroups((current) => mergeById(current, parsed.items));
    },
  };
}
