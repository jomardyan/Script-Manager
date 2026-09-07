import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  apiError, folderRootsApi, ftsApi, notificationsApi, schedulesApi, searchApi,
} from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Card, EmptyState, ErrorBanner, PageHeader, StatusBadge, TableSkeleton,
} from '../components/ui';
import { formatDateTime, formatRelative } from '../lib/format';

/**
 * Overview of the collection and of anything that needs attention.
 *
 * The previous dashboard showed three counters and a list of folder roots and
 * ignored the operational half of the product entirely, so an open incident or
 * a failing job was invisible until you went looking for it.
 */
export default function Dashboard() {
  const { can, isAdmin, config } = useAuth();
  const authOff = config?.auth_required === false;

  const [state, setState] = useState({ loading: true, error: null });
  const [stats, setStats] = useState(null);
  const [roots, setRoots] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [fts, setFts] = useState(null);
  const [incidentStats, setIncidentStats] = useState(null);

  const load = useCallback(async () => {
    setState({ loading: true, error: null });

    // Every panel is optional: a viewer without the matching permission simply
    // sees fewer panels rather than an error page.
    const wanted = [
      ['stats', can('search.read'), () => searchApi.getStats()],
      ['roots', can('roots.read'), () => folderRootsApi.stats()],
      ['incidents', can('incidents.read'), () => notificationsApi.listIncidents({ status: 'open', limit: 5 })],
      // The list above is capped for display; the real count comes from the
      // stats endpoint, so the tile does not silently plateau at 5.
      ['incidentStats', can('incidents.read'), () => notificationsApi.incidentStats()],
      ['jobs', can('schedules.read'), () => schedulesApi.list()],
      ['fts', can('search.read'), () => ftsApi.status()],
    ];

    const results = await Promise.allSettled(
      wanted.map(([, allowed, run]) => (allowed || authOff ? run() : Promise.resolve(null))),
    );

    const byKey = {};
    wanted.forEach(([key], index) => { byKey[key] = results[index]; });

    setStats(byKey.stats?.status === 'fulfilled' ? byKey.stats.value?.data ?? null : null);
    setRoots(byKey.roots?.status === 'fulfilled' ? byKey.roots.value?.data ?? [] : []);
    setIncidents(byKey.incidents?.status === 'fulfilled' ? byKey.incidents.value?.data ?? [] : []);
    setJobs(byKey.jobs?.status === 'fulfilled' ? byKey.jobs.value?.data ?? [] : []);
    setFts(byKey.fts?.status === 'fulfilled' ? byKey.fts.value?.data ?? null : null);
    setIncidentStats(
      byKey.incidentStats?.status === 'fulfilled' ? byKey.incidentStats.value?.data ?? null : null,
    );

    // Only report a failure when everything the account could see failed,
    // which is the signal that the server (not a permission) is the problem.
    const attempted = results.filter((r, i) => wanted[i][1] || authOff);
    const failed = attempted.filter((r) => r.status === 'rejected');
    setState({
      loading: false,
      error: attempted.length > 0 && failed.length === attempted.length
        ? apiError(failed[0].reason)
        : null,
    });
  }, [can, authOff]);

  useEffect(() => { load(); }, [load]);

  const openIncidentCount = incidentStats?.open ?? incidents.length;
  const failingJobs = jobs.filter((j) => j.last_status && j.last_status !== 'success');
  const nextJob = jobs
    .filter((j) => j.enabled && j.next_run_at)
    .sort((a, b) => String(a.next_run_at).localeCompare(String(b.next_run_at)))[0];
  const staleRoots = roots.filter((r) => !r.last_scan_time || r.path_exists === false);

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Overview of your script collection and its operational health."
        actions={
          <button type="button" className="button button-secondary" onClick={load} disabled={state.loading}>
            Refresh
          </button>
        }
      />

      <ErrorBanner message={state.error} onRetry={load} onDismiss={() => setState((s) => ({ ...s, error: null }))} />

      {state.loading ? (
        <Card><TableSkeleton rows={4} columns={4} /></Card>
      ) : (
        <>
          <div className="stats-grid">
            <StatTile label="Scripts" value={stats?.total_scripts ?? '—'} to="/scripts" hint="Indexed and present on disk" />
            <StatTile label="Folder roots" value={stats?.total_roots ?? '—'} to="/folder-roots" hint={`${staleRoots.length} need attention`} tone={staleRoots.length ? 'warning' : undefined} />
            <StatTile label="Tags" value={stats?.total_tags ?? '—'} to="/tags" hint="Available for classification" />
            <StatTile
              label="Open incidents"
              value={openIncidentCount}
              to="/notifications"
              hint={openIncidentCount ? 'Needs acknowledgement' : 'All clear'}
              tone={openIncidentCount ? 'danger' : undefined}
            />
          </div>

          {incidents.length > 0 && (
            <Card
              title={`Open incidents (${openIncidentCount})`}
              description={
                openIncidentCount > incidents.length
                  ? `Raised by heartbeat monitors and scheduled jobs. Showing the ${incidents.length} most recent.`
                  : 'Raised by heartbeat monitors and scheduled jobs.'
              }
              actions={<Link className="button button-secondary button--small" to="/notifications">View all</Link>}
            >
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Title</th>
                      <th scope="col">Source</th>
                      <th scope="col">Severity</th>
                      <th scope="col">Raised</th>
                    </tr>
                  </thead>
                  <tbody>
                    {incidents.map((incident) => (
                      <tr key={incident.id}>
                        <td>{incident.title}</td>
                        <td className="text-muted">{incident.source_type} #{incident.source_id}</td>
                        <td><StatusBadge status={incident.severity} /></td>
                        <td className="nowrap" title={formatDateTime(incident.created_at)}>
                          {formatRelative(incident.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          <div className="grid-2">
            {(can('scripts.read') || authOff) && (
              <Card title="Scripts by language">
                {stats?.by_language && Object.keys(stats.by_language).length > 0 ? (
                  <BreakdownList data={stats.by_language} total={stats.total_scripts} />
                ) : (
                  <EmptyState
                    icon="◈"
                    title="No scripts indexed yet"
                    description="Add a folder root and run a scan to populate the index."
                    action={<Link className="button" to="/folder-roots">Add a folder root</Link>}
                  />
                )}
              </Card>
            )}

            {(can('scripts.read') || authOff) && (
              <Card title="Scripts by lifecycle status">
                {stats?.by_status && Object.keys(stats.by_status).length > 0 ? (
                  <BreakdownList data={stats.by_status} total={stats.total_scripts} />
                ) : (
                  <p className="text-muted">Nothing classified yet.</p>
                )}
              </Card>
            )}
          </div>

          {(can('schedules.read') || authOff) && jobs.length > 0 && (
            <Card
              title="Scheduled jobs"
              description={
                nextJob
                  ? `Next run: ${nextJob.name} ${formatRelative(nextJob.next_run_at)}`
                  : 'No enabled jobs have an upcoming run.'
              }
              actions={<Link className="button button-secondary button--small" to="/schedules">Manage</Link>}
            >
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Job</th>
                      <th scope="col">Schedule</th>
                      <th scope="col">Last result</th>
                      <th scope="col">Next run</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.slice(0, 6).map((job) => (
                      <tr key={job.id}>
                        <td>
                          <strong>{job.name}</strong>
                          {!job.enabled && <span className="text-small text-muted"> (disabled)</span>}
                        </td>
                        <td><code className="text-small">{job.cron_expression}</code></td>
                        <td>{job.last_status ? <StatusBadge status={job.last_status} /> : <span className="text-muted">Never run</span>}</td>
                        <td className="nowrap" title={formatDateTime(job.next_run_at)}>
                          {job.enabled && job.next_run_at ? formatRelative(job.next_run_at) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {failingJobs.length > 0 && (
                <p className="text-small" style={{ marginTop: 'var(--space-3)', color: 'var(--danger)' }}>
                  {failingJobs.length} job{failingJobs.length === 1 ? '' : 's'} last finished unsuccessfully.
                </p>
              )}
            </Card>
          )}

          {(can('roots.read') || authOff) && (
            <Card
              title="Folder roots"
              actions={<Link className="button button-secondary button--small" to="/folder-roots">Manage</Link>}
            >
              {roots.length === 0 ? (
                <EmptyState
                  icon="▣"
                  title="No folder roots configured"
                  description="A folder root tells Script Manager which directories to index."
                  action={<Link className="button" to="/folder-roots">Add a folder root</Link>}
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
                          <td className="text-muted text-small" title={root.path}>{root.path}</td>
                          <td>
                            {root.script_count ?? 0}
                            {root.missing_count > 0 && (
                              <span className="text-small text-muted"> ({root.missing_count} missing)</span>
                            )}
                          </td>
                          <td className="nowrap" title={formatDateTime(root.last_scan_time)}>
                            {root.last_scan_time ? formatRelative(root.last_scan_time) : 'Never'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}

          {fts && (can('search.read') || authOff) && (
            <Card
              title="Full-text index"
              description="Content indexing must be enabled per folder root."
              actions={<Link className="button button-secondary button--small" to="/search">Search contents</Link>}
            >
              <div className="row row--between" style={{ marginBottom: 'var(--space-2)' }}>
                <span>{fts.indexed_scripts} of {fts.total_scripts} scripts indexed</span>
                <strong>{fts.coverage_percent}%</strong>
              </div>
              <div className="meter">
                <div className="meter__fill" style={{ width: `${Math.min(100, fts.coverage_percent || 0)}%` }} />
              </div>
            </Card>
          )}

          {isAdmin && !authOff && incidents.length === 0 && jobs.length === 0 && roots.length === 0 && (
            <Card title="Getting started">
              <ol className="stack" style={{ paddingLeft: 'var(--space-5)' }}>
                <li>Add a <Link to="/folder-roots">folder root</Link> pointing at your scripts and run a scan.</li>
                <li>Create <Link to="/tags">tags</Link> to classify what the scan finds.</li>
                <li>Add a <Link to="/notifications">notification channel</Link> so alerts reach you.</li>
                <li>Set up <Link to="/monitors">heartbeat monitors</Link> or <Link to="/schedules">scheduled jobs</Link>.</li>
              </ol>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function StatTile({ label, value, hint, to, tone }) {
  const body = (
    <>
      <span className="stat-card__label">{label}</span>
      <span className="stat-card__value">{value}</span>
      {hint && <span className="stat-card__hint">{hint}</span>}
    </>
  );
  const className = `stat-card${tone ? ` stat-card--${tone}` : ''}${to ? ' stat-card__link' : ''}`;
  return to ? <Link className={className} to={to}>{body}</Link> : <div className={className}>{body}</div>;
}

function BreakdownList({ data, total }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(([, count]) => count), 1);

  return (
    <ul className="stack" style={{ listStyle: 'none' }}>
      {entries.map(([label, count]) => (
        <li key={label}>
          <div className="row row--between text-small">
            <span>{label}</span>
            <span className="text-muted">
              {count}
              {total ? ` · ${Math.round((count / total) * 100)}%` : ''}
            </span>
          </div>
          <div className="meter" style={{ marginTop: 4 }}>
            <div className="meter__fill" style={{ width: `${(count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
