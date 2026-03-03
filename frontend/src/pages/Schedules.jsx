import { useState, useEffect } from 'react';
import { schedulesApi } from '../services/api';

const STATUS_COLOR = {
  success: '#22c55e',
  failed: '#ef4444',
  running: '#3b82f6',
  timeout: '#f59e0b',
};

function StatusBadge({ status }) {
  const color = STATUS_COLOR[status] || '#94a3b8';
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 12,
      background: color, color: '#fff', fontWeight: 600, fontSize: 12,
    }}>
      {status || 'unknown'}
    </span>
  );
}

/** Simple SVG dual-bar chart: success (green) + failed (red) per day */
function DurationBarChart({ data }) {
  if (!data || data.length === 0) return <p>No execution data available yet.</p>;

  const W = 680, H = 180, padL = 48, padB = 36, padT = 16, padR = 12;
  const chartW = W - padL - padR;
  const chartH = H - padB - padT;
  const barW = Math.max(4, Math.min(28, Math.floor(chartW / data.length) - 4));

  const maxDur = Math.max(...data.map(d => d.max_duration || 0), 0.1);
  const maxRuns = Math.max(...data.map(d => d.total_runs || 0), 1);

  const xStep = chartW / data.length;

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg width={W} height={H} style={{ display: 'block', fontFamily: 'inherit', fontSize: 10 }}>
        {/* Y-axis labels (duration) */}
        {[0, 0.25, 0.5, 0.75, 1].map(frac => {
          const y = padT + chartH * (1 - frac);
          return (
            <g key={frac}>
              <line x1={padL} x2={W - padR} y1={y} y2={y}
                stroke="#e2e8f0" strokeWidth={1} />
              <text x={padL - 4} y={y + 3} textAnchor="end" fill="#94a3b8">
                {(maxDur * frac).toFixed(1)}s
              </text>
            </g>
          );
        })}

        {/* Bars: avg duration (blue) */}
        {data.map((d, i) => {
          const x = padL + i * xStep + xStep / 2;
          const h = d.avg_duration != null ? (d.avg_duration / maxDur) * chartH : 0;
          const y = padT + chartH - h;
          return (
            <g key={d.run_date}>
              <rect x={x - barW / 2} y={y} width={barW} height={h}
                fill="#3b82f6" opacity={0.8} rx={2} />
              {/* success count dot */}
              {d.failed > 0 && (
                <rect x={x - barW / 2} y={y} width={barW} height={Math.min(4, h)}
                  fill="#ef4444" rx={2} />
              )}
            </g>
          );
        })}

        {/* X-axis labels */}
        {data.map((d, i) => {
          const x = padL + i * xStep + xStep / 2;
          const label = d.run_date ? d.run_date.slice(5) : ''; // MM-DD
          return (
            <text key={d.run_date} x={x} y={H - 4} textAnchor="middle" fill="#94a3b8">
              {label}
            </text>
          );
        })}

        {/* Y-axis line */}
        <line x1={padL} x2={padL} y1={padT} y2={padT + chartH} stroke="#cbd5e1" />
      </svg>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, marginTop: 4, fontSize: 11, color: '#64748b' }}>
        <span><span style={{ display: 'inline-block', width: 10, height: 10, background: '#3b82f6', borderRadius: 2, marginRight: 4 }} />Avg duration (s)</span>
        <span><span style={{ display: 'inline-block', width: 10, height: 4, background: '#ef4444', borderRadius: 2, marginRight: 4 }} />Has failures</span>
      </div>
    </div>
  );
}

function Schedules() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    command: '',
    cron_expression: '0 * * * *',
    timezone: 'UTC',
    enabled: true,
    max_retries: 0,
    retry_delay_seconds: 60,
    prevent_overlap: true,
    timeout_seconds: '',
  });
  const [selectedJob, setSelectedJob] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [selectedExecution, setSelectedExecution] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [metricsView, setMetricsView] = useState(false);

  useEffect(() => {
    loadJobs();
  }, []);

  const loadJobs = async () => {
    try {
      setLoading(true);
      const res = await schedulesApi.list();
      setJobs(res.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    const payload = {
      ...formData,
      timeout_seconds: formData.timeout_seconds ? parseInt(formData.timeout_seconds) : null,
    };
    try {
      await schedulesApi.create(payload);
      setShowForm(false);
      setFormData({ name: '', description: '', command: '', cron_expression: '0 * * * *', timezone: 'UTC', enabled: true, max_retries: 0, retry_delay_seconds: 60, prevent_overlap: true, timeout_seconds: '' });
      loadJobs();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this job?')) return;
    try {
      await schedulesApi.delete(id);
      if (selectedJob?.id === id) setSelectedJob(null);
      loadJobs();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleToggle = async (job) => {
    try {
      if (job.enabled) {
        await schedulesApi.disable(job.id);
      } else {
        await schedulesApi.enable(job.id);
      }
      loadJobs();
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleTrigger = async (job) => {
    try {
      const res = await schedulesApi.trigger(job.id);
      alert(`Job triggered! Execution ID: ${res.data.execution_id}`);
      if (selectedJob?.id === job.id) {
        loadExecutions(job.id);
      }
    } catch (err) {
      alert('Error: ' + (err.response?.data?.detail || err.message));
    }
  };

  const loadExecutions = async (jobId) => {
    try {
      const res = await schedulesApi.listExecutions(jobId);
      setExecutions(res.data);
    } catch {
      setExecutions([]);
    }
  };

  const loadMetrics = async (jobId) => {
    try {
      const res = await schedulesApi.getMetrics(jobId);
      setMetrics(res.data);
      setMetricsView(true);
    } catch (err) {
      alert('Error loading metrics: ' + err.message);
    }
  };

  const handleSelectJob = async (job) => {
    setSelectedJob(job);
    setSelectedExecution(null);
    setMetricsView(false);
    await loadExecutions(job.id);
  };

  const handleSelectExecution = async (exec) => {
    try {
      const res = await schedulesApi.getExecution(exec.job_id, exec.id);
      setSelectedExecution(res.data);
    } catch {
      setSelectedExecution(exec);
    }
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Error: {error}</div>;

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>Scheduled Jobs</h2>
          <p>Manage cron jobs with timezone support, overlap prevention, auto-retry, and log capture.</p>
        </div>
        <button className="button" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ New Job'}
        </button>
      </div>

      {showForm && (
        <div className="card">
          <h3>Create Scheduled Job</h3>
          <form onSubmit={handleCreate}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
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
              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label>Command *</label>
                <input className="input" required value={formData.command}
                  placeholder="e.g. /usr/bin/python3 /scripts/backup.py"
                  onChange={e => setFormData({ ...formData, command: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Cron expression *</label>
                <input className="input" required value={formData.cron_expression}
                  placeholder="0 * * * *"
                  onChange={e => setFormData({ ...formData, cron_expression: e.target.value })} />
                <small style={{ color: '#64748b' }}>minute hour day month weekday</small>
              </div>
              <div className="form-group">
                <label>Timezone</label>
                <input className="input" value={formData.timezone}
                  placeholder="UTC / America/New_York / Europe/London"
                  onChange={e => setFormData({ ...formData, timezone: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Max retries</label>
                <input className="input" type="number" min="0" value={formData.max_retries}
                  onChange={e => setFormData({ ...formData, max_retries: parseInt(e.target.value) })} />
              </div>
              <div className="form-group">
                <label>Retry delay (seconds)</label>
                <input className="input" type="number" min="1" value={formData.retry_delay_seconds}
                  onChange={e => setFormData({ ...formData, retry_delay_seconds: parseInt(e.target.value) })} />
              </div>
              <div className="form-group">
                <label>Timeout (seconds, optional)</label>
                <input className="input" type="number" min="1" value={formData.timeout_seconds}
                  onChange={e => setFormData({ ...formData, timeout_seconds: e.target.value })} />
              </div>
              <div className="form-group" style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
                <label>
                  <input type="checkbox" checked={formData.prevent_overlap}
                    onChange={e => setFormData({ ...formData, prevent_overlap: e.target.checked })} />
                  {' '}Prevent overlap
                </label>
                <label>
                  <input type="checkbox" checked={formData.enabled}
                    onChange={e => setFormData({ ...formData, enabled: e.target.checked })} />
                  {' '}Enabled
                </label>
              </div>
            </div>
            <button className="button" type="submit">Create Job</button>
          </form>
        </div>
      )}

      <div className="card">
        <h3>All Jobs</h3>
        {jobs.length === 0 ? (
          <p>No scheduled jobs configured.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Cron</th>
                <th>TZ</th>
                <th>Last Run</th>
                <th>Last Status</th>
                <th>Overlap</th>
                <th>Retries</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(job => (
                <tr key={job.id} style={{ cursor: 'pointer', opacity: job.enabled ? 1 : 0.5 }}
                  onClick={() => handleSelectJob(job)}>
                  <td>
                    <strong>{job.name}</strong>
                    {job.description && <div style={{ fontSize: 12, color: '#64748b' }}>{job.description}</div>}
                    <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'monospace' }}>{job.command}</div>
                  </td>
                  <td><code>{job.cron_expression}</code></td>
                  <td>{job.timezone}</td>
                  <td>{job.last_run_at ? new Date(job.last_run_at).toLocaleString() : 'Never'}</td>
                  <td>{job.last_status ? <StatusBadge status={job.last_status} /> : '—'}</td>
                  <td>{job.prevent_overlap ? '✓' : '✗'}</td>
                  <td>{job.max_retries}</td>
                  <td onClick={e => e.stopPropagation()} style={{ whiteSpace: 'nowrap' }}>
                    <button className="button" style={{ marginRight: 4 }} onClick={() => handleTrigger(job)}>Run</button>
                    <button className="button" style={{ marginRight: 4 }} onClick={() => handleToggle(job)}>
                      {job.enabled ? 'Pause' : 'Enable'}
                    </button>
                    <button className="button" onClick={() => handleDelete(job.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selectedJob && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3>Job Details — {selectedJob.name}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="button" onClick={() => loadMetrics(selectedJob.id)}>📊 Metrics</button>
              <button className="button" onClick={() => setSelectedJob(null)}>Close</button>
            </div>
          </div>

          {metricsView && metrics ? (
            <div>
              <h4>Execution Metrics (last {metrics.days} days)</h4>
              <DurationBarChart data={metrics.data} />
              {metrics.data.length === 0 ? null : (
                <table className="table" style={{ marginTop: 16 }}>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Runs</th>
                      <th>✓ Success</th>
                      <th>✗ Failed</th>
                      <th>Avg Duration (s)</th>
                      <th>Max Duration (s)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.data.map(d => (
                      <tr key={d.run_date}>
                        <td>{d.run_date}</td>
                        <td>{d.total_runs}</td>
                        <td style={{ color: '#22c55e' }}>{d.successful}</td>
                        <td style={{ color: '#ef4444' }}>{d.failed}</td>
                        <td>{d.avg_duration !== null ? d.avg_duration.toFixed(2) : '—'}</td>
                        <td>{d.max_duration !== null ? d.max_duration.toFixed(2) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <button className="button" style={{ marginTop: 8 }} onClick={() => setMetricsView(false)}>← Back to executions</button>
            </div>
          ) : (
            <div>
              <h4>Recent Executions</h4>
              {executions.length === 0 ? (
                <p>No executions yet. Click <strong>Run</strong> to trigger manually.</p>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Started</th>
                      <th>Ended</th>
                      <th>Status</th>
                      <th>Duration</th>
                      <th>Exit code</th>
                      <th>Triggered by</th>
                      <th>Retry</th>
                      <th>Logs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {executions.map(ex => (
                      <tr key={ex.id}>
                        <td>{new Date(ex.started_at).toLocaleString()}</td>
                        <td>{ex.ended_at ? new Date(ex.ended_at).toLocaleString() : '—'}</td>
                        <td><StatusBadge status={ex.status} /></td>
                        <td>{ex.duration_seconds != null ? `${ex.duration_seconds.toFixed(2)}s` : '—'}</td>
                        <td>{ex.exit_code != null ? ex.exit_code : '—'}</td>
                        <td>{ex.triggered_by}</td>
                        <td>{ex.retry_attempt}</td>
                        <td>
                          <button className="button" onClick={() => handleSelectExecution(ex)}>View logs</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      )}

      {selectedExecution && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <h3>Execution Logs — #{selectedExecution.id}</h3>
            <button className="button" onClick={() => setSelectedExecution(null)}>Close</button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <h4>stdout</h4>
              <pre style={{ background: '#0f172a', color: '#e2e8f0', padding: 12, borderRadius: 6, fontSize: 12, overflowX: 'auto', minHeight: 80 }}>
                {selectedExecution.stdout || '(empty)'}
              </pre>
            </div>
            <div>
              <h4>stderr</h4>
              <pre style={{ background: '#0f172a', color: '#fca5a5', padding: 12, borderRadius: 6, fontSize: 12, overflowX: 'auto', minHeight: 80 }}>
                {selectedExecution.stderr || '(empty)'}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Schedules;
