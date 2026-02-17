const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

let _getToken = () => null;
let _setToken = () => {};
let _onAuthFailure = () => {};
let _refreshing = null; // singleton promise to avoid concurrent refreshes

export function setTokenGetter(fn) {
  _getToken = fn;
}

export function setTokenSetter(fn) {
  _setToken = fn;
}

export function setAuthFailureHandler(fn) {
  _onAuthFailure = fn;
}

// ---------------------------------------------------------------------------
// Usage warning interceptor — surfaces X-WarmPath-Usage-Warning headers
// ---------------------------------------------------------------------------
let _usageWarningCallback = null;
const _shownWarnings = new Set();

export function onUsageWarning(cb) {
  _usageWarningCallback = cb;
}

// ---------------------------------------------------------------------------
// Token refresh
// ---------------------------------------------------------------------------

async function _tryRefresh() {
  const res = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data?.data?.access_token || null;
}

// ---------------------------------------------------------------------------
// Core API caller with auto-refresh on 401
// ---------------------------------------------------------------------------

async function _rawFetch(path, options = {}) {
  const token = _getToken();
  const headers = { ...options.headers };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  return fetch(`${BASE_URL}${path}`, { ...options, headers, credentials: 'include' });
}

export async function api(path, options = {}) {
  // Clone body for potential retry (can only read a stream once)
  const origBody = options.body;

  let res = await _rawFetch(path, options);

  // Check for usage warning header on every response
  const warning = res.headers.get('x-warmpath-usage-warning');
  if (warning && _usageWarningCallback && !_shownWarnings.has(warning)) {
    _shownWarnings.add(warning);
    _usageWarningCallback(warning);
  }

  // Auto-refresh on 401 (skip for auth endpoints to avoid loops)
  if (res.status === 401 && !path.includes('/auth/refresh') && !path.includes('/auth/login')) {
    // Deduplicate concurrent refresh attempts
    if (!_refreshing) {
      _refreshing = _tryRefresh().finally(() => { _refreshing = null; });
    }
    const newToken = await _refreshing;

    if (newToken) {
      _setToken(newToken);
      // Retry with new token — rebuild options with original body
      const retryOptions = { ...options, body: origBody };
      res = await _rawFetch(path, retryOptions);
    } else {
      // Refresh failed — session is truly expired
      _onAuthFailure();
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const message = err.detail || err.error?.message || 'Session expired';
      const error = new Error(typeof message === 'string' ? message : JSON.stringify(message));
      error.status = res.status;
      throw error;
    }
  }

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
  updateUserType: (userType) =>
    api('/api/v1/auth/user-type', { method: 'PATCH', body: { user_type: userType } }),
  resendVerification: () =>
    api('/api/v1/auth/resend-verification', { method: 'POST' }),
  forgotPassword: (body) =>
    api('/api/v1/auth/forgot-password', { method: 'POST', body }),
  resetPassword: (body) =>
    api('/api/v1/auth/reset-password', { method: 'POST', body }),
  deleteAccount: (body) =>
    api('/api/v1/auth/delete-account', { method: 'POST', body }),
  linkedinAuthorize: () => api('/api/v1/auth/linkedin/authorize'),
  linkedinCallback: (body) =>
    api('/api/v1/auth/linkedin/callback', { method: 'POST', body }),
  uploadResume: (file) => {
    const form = new FormData();
    form.append('file', file);
    return api('/api/v1/auth/profile/import-resume', { method: 'POST', body: form });
  },
};

export const contacts = {
  upload: (file) => {
    const form = new FormData();
    form.append('file', file);
    return api('/api/v1/contacts/upload', { method: 'POST', body: form });
  },
  list: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries({ page: 1, per_page: 50, ...params }).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v);
    });
    return api(`/api/v1/contacts?${qs}`);
  },
  get: (id) => api(`/api/v1/contacts/${id}`),
  patch: (id, body) => api(`/api/v1/contacts/${id}`, { method: 'PATCH', body }),
  createManual: (body) => api('/api/v1/contacts/manual', { method: 'POST', body }),
  bulkImport: (contactsList) =>
    api('/api/v1/contacts/manual/bulk', { method: 'POST', body: { contacts: contactsList } }),
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
  smart: (body) => api('/api/v1/search/smart', { method: 'POST', body }),
  recommendations: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v);
    });
    return api(`/api/v1/search/recommendations?${qs}`);
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

export const marketplace = {
  search: (body) => api('/api/v1/marketplace/search', { method: 'POST', body }),
  requestIntro: (body) =>
    api('/api/v1/marketplace/request-intro', { method: 'POST', body }),
  myRequests: () => api('/api/v1/marketplace/my-requests'),
  incomingRequests: () => api('/api/v1/marketplace/incoming-requests'),
  updateRequest: (id, body) =>
    api(`/api/v1/marketplace/requests/${id}`, { method: 'PATCH', body }),
  getSharingPrefs: () => api('/api/v1/marketplace/sharing-preferences'),
  updateSharingPrefs: (body) =>
    api('/api/v1/marketplace/sharing-preferences', { method: 'PUT', body }),
  myListings: () => api('/api/v1/marketplace/my-listings'),
};

export const credits = {
  balance: () => api('/api/v1/credits/balance'),
  history: () => api('/api/v1/credits/history'),
  purchase: (body) => api('/api/v1/credits/purchase', { method: 'POST', body }),
};

export const preferences = {
  getJob: () => api('/api/v1/preferences/job'),
  upsertJob: (body) => api('/api/v1/preferences/job', { method: 'PUT', body }),
  deleteJob: () => api('/api/v1/preferences/job', { method: 'DELETE' }),
};

export const applications = {
  list: (status) => {
    const qs = status ? `?status=${status}` : '';
    return api(`/api/v1/applications${qs}`);
  },
  create: (body) => api('/api/v1/applications', { method: 'POST', body }),
  update: (id, body) => api(`/api/v1/applications/${id}`, { method: 'PATCH', body }),
  stats: () => api('/api/v1/applications/stats'),
};

export const usage = {
  summary: () => api('/api/v1/usage/me'),
  history: (page = 1, perPage = 20) =>
    api(`/api/v1/usage/me/history?page=${page}&per_page=${perPage}`),
};

export const dashboard = {
  insights: () => api('/api/v1/dashboard/insights'),
};

export const health = {
  check: () => api('/health'),
  usage: () => api('/api/v1/usage/me'),
};
