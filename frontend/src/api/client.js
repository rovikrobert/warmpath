import posthog from 'posthog-js';

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Analytics helper — no-op when PostHog is not initialized
// ---------------------------------------------------------------------------
export function track(event, properties = {}) {
  if (posthog.__loaded) {
    posthog.capture(event, properties);
  }
}

let _getToken = () => null;

export function setTokenGetter(fn) {
  _getToken = fn;
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
// Core API caller — Clerk manages token refresh automatically
// ---------------------------------------------------------------------------

async function _rawFetch(path, options = {}) {
  const tokenOrPromise = _getToken();
  const token = tokenOrPromise instanceof Promise ? await tokenOrPromise : tokenOrPromise;
  const headers = { ...options.headers };

  if (token && token !== 'clerk-managed') {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  return fetch(`${BASE_URL}${path}`, { ...options, headers });
}

export async function api(path, options = {}) {
  const res = await _rawFetch(path, options);

  // Check for usage warning header on every response
  const warning = res.headers.get('x-warmpath-usage-warning');
  if (warning && _usageWarningCallback && !_shownWarnings.has(warning)) {
    _shownWarnings.add(warning);
    _usageWarningCallback(warning);
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    let message = err.detail || err.error?.message || 'Request failed';
    // Pydantic validation errors come as an array of {msg, loc, ...} objects
    if (Array.isArray(message)) {
      message = message.map((e) => e.msg || JSON.stringify(e)).join('; ');
    }
    const error = new Error(typeof message === 'string' ? message : JSON.stringify(message));
    error.status = res.status;
    throw error;
  }

  return res.json();
}

export const auth = {
  me: () => api('/api/v1/auth/me'),
  upsertProfile: (body) => api('/api/v1/auth/profile', { method: 'POST', body }),
  updateIntent: (intent, fullName) =>
    api('/api/v1/auth/intent', { method: 'PATCH', body: { intent, full_name: fullName || undefined } }),
  deleteAccount: (body) =>
    api('/api/v1/auth/delete-account', { method: 'POST', body }),
  uploadResume: (file) => {
    const form = new FormData();
    form.append('file', file);
    return api('/api/v1/auth/profile/import-resume', { method: 'POST', body: form });
  },
  completeOnboarding: () =>
    api('/api/v1/auth/onboarding-complete', { method: 'POST' }),
};

export const contacts = {
  upload: (file) => {
    const form = new FormData();
    form.append('file', file);
    return api('/api/v1/contacts/upload', { method: 'POST', body: form }).then((r) => {
      track('csv_upload');
      return r;
    });
  },
  getUploadStatus: (uploadId) => api(`/api/v1/contacts/uploads/${uploadId}`),
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
  nlpSearch: (query) =>
    api('/api/v1/contacts/nlp-search', { method: 'POST', body: { query } }).then((r) => {
      track('nlp_search', { query_length: query.length });
      return r;
    }),
  exportCsv: async (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v);
    });
    const res = await _rawFetch(`/api/v1/contacts/export?${qs}`);
    if (!res.ok) throw new Error('Export failed');
    const blob = await res.blob();
    if (blob.size === 0) throw new Error('Export returned empty file');
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = res.headers.get('content-disposition')?.match(/filename="(.+)"/)?.[1] || 'contacts.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 100);
  },
  enrichmentProgress: () => api('/api/v1/contacts/enrichment-progress'),
};

export const companies = {
  list: (page = 1, perPage = 50) =>
    api(`/api/v1/companies?page=${page}&per_page=${perPage}`),
  search: ({ query, limit = 8 } = {}) => {
    const qs = new URLSearchParams();
    if (query) qs.set('search', query);
    qs.set('per_page', String(limit));
    return api(`/api/v1/companies?${qs}`);
  },
};

export const search = {
  create: (body) =>
    api('/api/v1/search', { method: 'POST', body }).then((r) => {
      track('search_created');
      return r;
    }),
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
    api('/api/v1/marketplace/request-intro', { method: 'POST', body }).then((r) => {
      track('intro_requested');
      return r;
    }),
  myRequests: () => api('/api/v1/marketplace/my-requests'),
  incomingRequests: () => api('/api/v1/marketplace/incoming-requests'),
  updateRequest: (id, body) =>
    api(`/api/v1/marketplace/requests/${id}`, { method: 'PATCH', body }),
  getSharingPrefs: () => api('/api/v1/marketplace/sharing-preferences'),
  updateSharingPrefs: (body) =>
    api('/api/v1/marketplace/sharing-preferences', { method: 'PUT', body }),
  myListings: () => api('/api/v1/marketplace/my-listings'),
  confirmSent: (facilitationId) =>
    api(`/api/v1/marketplace/requests/${facilitationId}/confirm-sent`, { method: 'POST' }),
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
  list: (paramsOrStatus) => {
    const params = typeof paramsOrStatus === 'string'
      ? { status: paramsOrStatus }
      : { ...paramsOrStatus };
    const sp = new URLSearchParams();
    if (params.status) sp.set('status', params.status);
    if (params.page != null) sp.set('page', String(params.page));
    if (params.per_page != null) sp.set('per_page', String(params.per_page));
    const qs = sp.toString() ? `?${sp.toString()}` : '';
    return api(`/api/v1/applications${qs}`);
  },
  create: (body) => api('/api/v1/applications', { method: 'POST', body }),
  update: (id, body) => api(`/api/v1/applications/${id}`, { method: 'PATCH', body }),
  stats: () => api('/api/v1/applications/stats'),
  fromIntro: (introId) =>
    api(`/api/v1/applications/from-intro/${introId}`, { method: 'POST' }),
  fromFacilitation: (facilitationId) =>
    api(`/api/v1/applications/from-facilitation/${facilitationId}`, { method: 'POST' }),
};

export const usage = {
  summary: () => api('/api/v1/usage/me'),
  history: (page = 1, perPage = 20) =>
    api(`/api/v1/usage/me/history?page=${page}&per_page=${perPage}`),
};

export const dashboard = {
  insights: () => api('/api/v1/dashboard/insights'),
};

export const coach = {
  briefing: () => api('/api/v1/coach/briefing'),
  chat: (body) => api('/api/v1/coach/chat', { method: 'POST', body }),
  chatStream: async (body) => {
    const tokenOrPromise = _getToken();
    const token = tokenOrPromise instanceof Promise ? await tokenOrPromise : tokenOrPromise;
    const res = await fetch(`${BASE_URL}/api/v1/coach/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error('Stream failed');
    return res.body.getReader();
  },
};

export const referrals = {
  create: (body) => api('/api/v1/referrals/create', { method: 'POST', body }),
  mine: () => api('/api/v1/referrals/mine'),
  redeem: (body) => api('/api/v1/referrals/redeem', { method: 'POST', body }),
  leaderboard: () => api('/api/v1/referrals/leaderboard'),
};

export const privacy = {
  exportData: () => api('/api/v1/privacy/export-data'),
  restrictProcessing: () =>
    api('/api/v1/privacy/restrict-processing', { method: 'POST' }),
  unrestrictProcessing: () =>
    api('/api/v1/privacy/unrestrict-processing', { method: 'POST' }),
  marketingOptOut: () =>
    api('/api/v1/privacy/marketing-opt-out', { method: 'POST' }),
  marketingOptIn: () =>
    api('/api/v1/privacy/marketing-opt-in', { method: 'POST' }),
  listConsent: () => api('/api/v1/privacy/consent'),
  submitConsent: (body) =>
    api('/api/v1/privacy/consent', { method: 'POST', body }),
  dataRequest: (body) =>
    api('/api/v1/privacy/data-request', { method: 'POST', body }),
};

export const feedback = {
  submit: (body) =>
    api('/api/v1/feedback', { method: 'POST', body }).then((r) => {
      track('feedback_submitted');
      return r;
    }),
};

export const feed = {
  list: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries({ limit: 20, offset: 0, ...params }).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v);
    });
    return api(`/api/v1/feed?${qs}`);
  },
  count: () => api('/api/v1/feed/count'),
  markSeen: (id) => api(`/api/v1/feed/${id}/seen`, { method: 'POST' }),
  act: (id) =>
    api(`/api/v1/feed/${id}/act`, { method: 'POST' }).then((r) => {
      track('feed_item_click');
      return r;
    }),
  dismiss: (id) => api(`/api/v1/feed/${id}/dismiss`, { method: 'POST' }),
  dismissAll: () => api('/api/v1/feed/dismiss-all', { method: 'POST' }),
  batchSeen: (itemIds) =>
    api('/api/v1/feed/batch-seen', { method: 'POST', body: { item_ids: itemIds } }),
  enrichmentResponse: (body) =>
    api('/api/v1/feed/enrichment-response', { method: 'POST', body }).then((r) => {
      track('enrichment_response', { signal_type: body.signal_type });
      return r;
    }),
  generate: () => api('/api/v1/feed/generate', { method: 'POST' }),
};

export const health = {
  check: () => api('/health'),
  usage: () => api('/api/v1/usage/me'),
};

export const introReview = {
  get: (token) =>
    fetch(`${BASE_URL}/api/v1/intro-review/${token}`).then((r) => {
      if (!r.ok) throw new Error('Not found');
      return r.json();
    }),
};
