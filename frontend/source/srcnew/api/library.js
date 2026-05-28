import { getJson, unpackPaginated, writeFormData, writeJson } from './client';

export const TRACKS_PAGE_SIZE = 50;
export const VIDEOS_PAGE_SIZE = 50;
export const VIDEO_SERIES_PAGE_SIZE = 36;
export const ALBUMS_PAGE_SIZE = 24;
export const ARTISTS_PAGE_SIZE = 50;
export const SOURCE_FOLDERS_PAGE_SIZE = 40;

function normalizeTagFilter(tagFilter = '') {
  if (!tagFilter) {
    return { include: [], exclude: [] };
  }
  if (Array.isArray(tagFilter)) {
    return { include: tagFilter.filter(Boolean), exclude: [] };
  }
  if (typeof tagFilter === 'object') {
    return {
      include: Array.isArray(tagFilter.include) ? tagFilter.include.filter(Boolean) : [],
      exclude: Array.isArray(tagFilter.exclude) ? tagFilter.exclude.filter(Boolean) : [],
    };
  }
  return { include: [tagFilter].filter(Boolean), exclude: [] };
}

function appendTagFilters(params, tagFilter = '') {
  const normalized = normalizeTagFilter(tagFilter);
  normalized.include.forEach((value) => params.append('tag_filter', value));
  normalized.exclude.forEach((value) => params.append('exclude_tag_filter', value));
}

function normalizePaginatedPath(path) {
  if (!path) {
    return null;
  }
  try {
    const parsed = new URL(path, window.location.origin);
    if (parsed.origin === window.location.origin || parsed.hostname === window.location.hostname) {
      return `${window.location.origin}${parsed.pathname}${parsed.search}`;
    }
    return parsed.toString();
  } catch (_error) {
    return path;
  }
}

async function fetchAllPages(basePath, fallbackMessage) {
  let nextPath = normalizePaginatedPath(basePath);
  const items = [];

  while (nextPath) {
    const payload = await getJson(nextPath, fallbackMessage);
    const unpacked = unpackPaginated(payload);
    items.push(...unpacked.items);
    nextPath = normalizePaginatedPath(unpacked.next);
  }

  return items;
}

export async function fetchLatestJob() {
  try {
    return await getJson('/api/scan-jobs/latest/', 'Unable to read current scan job');
  } catch (error) {
    if (String(error.message || '').includes('[404]')) {
      return null;
    }
    throw error;
  }
}

export async function fetchLatestDigestJob() {
  try {
    return await getJson('/api/digest-jobs/latest/', 'Unable to read current trive-up job');
  } catch (error) {
    if (String(error.message || '').includes('[404]')) {
      return null;
    }
    throw error;
  }
}

export async function resolveLibraryId() {
  const [latestJob, latestDigestJob] = await Promise.all([
    fetchLatestJob(),
    fetchLatestDigestJob(),
  ]);
  return latestDigestJob?.library || latestJob?.library || null;
}

export async function fetchTracks(libraryId, page = 1, searchTerm = '', jumpKey = '', tagFilter = '') {
  const params = new URLSearchParams({
    library: String(libraryId),
    ordering: 'canonical_title',
    page: String(page),
    page_size: String(TRACKS_PAGE_SIZE),
  });
  if (searchTerm.trim()) {
    params.set('search', searchTerm.trim());
  }
  if (jumpKey) {
    params.set('starts_with', jumpKey);
  }
  appendTagFilters(params, tagFilter);

  const payload = await getJson(`/api/tracks/?${params.toString()}`, 'Unable to read track list');
  return unpackPaginated(payload);
}

export async function fetchTrackById(trackId) {
  return getJson(`/api/tracks/${trackId}/`, 'Unable to read track detail');
}

export async function fetchVideos(libraryId, page = 1, searchTerm = '', jumpKey = '', tagFilter = '') {
  const params = new URLSearchParams({
    library: String(libraryId),
    ordering: 'canonical_title',
    page: String(page),
    page_size: String(VIDEOS_PAGE_SIZE),
  });
  if (searchTerm.trim()) {
    params.set('search', searchTerm.trim());
  }
  if (jumpKey) {
    params.set('starts_with', jumpKey);
  }
  appendTagFilters(params, tagFilter);

  const payload = await getJson(`/api/videos/?${params.toString()}`, 'Unable to load video items');
  return unpackPaginated(payload);
}

export async function fetchVideoSeriesGroups(libraryId, page = 1, searchTerm = '', jumpKey = '', tagFilter = '', curationQuery = {}) {
  const params = new URLSearchParams({
    library: String(libraryId),
    page: String(page),
    page_size: String(VIDEO_SERIES_PAGE_SIZE),
  });
  if (searchTerm.trim()) {
    params.set('search', searchTerm.trim());
  }
  if (jumpKey) {
    params.set('starts_with', jumpKey);
  }
  if (curationQuery?.curation_system) {
    params.set('curation_system', curationQuery.curation_system);
  }
  if (curationQuery?.tag_value) {
    params.set('tag_value', String(curationQuery.tag_value));
  }
  appendTagFilters(params, tagFilter);

  const payload = await getJson(`/api/videos/series-groups/?${params.toString()}`, 'Unable to read video series');
  return unpackPaginated(payload);
}

export async function fetchVideoSeriesGroupsFromPath(path) {
  const payload = await getJson(normalizePaginatedPath(path), 'Unable to read video series');
  return unpackPaginated(payload);
}

export async function fetchVideoSeriesTracks(libraryId, seriesKey) {
  const params = new URLSearchParams({
    library: String(libraryId),
    series_key: String(seriesKey || ''),
  });
  const payload = await getJson(`/api/videos/series-tracks/?${params.toString()}`, 'Unable to read series episodes');
  return Array.isArray(payload) ? payload : [];
}

export async function fetchVideoPosterCandidates(trackId, count = 6) {
  const params = new URLSearchParams({ count: String(count) });
  return getJson(`/api/tracks/${trackId}/poster/candidates/?${params.toString()}`, 'Unable to read video frames');
}

export async function selectVideoPosterFrame(trackId, seconds) {
  return writeJson(`/api/tracks/${trackId}/poster/select/`, 'POST', { seconds }, 'Unable to select video poster');
}

export async function selectVideoSeriesPosterFrame(seriesKey, trackId, seconds) {
  return writeJson(
    '/api/videos/series-poster/',
    'POST',
    { series_key: seriesKey, track_id: trackId, seconds },
    'Unable to select series poster',
  );
}

export async function fetchAllVideos(libraryId, searchTerm = '') {
  if (!libraryId) {
    return [];
  }
  const params = new URLSearchParams({
    library: String(libraryId),
    ordering: '-created_at',
    page: '1',
    page_size: '200',
  });
  if (searchTerm.trim()) {
    params.set('search', searchTerm.trim());
  }
  return fetchAllPages(`/api/videos/?${params.toString()}`, 'Unable to load video items');
}

export async function fetchAllTracks(libraryId, searchTerm = '') {
  if (!libraryId) {
    return [];
  }
  const params = new URLSearchParams({
    library: String(libraryId),
    ordering: 'canonical_title',
    page: '1',
    page_size: '200',
  });
  if (searchTerm.trim()) {
    params.set('search', searchTerm.trim());
  }
  return fetchAllPages(`/api/tracks/?${params.toString()}`, 'Unable to load tracks');
}

export async function fetchAlbums(libraryId, page = 1, searchTerm = '', jumpKey = '', tagFilter = '') {
  const params = new URLSearchParams({
    library: String(libraryId),
    media_kind: 'audio',
    ordering: 'title',
    page: String(page),
    page_size: String(ALBUMS_PAGE_SIZE),
  });
  if (searchTerm.trim()) {
    params.set('search', searchTerm.trim());
  }
  if (jumpKey) {
    params.set('starts_with', jumpKey);
  }
  appendTagFilters(params, tagFilter);

  const payload = await getJson(`/api/albums/?${params.toString()}`, 'Unable to read album list');
  return unpackPaginated(payload);
}

export async function fetchAlbumTracks(libraryId, albumId) {
  const params = new URLSearchParams({
    library: String(libraryId),
    album: String(albumId),
    ordering: 'disc_number,track_number',
    page: '1',
    page_size: '200',
  });
  const payload = await getJson(`/api/tracks/?${params.toString()}`, 'Unable to read album tracklist');
  return unpackPaginated(payload).items;
}

export async function fetchArtists(libraryId, page = 1, searchTerm = '', jumpKey = '', artistRole = 'all', tagFilter = '') {
  const params = new URLSearchParams({
    library: String(libraryId),
    ordering: 'name',
    page: String(page),
    page_size: String(ARTISTS_PAGE_SIZE),
  });
  if (searchTerm.trim()) {
    params.set('search', searchTerm.trim());
  }
  if (jumpKey) {
    params.set('starts_with', jumpKey);
  }
  const artistRoles = Array.isArray(artistRole) ? artistRole : [artistRole];
  artistRoles
    .filter((role) => role && role !== 'all')
    .forEach((role) => params.append('role', role));
  appendTagFilters(params, tagFilter);

  const payload = await getJson(`/api/artists/?${params.toString()}`, 'Unable to read artist list');
  return unpackPaginated(payload);
}

export async function fetchAllArtists(libraryId, searchTerm = '') {
  if (!libraryId) {
    return [];
  }
  const params = new URLSearchParams({
    library: String(libraryId),
    ordering: 'name',
    page: '1',
    page_size: '200',
  });
  if (searchTerm.trim()) {
    params.set('search', searchTerm.trim());
  }
  return fetchAllPages(`/api/artists/?${params.toString()}`, 'Unable to load artists');
}

export async function fetchArtistById(artistId) {
  return getJson(`/api/artists/${artistId}/`, 'Unable to read artist detail');
}

export async function updateArtist(artistId, payload) {
  return writeJson(`/api/artists/${artistId}/`, 'PATCH', payload, 'Unable to update artist');
}

export async function fetchArtistCoverCandidates(artistId, libraryId) {
  const params = new URLSearchParams();
  if (libraryId) {
    params.set('library', String(libraryId));
  }
  const suffix = params.toString() ? `?${params.toString()}` : '';
  return getJson(`/api/artists/${artistId}/cover-candidates/${suffix}`, 'Unable to read artist images');
}

export async function selectArtistCover(artistId, selection) {
  return writeJson(`/api/artists/${artistId}/cover-selection/`, 'PATCH', selection, 'Unable to select artist image');
}

export async function uploadArtistProfileImage(artistId, file) {
  const formData = new FormData();
  formData.set('image', file);
  return writeFormData(`/api/artists/${artistId}/profile-image/`, 'POST', formData, 'Unable to upload artist image');
}

export async function fetchArtistBioSuggestion(artistId, language = 'it') {
  return writeJson(`/api/artists/${artistId}/bio-suggestion/`, 'POST', { language }, 'Unable to generate artist bio');
}

export async function fetchArtistByName(libraryId, artistName) {
  const params = new URLSearchParams({
    library: String(libraryId),
    search: String(artistName || ''),
    ordering: 'name',
    page: '1',
    page_size: '20',
  });
  const payload = await getJson(`/api/artists/?${params.toString()}`, 'Unable to search artist');
  const items = unpackPaginated(payload).items || [];
  const normalizedName = String(artistName || '').toLowerCase();
  return items.find((entry) => entry.name?.toLowerCase() === normalizedName) || items[0] || null;
}

export async function fetchArtistTracks(libraryId, artistId) {
  const params = new URLSearchParams({
    library: String(libraryId),
    artist: String(artistId),
    ordering: 'canonical_title',
    page: '1',
    page_size: '500',
  });
  const payload = await getJson(`/api/tracks/?${params.toString()}`, 'Unable to read artist tracklist');
  return unpackPaginated(payload).items;
}

export async function fetchAllAlbums(libraryId, searchTerm = '') {
  if (!libraryId) {
    return [];
  }
  const params = new URLSearchParams({
    library: String(libraryId),
    ordering: 'title',
    page: '1',
    page_size: '200',
  });
  if (searchTerm.trim()) {
    params.set('search', searchTerm.trim());
  }
  return fetchAllPages(`/api/albums/?${params.toString()}`, 'Unable to load albums');
}

export async function fetchTrackWaveform(track) {
  if (!track?.waveform_url) {
    return [];
  }
  const params = new URLSearchParams({ level: '16384' });
  const payload = await getJson(`${track.waveform_url}?${params.toString()}`, 'Unable to read waveform');
  return payload.points || [];
}

export async function fetchSourceFolders(libraryId, page = 1, jumpKey = '') {
  const params = new URLSearchParams({
    library: String(libraryId),
    ordering: 'relative_path',
    page: String(page),
    page_size: String(SOURCE_FOLDERS_PAGE_SIZE),
  });
  if (jumpKey) {
    params.set('starts_with', jumpKey);
  }

  const payload = await getJson(`/api/source-folders/?${params.toString()}`, 'Unable to read library source folder list');
  return unpackPaginated(payload);
}

export async function fetchQuickSearch(libraryId, query, scope = 'all') {
  if (!libraryId || String(query || '').trim().length < 2) {
    return [];
  }
  const params = new URLSearchParams({
    library: String(libraryId),
    q: String(query).trim(),
    scope,
    limit: '8',
  });
  const payload = await getJson(`/api/quick-search/?${params.toString()}`, 'Quick search failed');
  return payload.results || [];
}
