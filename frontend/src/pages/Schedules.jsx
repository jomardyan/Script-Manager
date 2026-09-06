import { useCallback, useEffect, useState } from 'react';

import { apiError, notificationsApi, schedulesApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Card, Checkbox, EmptyState, ErrorBanner, Field, PageHeader, StatusBadge, TableSkeleton,
} from '../components/ui';
import ChannelPicker from '../components/ChannelPicker';
import Modal from '../components/Modal';
import { useConfirm } from '../components/ConfirmDialog';
import { useToast } from '../context/ToastContext';
import { formatDateTime, formatDuration, formatRelative } from '../lib/format';

const CRON_PRESETS = [
  { label: 'Every 15 minutes', value: '*/15 * * * *' },
  { label: 'Hourly', value: '0 * * * *' },
  { label: 'Daily at 02:00', value: '0 2 * * *' },
  { label: 'Weekdays at 09:00', value: '0 9 * * 1-5' },
  { label: 'Weekly on Sunday', value: '0 0 * * 0' },
  { label: 'Monthly on the 1st', value: '0 0 1 * *' },
];

const EMPTY_FORM = {
  name: '',
  description: '',
  command: '',
  script_id: null,
  cron_expression: '0 * * * *',
  timezone: 'UTC',
  enabled: true,
  max_retries: 0,
  retry_delay_seconds: 60,
  prevent_overlap: true,
  timeout_seconds: '',
  notify_channel_ids: [],
};

export default function Schedules() {
  const toast = useToast();
  const { can } = useAuth();
  const { confirm, confirmElement } = useConfirm();

  const [jobs, setJobs] = useState([]);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [selectedExecution, setSelectedExecution] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [detailTab, setDetailTab] = useState('executions');

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [jobsRes, chRes] = await Promise.allSettled([
        schedulesApi.list(), notificationsApi.listChannels(),
      ]);
      if (jobsRes.status === 'rejected') throw jobsRes.reason;
      setJobs(jobsRes.value.data);
      setChannels(chRes.status === 'fulfilled' ? chRes.value.data : []);
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadJobs(); }, [loadJobs]);

  const loadExecutions = useCallback(async (jobId) => {
    try {
      const { data } = await schedulesApi.listExecutions(jobId);
      setExecutions(data);
    } catch (err) {
      setExecutions([]);
      toast.error(apiError(err));
    }
  }, [toast]);

  const act = async (id, fn, message) => {
    setBusyId(id);
    try {
      await fn();
      toast.success(message);
      await loadJobs();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const handleTrigger = async (job) => {
    // Running a job executes an arbitrary shell command on the server, so it
    // is worth naming that command before doing it.
    const ok = await confirm({
      title: `Run "${job.name}" now?`,
      message: 'This executes the job immediately, outside its schedule.',
      detail: job.command ? `Command: ${job.command}` : 'The job runs its linked script.',
      confirmLabel: 'Run now',
      tone: 'primary',
    });
    if (!ok) return;

    setBusyId(job.id);
    try {
      const { data } = await schedulesApi.trigger(job.id);
      toast.success(`Started "${job.name}" (execution #${data.execution_id}).`);
      if (selectedJob?.id === job.id) await loadExecutions(job.id);
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (job) => {
    const ok = await confirm({
      title: `Delete job "${job.name}"?`,
      message: 'Its execution history and related incidents are deleted with it.',
      confirmLabel: 'Delete job',
    });
    if (!ok) return;
    await act(job.id, () => schedulesApi.delete(job.id), `Deleted "${job.name}".`);
    if (selectedJob?.id === job.id) setSelectedJob(null);
  };

  const openJob = async (job) => {
    setSelectedJob(job);
    setSelectedExecution(null);
    setDetailTab('executions');
    setMetrics(null);
    await loadExecutions(job.id);
  };

  const openMetrics = async (job) => {
    setDetailTab('metrics');
    try {
      const { data } = await schedulesApi.getMetrics(job.id);
      setMetrics(data);
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const canManage = can('schedules.update');

  return (
    <div>
      {confirmElement}
      <PageHeader
        title="Scheduled Jobs"
        description="Cron-scheduled commands with retries, overlap protection and captured output. The backend runs them; you do not need an external scheduler."
        actions={can('schedules.create') && (
          <button type="button" className="button" onClick={() => setEditing('new')}>
            New job
          </button>
        )}
      />

      <ErrorBanner message={error} onRetry={loadJobs} onDismiss={() => setError(null)} />

      <Card title="All jobs">
        {loading ? (
          <TableSkeleton rows={4} columns={7} />
        ) : jobs.length === 0 ? (
          <EmptyState
            icon="⏱"
            title="No scheduled jobs"
            description="Create a job to run a command on a cron schedule and keep its output."
            action={can('schedules.create') && (
              <button type="button" className="button" onClick={() => setEditing('new')}>
                Create your first job
              </button>
            )}
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Job</th>
                  <th scope="col">Schedule</th>
                  <th scope="col">Last run</th>
                  <th scope="col">Result</th>
                  <th scope="col">Next run</th>
                  <th scope="col">Alerts</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const channelNames = (job.notify_channel_ids || [])
                    .map((id) => channels.find((c) => c.id === id)?.name)
                    .filter(Boolean);
                  return (
                    <tr key={job.id} style={{ opacity: job.enabled ? 1 : 0.65 }}>
                      <td>
                        <button
                          type="button"
                          className="button button-ghost button--small"
                          onClick={() => openJob(job)}
                        >
                          <strong>{job.name}</strong>
                        </button>
                        {!job.enabled && <StatusBadge status="disabled" />}
                        {job.description && (
                          <div className="text-small text-muted">{job.description}</div>
                        )}
                        {job.command && (
                          <div className="text-small text-muted mono" title={job.command}>
                            {job.command.length > 60 ? `${job.command.slice(0, 60)}…` : job.command}
                          </div>
                        )}
                      </td>
                      <td className="nowrap">
                        <code className="text-small">{job.cron_expression}</code>
                        <div className="text-small text-muted">{job.timezone}</div>
                      </td>
                      <td className="nowrap" title={formatDateTime(job.last_run_at)}>
                        {job.last_run_at ? formatRelative(job.last_run_at) : '—'}
                      </td>
                      <td>{job.last_status ? <StatusBadge status={job.last_status} /> : <span className="text-muted">—</span>}</td>
                      <td className="nowrap" title={formatDateTime(job.next_run_at)}>
                        {job.enabled && job.next_run_at ? formatRelative(job.next_run_at) : '—'}
                      </td>
                      <td className="text-small">
                        {channelNames.length ? channelNames.join(', ') : (
                          <span className="text-muted">None</span>
                        )}
                      </td>
                      <td>
                        <div className="row-actions">
                          {can('schedules.run') && (
                            <button
                              type="button"
                              className="button button--small"
                              onClick={() => handleTrigger(job)}
                              disabled={busyId === job.id}
                            >
                              Run
                            </button>
                          )}
                          {canManage && (
                            <button
                              type="button"
                              className="button button-secondary button--small"
                              onClick={() => setEditing(job)}
                            >
                              Edit
                            </button>
                          )}
                          {canManage && (
                            <button
                              type="button"
                              className="button button-secondary button--small"
                              onClick={() => act(
                                job.id,
                                () => (job.enabled ? schedulesApi.disable(job.id) : schedulesApi.enable(job.id)),
                                job.enabled ? `Disabled "${job.name}".` : `Enabled "${job.name}".`,
                              )}
                              disabled={busyId === job.id}
                            >
                              {job.enabled ? 'Disable' : 'Enable'}
                            </button>
                          )}
                          {can('schedules.delete') && (
                            <button
                              type="button"
                              className="button button-danger button--small"
                              onClick={() => handleDelete(job)}
                              disabled={busyId === job.id}
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

      {selectedJob && (
        <Card
          title={`Job details — ${selectedJob.name}`}
          actions={
            <div className="button-group">
              <button type="button" className="button button-secondary button--small" onClick={() => setSelectedJob(null)}>
                Close
              </button>
            </div>
          }
        >
          <div className="tabs" role="tablist" aria-label="Job detail view">
            <button
              type="button" role="tab" className="tab" aria-selected={detailTab === 'executions'}
              onClick={() => setDetailTab('executions')}
            >
              Executions
            </button>
            <button
              type="button" role="tab" className="tab" aria-selected={detailTab === 'metrics'}
              onClick={() => openMetrics(selectedJob)}
            >
              Metrics
            </button>
          </div>

          {detailTab === 'executions' && (
            executions.length === 0 ? (
              <EmptyState icon="⏱" title="No executions yet" description="Use Run to trigger the job manually, or wait for its next scheduled run." />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Started</th>
                      <th scope="col">Status</th>
                      <th scope="col">Duration</th>
                      <th scope="col">Exit code</th>
                      <th scope="col">Trigger</th>
                      <th scope="col">Attempt</th>
                      <th scope="col">Logs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {executions.map((execution) => (
                      <tr key={execution.id}>
                        <td className="nowrap" title={formatDateTime(execution.started_at)}>
                          {formatRelative(execution.started_at)}
                        </td>
                        <td><StatusBadge status={execution.status} /></td>
                        <td className="nowrap">{formatDuration(execution.duration_seconds)}</td>
                        <td>{execution.exit_code ?? '—'}</td>
                        <td>{execution.triggered_by}</td>
                        <td>{execution.retry_attempt || 0}</td>
                        <td>
                          <button
                            type="button"
                            className="button button-secondary button--small"
                            onClick={async () => {
                              try {
                                const { data } = await schedulesApi.getExecution(execution.job_id, execution.id);
                                setSelectedExecution(data);
                              } catch {
                                setSelectedExecution(execution);
                              }
                            }}
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}

          {detailTab === 'metrics' && (
            metrics === null ? <TableSkeleton rows={3} columns={5} /> : (
              <>
                {metrics.summary?.total_runs ? (
                  <div className="stats-grid">
                    <div className="stat-card">
                      <span className="stat-card__label">Runs ({metrics.days} days)</span>
                      <span className="stat-card__value">{metrics.summary.total_runs}</span>
                    </div>
                    <div className="stat-card">
                      <span className="stat-card__label">Success rate</span>
                      <span className="stat-card__value">
                        {metrics.summary.success_rate !== null ? `${metrics.summary.success_rate}%` : '—'}
                      </span>
                    </div>
                    <div className="stat-card">
                      <span className="stat-card__label">Average duration</span>
                      <span className="stat-card__value">
                        {formatDuration(metrics.summary.avg_duration)}
                      </span>
                    </div>
                  </div>
                ) : (
                  <p className="text-muted">No completed runs in the last {metrics.days} days.</p>
                )}

                {metrics.data.length > 0 && (
                  <>
                    <DurationChart data={metrics.data} />
                    <div className="table-wrap">
                      <table className="table">
                        <thead>
                          <tr>
                            <th scope="col">Date</th>
                            <th scope="col">Runs</th>
                            <th scope="col">Succeeded</th>
                            <th scope="col">Failed</th>
                            <th scope="col">Average</th>
                            <th scope="col">Slowest</th>
                          </tr>
                        </thead>
                        <tbody>
                          {metrics.data.map((day) => (
                            <tr key={day.run_date}>
                              <td className="nowrap">{day.run_date}</td>
                              <td>{day.total_runs}</td>
                              <td>{day.successful}</td>
                              <td>{day.failed}</td>
                              <td>{formatDuration(day.avg_duration)}</td>
                              <td>{formatDuration(day.max_duration)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </>
            )
          )}
        </Card>
      )}

      {selectedExecution && (
        <Modal
          title={`Execution #${selectedExecution.id}`}
          description={`${selectedExecution.status} · ${formatDuration(selectedExecution.duration_seconds)} · exit ${selectedExecution.exit_code ?? '—'}`}
          onClose={() => setSelectedExecution(null)}
          size="large"
        >
          <h4>Standard output</h4>
          <pre className="log-view">{selectedExecution.stdout || '(empty)'}</pre>
          <h4 style={{ marginTop: 'var(--space-4)' }}>Standard error</h4>
          <pre className="log-view log-view--error">{selectedExecution.stderr || '(empty)'}</pre>
        </Modal>
      )}

      {editing && (
        <JobModal
          job={editing === 'new' ? null : editing}
          channels={channels}
          onClose={() => setEditing(null)}
          onSaved={(message) => {
            setEditing(null);
            toast.success(message);
            loadJobs();
          }}
          onError={(message) => toast.error(message)}
        />
      )}
    </div>
  );
}

/** Average duration per day, with failures marked. */
function DurationChart({ data }) {
  const width = 680;
  const height = 170;
  const padding = { left: 48, right: 12, top: 12, bottom: 32 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const maxDuration = Math.max(...data.map((d) => d.max_duration || 0), 0.1);
  const step = chartWidth / data.length;
  const barWidth = Math.max(4, Math.min(28, step - 6));

  return (
    <figure style={{ overflowX: 'auto', margin: '0 0 var(--space-4)' }}>
      <figcaption className="visually-hidden">
        Average execution duration per day over the reporting period.
      </figcaption>
      <svg width={width} height={height} role="img" aria-label="Average execution duration per day">
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
          const y = padding.top + chartHeight * (1 - fraction);
          return (
            <g key={fraction}>
              <line x1={padding.left} x2={width - padding.right} y1={y} y2={y}
                stroke="var(--border)" strokeWidth={1} />
              <text x={padding.left - 6} y={y + 3} textAnchor="end" fontSize={10} fill="var(--text-muted)">
                {(maxDuration * fraction).toFixed(1)}s
              </text>
            </g>
          );
        })}
        {data.map((day, index) => {
          const x = padding.left + index * step + step / 2;
          const barHeight = day.avg_duration != null ? (day.avg_duration / maxDuration) * chartHeight : 0;
          const y = padding.top + chartHeight - barHeight;
          return (
            <g key={day.run_date}>
              <rect
                x={x - barWidth / 2} y={y} width={barWidth} height={barHeight}
                fill={day.failed > 0 ? 'var(--danger)' : 'var(--primary)'} rx={2}
              >
                <title>
                  {`${day.run_date}: ${day.total_runs} runs, avg ${(day.avg_duration || 0).toFixed(2)}s, ${day.failed} failed`}
                </title>
              </rect>
            </g>
          );
        })}
        {data.map((day, index) => (
          <text
            key={day.run_date}
            x={padding.left + index * step + step / 2}
            y={height - 8}
            textAnchor="middle"
            fontSize={10}
            fill="var(--text-muted)"
          >
            {day.run_date ? day.run_date.slice(5) : ''}
          </text>
        ))}
        <line x1={padding.left} x2={padding.left} y1={padding.top} y2={padding.top + chartHeight}
          stroke="var(--border-strong)" />
      </svg>
      <div className="row text-small text-muted">
        <span><span className="badge__dot" style={{ background: 'var(--primary)' }} /> Average duration</span>
        <span><span className="badge__dot" style={{ background: 'var(--danger)' }} /> Day included failures</span>
      </div>
    </figure>
  );
}

function JobModal({ job, channels, onClose, onSaved, onError }) {
  const isEdit = Boolean(job);
  const [form, setForm] = useState(() => (job ? {
    name: job.name,
    description: job.description || '',
    command: job.command || '',
    // Carried through so a job linked to a script keeps that link on save, and
    // so the command field knows it is optional.
    script_id: job.script_id ?? null,
    cron_expression: job.cron_expression,
    timezone: job.timezone,
    enabled: job.enabled,
    max_retries: job.max_retries,
    retry_delay_seconds: job.retry_delay_seconds,
    prevent_overlap: job.prevent_overlap,
    timeout_seconds: job.timeout_seconds ?? '',
    notify_channel_ids: job.notify_channel_ids || [],
  } : { ...EMPTY_FORM }));
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);

  // Show what the schedule actually means before it is saved; an invalid cron
  // expression used to be accepted silently and simply never run.
  useEffect(() => {
    let cancelled = false;
    const handle = setTimeout(() => {
      schedulesApi.previewCron(form.cron_expression, form.timezone, 3)
        .then(({ data }) => { if (!cancelled) setPreview({ ok: true, ...data }); })
        .catch((err) => { if (!cancelled) setPreview({ ok: false, message: apiError(err) }); });
    }, 350);
    return () => { cancelled = true; clearTimeout(handle); };
  }, [form.cron_expression, form.timezone]);

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        command: form.command.trim() || null,
        script_id: form.script_id ?? undefined,
        cron_expression: form.cron_expression.trim(),
        timezone: form.timezone.trim() || 'UTC',
        enabled: form.enabled,
        max_retries: Number(form.max_retries) || 0,
        retry_delay_seconds: Number(form.retry_delay_seconds) || 60,
        prevent_overlap: form.prevent_overlap,
        timeout_seconds: form.timeout_seconds === '' ? null : Number(form.timeout_seconds),
        notify_channel_ids: form.notify_channel_ids,
      };
      if (isEdit) {
        await schedulesApi.update(job.id, payload);
        onSaved(`Updated "${payload.name}".`);
      } else {
        await schedulesApi.create(payload);
        onSaved(`Created job "${payload.name}".`);
      }
    } catch (err) {
      onError(apiError(err));
      setBusy(false);
    }
  };

  return (
    <Modal title={isEdit ? `Edit "${job.name}"` : 'New scheduled job'} onClose={onClose} size="large">
      <form onSubmit={submit}>
        <div className="grid-2">
          <Field label="Name" required>
            {(props) => (
              <input {...props} type="text" required value={form.name} autoFocus
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            )}
          </Field>
          <Field label="Description">
            {(props) => (
              <input {...props} type="text" value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })} />
            )}
          </Field>
        </div>

        <Field
          label="Command"
          required={!form.script_id}
          hint={form.script_id
            ? "Optional for a script-linked job: leave blank to execute the script's own path."
            : "Runs through a shell on the backend host, with the backend's own privileges."}
        >
          {(props) => (
            <input {...props} type="text" required={!form.script_id} value={form.command}
              className="mono"
              placeholder="/usr/bin/python3 /srv/scripts/backup.py"
              onChange={(e) => setForm({ ...form, command: e.target.value })} />
          )}
        </Field>

        <div className="grid-2">
          <Field label="Cron expression" required hint="minute hour day-of-month month day-of-week">
            {(props) => (
              <input {...props} type="text" required value={form.cron_expression} className="mono"
                onChange={(e) => setForm({ ...form, cron_expression: e.target.value })} />
            )}
          </Field>
          <Field label="Timezone" hint="An IANA name such as Europe/Warsaw, or UTC.">
            {(props) => (
              <input {...props} type="text" value={form.timezone}
                onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
            )}
          </Field>
        </div>

        <div className="row" style={{ marginBottom: 'var(--space-3)' }}>
          {CRON_PRESETS.map((preset) => (
            <button
              key={preset.value}
              type="button"
              className="button button-secondary button--small"
              onClick={() => setForm({ ...form, cron_expression: preset.value })}
            >
              {preset.label}
            </button>
          ))}
        </div>

        {preview && (
          preview.ok ? (
            <div className="banner banner--info">
              <span className="banner__message">
                <strong>{preview.description}</strong>
                <br />
                Next runs: {preview.next_runs.map((run) => formatDateTime(run)).join(' · ') || 'none'}
              </span>
            </div>
          ) : (
            <div className="banner banner--error" role="alert">
              <span className="banner__message">{preview.message}</span>
            </div>
          )
        )}

        <div className="grid-3">
          <Field label="Max retries" hint="Extra attempts after a failure (0-10).">
            {(props) => (
              <input {...props} type="number" min={0} max={10} value={form.max_retries}
                onChange={(e) => setForm({ ...form, max_retries: e.target.value })} />
            )}
          </Field>
          <Field label="Retry delay (seconds)">
            {(props) => (
              <input {...props} type="number" min={1} value={form.retry_delay_seconds}
                onChange={(e) => setForm({ ...form, retry_delay_seconds: e.target.value })} />
            )}
          </Field>
          <Field label="Timeout (seconds)" hint="Blank means no timeout.">
            {(props) => (
              <input {...props} type="number" min={1} value={form.timeout_seconds}
                onChange={(e) => setForm({ ...form, timeout_seconds: e.target.value })} />
            )}
          </Field>
        </div>

        <fieldset>
          <legend>Behaviour</legend>
          <Checkbox
            label="Prevent overlapping runs"
            hint="Skip a scheduled run while the previous one is still going."
            checked={form.prevent_overlap}
            onChange={(value) => setForm({ ...form, prevent_overlap: value })}
          />
          <Checkbox
            label="Enabled"
            hint="A disabled job keeps its history but is never scheduled."
            checked={form.enabled}
            onChange={(value) => setForm({ ...form, enabled: value })}
          />
        </fieldset>

        <ChannelPicker
          channels={channels}
          value={form.notify_channel_ids}
          onChange={(ids) => setForm({ ...form, notify_channel_ids: ids })}
          label="Alert these channels when the job fails"
        />

        <div className="modal__footer">
          <button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="submit"
            className="button"
            disabled={
              busy
              || !form.name.trim()
              || (!form.command.trim() && !form.script_id)
              || (preview && !preview.ok)
            }
          >
            {busy ? 'Saving…' : (isEdit ? 'Save changes' : 'Create job')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
