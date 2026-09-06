import { useCallback, useEffect, useState } from 'react';

import { apiError, teamApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Badge, Card, Checkbox, EmptyState, ErrorBanner, Field, PageHeader, StatusBadge,
  TableSkeleton,
} from '../components/ui';
import Modal from '../components/Modal';
import { useConfirm } from '../components/ConfirmDialog';
import { useToast } from '../context/ToastContext';
import { formatDateTime, formatRelative } from '../lib/format';

const ROLE_TONES = { admin: 'danger', editor: 'info', viewer: 'success' };

function RoleBadge({ name }) {
  return <Badge tone={ROLE_TONES[name] || 'neutral'}>{name}</Badge>;
}

export default function Team() {
  const toast = useToast();
  const { user: currentUser } = useAuth();
  const { confirm, confirmElement } = useConfirm();

  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null); // null | 'new' | user
  const [busyId, setBusyId] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [usersRes, rolesRes] = await Promise.all([teamApi.listUsers(), teamApi.listRoles()]);
      setUsers(usersRes.data);
      setRoles(rolesRes.data);
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const act = async (id, fn, message) => {
    setBusyId(id);
    try {
      await fn();
      toast.success(message);
      await loadData();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const toggleActive = async (user) => {
    if (user.is_active) {
      const ok = await confirm({
        title: `Deactivate ${user.username}?`,
        message: 'They are signed out immediately and cannot sign in again until reactivated.',
        detail: 'Their data, notes and audit trail entries are kept.',
        confirmLabel: 'Deactivate',
      });
      if (!ok) return;
    }
    await act(
      user.id,
      () => teamApi.updateUser(user.id, { is_active: !user.is_active }),
      user.is_active ? `Deactivated ${user.username}.` : `Reactivated ${user.username}.`,
    );
  };

  const deleteUser = async (user) => {
    const ok = await confirm({
      title: `Delete ${user.username}?`,
      message: 'The account is removed permanently.',
      detail: 'Deactivating instead keeps the account and its history but blocks sign-in.',
      confirmLabel: 'Delete account',
    });
    if (!ok) return;
    await act(user.id, () => teamApi.deleteUser(user.id), `Deleted ${user.username}.`);
  };

  return (
    <div>
      {confirmElement}
      <PageHeader
        title="Team & Access Control"
        description="Accounts and the roles that decide what each one can do."
        actions={
          <button type="button" className="button" onClick={() => setEditing('new')}>
            New user
          </button>
        }
      />

      <ErrorBanner message={error} onRetry={loadData} onDismiss={() => setError(null)} />

      <Card title={`Users${users.length ? ` (${users.length})` : ''}`}>
        {loading ? (
          <TableSkeleton rows={4} columns={6} />
        ) : users.length === 0 ? (
          <EmptyState icon="☰" title="No users" description="This installation has no accounts." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Username</th>
                  <th scope="col">Email</th>
                  <th scope="col">Roles</th>
                  <th scope="col">Status</th>
                  <th scope="col">Last sign-in</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <strong>{user.username}</strong>
                      {user.id === currentUser?.id && (
                        <span className="text-small text-muted"> (you)</span>
                      )}
                      {user.full_name && (
                        <div className="text-small text-muted">{user.full_name}</div>
                      )}
                    </td>
                    <td className="text-small">{user.email}</td>
                    <td>
                      {user.is_superuser && <Badge tone="danger">superuser</Badge>}
                      {(user.roles || []).map((role) => <RoleBadge key={role.id} name={role.name} />)}
                      {!user.is_superuser && (user.roles || []).length === 0 && (
                        <span className="text-muted text-small">No roles — read nothing</span>
                      )}
                    </td>
                    <td><StatusBadge status={user.is_active ? 'active' : 'inactive'} /></td>
                    <td className="nowrap" title={formatDateTime(user.last_login_at)}>
                      {user.last_login_at ? formatRelative(user.last_login_at) : 'Never'}
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          type="button"
                          className="button button-secondary button--small"
                          onClick={() => setEditing(user)}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="button button-secondary button--small"
                          onClick={() => toggleActive(user)}
                          disabled={busyId === user.id || user.id === currentUser?.id}
                          title={user.id === currentUser?.id ? 'You cannot deactivate your own account' : undefined}
                        >
                          {user.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                        <button
                          type="button"
                          className="button button-danger button--small"
                          onClick={() => deleteUser(user)}
                          disabled={busyId === user.id || user.id === currentUser?.id}
                          title={user.id === currentUser?.id ? 'You cannot delete your own account' : undefined}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Roles" description="Built-in roles and the permissions they grant.">
        {loading ? (
          <TableSkeleton rows={3} columns={3} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Role</th>
                  <th scope="col">Description</th>
                  <th scope="col">Permissions</th>
                </tr>
              </thead>
              <tbody>
                {roles.map((role) => (
                  <tr key={role.id}>
                    <td><RoleBadge name={role.name} /></td>
                    <td>{role.description}</td>
                    <td className="text-small text-muted mono">
                      {Array.isArray(role.permissions) ? role.permissions.join(', ') : String(role.permissions)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {editing && (
        <UserModal
          user={editing === 'new' ? null : editing}
          roles={roles}
          onClose={() => setEditing(null)}
          onSaved={(message) => {
            setEditing(null);
            toast.success(message);
            loadData();
          }}
          onError={(message) => toast.error(message)}
        />
      )}
    </div>
  );
}

function UserModal({ user, roles, onClose, onSaved, onError }) {
  const isEdit = Boolean(user);
  const [form, setForm] = useState(() => ({
    username: user?.username || '',
    email: user?.email || '',
    full_name: user?.full_name || '',
    password: '',
    is_superuser: user?.is_superuser ?? false,
    role_ids: (user?.roles || []).map((r) => r.id),
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const toggleRole = (roleId) => {
    setForm((current) => ({
      ...current,
      role_ids: current.role_ids.includes(roleId)
        ? current.role_ids.filter((id) => id !== roleId)
        : [...current.role_ids, roleId],
    }));
  };

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;

    // Validate here so a weak password produces a readable message rather than
    // a raw 422 validation payload.
    if (!isEdit || form.password) {
      if (form.password.length < 8) {
        setError('The password must be at least 8 characters long.');
        return;
      }
      if (!/[a-zA-Z]/.test(form.password) || !/\d/.test(form.password)) {
        setError('The password must contain at least one letter and one number.');
        return;
      }
    }

    setError(null);
    setBusy(true);
    try {
      if (isEdit) {
        await teamApi.updateUser(user.id, {
          email: form.email.trim() || undefined,
          full_name: form.full_name.trim() || undefined,
          is_superuser: form.is_superuser,
          role_ids: form.role_ids,
          password: form.password || undefined,
        });
        onSaved(`Updated ${user.username}.`);
      } else {
        await teamApi.register({
          username: form.username.trim(),
          email: form.email.trim(),
          password: form.password,
          full_name: form.full_name.trim(),
          role_ids: form.role_ids,
        });
        onSaved(`Created ${form.username.trim()}.`);
      }
    } catch (err) {
      onError(apiError(err));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={isEdit ? `Edit ${user.username}` : 'New user'}
      description={isEdit ? 'Leave the password blank to keep the current one.' : undefined}
      onClose={onClose}
    >
      <form onSubmit={submit}>
        {error && (
          <div className="banner banner--error" role="alert">
            <span className="banner__message">{error}</span>
          </div>
        )}

        <div className="grid-2">
          <Field label="Username" required={!isEdit}>
            {(props) => (
              <input
                {...props}
                type="text"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                required={!isEdit}
                disabled={isEdit}
                autoFocus={!isEdit}
                autoComplete="off"
              />
            )}
          </Field>
          <Field label="Email" required>
            {(props) => (
              <input
                {...props}
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
                autoComplete="off"
              />
            )}
          </Field>
          <Field label="Full name">
            {(props) => (
              <input
                {...props}
                type="text"
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                autoComplete="off"
              />
            )}
          </Field>
          <Field
            label={isEdit ? 'New password' : 'Password'}
            required={!isEdit}
            hint="At least 8 characters, with a letter and a number."
          >
            {(props) => (
              <input
                {...props}
                type="password"
                minLength={8}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required={!isEdit}
                autoComplete="new-password"
              />
            )}
          </Field>
        </div>

        <fieldset>
          <legend>Roles</legend>
          <div className="check-grid">
            {roles.map((role) => (
              <div className="checkbox" key={role.id}>
                <input
                  id={`role-${role.id}`}
                  type="checkbox"
                  checked={form.role_ids.includes(role.id)}
                  onChange={() => toggleRole(role.id)}
                />
                <label htmlFor={`role-${role.id}`}>
                  {role.name}
                  {role.description && (
                    <span className="text-muted text-small"> — {role.description}</span>
                  )}
                </label>
              </div>
            ))}
          </div>
        </fieldset>

        {isEdit && (
          <Checkbox
            label="Superuser"
            hint="Bypasses every permission check. Grant sparingly."
            checked={form.is_superuser}
            onChange={(value) => setForm({ ...form, is_superuser: value })}
          />
        )}

        <div className="modal__footer">
          <button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="button" disabled={busy}>
            {busy ? 'Saving…' : (isEdit ? 'Save changes' : 'Create user')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
