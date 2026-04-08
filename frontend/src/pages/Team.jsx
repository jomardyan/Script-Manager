import { useState, useEffect } from 'react';
import { teamApi } from '../services/api';

const ROLE_COLORS = { admin: '#ef4444', editor: '#3b82f6', viewer: '#22c55e' };

function RoleBadge({ name }) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 10,
      background: ROLE_COLORS[name] || '#94a3b8', color: '#fff',
      fontWeight: 600, fontSize: 11, marginRight: 4,
    }}>
      {name}
    </span>
  );
}

function Team() {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [registerData, setRegisterData] = useState({ username: '', email: '', password: '', full_name: '' });
  const [editingUser, setEditingUser] = useState(null); // { id, role_ids }

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [uRes, rRes] = await Promise.all([teamApi.listUsers(), teamApi.listRoles()]);
      setUsers(uRes.data);
      setRoles(rRes.data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    try {
      await teamApi.register(registerData);
      setShowForm(false);
      setRegisterData({ username: '', email: '', password: '', full_name: '' });
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleToggleActive = async (user) => {
    try {
      await teamApi.updateUser(user.id, { is_active: !user.is_active });
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDeleteUser = async (user) => {
    if (!confirm(`Delete user "${user.username}"?`)) return;
    try {
      await teamApi.deleteUser(user.id);
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleSaveRoles = async () => {
    try {
      await teamApi.updateUser(editingUser.id, { role_ids: editingUser.role_ids });
      setEditingUser(null);
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const toggleRole = (roleId) => {
    setEditingUser(prev => ({
      ...prev,
      role_ids: prev.role_ids.includes(roleId)
        ? prev.role_ids.filter(id => id !== roleId)
        : [...prev.role_ids, roleId],
    }));
  };

  if (loading) return <div className="loading">Loading…</div>;
  if (error) return (
    <div className="error">
      {error.includes('Admin') ? (
        <p>⚠ You need admin (superuser) privileges to manage team members.</p>
      ) : (
        <p>Error: {error}</p>
      )}
    </div>
  );

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>Team & Access Control</h2>
          <p>Manage users and role-based permissions (RBAC).</p>
        </div>
        <button className="button" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ New User'}
        </button>
      </div>

      {showForm && (
        <div className="card">
          <h3>Register New User</h3>
          <form onSubmit={handleRegister}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div className="form-group">
                <label>Username *</label>
                <input className="input" required value={registerData.username}
                  onChange={e => setRegisterData({ ...registerData, username: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Email *</label>
                <input className="input" type="email" required value={registerData.email}
                  onChange={e => setRegisterData({ ...registerData, email: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Full Name</label>
                <input className="input" value={registerData.full_name}
                  onChange={e => setRegisterData({ ...registerData, full_name: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Password *</label>
                <input className="input" type="password" required value={registerData.password}
                  onChange={e => setRegisterData({ ...registerData, password: e.target.value })} />
                <small style={{ color: '#64748b' }}>Min 8 chars, must include letter and number</small>
              </div>
            </div>
            <button className="button" type="submit">Create User</button>
          </form>
        </div>
      )}

      <div className="card">
        <h3>Available Roles</h3>
        <table className="table">
          <thead>
            <tr><th>Role</th><th>Description</th><th>Permissions</th></tr>
          </thead>
          <tbody>
            {roles.map(r => (
              <tr key={r.id}>
                <td><RoleBadge name={r.name} /></td>
                <td>{r.description}</td>
                <td>
                  <code style={{ fontSize: 11, color: '#64748b' }}>
                    {(() => {
                      try {
                        const perms = typeof r.permissions === 'string' ? JSON.parse(r.permissions) : r.permissions;
                        return Array.isArray(perms) ? perms.join(', ') : String(perms);
                      } catch { return r.permissions; }
                    })()}
                  </code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Users ({users.length})</h3>
        {users.length === 0 ? (
          <p>No users found.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Email</th>
                <th>Full Name</th>
                <th>Roles</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td>
                    <strong>{u.username}</strong>
                    {u.is_superuser && (
                      <span style={{ fontSize: 10, marginLeft: 4, color: '#ef4444' }}>SUPER</span>
                    )}
                  </td>
                  <td>{u.email}</td>
                  <td>{u.full_name || '—'}</td>
                  <td>
                    {editingUser?.id === u.id ? (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {roles.map(r => (
                          <label key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                            <input
                              type="checkbox"
                              checked={editingUser.role_ids.includes(r.id)}
                              onChange={() => toggleRole(r.id)}
                            />
                            <RoleBadge name={r.name} />
                          </label>
                        ))}
                      </div>
                    ) : (
                      (u.roles && u.roles.length > 0)
                        ? u.roles.map(r => <RoleBadge key={r.id} name={r.name} />)
                        : <span style={{ color: '#94a3b8', fontSize: 12 }}>—</span>
                    )}
                  </td>
                  <td>
                    <span style={{
                      display: 'inline-block', padding: '2px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600,
                      background: u.is_active ? '#22c55e' : '#94a3b8', color: '#fff',
                    }}>
                      {u.is_active ? 'active' : 'inactive'}
                    </span>
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {editingUser?.id === u.id ? (
                      <>
                        <button className="button" style={{ marginRight: 4 }} onClick={handleSaveRoles}>Save</button>
                        <button className="button" onClick={() => setEditingUser(null)}>Cancel</button>
                      </>
                    ) : (
                      <>
                        <button className="button" style={{ marginRight: 4 }}
                          onClick={() => setEditingUser({ id: u.id, role_ids: u.roles?.map(r => r.id) || [] })}>
                          Edit Roles
                        </button>
                        <button className="button" style={{ marginRight: 4 }}
                          onClick={() => handleToggleActive(u)}>
                          {u.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                        <button className="button" onClick={() => handleDeleteUser(u)}>Delete</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default Team;
