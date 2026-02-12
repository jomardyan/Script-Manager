import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { scriptsApi } from '../services/api';

/**
 * List and filter indexed scripts.
 */
function Scripts() {
  const [scripts, setScripts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState({
    language: '',
    status: ''
  });

  useEffect(() => {
    loadScripts();
  }, [page, search, filters]);

  /**
   * Fetch scripts using the current filters and pagination.
   */
  const loadScripts = async () => {
    try {
      setLoading(true);
      const params = {
        page,
        page_size: 50,
        search: search || undefined,
        language: filters.language || undefined,
        status: filters.status || undefined
      };
      const response = await scriptsApi.list(params);
      setScripts(response.data.items);
      setTotalPages(response.data.total_pages);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Apply the search term and reload results.
   */
  const handleSearch = (e) => {
    e.preventDefault();
    setPage(1);
    loadScripts();
  };

  /**
   * Resolve the status badge class name.
   */
  const getStatusClass = (status) => {
    if (!status) return 'status-badge';
    return `status-badge status-${status.toLowerCase()}`;
  };

  if (error) return <div className="error">Error: {error}</div>;

  return (
    <div>
      <div className="page-header">
        <h2>Scripts</h2>
        <p>Browse and manage your script collection</p>
      </div>

      <form onSubmit={handleSearch} className="search-bar">
        <input
          type="text"
          placeholder="Search scripts by name or path..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </form>

      <div className="filters">
        <select
          value={filters.language}
          onChange={(e) => {
            setFilters({ ...filters, language: e.target.value });
            setPage(1);
          }}
        >
          <option value="">All Languages</option>
          <option value="Python">Python</option>
          <option value="PowerShell">PowerShell</option>
          <option value="Bash">Bash</option>
          <option value="SQL">SQL</option>
          <option value="JavaScript">JavaScript</option>
        </select>

        <select
          value={filters.status}
          onChange={(e) => {
            setFilters({ ...filters, status: e.target.value });
            setPage(1);
          }}
        >
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="draft">Draft</option>
          <option value="deprecated">Deprecated</option>
          <option value="archived">Archived</option>
        </select>
      </div>

      {loading ? (
        <div className="loading">Loading...</div>
      ) : (
        <>
          <div className="card">
            {scripts.length > 0 ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Language</th>
                    <th>Path</th>
                    <th>Size</th>
                    <th>Modified</th>
                    <th>Status</th>
                    <th>Tags</th>
                  </tr>
                </thead>
                <tbody>
                  {scripts.map(script => (
                    <tr key={script.id}>
                      <td>
                        <Link to={`/scripts/${script.id}`}>{script.name}</Link>
                      </td>
                      <td>{script.language || '-'}</td>
                      <td title={script.path}>{script.path.length > 50 ? '...' + script.path.slice(-50) : script.path}</td>
                      <td>{script.size ? Math.round(script.size / 1024) + ' KB' : '-'}</td>
                      <td>{script.mtime ? new Date(script.mtime).toLocaleDateString() : '-'}</td>
                      <td>
                        <span className={getStatusClass(script.status)}>
                          {script.status || 'unknown'}
                        </span>
                      </td>
                      <td>
                        {script.tags?.map(tag => (
                          <span key={tag} className="tag">{tag}</span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>No scripts found. Try scanning a folder root or adjusting your filters.</p>
            )}
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
              >
                Previous
              </button>
              <span style={{ padding: '8px 12px' }}>
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page === totalPages}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default Scripts;
