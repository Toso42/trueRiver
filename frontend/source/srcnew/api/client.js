export async function readJsonResponse(response, fallbackMessage) {
  const contentType = response.headers.get('content-type') || '';
  const rawBody = await response.text();

  if (!response.ok) {
    const snippet = rawBody.trim().slice(0, 220);
    throw new Error(`${fallbackMessage} [${response.status}]${snippet ? `: ${snippet}` : ''}`);
  }

  if (!contentType.includes('application/json')) {
    const snippet = rawBody.trim().slice(0, 220) || 'non-JSON response';
    throw new Error(`${fallbackMessage}: ${snippet}`);
  }

  return JSON.parse(rawBody);
}

export function unpackPaginated(payload) {
  if (Array.isArray(payload)) {
    return { items: payload, count: payload.length, next: null, previous: null };
  }

  return {
    items: payload.results ?? [],
    count: payload.count ?? (payload.results?.length ?? 0),
    next: payload.next ?? null,
    previous: payload.previous ?? null,
  };
}

export function resolveRequestUrl(path, { bustCache = false } = {}) {
  try {
    const url = new URL(path, window.location.origin);
    if (url.origin === window.location.origin || url.hostname === window.location.hostname) {
      url.protocol = window.location.protocol;
      url.host = window.location.host;
    }
    if (bustCache && url.origin === window.location.origin && url.pathname.startsWith('/api/')) {
      url.searchParams.set('_triver_ts', String(Date.now()));
    }
    return url.href;
  } catch (_error) {
    return path;
  }
}

export async function getJson(path, fallbackMessage) {
  const response = await fetch(resolveRequestUrl(path, { bustCache: true }), {
    cache: 'no-store',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  });
  return readJsonResponse(response, fallbackMessage);
}

export async function writeJson(path, method, body, fallbackMessage) {
  await fetch(resolveRequestUrl('/api/getcsrf/', { bustCache: true }), {
    cache: 'no-store',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  });
  const response = await fetch(resolveRequestUrl(path), {
    method,
    cache: 'no-store',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 204) {
    return null;
  }

  const contentLength = response.headers.get('content-length');
  if (contentLength === '0') {
    if (!response.ok) {
      throw new Error(`${fallbackMessage} [${response.status}]`);
    }
    return null;
  }

  return readJsonResponse(response, fallbackMessage);
}

export async function writeFormData(path, method, formData, fallbackMessage) {
  await fetch(resolveRequestUrl('/api/getcsrf/', { bustCache: true }), {
    cache: 'no-store',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  });
  const response = await fetch(resolveRequestUrl(path), {
    method,
    cache: 'no-store',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: formData,
  });

  if (response.status === 204) {
    return null;
  }

  return readJsonResponse(response, fallbackMessage);
}

export function getCookie(name) {
  const cookies = document.cookie.split(';').map((item) => item.trim());
  const entry = cookies.find((item) => item.startsWith(`${name}=`));
  return entry ? decodeURIComponent(entry.split('=').slice(1).join('=')) : '';
}
