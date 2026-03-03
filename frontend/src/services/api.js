import axios from 'axios';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Folder Roots API
export const folderRootsApi = {
  list: () => api.get('/folder-roots/'),
  create: (data) => api.post('/folder-roots/', data),
  get: (id) => api.get(`/folder-roots/${id}`),
  delete: (id) => api.delete(`/folder-roots/${id}`),
  scan: (id, fullScan = false) => api.post(`/folder-roots/${id}/scan`, { full_scan: fullScan }),
  getScanStatus: (id, scanId) => api.get(`/folder-roots/${id}/scan/${scanId}`),
};

// Scripts API
export const scriptsApi = {
  list: (params) => api.get('/scripts/', { params }),
  get: (id) => api.get(`/scripts/${id}`),
  getContent: (id) => api.get(`/scripts/${id}/content`),
  getHistory: (id) => api.get(`/scripts/${id}/history`),
  updateStatus: (id, data) => api.put(`/scripts/${id}/status`, data),
  addTag: (scriptId, tagId) => api.post(`/scripts/${scriptId}/tags/${tagId}`),
  removeTag: (scriptId, tagId) => api.delete(`/scripts/${scriptId}/tags/${tagId}`),
  getDuplicates: () => api.get('/scripts/duplicates/list'),
};

// Tags API
export const tagsApi = {
  list: () => api.get('/tags/'),
  create: (data) => api.post('/tags/', data),
  get: (id) => api.get(`/tags/${id}`),
  delete: (id) => api.delete(`/tags/${id}`),
  getScripts: (id) => api.get(`/tags/${id}/scripts`),
};

// Notes API
export const notesApi = {
  getScriptNotes: (scriptId) => api.get(`/notes/script/${scriptId}`),
  create: (scriptId, data) => api.post(`/notes/script/${scriptId}`, data),
  update: (noteId, data) => api.put(`/notes/${noteId}`, data),
  delete: (noteId) => api.delete(`/notes/${noteId}`),
};

// Search API
export const searchApi = {
  search: (data) => api.post('/search/', data),
  getStats: () => api.get('/search/stats'),
};

// Monitors API
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
};

// Schedules API
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
};

// Notifications API (channels + incidents)
export const notificationsApi = {
  listChannels: () => api.get('/notifications/channels/'),
  createChannel: (data) => api.post('/notifications/channels/', data),
  getChannel: (id) => api.get(`/notifications/channels/${id}`),
  updateChannel: (id, data) => api.put(`/notifications/channels/${id}`, data),
  deleteChannel: (id) => api.delete(`/notifications/channels/${id}`),
  testChannel: (id) => api.post(`/notifications/channels/${id}/test`),
  listIncidents: (status) => api.get('/notifications/incidents/', { params: status ? { status } : {} }),
  getIncident: (id) => api.get(`/notifications/incidents/${id}`),
  updateIncident: (id, data) => api.put(`/notifications/incidents/${id}`, data),
  deleteIncident: (id) => api.delete(`/notifications/incidents/${id}`),
};

// Team / User management API (admin)
export const teamApi = {
  listUsers: () => api.get('/auth/users'),
  getUser: (id) => api.get(`/auth/users/${id}`),
  updateUser: (id, params) => api.put(`/auth/users/${id}`, null, { params }),
  deleteUser: (id) => api.delete(`/auth/users/${id}`),
  listRoles: () => api.get('/auth/roles'),
  register: (data) => api.post('/auth/register', null, {
    params: {
      username: data.username,
      email: data.email,
      password: data.password,
      full_name: data.full_name || undefined,
    },
  }),
};

export default api;

// Setup Wizard API (uses fetch directly to avoid auth headers on first run)
async function setupFetch(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status} ${res.statusText}`);
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
