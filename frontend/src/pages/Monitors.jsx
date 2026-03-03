import { useState, useEffect } from 'react';
import { monitorsApi, notificationsApi } from '../services/api';

const STATUS_COLOR = {
  ok: '#22c55e',
  failing: '#ef4444',
  new: '#94a3b8',
  paused: '#f59e0b',
};

function MonitorStatusBadge({ status }) {
  const color = STATUS_COLOR[status] || '#94a3b8';
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 10px',
      borderRadius: 12,
      background: color,
      color: '#fff',
      fontWeight: 600,
      fontSize: 12,
    }}>
      {status}
    </span>
  );
}

function Monitors() {
  const [monitors, setMonitors] = useState([]);
  const [channels, setChannels] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    expected_interval_seconds: 300,
    grace_period_seconds: 60,
    notify_channel_ids: [],
  });
  const [selectedMonitor, setSelectedMonitor] = useState(null);
  const [pings, setPings] = useState([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [monRes, chRes, incRes] = await Promise.all([
        monitorsApi.list(),
        notificationsApi.listChannels(),
        notificationsApi.listIncidents(),
      ]);
      setMonitors(monRes.data);
      setChannels(chRes.data);
      setIncidents(incRes.data.filter(i => i.source_type === 'monitor'));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      await monitorsApi.create(formData);
      setShowForm(false);
      setFormData({ name: '', description: '', expected_interval_seconds: 300, grace_period_seconds: 60, notify_channel_ids: [] });
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this monitor?')) return;
    try {
      await monitorsApi.delete(id);
      if (selectedMonitor?.id === id) setSelectedMonitor(null);
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleSelectMonitor = async (monitor) => {
    setSelectedMonitor(monitor);
    try {
      const res = await monitorsApi.getPings(monitor.id);
      setPings(res.data);
    } catch {
      setPings([]);
    }
  };

  const handleAcknowledgeIncident = async (incidentId) => {
    try {
      await notificationsApi.updateIncident(incidentId, { status: 'acknowledged', acknowledged_by: 'user' });
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleResolveIncident = async (incidentId) => {
    try {
      await notificationsApi.updateIncident(incidentId, { status: 'resolved' });
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Error: {error}</div>;

  const openIncidents = incidents.filter(i => i.status === 'open');

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>Heartbeat Monitors</h2>
          <p>Fail-safe monitoring — get alerted when jobs stop reporting in.</p>
        </div>
        <button className="button" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ New Monitor'}
        </button>
      </div>

      {openIncidents.length > 0 && (
        <div className="card" style={{ borderLeft: '4px solid #ef4444', background: '#fef2f2' }}>
          <h3 style={{ color: '#ef4444' }}>⚠ Open Incidents ({openIncidents.length})</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Severity</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {openIncidents.map(inc => (
                <tr key={inc.id}>
                  <td>{inc.title}</td>
                  <td><MonitorStatusBadge status={inc.severity} /></td>
                  <td>{new Date(inc.created_at).toLocaleString()}</td>
                  <td>
                    <button className="button" style={{ marginRight: 4 }} onClick={() => handleAcknowledgeIncident(inc.id)}>Acknowledge</button>
                    <button className="button" onClick={() => handleResolveIncident(inc.id)}>Resolve</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <div className="card">
          <h3>Create Monitor</h3>
          <form onSubmit={handleCreate}>
            <div className="form-group">
              <label>Name *</label>
              <input className="input" required value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })} />
            </div>
            <div className="form-group">
              <label>Description</label>
              <input className="input" value={formData.description}
                onChange={e => setFormData({ ...formData, description: e.target.value })} />
            </div>
            <div className="form-group">
              <label>Expected interval (seconds)</label>
              <input className="input" type="number" min="10" value={formData.expected_interval_seconds}
                onChange={e => setFormData({ ...formData, expected_interval_seconds: parseInt(e.target.value) })} />
            </div>
            <div className="form-group">
              <label>Grace period (seconds)</label>
              <input className="input" type="number" min="0" value={formData.grace_period_seconds}
                onChange={e => setFormData({ ...formData, grace_period_seconds: parseInt(e.target.value) })} />
            </div>
            <button className="button" type="submit">Create Monitor</button>
          </form>
        </div>
      )}

      <div className="card">
        <h3>All Monitors</h3>
        {monitors.length === 0 ? (
          <p>No monitors configured. Create one to start monitoring your cron jobs.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Interval</th>
                <th>Grace</th>
                <th>Last Ping</th>
                <th>Ping URL</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {monitors.map(m => (
                <tr key={m.id} style={{ cursor: 'pointer' }} onClick={() => handleSelectMonitor(m)}>
                  <td><strong>{m.name}</strong>{m.description && <div style={{ fontSize: 12, color: '#64748b' }}>{m.description}</div>}</td>
                  <td><MonitorStatusBadge status={m.status} /></td>
                  <td>{m.expected_interval_seconds}s</td>
                  <td>{m.grace_period_seconds}s</td>
                  <td>{m.last_ping_at ? new Date(m.last_ping_at).toLocaleString() : 'Never'}</td>
                  <td>
                    <code style={{ fontSize: 11, background: '#f1f5f9', padding: '2px 6px', borderRadius: 4 }}>
                      /api/monitors/ping/{m.ping_key}
                    </code>
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    <button className="button" onClick={() => handleDelete(m.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selectedMonitor && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <h3>Ping History — {selectedMonitor.name}</h3>
            <button className="button" onClick={() => setSelectedMonitor(null)}>Close</button>
          </div>
          {pings.length === 0 ? (
            <p>No pings recorded yet. Call the ping URL from your cron job to register heartbeats.</p>
          ) : (
            <table className="table">
              <thead>
                <tr><th>Time</th><th>Source IP</th></tr>
              </thead>
              <tbody>
                {pings.map(p => (
                  <tr key={p.id}>
                    <td>{new Date(p.pinged_at).toLocaleString()}</td>
                    <td>{p.source_ip || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div style={{ marginTop: 12, background: '#f8fafc', padding: 12, borderRadius: 6, fontSize: 13 }}>
            <strong>Integration example (bash/curl):</strong>
            <pre style={{ margin: '6px 0 0' }}>
              {`# Add to end of your cron script:
curl -fsS -m 10 --retry 5 \\
  -o /dev/null \\
  "$\{API_BASE_URL}/api/monitors/ping/${selectedMonitor.ping_key}"`}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

export default Monitors;
