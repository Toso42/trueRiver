import { getCookie, getJson, readJsonResponse, unpackPaginated, writeJson } from './client';

export async function fetchMetadataModel() {
  const [fieldsPayload, rulesPayload, groupsPayload] = await Promise.all([
    getJson('/api/meta-fields/?ordering=name&page=1&page_size=200', 'Unable to read trueRiver metadata fields'),
    getJson('/api/meta-normalization-rules/?ordering=source_family,source_name&page=1&page_size=500', 'Unable to read normalization rules'),
    getJson('/api/meta-fields/search_groups/', 'Unable to read metadata search groups'),
  ]);

  return {
    fields: unpackPaginated(fieldsPayload).items,
    rules: unpackPaginated(rulesPayload).items,
    searchGroups: groupsPayload || {},
  };
}

export async function fetchMetadataValueSuggestions(field, query = '', limit = 10) {
  const params = new URLSearchParams();
  params.set('field', field || '');
  if (String(query || '').trim()) {
    params.set('q', String(query).trim());
  }
  params.set('limit', String(limit));
  const payload = await getJson(
    `/api/meta-fields/value-suggestions/?${params.toString()}`,
    'Unable to read metadata suggestions',
  );
  return payload.suggestions || [];
}

export async function fetchMediaFile(primaryFileId) {
  return getJson(`/api/media-files/${primaryFileId}/`, 'Unable to read media file metadata');
}

export async function patchMediaFileMetadata(primaryFileId, field, values = []) {
  await fetch('/api/getcsrf/', { credentials: 'include' });
  const response = await fetch(`/api/media-files/${primaryFileId}/metadata/`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify({
      metadata: {
        [field]: values.map((value) => String(value || '').trim()).filter(Boolean),
      },
    }),
  });
  return readJsonResponse(response, 'Metadata update failed');
}

export async function fetchAlbumMetadata(albumId) {
  return getJson(`/api/albums/${albumId}/metadata/`, 'Unable to read album metadata');
}

export async function patchAlbumMetadata(albumId, field, values = []) {
  await fetch('/api/getcsrf/', { credentials: 'include' });
  const response = await fetch(`/api/albums/${albumId}/metadata/`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify({
      metadata: {
        [field]: values.map((value) => String(value || '').trim()).filter(Boolean),
      },
    }),
  });
  return readJsonResponse(response, 'Album metadata update failed');
}

export async function mergeAlbums({ albumIds = [], targetTitle = '', releaseDateResolution = undefined }) {
  await fetch('/api/getcsrf/', { credentials: 'include' });
  const body = {
    album_ids: albumIds.map((albumId) => String(albumId || '').trim()).filter(Boolean),
    target_title: String(targetTitle || '').trim(),
  };
  if (releaseDateResolution !== undefined) {
    body.release_date_resolution = releaseDateResolution;
  }
  const response = await fetch('/api/albums/merge/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify(body),
  });
  const rawBody = await response.text();
  const payload = rawBody ? JSON.parse(rawBody) : {};
  if (!response.ok) {
    const error = new Error(payload.message || payload.detail || `Album merge failed [${response.status}]`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export function previewTrackAutoMetadata(trackIds = []) {
  return writeJson('/api/tracks/auto-metadata-preview/', 'POST', {
    track_ids: trackIds.map((trackId) => String(trackId || '').trim()).filter(Boolean),
  }, 'Unable to prepare auto metadata');
}

export function applyTrackAutoMetadata(items = []) {
  return writeJson('/api/tracks/auto-metadata-apply/', 'POST', { items }, 'Unable to apply auto metadata');
}

export function fetchRemoteMetadataSettings() {
  return getJson('/api/remote-metadata-settings/current/', 'Unable to read remote metadata settings');
}

export function updateRemoteMetadataSettings(settings = {}) {
  return writeJson(
    '/api/remote-metadata-settings/current/',
    'PATCH',
    settings,
    'Unable to update remote metadata settings',
  );
}

export function startRemoteMetadataPreview({ trackIds = [], mode = 'find', providerKey = '', overwritePolicy = '' } = {}) {
  return writeJson('/api/metadata-enrichment-jobs/preview/', 'POST', {
    track_ids: trackIds.map((trackId) => String(trackId || '').trim()).filter(Boolean),
    mode,
    provider_key: providerKey,
    overwrite_policy: overwritePolicy,
  }, 'Unable to start remote metadata lookup');
}

export function fetchRemoteMetadataJob(jobId) {
  return getJson(`/api/metadata-enrichment-jobs/${jobId}/`, 'Unable to read remote metadata job');
}

export function applyRemoteMetadataJob(jobId, items = []) {
  return writeJson(
    `/api/metadata-enrichment-jobs/${jobId}/apply/`,
    'POST',
    { items },
    'Unable to apply remote metadata',
  );
}
