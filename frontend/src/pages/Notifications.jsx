import { useCallback, useEffect, useState } from 'react';

import { apiError, notificationsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Card, Checkbox, EmptyState, ErrorBanner, Field, PageHeader, StatusBadge, TableSkeleton,
} from '../components/ui';
import Modal from '../components/Modal';
import { useConfirm } from '../components/ConfirmDialog';
import { useToast } from '../context/ToastContext';
import { formatDateTime, formatRelative } from '../lib/format';

const CHANNEL_ICONS = {
  slack: '💬', discord: '🎮', email: '📧', webhook: '🔗', pagerduty: '🚨', sms: '📱',
};

export default function Notifications() {
  const toast = useToast();
  const { can } = useAuth();
  const { confirm, confirmElement } = useConfirm();

  const [tab, setTab] = useState('channels');
  const [channels, setChannels] = useState([]);
  const [channelTypes, setChannelTypes] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [stats, setStats] = useState(null);
  const [incidentFilter, setIncidentFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [chRes, typesRes, incRes, statsRes] = await Promise.allSettled([
        notificationsApi.listChannels(),
        notificationsApi.channelTypes(),
        notificationsApi.listIncidents(incidentFilter ? { status: incidentFilter } : {}),
        notificationsApi.incidentStats(),
      ]);
      if (chRes.status === 'rejected' && incRes.status === 'rejected') throw chRes.reason;
      setChannels(chRes.status === 'fulfilled' ? chRes.value.data : []);
      setChannelTypes(typesRes.status === 'fulfilled' ? typesRes.value.data.types : []);
      setIncidents(incRes.status === 'fulfilled' ? incRes.value.data : []);
      // Counts come from the server, so filtering the list no longer hides the
      // open-incident banner.
      setStats(statsRes.status === 'fulfilled' ? statsRes.value.data : null);
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
    }
  }, [incidentFilter]);

  useEffect(() => { loadData(); }, [loadData]);

  const act = async (id, fn, message) => {
    setBusyId(id);
    try {
      await fn();
      if (message) toast.success(message);
      await loadData();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const testChannel = async (channel) => {
    setBusyId(channel.id);
    try {
      const { data } = await notificationsApi.testChannel(channel.id);
      if (data.success) toast.success(`${channel.name}: ${data.message}`);
      else toast.error(`${channel.name}: ${data.message}`);
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const deleteChannel = async (channel) => {
    const ok = await confirm({
      title: `Delete channel "${channel.name}"?`,
      message: 'Monitors and jobs that reference it stop alerting through this channel.',
      confirmLabel: 'Delete channel',
    });
    if (!ok) return;
    await act(channel.id, () => notificationsApi.deleteChannel(channel.id), `Deleted "${channel.name}".`);
  };

  const deleteIncident = async (incident) => {
    const ok = await confirm({
      title: 'Delete this incident?',
      message: incident.title,
      detail: 'This removes the record. Resolving it instead keeps the history.',
      confirmLabel: 'Delete incident',
    });
    if (!ok) return;
    await act(incident.id, () => notificationsApi.deleteIncident(incident.id), 'Incident deleted.');
  };

  const openCount = stats?.open ?? 0;
  const ackCount = stats?.acknowledged ?? 0;

  return (
    <div>
      {confirmElement}
      <PageHeader
        title="Notifications & Incidents"
        description="Where alerts go, and what has gone wrong recently."
        actions={tab === 'channels' && can('notifications.create') && (
          <button type="button" className="button" onClick={() => setEditing('new')}>
            New channel
          </button>
        )}
      />

      <ErrorBanner message={error} onRetry={loadData} onDismiss={() => setError(null)} />

      {openCount > 0 && (
        <div className="banner banner--error" role="status">
          <span className="banner__message">
            {openCount} open incident{openCount === 1 ? '' : 's'}
            {ackCount > 0 && `, ${ackCount} acknowledged`}.
          </span>
        </div>
      )}

      <div className="tabs" role="tablist" aria-label="Notifications view">
        <button
          type="button" role="tab" className="tab" aria-selected={tab === 'channels'}
          onClick={() => setTab('channels')}
        >
          Channels ({channels.length})
        </button>
        <button
          type="button" role="tab" className="tab" aria-selected={tab === 'incidents'}
          onClick={() => setTab('incidents')}
        >
          Incidents{stats ? ` (${(stats.open || 0) + (stats.acknowledged || 0)} unresolved)` : ''}
        </button>
      </div>

      {tab === 'channels' && (
        <Card title="Notification channels">
          {loading ? (
            <TableSkeleton rows={3} columns={4} />
          ) : channels.length === 0 ? (
            <EmptyState
              icon="✉"
              title="No channels configured"
              description="Without a channel, monitors and jobs raise incidents but nobody is told about them."
              action={can('notifications.create') && (
                <button type="button" className="button" onClick={() => setEditing('new')}>
                  Add your first channel
                </button>
              )}
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Type</th>
                    <th scope="col">Status</th>
                    <th scope="col">Configuration</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {channels.map((channel) => (
                    <tr key={channel.id}>
                      <td><strong>{channel.name}</strong></td>
                      <td className="nowrap">
                        <span aria-hidden="true">{CHANNEL_ICONS[channel.type]}</span> {channel.type}
                      </td>
                      <td><StatusBadge status={channel.enabled ? 'enabled' : 'disabled'} /></td>
                      <td className="text-small text-muted mono">
                        {Object.entries(channel.config || {})
                          .map(([key, value]) => `${key}=${value}`)
                          .join(' · ') || '—'}
                      </td>
                      <td>
                        <div className="row-actions">
                          {can('notifications.update') && (
                            <button
                              type="button"
                              className="button button--small"
                              onClick={() => testChannel(channel)}
                              disabled={busyId === channel.id}
                            >
                              {busyId === channel.id ? 'Sending…' : 'Send test'}
                            </button>
                          )}
                          {can('notifications.update') && (
                            <button
                              type="button"
                              className="button button-secondary button--small"
                              onClick={() => setEditing(channel)}
                            >
                              Edit
                            </button>
                          )}
                          {can('notifications.delete') && (
                            <button
                              type="button"
                              className="button button-danger button--small"
                              onClick={() => deleteChannel(channel)}
                              disabled={busyId === channel.id}
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
          <p className="text-small text-muted" style={{ marginTop: 'var(--space-3)' }}>
            Secrets such as webhook URLs and API tokens are never returned by the API; they
            appear as <code>***</code> and keep their stored value unless you replace them.
          </p>
        </Card>
      )}

      {tab === 'incidents' && (
        <Card
          title="Incidents"
          actions={
            <Field label="Status">
              {(props) => (
                <select {...props} value={incidentFilter} onChange={(e) => setIncidentFilter(e.target.value)}>
                  <option value="">All statuses</option>
                  <option value="open">Open</option>
                  <option value="acknowledged">Acknowledged</option>
                  <option value="resolved">Resolved</option>
                </select>
              )}
            </Field>
          }
        >
          {loading ? (
            <TableSkeleton rows={4} columns={6} />
          ) : incidents.length === 0 ? (
            <EmptyState
              icon="✓"
              title={incidentFilter ? `No ${incidentFilter} incidents` : 'No incidents'}
              description="Incidents are raised automatically when a monitor goes overdue or a scheduled job fails."
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Title</th>
                    <th scope="col">Source</th>
                    <th scope="col">Severity</th>
                    <th scope="col">Status</th>
                    <th scope="col">Raised</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.map((incident) => (
                    <tr key={incident.id}>
                      <td>
                        <strong>{incident.title}</strong>
                        {incident.description && (
                          <div className="text-small text-muted">{incident.description}</div>
                        )}
                        {incident.acknowledged_by && (
                          <div className="text-small text-muted">
                            Acknowledged by {incident.acknowledged_by}
                          </div>
                        )}
                      </td>
                      <td className="nowrap text-muted">{incident.source_type} #{incident.source_id}</td>
                      <td><StatusBadge status={incident.severity} /></td>
                      <td><StatusBadge status={incident.status} /></td>
                      <td className="nowrap" title={formatDateTime(incident.created_at)}>
                        {formatRelative(incident.created_at)}
                      </td>
                      <td>
                        <div className="row-actions">
                          {incident.status === 'open' && can('incidents.update') && (
                            <button
                              type="button"
                              className="button button-secondary button--small"
                              onClick={() => act(
                                incident.id,
                                () => notificationsApi.updateIncident(incident.id, { status: 'acknowledged' }),
                                'Incident acknowledged.',
                              )}
                              disabled={busyId === incident.id}
                            >
                              Acknowledge
                            </button>
                          )}
                          {incident.status !== 'resolved' && can('incidents.update') && (
                            <button
                              type="button"
                              className="button button--small"
                              onClick={() => act(
                                incident.id,
                                () => notificationsApi.updateIncident(incident.id, { status: 'resolved' }),
                                'Incident resolved.',
                              )}
                              disabled={busyId === incident.id}
                            >
                              Resolve
                            </button>
                          )}
                          {can('incidents.update') && (
                            <button
                              type="button"
                              className="button button-danger button--small"
                              onClick={() => deleteIncident(incident)}
                              disabled={busyId === incident.id}
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
      )}

      {editing && (
        <ChannelModal
          channel={editing === 'new' ? null : editing}
          types={channelTypes}
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

/**
 * Typed configuration form.
 *
 * The old form was a raw JSON textarea seeded with a template the backend
 * rejected, so the first attempt at every channel type failed.
 */
function ChannelModal({ channel, types, onClose, onSaved, onError }) {
  const isEdit = Boolean(channel);
  const [name, setName] = useState(channel?.name || '');
  const [type, setType] = useState(channel?.type || 'slack');
  const [enabled, setEnabled] = useState(channel?.enabled ?? true);
  const [config, setConfig] = useState(channel?.config || {});
  const [busy, setBusy] = useState(false);

  const definition = types.find((t) => t.type === type);

  const changeType = (nextType) => {
    setType(nextType);
    // Keep whatever the user already typed for keys the new type also uses.
    const nextDefinition = types.find((t) => t.type === nextType);
    if (!nextDefinition) return;
    const keep = {};
    nextDefinition.fields.forEach((field) => {
      if (config[field.key] !== undefined) keep[field.key] = config[field.key];
    });
    setConfig(keep);
  };

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      // Blank optional fields are dropped rather than sent as empty strings,
      // which the backend would treat as "provided but invalid".
      const cleaned = {};
      Object.entries(config).forEach(([key, value]) => {
        if (value !== '' && value !== null && value !== undefined) cleaned[key] = value;
      });

      if (isEdit) {
        await notificationsApi.updateChannel(channel.id, {
          name: name.trim(), type, enabled, config: cleaned,
        });
        onSaved(`Updated "${name.trim()}".`);
      } else {
        await notificationsApi.createChannel({
          name: name.trim(), type, enabled, config: cleaned,
        });
        onSaved(`Created channel "${name.trim()}".`);
      }
    } catch (err) {
      onError(apiError(err));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={isEdit ? `Edit "${channel.name}"` : 'New notification channel'}
      description={isEdit ? 'Secrets show as *** — leave them as they are to keep the stored value.' : undefined}
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <div className="grid-2">
          <Field label="Name" required>
            {(props) => (
              <input {...props} type="text" required value={name} autoFocus
                onChange={(e) => setName(e.target.value)} />
            )}
          </Field>
          <Field label="Type" required>
            {(props) => (
              <select {...props} value={type} onChange={(e) => changeType(e.target.value)}>
                {(types.length ? types : [{ type: 'slack', label: 'Slack' }]).map((t) => (
                  <option key={t.type} value={t.type}>
                    {CHANNEL_ICONS[t.type]} {t.label || t.type}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </div>

        {definition ? (
          <fieldset>
            <legend>{definition.label} settings</legend>
            {definition.fields.map((field) => (
              <Field
                key={field.key}
                label={field.label}
                required={field.required}
                hint={field.secret ? 'Stored write-only; never returned by the API.' : undefined}
              >
                {(props) => (
                  <input
                    {...props}
                    type={field.secret && !isEdit ? 'password' : 'text'}
                    value={config[field.key] ?? ''}
                    placeholder={field.placeholder}
                    required={field.required}
                    autoComplete="off"
                    onChange={(e) => setConfig({ ...config, [field.key]: e.target.value })}
                  />
                )}
              </Field>
            ))}
          </fieldset>
        ) : (
          <p className="text-muted text-small">Loading the field list for this channel type…</p>
        )}

        <Checkbox
          label="Enabled"
          hint="A disabled channel is skipped when alerts are dispatched."
          checked={enabled}
          onChange={setEnabled}
        />

        <div className="modal__footer">
          <button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="button" disabled={busy || !name.trim()}>
            {busy ? 'Saving…' : (isEdit ? 'Save changes' : 'Create channel')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
