import { useState, useEffect } from 'react';
import { notificationsApi } from '../services/api';

const CHANNEL_ICONS = {
  slack: '💬',
  discord: '🎮',
  email: '📧',
  webhook: '🔗',
  pagerduty: '🚨',
  sms: '📱',
};

const INCIDENT_STATUS_COLOR = {
  open: '#ef4444',
  acknowledged: '#f59e0b',
  resolved: '#22c55e',
};

function Notifications() {
  const [channels, setChannels] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [activeTab, setActiveTab] = useState('channels');
  const [incidentFilter, setIncidentFilter] = useState('');
  const [formData, setFormData] = useState({
    name: '',
    type: 'slack',
    enabled: true,
    config: {},
  });
  const [configText, setConfigText] = useState('{}');
  const [configError, setConfigError] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [chRes, incRes] = await Promise.all([
        notificationsApi.listChannels(),
        notificationsApi.listIncidents(incidentFilter || undefined),
      ]);
      setChannels(chRes.data);
      setIncidents(incRes.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    let config;
    try {
      config = JSON.parse(configText);
    } catch {
      setConfigError('Invalid JSON in config');
      return;
    }
    setConfigError('');
    try {
      await notificationsApi.createChannel({ ...formData, config });
      setShowForm(false);
      setFormData({ name: '', type: 'slack', enabled: true, config: {} });
      setConfigText('{}');
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDeleteChannel = async (id) => {
    if (!confirm('Delete this channel?')) return;
    try {
      await notificationsApi.deleteChannel(id);
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleTestChannel = async (id) => {
    try {
      const res = await notificationsApi.testChannel(id);
      alert(res.data.message);
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleUpdateIncident = async (id, update) => {
    try {
      await notificationsApi.updateIncident(id, update);
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDeleteIncident = async (id) => {
    if (!confirm('Delete this incident?')) return;
    try {
      await notificationsApi.deleteIncident(id);
      loadData();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleFilterChange = (val) => {
    setIncidentFilter(val);
  };

  useEffect(() => {
    if (activeTab === 'incidents') {
      loadData();
    }
  }, [incidentFilter]);

  const configPlaceholders = {
    slack: '{"webhook_url": "https://hooks.slack.com/services/..."}',
    discord: '{"webhook_url": "https://discord.com/api/webhooks/..."}',
    email: '{"to": "ops@example.com", "smtp_host": "smtp.example.com", "smtp_port": 587, "from": "alerts@example.com"}',
    webhook: '{"url": "https://example.com/webhook", "method": "POST", "headers": {}}',
    pagerduty: '{"routing_key": "your-pagerduty-routing-key"}',
    sms: '{"to": "+15551234567", "provider": "twilio", "account_sid": "...", "auth_token": "..."}',
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Error: {error}</div>;

  const openCount = incidents.filter(i => i.status === 'open').length;
  const ackCount = incidents.filter(i => i.status === 'acknowledged').length;

  return (
    <div>
      <div className="page-header">
        <h2>Notifications & Incidents</h2>
        <p>Manage alert channels and track incidents from monitors and scheduled jobs.</p>
      </div>

      {openCount > 0 && (
        <div className="card" style={{ borderLeft: '4px solid #ef4444', background: '#fef2f2' }}>
          <strong style={{ color: '#ef4444' }}>⚠ {openCount} open incident{openCount !== 1 ? 's' : ''}</strong>
          {ackCount > 0 && <span style={{ marginLeft: 16, color: '#f59e0b' }}>{ackCount} acknowledged</span>}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          className="button"
          style={{ background: activeTab === 'channels' ? '#3b82f6' : undefined }}
          onClick={() => setActiveTab('channels')}
        >
          Channels ({channels.length})
        </button>
        <button
          className="button"
          style={{ background: activeTab === 'incidents' ? '#3b82f6' : undefined }}
          onClick={() => setActiveTab('incidents')}
        >
          Incidents ({incidents.length})
        </button>
      </div>

      {activeTab === 'channels' && (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
            <button className="button" onClick={() => setShowForm(!showForm)}>
              {showForm ? 'Cancel' : '+ New Channel'}
            </button>
          </div>

          {showForm && (
            <div className="card">
              <h3>Create Notification Channel</h3>
              <form onSubmit={handleCreate}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div className="form-group">
                    <label>Name *</label>
                    <input className="input" required value={formData.name}
                      onChange={e => setFormData({ ...formData, name: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label>Type *</label>
                    <select className="input" value={formData.type}
                      onChange={e => {
                        setFormData({ ...formData, type: e.target.value });
                        setConfigText(configPlaceholders[e.target.value] || '{}');
                      }}>
                      {['slack', 'discord', 'email', 'webhook', 'pagerduty', 'sms'].map(t => (
                        <option key={t} value={t}>{CHANNEL_ICONS[t]} {t}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                    <label>Config (JSON)</label>
                    <textarea
                      className="input"
                      rows={4}
                      value={configText}
                      onChange={e => { setConfigText(e.target.value); setConfigError(''); }}
                      style={{ fontFamily: 'monospace', fontSize: 13 }}
                    />
                    {configError && <div style={{ color: '#ef4444', fontSize: 13 }}>{configError}</div>}
                    <small style={{ color: '#64748b' }}>Example: {configPlaceholders[formData.type]}</small>
                  </div>
                  <div className="form-group">
                    <label>
                      <input type="checkbox" checked={formData.enabled}
                        onChange={e => setFormData({ ...formData, enabled: e.target.checked })} />
                      {' '}Enabled
                    </label>
                  </div>
                </div>
                <button className="button" type="submit">Create Channel</button>
              </form>
            </div>
          )}

          <div className="card">
            <h3>Notification Channels</h3>
            {channels.length === 0 ? (
              <p>No notification channels configured. Add one to receive alerts.</p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {channels.map(ch => (
                    <tr key={ch.id}>
                      <td><strong>{ch.name}</strong></td>
                      <td>{CHANNEL_ICONS[ch.type]} {ch.type}</td>
                      <td>
                        <span style={{
                          display: 'inline-block', padding: '2px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600,
                          background: ch.enabled ? '#22c55e' : '#94a3b8', color: '#fff',
                        }}>
                          {ch.enabled ? 'enabled' : 'disabled'}
                        </span>
                      </td>
                      <td>
                        <button className="button" style={{ marginRight: 4 }} onClick={() => handleTestChannel(ch.id)}>Test</button>
                        <button className="button" onClick={() => handleDeleteChannel(ch.id)}>Delete</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {activeTab === 'incidents' && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h3>Incidents</h3>
            <select className="input" style={{ width: 180 }} value={incidentFilter}
              onChange={e => handleFilterChange(e.target.value)}>
              <option value="">All statuses</option>
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>

          {incidents.length === 0 ? (
            <p>No incidents{incidentFilter ? ` with status "${incidentFilter}"` : ''}.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Source</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map(inc => (
                  <tr key={inc.id}>
                    <td>
                      <strong>{inc.title}</strong>
                      {inc.description && <div style={{ fontSize: 12, color: '#64748b' }}>{inc.description}</div>}
                    </td>
                    <td>{inc.source_type} #{inc.source_id}</td>
                    <td>
                      <span style={{
                        display: 'inline-block', padding: '2px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600,
                        background: inc.severity === 'critical' ? '#ef4444' : '#f59e0b', color: '#fff',
                      }}>
                        {inc.severity}
                      </span>
                    </td>
                    <td>
                      <span style={{
                        display: 'inline-block', padding: '2px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600,
                        background: INCIDENT_STATUS_COLOR[inc.status] || '#94a3b8', color: '#fff',
                      }}>
                        {inc.status}
                      </span>
                    </td>
                    <td>{new Date(inc.created_at).toLocaleString()}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      {inc.status === 'open' && (
                        <button className="button" style={{ marginRight: 4 }}
                          onClick={() => handleUpdateIncident(inc.id, { status: 'acknowledged' })}>
                          Acknowledge
                        </button>
                      )}
                      {inc.status !== 'resolved' && (
                        <button className="button" style={{ marginRight: 4 }}
                          onClick={() => handleUpdateIncident(inc.id, { status: 'resolved' })}>
                          Resolve
                        </button>
                      )}
                      <button className="button" onClick={() => handleDeleteIncident(inc.id)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

export default Notifications;
