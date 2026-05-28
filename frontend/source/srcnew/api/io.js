import { getCookie, getJson, readJsonResponse, resolveRequestUrl, unpackPaginated, writeFormData, writeJson } from './client';

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

export async function fetchLatestScanJob() {
  try {
    return await getJson('/api/scan-jobs/latest/', 'Unable to read latest scan job');
  } catch (error) {
    if (String(error.message || '').includes('[404]')) {
      return null;
    }
    throw error;
  }
}

export async function fetchLatestDigestJob() {
  try {
    return await getJson('/api/digest-jobs/latest/', 'Unable to read latest digest job');
  } catch (error) {
    if (String(error.message || '').includes('[404]')) {
      return null;
    }
    throw error;
  }
}

export async function fetchClassicImportSources() {
  return getJson('/api/scan-jobs/classic-sources/', 'Unable to read classic import folders');
}

export async function fetchAutoImportSettings() {
  return getJson('/api/auto-import/', 'Unable to read auto import settings');
}

export async function updateAutoImportSettings(payload = {}) {
  return writeJson('/api/auto-import/settings/', 'PATCH', payload, 'Unable to update auto import settings');
}

export async function runAutoImportCheckNow() {
  return writeJson('/api/auto-import/check-now/', 'POST', {}, 'Unable to start auto import check');
}

export async function fetchIoMediaFiles(libraryId) {
  if (!libraryId) {
    return [];
  }
  return fetchAllPages(
    `/api/media-files/?library=${libraryId}&ordering=relative_path&page=1&page_size=500`,
    'Unable to read media files',
  );
}

export async function fetchIoSourceFolders(libraryId) {
  if (!libraryId) {
    return [];
  }
  return fetchAllPages(
    `/api/source-folders/?library=${libraryId}&ordering=relative_path&page=1&page_size=500`,
    'Unable to read source folders',
  );
}

export async function fetchFileExplorer(root = 'trive-In', path = '') {
  const params = new URLSearchParams();
  params.set('root', root);
  if (String(path || '').trim()) {
    params.set('path', String(path).trim());
  }
  const query = params.toString();
  return getJson(`/api/ingest-browser/${query ? `?${query}` : ''}`, 'Unable to read file explorer');
}

export async function fetchExplorerMetadataTargets(root = 'trive-In', path = '') {
  const params = new URLSearchParams();
  params.set('root', root);
  if (String(path || '').trim()) {
    params.set('path', String(path).trim());
  }
  return getJson(
    `/api/ingest-browser/metadata-targets/?${params.toString()}`,
    'Unable to read metadata targets',
  );
}

export async function assignArtistFromFolderName(root = 'trive-In', path = '') {
  return writeJson(
    '/api/ingest-browser/artist-from-folder-name/',
    'POST',
    { root, path },
    'Unable to assign artist from folder name',
  );
}

async function ensureCsrfCookie() {
  await fetch(resolveRequestUrl('/api/getcsrf/', { bustCache: true }), {
    cache: 'no-store',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  });
}

function parseXhrJson(xhr, fallbackMessage) {
  const rawBody = xhr.responseText || '';
  const contentType = xhr.getResponseHeader('content-type') || '';
  if (xhr.status < 200 || xhr.status >= 300) {
    let detail = '';
    if (contentType.includes('application/json')) {
      try {
        const payload = JSON.parse(rawBody);
        detail = payload?.detail || payload?.message || '';
      } catch (_error) {
        detail = '';
      }
    }
    const snippet = (detail || rawBody.trim()).slice(0, 220);
    throw new Error(`${fallbackMessage} [${xhr.status}]${snippet ? `: ${snippet}` : ''}`);
  }
  if (xhr.status === 204 || !rawBody.trim()) {
    return null;
  }
  if (!contentType.includes('application/json')) {
    const snippet = rawBody.trim().slice(0, 220) || 'non-JSON response';
    throw new Error(`${fallbackMessage}: ${snippet}`);
  }
  return JSON.parse(rawBody);
}

export async function uploadTriveInFile(path = '', entry = {}, onProgress = null) {
  if (!entry?.file) {
    throw new Error('No file provided.');
  }
  await ensureCsrfCookie();
  const formData = new FormData();
  formData.set('root', 'trive-In');
  formData.set('path', String(path || ''));
  formData.append('files', entry.file, entry.file.name);
  formData.append('relative_paths', entry.relativePath || entry.file.name);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', resolveRequestUrl('/api/ingest-browser/upload/'));
    xhr.withCredentials = true;
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));
    xhr.upload.addEventListener('progress', (event) => {
      if (typeof onProgress !== 'function') {
        return;
      }
      onProgress({
        loaded: event.loaded,
        total: event.lengthComputable ? event.total : (entry.file.size || 0),
        lengthComputable: event.lengthComputable,
      });
    });
    xhr.addEventListener('load', () => {
      try {
        resolve(parseXhrJson(xhr, 'Unable to upload files'));
      } catch (error) {
        reject(error);
      }
    });
    xhr.addEventListener('error', () => reject(new Error('Unable to upload files: network error')));
    xhr.addEventListener('abort', () => reject(new Error('Unable to upload files: upload aborted')));
    xhr.send(formData);
  });
}

export async function uploadTriveInFiles(path = '', fileEntries = []) {
  const formData = new FormData();
  formData.set('root', 'trive-In');
  formData.set('path', String(path || ''));
  fileEntries.forEach((entry) => {
    if (!entry?.file) {
      return;
    }
    formData.append('files', entry.file);
    formData.append('relative_paths', entry.relativePath || entry.file.name);
  });
  return writeFormData(
    '/api/ingest-browser/upload/',
    'POST',
    formData,
    'Unable to upload files',
  );
}

export async function deleteExplorerEntry(root = 'trive-In', path = '') {
  return writeJson(
    '/api/ingest-browser/delete-entry/',
    'POST',
    { root, path },
    'Unable to delete file explorer entry',
  );
}

export async function fetchIoAccessoryFiles(libraryId) {
  if (!libraryId) {
    return [];
  }
  return fetchAllPages(
    `/api/accessory-files/?library=${libraryId}&ordering=relative_path&page=1&page_size=500`,
    'Unable to read accessory files',
  );
}

export async function fetchScanSkips(scanJobId) {
  if (!scanJobId) {
    return [];
  }
  return fetchAllPages(
    `/api/scan-skips/?scan_job=${scanJobId}&ordering=relative_path&page=1&page_size=500`,
    'Unable to read scan skips',
  );
}

export async function fetchDigestErrors(digestJobId) {
  if (!digestJobId) {
    return [];
  }
  return fetchAllPages(
    `/api/digest-errors/?digest_job=${digestJobId}&ordering=created_at&page=1&page_size=500`,
    'Unable to read digest errors',
  );
}

async function ensureCsrf() {
  await fetch('/api/getcsrf/', {
    credentials: 'include',
  });
}

export async function startScanJob(options = '') {
  const update = typeof options === 'string' ? options : (options?.update || '');
  const targetPath = typeof options === 'object' ? (options?.targetPath || '') : '';
  await ensureCsrf();
  const response = await fetch('/api/scan-jobs/start_scan/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify({ update, target_path: targetPath }),
  });
  return readJsonResponse(response, 'Failed to start scan');
}

export async function startRescanJob(options = {}) {
  const targetPath = options?.targetPath || '';
  await ensureCsrf();
  const response = await fetch('/api/scan-jobs/start_rescan/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify({ target_path: targetPath }),
  });
  return readJsonResponse(response, 'Failed to start library rescan');
}

export async function startDigestJob(options = {}) {
  const targetPath = options?.targetPath || '';
  await ensureCsrf();
  const response = await fetch('/api/digest-jobs/start_up/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify({ target_path: targetPath }),
  });
  return readJsonResponse(response, 'Failed to start trive-up');
}

export async function startClassicImport(sourceKeys = []) {
  await ensureCsrf();
  const response = await fetch('/api/scan-jobs/start-classic-import/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify({ source_keys: sourceKeys }),
  });
  return readJsonResponse(response, 'Failed to start classic import');
}

export async function cancelDigestJob(jobId) {
  if (!jobId) {
    throw new Error('No trive-up job selected.');
  }
  await ensureCsrf();
  const response = await fetch(`/api/digest-jobs/${jobId}/cancel/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify({}),
  });
  return readJsonResponse(response, 'Failed to cancel trive-up');
}
