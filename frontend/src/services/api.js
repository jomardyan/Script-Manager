import axios from 'axios';

/**
 * Shared API client for the Script Manager backend.
 */
const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Folder roots API client.
 */
export const folderRootsApi = {
  list: () => api.get('/folder-roots/'),
  create: (data) => api.post('/folder-roots/', data),
  get: (id) => api.get(`/folder-roots/${id}`),
  delete: (id) => api.delete(`/folder-roots/${id}`),
  scan: (id, fullScan = false) => api.post(`/folder-roots/${id}/scan`, { full_scan: fullScan }),
};

/**
 * Scripts API client.
 */
export const scriptsApi = {
  list: (params) => api.get('/scripts/', { params }),
  get: (id) => api.get(`/scripts/${id}`),
  updateStatus: (id, data) => api.put(`/scripts/${id}/status`, data),
  addTag: (scriptId, tagId) => api.post(`/scripts/${scriptId}/tags/${tagId}`),
  removeTag: (scriptId, tagId) => api.delete(`/scripts/${scriptId}/tags/${tagId}`),
  getDuplicates: () => api.get('/scripts/duplicates/list'),
};

/**
 * Tags API client.
 */
export const tagsApi = {
  list: () => api.get('/tags/'),
  create: (data) => api.post('/tags/', data),
  get: (id) => api.get(`/tags/${id}`),
  delete: (id) => api.delete(`/tags/${id}`),
  getScripts: (id) => api.get(`/tags/${id}/scripts`),
};

/**
 * Notes API client.
 */
export const notesApi = {
  getScriptNotes: (scriptId) => api.get(`/notes/script/${scriptId}`),
  create: (scriptId, data) => api.post(`/notes/script/${scriptId}`, data),
  update: (noteId, data) => api.put(`/notes/${noteId}`, data),
  delete: (noteId) => api.delete(`/notes/${noteId}`),
};

/**
 * Search API client.
 */
export const searchApi = {
  search: (data) => api.post('/search/', data),
  getStats: () => api.get('/search/stats'),
};

export default api;
