import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { scriptsApi } from '../services/api';

function Scripts() {
  const [scripts, setScripts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [totalPages, setTotalPages] = useState(1);
  const [totalResults, setTotalResults] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');
  const [filters, setFilters] = useState({
    language: '',
    status: ''
  });

  useEffect(() => {
    loadScripts();
  }, [page, pageSize, appliedSearch, filters, sortBy, sortOrder]);

  const loadScripts = async () => {
    try {
      setLoading(true);
      setError(null);
      const params = {
        page,
        page_size: pageSize,
        search: appliedSearch || undefined,
        language: filters.language || undefined,
        status: filters.status || undefined,
        sort_by: sortBy,
        sort_order: sortOrder
      };
      const response = await scriptsApi.list(params);
      setScripts(response.data.items);
      setTotalPages(response.data.total_pages);
      setTotalResults(response.data.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    setAppliedSearch(searchInput.trim());
    setPage(1);
  };

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
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
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

        <select
          value={sortBy}
          onChange={(e) => {
            setSortBy(e.target.value);
            setPage(1);
          }}
        >
          <option value="name">Sort: Name</option>
          <option value="mtime">Sort: Modified</option>
          <option value="size">Sort: Size</option>
          <option value="language">Sort: Language</option>
          <option value="status">Sort: Status</option>
          <option value="path">Sort: Path</option>
        </select>

        <select
          value={sortOrder}
          onChange={(e) => {
            setSortOrder(e.target.value);
            setPage(1);
          }}
        >
          <option value="asc">Order: Ascending</option>
          <option value="desc">Order: Descending</option>
        </select>

        <select
          value={pageSize}
          onChange={(e) => {
            setPageSize(Number(e.target.value));
            setPage(1);
          }}
        >
          <option value={25}>25 / page</option>
          <option value={50}>50 / page</option>
          <option value={100}>100 / page</option>
        </select>
      </div>

      {loading ? (
        <div className="loading">Loading...</div>
      ) : (
        <>
          <div className="card">
            <p style={{ marginBottom: '12px', color: '#7f8c8d' }}>
              Showing {scripts.length} of {totalResults} scripts
            </p>
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
