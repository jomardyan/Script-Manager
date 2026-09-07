import axios from 'axios';

const API_BASE_URL = '/api';
const TOKEN_STORAGE_KEY = 'script-manager.token';

/**
 * Callbacks the auth layer registers so the interceptors can react to an
 * expired session without importing React state into this module.
 */
let onUnauthorized = null;

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

// ── Token storage ─────────────────────────────────────────────────────────────
// Kept in localStorage so a refresh does not sign the user out. Every accessor
// is guarded: storage throws in private-mode browsers and sandboxed frames.

export function getToken() {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    /* storage unavailable; the token still works for this page load */
  }
}

export function clearToken() {
  setToken(null);
}

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Attach the bearer token to every request. Without this the API's entire
// authenticated surface (team management, running a job, testing a channel)
// was unreachable from the UI.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    if (status === 401) {
      clearToken();
      if (onUnauthorized) onUnauthorized();
    }
    // Surface the server's explanation instead of axios's generic
    // "Request failed with status code 400".
    error.message = extractErrorMessage(error);
    return Promise.reject(error);
  },
);

/**
 * Pull a readable message out of an axios error.
 *
 * FastAPI returns `{detail: "..."}` for HTTPException and `{detail: [...]}`
 * for validation failures; the latter used to render as "[object Object]".
 */
export function extractErrorMessage(error) {
  if (!error) return 'Unknown error';
  if (typeof error === 'string') return error;

  const detail = error.response?.data?.detail ?? error.response?.data?.message;

  if (typeof detail === 'string' && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === 'string') return item;
        const field = Array.isArray(item?.loc)
          ? item.loc.filter((p) => p !== 'body' && p !== 'query').join('.')
          : '';
        const message = item?.msg || 'is invalid';
        return field ? `${field}: ${message}` : message;
      })
      .filter(Boolean);
    if (parts.length) return parts.join('; ');
  }

  if (detail && typeof detail === 'object') {
    try {
      return JSON.stringify(detail);
    } catch {
      /* fall through */
    }
  }

  if (error.response?.status === 403) return 'You do not have permission to do that.';
  if (error.code === 'ERR_NETWORK') return 'Cannot reach the server. Is the backend running?';
  return error.message || 'Request failed';
}

/** Convenience alias used throughout the pages. */
export const apiError = extractErrorMessage;

// ── Authentication ────────────────────────────────────────────────────────────
export const authApi = {
  // The token endpoint is an OAuth2 password flow, so it wants a form body.
  login: (username, password) => {
    const body = new URLSearchParams();
    body.append('username', username);
    body.append('password', password);
    return api.post('/auth/login', body, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  },
  me: () => api.get('/auth/me'),
  config: () => api.get('/auth/config'),
  changePassword: (data) => api.put('/auth/change-password', data),
};

// ── Folder Roots ──────────────────────────────────────────────────────────────
export const folderRootsApi = {
  list: () => api.get('/folder-roots/'),
  stats: () => api.get('/folder-roots/stats'),
  create: (data) => api.post('/folder-roots/', data),
  get: (id) => api.get(`/folder-roots/${id}`),
  update: (id, data) => api.put(`/folder-roots/${id}`, data),
  delete: (id) => api.delete(`/folder-roots/${id}`),
  scan: (id, fullScan = false) => api.post(`/folder-roots/${id}/scan`, { full_scan: fullScan }),
  getScanStatus: (id, scanId) => api.get(`/folder-roots/${id}/scan/${scanId}`),
  listScans: (id, limit = 20) => api.get(`/folder-roots/${id}/scans`, { params: { limit } }),
};

// ── Scripts ───────────────────────────────────────────────────────────────────
export const scriptsApi = {
  list: (params, config = {}) => api.get('/scripts/', { params, ...config }),
  get: (id) => api.get(`/scripts/${id}`),
  getContent: (id) => api.get(`/scripts/${id}/content`),
  getHistory: (id) => api.get(`/scripts/${id}/history`),
  updateStatus: (id, data) => api.put(`/scripts/${id}/status`, data),
  addTag: (scriptId, tagId) => api.post(`/scripts/${scriptId}/tags/${tagId}`),
  removeTag: (scriptId, tagId) => api.delete(`/scripts/${scriptId}/tags/${tagId}`),
  getDuplicates: () => api.get('/scripts/duplicates/list'),
  bulkTags: (data) => api.post('/scripts/bulk/tags', data),
  bulkStatus: (data) => api.post('/scripts/bulk/status', data),
  getFields: (id) => api.get(`/scripts/${id}/fields`),
  setField: (id, key, value) => api.put(`/scripts/${id}/fields/${encodeURIComponent(key)}`, { value }),
  deleteField: (id, key) => api.delete(`/scripts/${id}/fields/${encodeURIComponent(key)}`),
  export: (scriptIds) => api.post('/scripts/export', { script_ids: scriptIds || null }),
};

// ── Tags ──────────────────────────────────────────────────────────────────────
export const tagsApi = {
  list: () => api.get('/tags/'),
  create: (data) => api.post('/tags/', data),
  get: (id) => api.get(`/tags/${id}`),
  delete: (id) => api.delete(`/tags/${id}`),
  getScripts: (id) => api.get(`/tags/${id}/scripts`),
};

// ── Notes ─────────────────────────────────────────────────────────────────────
export const notesApi = {
  getScriptNotes: (scriptId) => api.get(`/notes/script/${scriptId}`),
  create: (scriptId, data) => api.post(`/notes/script/${scriptId}`, data),
  update: (noteId, data) => api.put(`/notes/${noteId}`, data),
  delete: (noteId) => api.delete(`/notes/${noteId}`),
  render: (noteId) => api.get(`/notes/${noteId}/render`),
  preview: (data) => api.post('/notes/preview', data),
};

// ── Search ────────────────────────────────────────────────────────────────────
export const searchApi = {
  search: (data) => api.post('/search/', data),
  getStats: () => api.get('/search/stats'),
};

// ── Full-text search ──────────────────────────────────────────────────────────
export const ftsApi = {
  search: (data) => api.post('/fts/', data),
  status: () => api.get('/fts/status'),
  rebuild: (rootId) => api.post('/fts/rebuild', null, { params: rootId ? { root_id: rootId } : {} }),
};

// ── Saved searches ────────────────────────────────────────────────────────────
export const savedSearchesApi = {
  list: () => api.get('/saved-searches/'),
  create: (data) => api.post('/saved-searches/', data),
  get: (id) => api.get(`/saved-searches/${id}`),
  update: (id, data) => api.put(`/saved-searches/${id}`, data),
  delete: (id) => api.delete(`/saved-searches/${id}`),
};

// ── Similarity ────────────────────────────────────────────────────────────────
export const similarityApi = {
  forScript: (scriptId, params) => api.get(`/similarity/${scriptId}`, { params }),
  groups: (params) => api.get('/similarity/groups/all', { params }),
  compare: (a, b) => api.get(`/similarity/compare/${a}/${b}`),
};

// ── Attachments ───────────────────────────────────────────────────────────────
export const attachmentsApi = {
  forScript: (scriptId) => api.get(`/attachments/script/${scriptId}`),
  forNote: (noteId) => api.get(`/attachments/note/${noteId}`),
  upload: (file, { scriptId, noteId } = {}) => {
    const body = new FormData();
    body.append('file', file);
    return api.post('/attachments/upload', body, {
      params: { script_id: scriptId, note_id: noteId },
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  delete: (id) => api.delete(`/attachments/${id}`),
  downloadUrl: (id) => `${API_BASE_URL}/attachments/${id}/download`,
  stats: () => api.get('/attachments/stats/all'),
};

// ── Folders ───────────────────────────────────────────────────────────────────
export const foldersApi = {
  list: (rootId) => api.get('/folders/', { params: rootId ? { root_id: rootId } : {} }),
  tree: (rootId) => api.get(`/folders/tree/${rootId}`),
  setNote: (folderId, note) => api.put(`/folders/${folderId}/note`, { note }),
  clearNote: (folderId) => api.delete(`/folders/${folderId}/note`),
};

// ── Watch mode ────────────────────────────────────────────────────────────────
export const watchApi = {
  status: () => api.get('/watch/status'),
  start: (rootId) => api.post(`/watch/start/${rootId}`),
  stop: (rootId) => api.post(`/watch/stop/${rootId}`),
  startAll: () => api.post('/watch/start-all'),
  stopAll: () => api.post('/watch/stop-all'),
};

// ── Monitors ──────────────────────────────────────────────────────────────────
export const monitorsApi = {
  list: () => api.get('/monitors/'),
  create: (data) => api.post('/monitors/', data),
  get: (id) => api.get(`/monitors/${id}`),
  update: (id, data) => api.put(`/monitors/${id}`, data),
  delete: (id) => api.delete(`/monitors/${id}`),
  pause: (id) => api.post(`/monitors/${id}/pause`),
  resume: (id) => api.post(`/monitors/${id}/resume`),
  getPings: (id, limit = 50) => api.get(`/monitors/${id}/pings`, { params: { limit } }),
  getIncidents: (id) => api.get(`/monitors/${id}/incidents`),
  getPingUrl: (id) => api.get(`/monitors/${id}/ping-url`),
};

// ── Schedules ─────────────────────────────────────────────────────────────────
export const schedulesApi = {
  list: () => api.get('/schedules/'),
  create: (data) => api.post('/schedules/', data),
  get: (id) => api.get(`/schedules/${id}`),
  update: (id, data) => api.put(`/schedules/${id}`, data),
  delete: (id) => api.delete(`/schedules/${id}`),
  enable: (id) => api.post(`/schedules/${id}/enable`),
  disable: (id) => api.post(`/schedules/${id}/disable`),
  trigger: (id) => api.post(`/schedules/${id}/trigger`),
  listExecutions: (id, limit = 50) => api.get(`/schedules/${id}/executions`, { params: { limit } }),
  getExecution: (jobId, execId) => api.get(`/schedules/${jobId}/executions/${execId}`),
  getMetrics: (id, days = 30) => api.get(`/schedules/${id}/metrics`, { params: { days } }),
  previewCron: (expression, timezone, count = 5) =>
    api.get('/schedules/preview/cron', { params: { expression, timezone, count } }),
};

// ── Notifications ─────────────────────────────────────────────────────────────
export const notificationsApi = {
  listChannels: () => api.get('/notifications/channels/'),
  channelTypes: () => api.get('/notifications/channels/types'),
  createChannel: (data) => api.post('/notifications/channels/', data),
  getChannel: (id) => api.get(`/notifications/channels/${id}`),
  updateChannel: (id, data) => api.put(`/notifications/channels/${id}`, data),
  deleteChannel: (id) => api.delete(`/notifications/channels/${id}`),
  testChannel: (id) => api.post(`/notifications/channels/${id}/test`),
  listIncidents: (params) => api.get('/notifications/incidents/', { params: params || {} }),
  incidentStats: () => api.get('/notifications/incidents/stats'),
  getIncident: (id) => api.get(`/notifications/incidents/${id}`),
  updateIncident: (id, data) => api.put(`/notifications/incidents/${id}`, data),
  deleteIncident: (id) => api.delete(`/notifications/incidents/${id}`),
};

// ── Team / user management (admin) ────────────────────────────────────────────
export const teamApi = {
  listUsers: () => api.get('/auth/users'),
  getUser: (id) => api.get(`/auth/users/${id}`),
  updateUser: (id, data) => api.put(`/auth/users/${id}`, data),
  deleteUser: (id) => api.delete(`/auth/users/${id}`),
  listRoles: () => api.get('/auth/roles'),
  register: (data) => api.post('/auth/register', {
    username: data.username,
    email: data.email,
    password: data.password,
    full_name: data.full_name || undefined,
    role_ids: data.role_ids && data.role_ids.length ? data.role_ids : undefined,
  }),
};

export default api;

// ── Setup wizard ──────────────────────────────────────────────────────────────
// Uses fetch directly: it runs before any account exists, so it must not carry
// (or trip over) the auth interceptors above.
async function setupFetch(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d) => d?.msg || String(d)).join('; ')
      : body.detail;
    throw new Error(detail || `Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const setupApi = {
  getStatus: () => setupFetch('/api/setup/status'),
  activateDemo: () => setupFetch('/api/setup/demo', { method: 'POST' }),
  complete: (payload) =>
    setupFetch('/api/setup/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  testDb: (config) =>
    setupFetch('/api/setup/test-db', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }),
};
