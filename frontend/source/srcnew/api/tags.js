import { getJson, unpackPaginated, writeJson } from './client';

function normalizeTagKey(value = '') {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export async function fetchTagDefinitions({ scope = '', visibility = '' } = {}) {
  const params = new URLSearchParams({
    ordering: 'scope,key',
    page: '1',
    page_size: '200',
  });
  if (scope) {
    params.set('scope', scope);
  }
  if (visibility) {
    params.set('visibility', visibility);
  }
  const payload = await getJson(`/api/tag-definitions/?${params.toString()}`, 'Unable to read tags');
  return unpackPaginated(payload).items;
}

export function createTagDefinition(payload) {
  return writeJson('/api/tag-definitions/', 'POST', payload, 'Unable to create tag');
}

export function patchTagValue(tagValueId, payload) {
  return writeJson(`/api/tag-values/${tagValueId}/`, 'PATCH', payload, 'Unable to update tag');
}

export function fetchVideoCurationSettings() {
  return getJson('/api/video-curation/current/', 'Unable to read video curation');
}

export function updateVideoCurationSettings(payload) {
  return writeJson('/api/video-curation/current/', 'PATCH', payload, 'Unable to update video curation');
}

export async function fetchTagValues(definitionId) {
  const params = new URLSearchParams({
    definition: String(definitionId),
    ordering: 'display_order,value_text',
    page: '1',
    page_size: '500',
  });
  const payload = await getJson(`/api/tag-values/?${params.toString()}`, 'Unable to read tag values');
  return unpackPaginated(payload).items;
}

export async function ensureTagValue({ definitionId, valueText, existingValues = [], displayOrder = 0 }) {
  const normalizedKey = normalizeTagKey(valueText);
  const existing = existingValues.find((value) => (
    String(value.definition) === String(definitionId)
    && String(value.normalized_key || normalizeTagKey(value.value_text)) === normalizedKey
  ));
  if (existing) {
    return existing;
  }
  return writeJson('/api/tag-values/', 'POST', {
    definition: definitionId,
    value_text: valueText,
    normalized_key: normalizedKey,
    display_order: displayOrder,
  }, 'Unable to create tag value');
}

export async function ensureCoreTrackTagDefinitions() {
  const definitions = await fetchTagDefinitions({ scope: 'track' });
  let audioTagDefinition = definitions.find((definition) => definition.key === 'audio-tag');
  let videoTagDefinition = definitions.find((definition) => definition.key === 'video-tag');

  if (!audioTagDefinition) {
    audioTagDefinition = await createTagDefinition({
      scope: 'track',
      key: 'audio-tag',
      label: 'Audio Tag',
      value_type: 'text',
      allow_multiple: true,
      visibility: 'global',
      description: 'Global audio-facing custom category.',
    });
  }
  if (!videoTagDefinition) {
    videoTagDefinition = await createTagDefinition({
      scope: 'track',
      key: 'video-tag',
      label: 'Video Tag',
      value_type: 'text',
      allow_multiple: true,
      visibility: 'global',
      description: 'Global video-facing custom category.',
    });
  }

  return { audioTagDefinition, videoTagDefinition };
}

export async function ensureCoreTagDefinitions(scope = 'track') {
  if (scope === 'track') {
    const { audioTagDefinition, videoTagDefinition } = await ensureCoreTrackTagDefinitions();
    return [
      { key: 'audio', definition: audioTagDefinition },
      { key: 'video', definition: videoTagDefinition },
    ];
  }

  const definitions = await fetchTagDefinitions({ scope });
  const key = `${scope}-tag`;
  let definition = definitions.find((entry) => entry.key === key);
  if (!definition) {
    definition = await createTagDefinition({
      scope,
      key,
      label: `${scope.slice(0, 1).toUpperCase()}${scope.slice(1)} Tag`,
      value_type: 'text',
      allow_multiple: true,
      visibility: 'global',
      description: `Global ${scope} category.`,
    });
  }
  return [{ key: scope, definition }];
}

const assignmentEndpoints = {
  track: {
    list: '/api/track-tags/',
    detail: (id) => `/api/track-tags/${id}/`,
    targetField: 'track',
  },
  album: {
    list: '/api/album-tags/',
    detail: (id) => `/api/album-tags/${id}/`,
    targetField: 'album',
  },
  artist: {
    list: '/api/artist-tags/',
    detail: (id) => `/api/artist-tags/${id}/`,
    targetField: 'artist',
  },
};

function endpointForScope(scope) {
  const endpoint = assignmentEndpoints[scope];
  if (!endpoint) {
    throw new Error(`Unsupported tag scope: ${scope}`);
  }
  return endpoint;
}

export async function fetchTrackTagAssignments(trackId, definitionId = '') {
  const params = new URLSearchParams({
    track: String(trackId),
    page: '1',
    page_size: '500',
  });
  if (definitionId) {
    params.set('tag_value__definition', String(definitionId));
  }
  const payload = await getJson(`/api/track-tags/?${params.toString()}`, 'Unable to read tag assignments');
  return unpackPaginated(payload).items;
}

export async function fetchTagAssignments(scope, targetId, definitionId = '') {
  const endpoint = endpointForScope(scope);
  const params = new URLSearchParams({
    [endpoint.targetField]: String(targetId),
    page: '1',
    page_size: '500',
  });
  if (definitionId) {
    params.set('tag_value__definition', String(definitionId));
  }
  const payload = await getJson(`${endpoint.list}?${params.toString()}`, 'Unable to read tag assignments');
  return unpackPaginated(payload).items;
}

export async function createTrackTextTagAssignment(trackId, definitionId, valueText) {
  const existingValues = await fetchTagValues(definitionId);
  const tagValue = await ensureTagValue({
    definitionId,
    valueText,
    existingValues,
    displayOrder: existingValues.length,
  });
  return writeJson('/api/track-tags/', 'POST', {
    track: trackId,
    tag_value: {
      definition: definitionId,
      value_text: tagValue.value_text || valueText,
      normalized_key: tagValue.normalized_key || normalizeTagKey(valueText),
      display_order: tagValue.display_order || 0,
    },
  }, 'Unable to assign tag');
}

export async function createTextTagAssignment(scope, targetId, definitionId, valueText) {
  const endpoint = endpointForScope(scope);
  const existingValues = await fetchTagValues(definitionId);
  const tagValue = await ensureTagValue({
    definitionId,
    valueText,
    existingValues,
    displayOrder: existingValues.length,
  });
  return writeJson(endpoint.list, 'POST', {
    [endpoint.targetField]: targetId,
    tag_value: {
      definition: definitionId,
      value_text: tagValue.value_text || valueText,
      normalized_key: tagValue.normalized_key || normalizeTagKey(valueText),
      display_order: tagValue.display_order || 0,
    },
  }, 'Unable to assign tag');
}

export function deleteTrackTagAssignment(assignmentId) {
  return writeJson(`/api/track-tags/${assignmentId}/`, 'DELETE', undefined, 'Unable to remove tag');
}

export function deleteTagAssignment(scope, assignmentId) {
  const endpoint = endpointForScope(scope);
  return writeJson(endpoint.detail(assignmentId), 'DELETE', undefined, 'Unable to remove tag');
}

export function tagFilterValue(definitionKey, normalizedKey, valueId = '') {
  if (valueId) {
    return `value:${valueId}`;
  }
  return `${definitionKey}:${normalizedKey}`;
}
