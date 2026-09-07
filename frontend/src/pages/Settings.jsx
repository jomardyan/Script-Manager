import { useCallback, useEffect, useState } from 'react';

import { apiError, authApi, ftsApi, folderRootsApi, watchApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { Card, Field, PageHeader, StatusBadge } from '../components/ui';
import { useToast } from '../context/ToastContext';
import { formatDateTime } from '../lib/format';

/**
 * Account and maintenance settings.
 *
 * Changing your own password, rebuilding the search index and starting or
 * stopping watch mode all existed in the API with no way to reach them.
 */
export default function Settings() {
  const { user, isAdmin, config, refresh } = useAuth();
  const toast = useToast();
  const authOff = config?.auth_required === false;

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Your account and index maintenance."
      />

      {user && <AccountCard user={user} onSaved={refresh} toast={toast} />}
      {(isAdmin || authOff) && <SearchIndexCard toast={toast} />}
      {(isAdmin || authOff) && <WatchModeCard toast={toast} />}
    </div>
  );
}

function AccountCard({ user, toast }) {
  const [form, setForm] = useState({ old_password: '', new_password: '', confirm: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;

    if (form.new_password !== form.confirm) {
      setError('The two new passwords do not match.');
      return;
    }
    if (form.new_password.length < 8) {
      setError('The new password must be at least 8 characters long.');
      return;
    }

    setError(null);
    setBusy(true);
    try {
      await authApi.changePassword({
        old_password: form.old_password,
        new_password: form.new_password,
      });
      setForm({ old_password: '', new_password: '', confirm: '' });
      toast.success('Password changed.');
    } catch (err) {
      setError(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const roles = (user.roles || []).map((r) => r.name).join(', ');

  return (
    <Card title="Your account">
      <dl className="definition-list" style={{ marginBottom: 'var(--space-4)' }}>
        <dt>Username</dt><dd>{user.username}</dd>
        <dt>Email</dt><dd>{user.email}</dd>
        <dt>Full name</dt><dd>{user.full_name || '—'}</dd>
        <dt>Roles</dt><dd>{user.is_superuser ? 'Administrator' : (roles || '—')}</dd>
        <dt>Permissions</dt>
        <dd className="text-small text-muted mono">
          {(user.permissions || []).join(', ') || 'none'}
        </dd>
      </dl>

      <h4 style={{ marginBottom: 'var(--space-3)' }}>Change password</h4>
      {error && (
        <div className="banner banner--error" role="alert">
          <span className="banner__message">{error}</span>
        </div>
      )}
      <form onSubmit={submit} className="grid-2">
        <Field label="Current password" required className="span-all">
          {(props) => (
            <input
              {...props}
              type="password"
              autoComplete="current-password"
              value={form.old_password}
              onChange={(e) => setForm({ ...form, old_password: e.target.value })}
              required
            />
          )}
        </Field>
        <Field label="New password" required hint="At least 8 characters, with a letter and a number.">
          {(props) => (
            <input
              {...props}
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={form.new_password}
              onChange={(e) => setForm({ ...form, new_password: e.target.value })}
              required
            />
          )}
        </Field>
        <Field label="Confirm new password" required>
          {(props) => (
            <input
              {...props}
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={form.confirm}
              onChange={(e) => setForm({ ...form, confirm: e.target.value })}
              required
            />
          )}
        </Field>
        <div className="span-all">
          <button type="submit" className="button" disabled={busy}>
            {busy ? 'Saving…' : 'Change password'}
          </button>
        </div>
      </form>
    </Card>
  );
}

function SearchIndexCard({ toast }) {
  const [status, setStatus] = useState(null);
  const [roots, setRoots] = useState([]);
  const [rootId, setRootId] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [statusRes, rootsRes] = await Promise.allSettled([ftsApi.status(), folderRootsApi.list()]);
    if (statusRes.status === 'fulfilled') setStatus(statusRes.value.data);
    if (rootsRes.status === 'fulfilled') setRoots(rootsRes.value.data);
  }, []);

  useEffect(() => { load(); }, [load]);

  const rebuild = async () => {
    setBusy(true);
    try {
      const { data } = await ftsApi.rebuild(rootId ? Number(rootId) : undefined);
      toast.success(`Rebuilt the index for ${data.indexed_count} scripts.`);
      await load();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title="Full-text search index"
      description="Rebuild after enabling content indexing on a folder root, or if results look stale."
    >
      {status && (
        <>
          <div className="row row--between" style={{ marginBottom: 'var(--space-2)' }}>
            <span>{status.indexed_scripts} of {status.total_scripts} scripts indexed</span>
            <strong>{status.coverage_percent}%</strong>
          </div>
          <div className="meter" style={{ marginBottom: 'var(--space-4)' }}>
            <div className="meter__fill" style={{ width: `${Math.min(100, status.coverage_percent || 0)}%` }} />
          </div>
          {status.indexed_roots.length === 0 && (
            <p className="text-small text-muted" style={{ marginBottom: 'var(--space-3)' }}>
              No folder root has content indexing enabled, so only names, paths and notes
              are searchable. Turn it on from the Folder Roots page.
            </p>
          )}
        </>
      )}

      <div className="filters">
        <Field label="Scope">
          {(props) => (
            <select {...props} value={rootId} onChange={(e) => setRootId(e.target.value)}>
              <option value="">All folder roots</option>
              {roots.map((root) => (
                <option key={root.id} value={root.id}>{root.name}</option>
              ))}
            </select>
          )}
        </Field>
        <button type="button" className="button" onClick={rebuild} disabled={busy}>
          {busy ? 'Rebuilding…' : 'Rebuild index'}
        </button>
      </div>
    </Card>
  );
}

function WatchModeCard({ toast }) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await watchApi.status();
      setStatus(data);
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const act = async (fn, message) => {
    setBusy(true);
    try {
      await fn();
      toast.success(message);
      await load();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  if (!status) return null;

  return (
    <Card
      title="Watch mode"
      description="Watched roots re-index automatically when files change on disk."
      actions={
        <div className="button-group">
          <button
            type="button"
            className="button button-secondary button--small"
            onClick={() => act(watchApi.startAll, 'Started watching every enabled root.')}
            disabled={busy}
          >
            Start all
          </button>
          <button
            type="button"
            className="button button-secondary button--small"
            onClick={() => act(watchApi.stopAll, 'Stopped all watchers.')}
            disabled={busy}
          >
            Stop all
          </button>
        </div>
      }
    >
      {status.enabled_roots.length === 0 ? (
        <p className="text-muted">
          No folder root has watch mode enabled. Turn it on for a root from the Folder Roots page.
        </p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Folder root</th>
                <th scope="col">Path</th>
                <th scope="col">State</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {status.enabled_roots.map((root) => (
                <tr key={root.root_id}>
                  <td>{root.name}</td>
                  <td className="text-muted text-small mono">{root.path}</td>
                  <td><StatusBadge status={root.watching ? 'active' : 'paused'} /></td>
                  <td>
                    {root.watching ? (
                      <button
                        type="button"
                        className="button button-secondary button--small"
                        onClick={() => act(() => watchApi.stop(root.root_id), `Stopped watching ${root.name}.`)}
                        disabled={busy}
                      >
                        Stop
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="button button-secondary button--small"
                        onClick={() => act(() => watchApi.start(root.root_id), `Watching ${root.name}.`)}
                        disabled={busy}
                      >
                        Start
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-small text-muted" style={{ marginTop: 'var(--space-3)' }}>
        Watchers do not survive a backend restart; start them again after one.
        {status.watching_count > 0 && ` Currently watching ${status.watching_count} root(s).`}
      </p>
    </Card>
  );
}
