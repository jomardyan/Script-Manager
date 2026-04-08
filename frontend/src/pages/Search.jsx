import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { searchApi, tagsApi, folderRootsApi } from '../services/api';

function Search() {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tags, setTags] = useState([]);
  const [roots, setRoots] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalResults, setTotalResults] = useState(0);
  const [hasSearched, setHasSearched] = useState(false);
  const [searchParams, setSearchParams] = useState({
    query: '',
    languages: [],
    tags: [],
    status: [],
    root_ids: [],
    sort_by: 'name',
    sort_order: 'asc',
    page: 1,
    page_size: 50
  });

  useEffect(() => {
    loadFilters();
  }, []);

  useEffect(() => {
    if (hasSearched) {
      handleSearch();
    }
  }, [page, searchParams.page_size, searchParams.sort_by, searchParams.sort_order]);

  const loadFilters = async () => {
    try {
      const [tagsRes, rootsRes] = await Promise.all([
        tagsApi.list(),
        folderRootsApi.list()
      ]);
      setTags(tagsRes.data);
      setRoots(rootsRes.data);
    } catch (err) {
      console.error('Error loading filters:', err);
    }
  };

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    try {
      setLoading(true);
      setError(null);
      const params = {
        ...searchParams,
        page,
        languages: searchParams.languages.length > 0 ? searchParams.languages : undefined,
        tags: searchParams.tags.length > 0 ? searchParams.tags : undefined,
        status: searchParams.status.length > 0 ? searchParams.status : undefined,
        root_ids: searchParams.root_ids.length > 0 ? searchParams.root_ids : undefined,
      };
      const response = await searchApi.search(params);
      setResults(response.data.items);
      setTotalPages(response.data.total_pages);
      setTotalResults(response.data.total);
      setHasSearched(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleArrayValue = (array, value) => {
    if (array.includes(value)) {
      return array.filter(v => v !== value);
    } else {
      return [...array, value];
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (page !== 1) {
      setPage(1);
      return;
    }
    handleSearch();
  };

  const handleReset = () => {
    setSearchParams({
      query: '',
      languages: [],
      tags: [],
      status: [],
      root_ids: [],
      sort_by: 'name',
      sort_order: 'asc',
      page: 1,
      page_size: 50
    });
    setPage(1);
    setResults([]);
    setTotalPages(1);
    setTotalResults(0);
    setError(null);
    setHasSearched(false);
  };

  return (
    <div>
      <div className="page-header">
        <h2>Advanced Search</h2>
        <p>Search scripts with multiple filters</p>
      </div>

      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Search Query</label>
            <input
              type="text"
              value={searchParams.query}
              onChange={(e) => setSearchParams({ ...searchParams, query: e.target.value })}
              placeholder="Search by name or path..."
            />
          </div>

          <div className="form-group">
            <label>Languages</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
              {['Python', 'PowerShell', 'Bash', 'SQL', 'JavaScript'].map(lang => (
                <label key={lang} style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={searchParams.languages.includes(lang)}
                    onChange={() => setSearchParams({
                      ...searchParams,
                      languages: toggleArrayValue(searchParams.languages, lang)
                    })}
                  />
                  {lang}
                </label>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>Status</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
              {['active', 'draft', 'deprecated', 'archived'].map(status => (
                <label key={status} style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={searchParams.status.includes(status)}
                    onChange={() => setSearchParams({
                      ...searchParams,
                      status: toggleArrayValue(searchParams.status, status)
                    })}
                  />
                  {status}
                </label>
              ))}
            </div>
          </div>

          {tags.length > 0 && (
            <div className="form-group">
              <label>Tags</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                {tags.slice(0, 10).map(tag => (
                  <label key={tag.id} style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={searchParams.tags.includes(tag.name)}
                      onChange={() => setSearchParams({
                        ...searchParams,
                        tags: toggleArrayValue(searchParams.tags, tag.name)
                      })}
                    />
                    {tag.name}
                  </label>
                ))}
              </div>
            </div>
          )}

          {roots.length > 0 && (
            <div className="form-group">
              <label>Folder Roots</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                {roots.map(root => (
                  <label key={root.id} style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={searchParams.root_ids.includes(root.id)}
                      onChange={() => setSearchParams({
                        ...searchParams,
                        root_ids: toggleArrayValue(searchParams.root_ids, root.id)
                      })}
                    />
                    {root.name}
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="filters">
            <select
              value={searchParams.sort_by}
              onChange={(e) => {
                setSearchParams({ ...searchParams, sort_by: e.target.value });
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
              value={searchParams.sort_order}
              onChange={(e) => {
                setSearchParams({ ...searchParams, sort_order: e.target.value });
                setPage(1);
              }}
            >
              <option value="asc">Order: Ascending</option>
              <option value="desc">Order: Descending</option>
            </select>

            <select
              value={searchParams.page_size}
              onChange={(e) => {
                setSearchParams({ ...searchParams, page_size: Number(e.target.value) });
                setPage(1);
              }}
            >
              <option value={25}>25 / page</option>
              <option value={50}>50 / page</option>
              <option value={100}>100 / page</option>
            </select>
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button type="submit" className="button">Search</button>
            <button type="button" className="button button-secondary" onClick={handleReset}>Clear</button>
          </div>
        </form>
      </div>

      {error && <div className="error">Error: {error}</div>}

      {loading ? (
        <div className="loading">Searching...</div>
      ) : results.length > 0 ? (
        <>
          <div className="card">
            <h3>Results ({results.length} of {totalResults})</h3>
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Language</th>
                  <th>Path</th>
                  <th>Status</th>
                  <th>Tags</th>
                </tr>
              </thead>
              <tbody>
                {results.map(script => (
                  <tr key={script.id}>
                    <td>
                      <Link to={`/scripts/${script.id}`}>{script.name}</Link>
                    </td>
                    <td>{script.language || '-'}</td>
                    <td title={script.path}>
                      {script.path.length > 60 ? '...' + script.path.slice(-60) : script.path}
                    </td>
                    <td>
                      <span className={`status-badge status-${(script.status || 'unknown').toLowerCase()}`}>
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
      ) : hasSearched ? (
        <div className="card">
          <p>No results found for the current filters.</p>
        </div>
      ) : null}
    </div>
  );
}

export default Search;
