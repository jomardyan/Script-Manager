import { useState, useEffect } from 'react';
import { searchApi, folderRootsApi } from '../services/api';

/**
 * Dashboard overview showing aggregate stats and folder roots.
 */
function Dashboard() {
  const [stats, setStats] = useState(null);
  const [roots, setRoots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  /**
   * Load statistics and folder roots for the dashboard.
   */
  const loadData = async () => {
    try {
      setLoading(true);
      const [statsRes, rootsRes] = await Promise.all([
        searchApi.getStats(),
        folderRootsApi.list()
      ]);
      setStats(statsRes.data);
      setRoots(rootsRes.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Error: {error}</div>;

  return (
    <div>
      <div className="page-header">
        <h2>Dashboard</h2>
        <p>Overview of your script collection</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <h3>Total Scripts</h3>
          <div className="value">{stats?.total_scripts || 0}</div>
        </div>
        <div className="stat-card">
          <h3>Folder Roots</h3>
          <div className="value">{stats?.total_roots || 0}</div>
        </div>
        <div className="stat-card">
          <h3>Total Tags</h3>
          <div className="value">{stats?.total_tags || 0}</div>
        </div>
      </div>

      <div className="card">
        <h3>Scripts by Language</h3>
        {stats?.by_language && Object.keys(stats.by_language).length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Language</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stats.by_language).map(([lang, count]) => (
                <tr key={lang}>
                  <td>{lang}</td>
                  <td>{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No scripts indexed yet</p>
        )}
      </div>

      <div className="card">
        <h3>Folder Roots</h3>
        {roots.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Path</th>
                <th>Last Scan</th>
              </tr>
            </thead>
            <tbody>
              {roots.map(root => (
                <tr key={root.id}>
                  <td>{root.name}</td>
                  <td>{root.path}</td>
                  <td>{root.last_scan_time ? new Date(root.last_scan_time).toLocaleString() : 'Never'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No folder roots configured. Add a folder root to start indexing scripts.</p>
        )}
      </div>
    </div>
  );
}

export default Dashboard;
