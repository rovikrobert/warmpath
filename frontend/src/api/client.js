const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

let _getToken = () => null;

export function setTokenGetter(fn) {
  _getToken = fn;
}

export async function api(path, options = {}) {
  const token = _getToken();
  const headers = { ...options.headers };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const message = err.detail || err.error?.message || 'Request failed';
    const error = new Error(typeof message === 'string' ? message : JSON.stringify(message));
    error.status = res.status;
    throw error;
  }

  return res.json();
}

export const auth = {
  signup: (body) => api('/api/v1/auth/signup', { method: 'POST', body }),
  login: (body) => api('/api/v1/auth/login', { method: 'POST', body }),
  me: () => api('/api/v1/auth/me'),
  upsertProfile: (body) => api('/api/v1/auth/profile', { method: 'POST', body }),
};

export const contacts = {
  upload: (file) => {
    const form = new FormData();
    form.append('file', file);
    return api('/api/v1/contacts/upload', { method: 'POST', body: form });
  },
  list: (page = 1, perPage = 50) =>
    api(`/api/v1/contacts?page=${page}&per_page=${perPage}`),
};

export const companies = {
  list: (page = 1, perPage = 50) =>
    api(`/api/v1/companies?page=${page}&per_page=${perPage}`),
};

export const search = {
  create: (body) => api('/api/v1/search', { method: 'POST', body }),
  list: () => api('/api/v1/search'),
  get: (id) => api(`/api/v1/search/${id}`),
  run: (id) => api(`/api/v1/search/${id}/run`, { method: 'POST' }),
  results: (id, params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v);
    });
    return api(`/api/v1/search/${id}/results?${qs}`);
  },
};

export const matches = {
  createIntro: (body) =>
    api('/api/v1/matches/intros', { method: 'POST', body }),
  getIntro: (id) => api(`/api/v1/matches/intros/${id}`),
  updateMessage: (introId, messageId, body) =>
    api(`/api/v1/matches/intros/${introId}/messages/${messageId}`, {
      method: 'PATCH',
      body,
    }),
};

export const health = {
  check: () => api('/health'),
  usage: () => api('/usage/me'),
};
