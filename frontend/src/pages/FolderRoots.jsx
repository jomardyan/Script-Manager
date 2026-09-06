import { useCallback, useEffect, useRef, useState } from 'react';

import { apiError, folderRootsApi, watchApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Card, Checkbox, EmptyState, ErrorBanner, Field, PageHeader, StatusBadge, TableSkeleton,
} from '../components/ui';
import Modal from '../components/Modal';
import { useConfirm } from '../components/ConfirmDialog';
import { useToast } from '../context/ToastContext';
import { formatBytes, formatDateTime, formatRelative } from '../lib/format';

// Polling gives up after this long rather than running until the tab closes.
const SCAN_POLL_INTERVAL_MS = 2000;
const SCAN_POLL_TIMEOUT_MS = 15 * 60 * 1000;

const EMPTY_FORM = {
  name: '',
  path: '',
  recursive: true,
  include_patterns: '',
  exclude_patterns: '',
  follow_symlinks: false,
  max_file_size: 10485760,
  enable_content_indexing: false,
  enable_watch_mode: false,
};

export default function FolderRoots() {
  const toast = useToast();
  const { can } = useAuth();
  const { confirm, confirmElement } = useConfirm();

  const [roots, setRoots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [scanning, setScanning] = useState({});
  const [busyId, setBusyId] = useState(null);
  const [editing, setEditing] = useState(null); // null | 'new' | root object
  const [watchState, setWatchState] = useState({});

  // Every in-flight poll is tracked so unmounting the page clears them; the
  // previous implementation leaked an interval per scan, forever.
  const pollTimers = useRef(new Map());

  useEffect(() => {
    const timers = pollTimers.current;
    return () => {
      timers.forEach((id) => clearInterval(id));
      timers.clear();
    };
  }, []);

  const loadRoots = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await folderRootsApi.stats();
      setRoots(data);
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadWatchState = useCallback(async () => {
    try {
      const { data } = await watchApi.status();
      const map = {};
      (data.enabled_roots || []).forEach((entry) => { map[entry.root_id] = entry.watching; });
      setWatchState(map);
    } catch {
      setWatchState({});
    }
  }, []);

  useEffect(() => {
    loadRoots();
    loadWatchState();
  }, [loadRoots, loadWatchState]);

  const stopPolling = useCallback((rootId) => {
    const timer = pollTimers.current.get(rootId);
    if (timer) {
      clearInterval(timer);
      pollTimers.current.delete(rootId);
    }
    setScanning((current) => ({ ...current, [rootId]: false }));
  }, []);

  const handleScan = async (root, fullScan = false) => {
    setScanning((current) => ({ ...current, [root.id]: true }));
    try {
      const { data } = await folderRootsApi.scan(root.id, fullScan);
      const scanId = data.scan_id;
      const startedAt = Date.now();

      const timer = setInterval(async () => {
        // Never poll indefinitely: a backend restart would otherwise leave
        // this running for as long as the tab stayed open.
        if (Date.now() - startedAt > SCAN_POLL_TIMEOUT_MS) {
          stopPolling(root.id);
          toast.warning(`Still scanning "${root.name}" after 15 minutes. Refresh to check on it.`);
          return;
        }
        try {
          const status = await folderRootsApi.getScanStatus(root.id, scanId);
          const result = status.data;
          if (result.status === 'completed') {
            stopPolling(root.id);
            toast.success(
              `Scanned "${root.name}": ${result.new_count} new, ${result.updated_count} updated, `
              + `${result.deleted_count} missing.`,
            );
            loadRoots();
          } else if (result.status === 'failed') {
            stopPolling(root.id);
            toast.error(`Scan of "${root.name}" failed: ${result.error_message || 'unknown error'}`);
            loadRoots();
          }
        } catch (err) {
          stopPolling(root.id);
          toast.error(`Lost track of the scan: ${apiError(err)}`);
        }
      }, SCAN_POLL_INTERVAL_MS);

      pollTimers.current.set(root.id, timer);
    } catch (err) {
      stopPolling(root.id);
      toast.error(apiError(err));
    }
  };

  const handleDelete = async (root) => {
    const ok = await confirm({
      title: `Delete folder root "${root.name}"?`,
      message: `All ${root.script_count ?? 0} indexed scripts under this root will be removed from Script Manager, along with their notes, tags and history.`,
      detail: 'The files on disk are not touched.',
      confirmLabel: 'Delete folder root',
    });
    if (!ok) return;

    setBusyId(root.id);
    try {
      await folderRootsApi.delete(root.id);
      toast.success(`Deleted folder root "${root.name}".`);
      stopPolling(root.id);
      await loadRoots();
      await loadWatchState();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const toggleWatch = async (root) => {
    setBusyId(root.id);
    try {
      if (watchState[root.id]) {
        await watchApi.stop(root.id);
        toast.success(`Stopped watching "${root.name}".`);
      } else {
        await watchApi.start(root.id);
        toast.success(`Watching "${root.name}" for changes.`);
      }
      await loadWatchState();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const canManage = can('roots.update');

  return (
    <div>
      {confirmElement}
      <PageHeader
        title="Folder Roots"
        description="Directories Script Manager indexes."
        actions={can('roots.create') && (
          <button type="button" className="button" onClick={() => setEditing('new')}>
            Add folder root
          </button>
        )}
      />

      <ErrorBanner message={error} onRetry={loadRoots} onDismiss={() => setError(null)} />

      <Card>
        {loading ? (
          <TableSkeleton rows={4} columns={6} />
        ) : roots.length === 0 ? (
          <EmptyState
            icon="▣"
            title="No folder roots configured"
            description="A folder root points at a directory on the server. Scanning it indexes every recognised script inside."
            action={can('roots.create') && (
              <button type="button" className="button" onClick={() => setEditing('new')}>
                Add your first folder root
              </button>
            )}
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Path</th>
                  <th scope="col">Scripts</th>
                  <th scope="col">Last scan</th>
                  <th scope="col">Options</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {roots.map((root) => (
                  <tr key={root.id}>
                    <td>
                      <strong>{root.name}</strong>
                      {root.path_exists === false && (
                        <div className="text-small" style={{ color: 'var(--danger)' }}>
                          Path is not accessible
                        </div>
                      )}
                    </td>
                    <td className="text-muted text-small mono" title={root.path}>{root.path}</td>
                    <td className="nowrap">
                      {root.script_count ?? 0}
                      {root.missing_count > 0 && (
                        <div className="text-small text-muted">{root.missing_count} missing</div>
                      )}
                    </td>
                    <td className="nowrap">
                      {root.last_scan_time ? (
                        <span title={formatDateTime(root.last_scan_time)}>
                          {formatRelative(root.last_scan_time)}
                        </span>
                      ) : <span className="text-muted">Never</span>}
                      {root.last_scan?.status === 'failed' && (
                        <div className="text-small" style={{ color: 'var(--danger)' }}>
                          Last scan failed
                        </div>
                      )}
                    </td>
                    <td>
                      <div className="row">
                        {watchState[root.id] !== undefined && (
                          <StatusBadge status={watchState[root.id] ? 'active' : 'paused'} />
                        )}
                        {root.id in watchState && (
                          <span className="text-small text-muted">watch</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="row-actions">
                        {can('roots.scan') && (
                          <button
                            type="button"
                            className="button button--small"
                            onClick={() => handleScan(root)}
                            disabled={Boolean(scanning[root.id])}
                          >
                            {scanning[root.id] ? (
                              <>
                                <span className="spinner spinner--inline" aria-hidden="true" />
                                Scanning…
                              </>
                            ) : 'Scan'}
                          </button>
                        )}
                        {canManage && (
                          <button
                            type="button"
                            className="button button-secondary button--small"
                            onClick={() => setEditing(root)}
                          >
                            Edit
                          </button>
                        )}
                        {canManage && root.id in watchState && (
                          <button
                            type="button"
                            className="button button-secondary button--small"
                            onClick={() => toggleWatch(root)}
                            disabled={busyId === root.id}
                          >
                            {watchState[root.id] ? 'Stop watching' : 'Watch'}
                          </button>
                        )}
                        {can('roots.delete') && (
                          <button
                            type="button"
                            className="button button-danger button--small"
                            onClick={() => handleDelete(root)}
                            disabled={busyId === root.id}
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {editing && (
        <FolderRootModal
          root={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(message) => {
            setEditing(null);
            toast.success(message);
            loadRoots();
            loadWatchState();
          }}
          onError={(message) => toast.error(message)}
        />
      )}
    </div>
  );
}

/**
 * Create or edit a folder root.
 *
 * Content indexing and watch mode had no UI at all, so the two flags could
 * never be turned on and the features they gate were unreachable.
 */
function FolderRootModal({ root, onClose, onSaved, onError }) {
  const isEdit = Boolean(root);
  const [form, setForm] = useState(() => (root ? {
    name: root.name || '',
    path: root.path || '',
    recursive: root.recursive ?? true,
    include_patterns: root.include_patterns || '',
    exclude_patterns: root.exclude_patterns || '',
    follow_symlinks: root.follow_symlinks ?? false,
    max_file_size: root.max_file_size ?? 10485760,
    enable_content_indexing: root.enable_content_indexing ?? false,
    enable_watch_mode: root.enable_watch_mode ?? false,
  } : { ...EMPTY_FORM }));
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState(root && !('recursive' in root) ? null : root);

  // The stats endpoint returns a summary, not the full record, so fetch the
  // real settings before showing them as editable values.
  useEffect(() => {
    if (!isEdit || detail) return;
    let cancelled = false;
    folderRootsApi.get(root.id).then(({ data }) => {
      if (cancelled) return;
      setDetail(data);
      setForm({
        name: data.name || '',
        path: data.path || '',
        recursive: data.recursive,
        include_patterns: data.include_patterns || '',
        exclude_patterns: data.exclude_patterns || '',
        follow_symlinks: data.follow_symlinks,
        max_file_size: data.max_file_size,
        enable_content_indexing: data.enable_content_indexing,
        enable_watch_mode: data.enable_watch_mode,
      });
    }).catch((err) => onError(apiError(err)));
    return () => { cancelled = true; };
  }, [isEdit, detail, root, onError]);

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const payload = {
        name: form.name.trim(),
        recursive: form.recursive,
        include_patterns: form.include_patterns.trim() || null,
        exclude_patterns: form.exclude_patterns.trim() || null,
        follow_symlinks: form.follow_symlinks,
        max_file_size: Number(form.max_file_size) || 10485760,
        enable_content_indexing: form.enable_content_indexing,
        enable_watch_mode: form.enable_watch_mode,
      };
      if (isEdit) {
        await folderRootsApi.update(root.id, payload);
        onSaved(`Updated "${payload.name}".`);
      } else {
        await folderRootsApi.create({ ...payload, path: form.path.trim() });
        onSaved(`Added folder root "${payload.name}". Run a scan to index it.`);
      }
    } catch (err) {
      onError(apiError(err));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={isEdit ? `Edit "${root.name}"` : 'Add folder root'}
      description={isEdit ? 'The path is fixed; delete and recreate the root to move it.' : undefined}
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <Field label="Name" required>
          {(props) => (
            <input
              {...props}
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              autoFocus
            />
          )}
        </Field>

        <Field
          label="Path"
          required={!isEdit}
          hint="An absolute path on the server running the backend, not on your own machine."
        >
          {(props) => (
            <input
              {...props}
              type="text"
              value={form.path}
              onChange={(e) => setForm({ ...form, path: e.target.value })}
              placeholder="/srv/scripts"
              required={!isEdit}
              disabled={isEdit}
              className="mono"
            />
          )}
        </Field>

        <div className="grid-2">
          <Field label="Include patterns" hint="Comma separated globs. Blank means every recognised script type.">
            {(props) => (
              <input
                {...props}
                type="text"
                value={form.include_patterns}
                onChange={(e) => setForm({ ...form, include_patterns: e.target.value })}
                placeholder="*.py, *.sh"
              />
            )}
          </Field>
          <Field label="Exclude patterns" hint="Comma separated globs applied before anything else.">
            {(props) => (
              <input
                {...props}
                type="text"
                value={form.exclude_patterns}
                onChange={(e) => setForm({ ...form, exclude_patterns: e.target.value })}
                placeholder="*test*, */node_modules/*"
              />
            )}
          </Field>
        </div>

        <Field
          label="Maximum file size (bytes)"
          hint={`Files larger than this are skipped. Currently ${formatBytes(form.max_file_size)}.`}
        >
          {(props) => (
            <input
              {...props}
              type="number"
              min={1}
              value={form.max_file_size}
              onChange={(e) => setForm({ ...form, max_file_size: e.target.value })}
            />
          )}
        </Field>

        <fieldset>
          <legend>Scanning options</legend>
          <Checkbox
            label="Scan subdirectories"
            checked={form.recursive}
            onChange={(value) => setForm({ ...form, recursive: value })}
          />
          <Checkbox
            label="Follow symbolic links"
            hint="Loops are detected, but symlinked files may be indexed under more than one path."
            checked={form.follow_symlinks}
            onChange={(value) => setForm({ ...form, follow_symlinks: value })}
          />
          <Checkbox
            label="Index file contents for full-text search"
            hint="Reads up to the first 100 KB of each file during a scan. Required for content search."
            checked={form.enable_content_indexing}
            onChange={(value) => setForm({ ...form, enable_content_indexing: value })}
          />
          <Checkbox
            label="Allow watch mode"
            hint="Lets you start a filesystem watcher for this root from Settings, so changes are indexed automatically."
            checked={form.enable_watch_mode}
            onChange={(value) => setForm({ ...form, enable_watch_mode: value })}
          />
        </fieldset>

        <div className="modal__footer">
          <button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="button" disabled={busy || !form.name.trim() || (!isEdit && !form.path.trim())}>
            {busy ? 'Saving…' : (isEdit ? 'Save changes' : 'Add folder root')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
