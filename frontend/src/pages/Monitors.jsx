import { useCallback, useEffect, useState } from 'react';

import { apiError, monitorsApi, notificationsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Card, EmptyState, ErrorBanner, Field, PageHeader, StatusBadge, TableSkeleton,
} from '../components/ui';
import ChannelPicker from '../components/ChannelPicker';
import Modal from '../components/Modal';
import { useConfirm } from '../components/ConfirmDialog';
import { useToast } from '../context/ToastContext';
import { formatDateTime, formatInterval, formatRelative } from '../lib/format';

const EMPTY_FORM = {
  name: '',
  description: '',
  expected_interval_seconds: 300,
  grace_period_seconds: 60,
  notify_channel_ids: [],
};

export default function Monitors() {
  const toast = useToast();
  const { can } = useAuth();
  const { confirm, confirmElement } = useConfirm();

  const [monitors, setMonitors] = useState([]);
  const [channels, setChannels] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null); // null | 'new' | monitor
  const [busyId, setBusyId] = useState(null);
  const [detail, setDetail] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [monRes, chRes, incRes] = await Promise.allSettled([
        monitorsApi.list(),
        notificationsApi.listChannels(),
        notificationsApi.listIncidents({ source_type: 'monitor' }),
      ]);
      if (monRes.status === 'rejected') throw monRes.reason;
      setMonitors(monRes.value.data);
      setChannels(chRes.status === 'fulfilled' ? chRes.value.data : []);
      setIncidents(incRes.status === 'fulfilled' ? incRes.value.data : []);
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

  const handleDelete = async (monitor) => {
    const ok = await confirm({
      title: `Delete monitor "${monitor.name}"?`,
      message: 'Its ping history and related incidents are deleted too.',
      detail: 'Any cron job still calling the ping URL will start receiving 404 responses.',
      confirmLabel: 'Delete monitor',
    });
    if (!ok) return;
    await act(monitor.id, () => monitorsApi.delete(monitor.id), `Deleted "${monitor.name}".`);
    if (detail?.monitor.id === monitor.id) setDetail(null);
  };

  const openDetail = async (monitor) => {
    setDetail({ monitor, pings: null, pingUrl: null });
    const [pingsRes, urlRes] = await Promise.allSettled([
      monitorsApi.getPings(monitor.id),
      monitorsApi.getPingUrl(monitor.id),
    ]);
    setDetail({
      monitor,
      pings: pingsRes.status === 'fulfilled' ? pingsRes.value.data : [],
      pingUrl: urlRes.status === 'fulfilled' ? urlRes.value.data : null,
    });
  };

  const openIncidents = incidents.filter((i) => i.status === 'open');
  const failing = monitors.filter((m) => m.status === 'failing');
  const canManage = can('monitors.update');

  return (
    <div>
      {confirmElement}
      <PageHeader
        title="Heartbeat Monitors"
        description="Each monitor expects a periodic ping. If one stops arriving, an incident is raised and the chosen channels are alerted."
        actions={can('monitors.create') && (
          <button type="button" className="button" onClick={() => setEditing('new')}>
            New monitor
          </button>
        )}
      />

      <ErrorBanner message={error} onRetry={loadData} onDismiss={() => setError(null)} />

      {(openIncidents.length > 0 || failing.length > 0) && (
        <div className="banner banner--error" role="status">
          <span className="banner__message">
            {failing.length > 0 && `${failing.length} monitor${failing.length === 1 ? ' is' : 's are'} overdue. `}
            {openIncidents.length > 0 && `${openIncidents.length} open incident${openIncidents.length === 1 ? '' : 's'}.`}
          </span>
        </div>
      )}

      {openIncidents.length > 0 && (
        <Card title={`Open incidents (${openIncidents.length})`}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">Severity</th>
                  <th scope="col">Raised</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {openIncidents.map((incident) => (
                  <tr key={incident.id}>
                    <td>
                      {incident.title}
                      {incident.description && (
                        <div className="text-small text-muted">{incident.description}</div>
                      )}
                    </td>
                    <td><StatusBadge status={incident.severity} /></td>
                    <td className="nowrap" title={formatDateTime(incident.created_at)}>
                      {formatRelative(incident.created_at)}
                    </td>
                    <td>
                      <div className="row-actions">
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
                        <button
                          type="button"
                          className="button button-secondary button--small"
                          onClick={() => act(
                            incident.id,
                            () => notificationsApi.updateIncident(incident.id, { status: 'resolved' }),
                            'Incident resolved.',
                          )}
                          disabled={busyId === incident.id}
                        >
                          Resolve
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card title="All monitors">
        {loading ? (
          <TableSkeleton rows={4} columns={6} />
        ) : monitors.length === 0 ? (
          <EmptyState
            icon="♥"
            title="No monitors configured"
            description="Create a monitor, then call its ping URL at the end of a cron job. If a ping does not arrive in time, Script Manager raises an incident."
            action={can('monitors.create') && (
              <button type="button" className="button" onClick={() => setEditing('new')}>
                Create your first monitor
              </button>
            )}
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Status</th>
                  <th scope="col">Expected every</th>
                  <th scope="col">Grace</th>
                  <th scope="col">Last ping</th>
                  <th scope="col">Alerts</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {monitors.map((monitor) => {
                  const channelNames = (monitor.notify_channel_ids || [])
                    .map((id) => channels.find((c) => c.id === id)?.name)
                    .filter(Boolean);
                  return (
                    <tr key={monitor.id}>
                      <td>
                        <button
                          type="button"
                          className="button button-ghost button--small"
                          onClick={() => openDetail(monitor)}
                        >
                          <strong>{monitor.name}</strong>
                        </button>
                        {monitor.description && (
                          <div className="text-small text-muted">{monitor.description}</div>
                        )}
                      </td>
                      <td><StatusBadge status={monitor.status} /></td>
                      <td className="nowrap">{formatInterval(monitor.expected_interval_seconds)}</td>
                      <td className="nowrap">{formatInterval(monitor.grace_period_seconds)}</td>
                      <td className="nowrap" title={formatDateTime(monitor.last_ping_at)}>
                        {monitor.last_ping_at ? formatRelative(monitor.last_ping_at) : 'Never'}
                      </td>
                      <td className="text-small">
                        {channelNames.length ? channelNames.join(', ') : (
                          <span className="text-muted">None — nobody is alerted</span>
                        )}
                      </td>
                      <td>
                        <div className="row-actions">
                          {canManage && (
                            <button
                              type="button"
                              className="button button-secondary button--small"
                              onClick={() => setEditing(monitor)}
                            >
                              Edit
                            </button>
                          )}
                          {canManage && (monitor.status === 'paused' ? (
                            <button
                              type="button"
                              className="button button-secondary button--small"
                              onClick={() => act(monitor.id, () => monitorsApi.resume(monitor.id), `Resumed "${monitor.name}".`)}
                              disabled={busyId === monitor.id}
                            >
                              Resume
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="button button-secondary button--small"
                              onClick={() => act(monitor.id, () => monitorsApi.pause(monitor.id), `Paused "${monitor.name}".`)}
                              disabled={busyId === monitor.id}
                            >
                              Pause
                            </button>
                          ))}
                          {can('monitors.delete') && (
                            <button
                              type="button"
                              className="button button-danger button--small"
                              onClick={() => handleDelete(monitor)}
                              disabled={busyId === monitor.id}
                            >
                              Delete
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {detail && (
        <Modal
          title={`Monitor: ${detail.monitor.name}`}
          onClose={() => setDetail(null)}
          size="large"
        >
          <h4>Ping URL</h4>
          <p className="text-small text-muted">
            Anyone with this URL can register a heartbeat, so treat it as a secret.
          </p>
          {detail.pingUrl ? (
            <pre className="code-view" style={{ maxHeight: 160 }}>
{`# Add to the end of your cron script:
curl -fsS -m 10 --retry 3 -o /dev/null \\
  "$BASE_URL${detail.pingUrl.ping_path}"`}
            </pre>
          ) : (
            <p className="text-muted text-small">Loading…</p>
          )}

          <h4 style={{ marginTop: 'var(--space-4)' }}>Recent pings</h4>
          {detail.pings === null ? (
            <TableSkeleton rows={3} columns={2} />
          ) : detail.pings.length === 0 ? (
            <p className="text-muted text-small">
              No pings recorded yet. Until the first one arrives, the deadline is measured
              from when the monitor was created.
            </p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th scope="col">Time</th><th scope="col">Source IP</th></tr>
                </thead>
                <tbody>
                  {detail.pings.map((ping) => (
                    <tr key={ping.id}>
                      <td title={formatDateTime(ping.pinged_at)}>{formatRelative(ping.pinged_at)}</td>
                      <td className="mono text-small">{ping.source_ip || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Modal>
      )}

      {editing && (
        <MonitorModal
          monitor={editing === 'new' ? null : editing}
          channels={channels}
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

function MonitorModal({ monitor, channels, onClose, onSaved, onError }) {
  const isEdit = Boolean(monitor);
  const [form, setForm] = useState(() => (monitor ? {
    name: monitor.name,
    description: monitor.description || '',
    expected_interval_seconds: monitor.expected_interval_seconds,
    grace_period_seconds: monitor.grace_period_seconds,
    notify_channel_ids: monitor.notify_channel_ids || [],
  } : { ...EMPTY_FORM }));
  const [busy, setBusy] = useState(false);

  // Number inputs come back as strings, and an empty one used to be sent as
  // NaN/null and rejected with an unreadable validation error.
  const setNumber = (key, raw, fallback) => {
    const parsed = parseInt(raw, 10);
    setForm({ ...form, [key]: Number.isNaN(parsed) ? fallback : parsed });
  };

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        expected_interval_seconds: Number(form.expected_interval_seconds),
        grace_period_seconds: Number(form.grace_period_seconds),
        notify_channel_ids: form.notify_channel_ids,
      };
      if (isEdit) {
        await monitorsApi.update(monitor.id, payload);
        onSaved(`Updated "${payload.name}".`);
      } else {
        await monitorsApi.create(payload);
        onSaved(`Created monitor "${payload.name}".`);
      }
    } catch (err) {
      onError(apiError(err));
      setBusy(false);
    }
  };

  return (
    <Modal title={isEdit ? `Edit "${monitor.name}"` : 'New monitor'} onClose={onClose}>
      <form onSubmit={submit}>
        <Field label="Name" required>
          {(props) => (
            <input {...props} type="text" value={form.name} required autoFocus
              onChange={(e) => setForm({ ...form, name: e.target.value })} />
          )}
        </Field>
        <Field label="Description">
          {(props) => (
            <input {...props} type="text" value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Nightly database backup on db-01" />
          )}
        </Field>

        <div className="grid-2">
          <Field
            label="Expected interval (seconds)"
            required
            hint={`How often a ping should arrive. Currently ${formatInterval(form.expected_interval_seconds)}.`}
          >
            {(props) => (
              <input {...props} type="number" min={10} required value={form.expected_interval_seconds}
                onChange={(e) => setNumber('expected_interval_seconds', e.target.value, 300)} />
            )}
          </Field>
          <Field
            label="Grace period (seconds)"
            required
            hint={`Extra time allowed before alerting. Currently ${formatInterval(form.grace_period_seconds)}.`}
          >
            {(props) => (
              <input {...props} type="number" min={0} required value={form.grace_period_seconds}
                onChange={(e) => setNumber('grace_period_seconds', e.target.value, 60)} />
            )}
          </Field>
        </div>

        <ChannelPicker
          channels={channels}
          value={form.notify_channel_ids}
          onChange={(ids) => setForm({ ...form, notify_channel_ids: ids })}
          label="Alert these channels when the monitor goes overdue"
        />

        <div className="modal__footer">
          <button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="button" disabled={busy || !form.name.trim()}>
            {busy ? 'Saving…' : (isEdit ? 'Save changes' : 'Create monitor')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
