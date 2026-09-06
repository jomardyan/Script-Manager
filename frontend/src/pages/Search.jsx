import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  apiError, folderRootsApi, ftsApi, savedSearchesApi, searchApi, tagsApi,
} from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Card, EmptyState, ErrorBanner, Field, PageHeader, Pagination, StatusBadge,
  TableSkeleton, TagChip,
} from '../components/ui';
import Modal from '../components/Modal';
import { useConfirm } from '../components/ConfirmDialog';
import { useToast } from '../context/ToastContext';
import { formatBytes, formatDate, formatDateTime, truncatePath } from '../lib/format';

const STATUSES = ['active', 'draft', 'deprecated', 'archived'];

const EMPTY_QUERY = {
  query: '',
  languages: [],
  tags: [],
  status: [],
  root_ids: [],
  owner: '',
  environment: '',
  classification: '',
  min_size: '',
  max_size: '',
  modified_after: '',
  modified_before: '',
  sort_by: 'name',
  sort_order: 'asc',
  page_size: 50,
};

export default function Search() {
  const toast = useToast();
  const { can } = useAuth();
  const { confirm, confirmElement } = useConfirm();

  const [mode, setMode] = useState('metadata'); // metadata | content
  const [form, setForm] = useState({ ...EMPTY_QUERY });
  const [results, setResults] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hasSearched, setHasSearched] = useState(false);

  const [tags, setTags] = useState([]);
  const [roots, setRoots] = useState([]);
  const [languages, setLanguages] = useState([]);
  const [tagFilter, setTagFilter] = useState('');

  const [saved, setSaved] = useState([]);
  const [saveOpen, setSaveOpen] = useState(false);
  const [ftsStatus, setFtsStatus] = useState(null);
  const [searchContent, setSearchContent] = useState(true);
  const [searchNotes, setSearchNotes] = useState(true);

  const requestId = useRef(0);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([
      tagsApi.list(), folderRootsApi.list(), searchApi.getStats(),
      savedSearchesApi.list(), ftsApi.status(),
    ]).then(([tagsRes, rootsRes, statsRes, savedRes, ftsRes]) => {
      if (cancelled) return;
      if (tagsRes.status === 'fulfilled') setTags(tagsRes.value.data);
      if (rootsRes.status === 'fulfilled') setRoots(rootsRes.value.data);
      if (statsRes.status === 'fulfilled') {
        setLanguages(Object.keys(statsRes.value.data.by_language || {}).sort());
      }
      if (savedRes.status === 'fulfilled') setSaved(savedRes.value.data);
      if (ftsRes.status === 'fulfilled') setFtsStatus(ftsRes.value.data);
    });
    return () => { cancelled = true; };
  }, []);

  const runSearch = useCallback(async (targetPage = page) => {
    const id = requestId.current + 1;
    requestId.current = id;
    setLoading(true);
    setError(null);

    try {
      let response;
      if (mode === 'content') {
        if (!form.query.trim()) {
          setError('Enter a search term to search file contents.');
          setLoading(false);
          return;
        }
        response = await ftsApi.search({
          query: form.query.trim(),
          search_content: searchContent,
          search_notes: searchNotes,
          page: targetPage,
          page_size: form.page_size,
        });
      } else {
        response = await searchApi.search({
          query: form.query || undefined,
          languages: form.languages.length ? form.languages : undefined,
          tags: form.tags.length ? form.tags : undefined,
          status: form.status.length ? form.status : undefined,
          root_ids: form.root_ids.length ? form.root_ids : undefined,
          owner: form.owner || undefined,
          environment: form.environment || undefined,
          classification: form.classification || undefined,
          min_size: form.min_size !== '' ? Number(form.min_size) : undefined,
          max_size: form.max_size !== '' ? Number(form.max_size) : undefined,
          modified_after: form.modified_after || undefined,
          modified_before: form.modified_before || undefined,
          sort_by: form.sort_by,
          sort_order: form.sort_order,
          page: targetPage,
          page_size: form.page_size,
        });
      }

      if (requestId.current !== id) return;
      setResults(response.data.items);
      setTotalPages(response.data.total_pages);
      setTotal(response.data.total);
      setHasSearched(true);
    } catch (err) {
      if (requestId.current !== id) return;
      setError(apiError(err));
    } finally {
      if (requestId.current === id) setLoading(false);
    }
  }, [mode, form, page, searchContent, searchNotes]);

  const handleSubmit = (event) => {
    event.preventDefault();
    setPage(1);
    runSearch(1);
  };

  const handlePageChange = (nextPage) => {
    setPage(nextPage);
    runSearch(nextPage);
  };

  const reset = () => {
    setForm({ ...EMPTY_QUERY });
    setPage(1);
    setResults([]);
    setTotal(0);
    setTotalPages(1);
    setError(null);
    setHasSearched(false);
  };

  const toggleValue = (key, value) => {
    setForm((current) => ({
      ...current,
      [key]: current[key].includes(value)
        ? current[key].filter((v) => v !== value)
        : [...current[key], value],
    }));
  };

  const applySaved = (entry) => {
    setMode('metadata');
    setForm({ ...EMPTY_QUERY, ...entry.query_params });
    setPage(1);
    // Run it immediately: loading a saved search that then does nothing is
    // just a slower way of typing the filters again.
    setTimeout(() => runSearch(1), 0);
    toast.info(`Loaded saved search "${entry.name}".`);
  };

  const deleteSaved = async (entry) => {
    const ok = await confirm({
      title: `Delete saved search "${entry.name}"?`,
      message: 'The filters are removed. Scripts are not affected.',
      confirmLabel: 'Delete',
    });
    if (!ok) return;
    try {
      await savedSearchesApi.delete(entry.id);
      setSaved((current) => current.filter((s) => s.id !== entry.id));
      toast.success('Saved search deleted.');
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const visibleTags = tagFilter
    ? tags.filter((t) => t.name.toLowerCase().includes(tagFilter.toLowerCase()))
    : tags;

  return (
    <div>
      {confirmElement}
      <PageHeader
        title="Search"
        description="Filter by metadata, or search inside the files themselves."
        actions={can('search.create') && hasSearched && mode === 'metadata' && (
          <button type="button" className="button button-secondary" onClick={() => setSaveOpen(true)}>
            Save this search
          </button>
        )}
      />

      {saved.length > 0 && (
        <Card title="Saved searches" description="Reusable filter sets.">
          <div className="row">
            {saved.map((entry) => (
              <span className="key-value" key={entry.id}>
                <button
                  type="button"
                  className="button button-ghost button--small"
                  onClick={() => applySaved(entry)}
                  title={entry.description || undefined}
                >
                  {entry.is_pinned ? '★ ' : ''}{entry.name}
                </button>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => deleteSaved(entry)}
                  aria-label={`Delete saved search ${entry.name}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        </Card>
      )}

      <div className="tabs" role="tablist" aria-label="Search mode">
        <button
          type="button" role="tab" className="tab"
          aria-selected={mode === 'metadata'}
          onClick={() => { setMode('metadata'); setHasSearched(false); setResults([]); }}
        >
          Metadata filters
        </button>
        <button
          type="button" role="tab" className="tab"
          aria-selected={mode === 'content'}
          onClick={() => { setMode('content'); setHasSearched(false); setResults([]); }}
        >
          File contents
        </button>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <Card>
        <form onSubmit={handleSubmit}>
          <Field
            label={mode === 'content' ? 'Search phrase' : 'Name or path contains'}
            hint={mode === 'content'
              ? 'Matched as a phrase against indexed content, notes, names and paths.'
              : undefined}
          >
            {(props) => (
              <input
                {...props}
                type="search"
                value={form.query}
                onChange={(e) => setForm({ ...form, query: e.target.value })}
                placeholder={mode === 'content' ? 'connection timeout' : 'backup'}
              />
            )}
          </Field>

          {mode === 'content' ? (
            <>
              <fieldset>
                <legend>Search in</legend>
                <div className="check-grid">
                  <div className="checkbox">
                    <input
                      id="fts-content" type="checkbox" checked={searchContent}
                      onChange={(e) => setSearchContent(e.target.checked)}
                    />
                    <label htmlFor="fts-content">File contents</label>
                  </div>
                  <div className="checkbox">
                    <input
                      id="fts-notes" type="checkbox" checked={searchNotes}
                      onChange={(e) => setSearchNotes(e.target.checked)}
                    />
                    <label htmlFor="fts-notes">Notes</label>
                  </div>
                </div>
              </fieldset>
              {ftsStatus && ftsStatus.indexed_roots.length === 0 && (
                <div className="banner banner--warning">
                  <span className="banner__message">
                    No folder root has content indexing enabled, so only names, paths and
                    notes are searchable. Enable it per root on the Folder Roots page, then
                    rebuild the index from Settings.
                  </span>
                </div>
              )}
            </>
          ) : (
            <>
              <fieldset>
                <legend>Languages</legend>
                {languages.length === 0 ? (
                  <p className="text-muted text-small">Nothing indexed yet.</p>
                ) : (
                  <div className="check-grid">
                    {languages.map((lang) => (
                      <div className="checkbox" key={lang}>
                        <input
                          id={`lang-${lang}`}
                          type="checkbox"
                          checked={form.languages.includes(lang)}
                          onChange={() => toggleValue('languages', lang)}
                        />
                        <label htmlFor={`lang-${lang}`}>{lang}</label>
                      </div>
                    ))}
                  </div>
                )}
              </fieldset>

              <fieldset>
                <legend>Lifecycle status</legend>
                <div className="check-grid">
                  {STATUSES.map((status) => (
                    <div className="checkbox" key={status}>
                      <input
                        id={`status-${status}`}
                        type="checkbox"
                        checked={form.status.includes(status)}
                        onChange={() => toggleValue('status', status)}
                      />
                      <label htmlFor={`status-${status}`}>{status}</label>
                    </div>
                  ))}
                </div>
              </fieldset>

              {tags.length > 0 && (
                <fieldset>
                  <legend>Tags</legend>
                  {tags.length > 12 && (
                    <input
                      type="search"
                      value={tagFilter}
                      onChange={(e) => setTagFilter(e.target.value)}
                      placeholder="Filter tags…"
                      aria-label="Filter the tag list"
                      style={{ marginBottom: 'var(--space-2)' }}
                    />
                  )}
                  {/* Scrollable rather than silently showing only the first ten. */}
                  <div className="check-grid scroll-box">
                    {visibleTags.map((tag) => (
                      <div className="checkbox" key={tag.id}>
                        <input
                          id={`tag-${tag.id}`}
                          type="checkbox"
                          checked={form.tags.includes(tag.name)}
                          onChange={() => toggleValue('tags', tag.name)}
                        />
                        <label htmlFor={`tag-${tag.id}`}>{tag.name}</label>
                      </div>
                    ))}
                  </div>
                </fieldset>
              )}

              {roots.length > 0 && (
                <fieldset>
                  <legend>Folder roots</legend>
                  <div className="check-grid">
                    {roots.map((root) => (
                      <div className="checkbox" key={root.id}>
                        <input
                          id={`root-${root.id}`}
                          type="checkbox"
                          checked={form.root_ids.includes(root.id)}
                          onChange={() => toggleValue('root_ids', root.id)}
                        />
                        <label htmlFor={`root-${root.id}`}>{root.name}</label>
                      </div>
                    ))}
                  </div>
                </fieldset>
              )}

              <fieldset>
                <legend>Ownership</legend>
                <div className="grid-3">
                  <Field label="Owner">
                    {(props) => (
                      <input {...props} type="text" value={form.owner}
                        onChange={(e) => setForm({ ...form, owner: e.target.value })} />
                    )}
                  </Field>
                  <Field label="Environment">
                    {(props) => (
                      <input {...props} type="text" value={form.environment}
                        onChange={(e) => setForm({ ...form, environment: e.target.value })} />
                    )}
                  </Field>
                  <Field label="Classification">
                    {(props) => (
                      <input {...props} type="text" value={form.classification}
                        onChange={(e) => setForm({ ...form, classification: e.target.value })} />
                    )}
                  </Field>
                </div>
              </fieldset>

              <fieldset>
                <legend>Size and age</legend>
                <div className="grid-2">
                  <Field label="Minimum size (bytes)">
                    {(props) => (
                      <input {...props} type="number" min={0} value={form.min_size}
                        onChange={(e) => setForm({ ...form, min_size: e.target.value })} />
                    )}
                  </Field>
                  <Field label="Maximum size (bytes)">
                    {(props) => (
                      <input {...props} type="number" min={0} value={form.max_size}
                        onChange={(e) => setForm({ ...form, max_size: e.target.value })} />
                    )}
                  </Field>
                  <Field label="Modified after">
                    {(props) => (
                      <input {...props} type="date" value={form.modified_after}
                        onChange={(e) => setForm({ ...form, modified_after: e.target.value })} />
                    )}
                  </Field>
                  <Field label="Modified before">
                    {(props) => (
                      <input {...props} type="date" value={form.modified_before}
                        onChange={(e) => setForm({ ...form, modified_before: e.target.value })} />
                    )}
                  </Field>
                </div>
              </fieldset>
            </>
          )}

          <div className="filters">
            {mode === 'metadata' && (
              <>
                <Field label="Sort by">
                  {(props) => (
                    <select {...props} value={form.sort_by}
                      onChange={(e) => setForm({ ...form, sort_by: e.target.value })}>
                      <option value="name">Name</option>
                      <option value="path">Path</option>
                      <option value="language">Language</option>
                      <option value="size">Size</option>
                      <option value="mtime">Modified</option>
                      <option value="status">Status</option>
                    </select>
                  )}
                </Field>
                <Field label="Order">
                  {(props) => (
                    <select {...props} value={form.sort_order}
                      onChange={(e) => setForm({ ...form, sort_order: e.target.value })}>
                      <option value="asc">Ascending</option>
                      <option value="desc">Descending</option>
                    </select>
                  )}
                </Field>
              </>
            )}
            <Field label="Per page">
              {(props) => (
                <select {...props} value={form.page_size}
                  onChange={(e) => setForm({ ...form, page_size: Number(e.target.value) })}>
                  {[25, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              )}
            </Field>
          </div>

          <div className="row">
            <button type="submit" className="button" disabled={loading}>
              {loading ? 'Searching…' : 'Search'}
            </button>
            <button type="button" className="button button-secondary" onClick={reset}>
              Clear
            </button>
          </div>
        </form>
      </Card>

      {loading && <Card><TableSkeleton rows={6} columns={5} /></Card>}

      {!loading && hasSearched && (
        <Card title={`Results (${total})`}>
          {results.length === 0 ? (
            <EmptyState
              icon="⌕"
              title="No matches"
              description={mode === 'content'
                ? 'Nothing in the indexed content, notes, names or paths matched that phrase.'
                : 'No script matched the current filters.'}
            />
          ) : (
            <>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Name</th>
                      <th scope="col">Language</th>
                      <th scope="col">Path</th>
                      <th scope="col">Size</th>
                      <th scope="col">Modified</th>
                      <th scope="col">Status</th>
                      <th scope="col">Tags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((script) => (
                      <tr key={script.id}>
                        <td><Link to={`/scripts/${script.id}`}>{script.name}</Link></td>
                        <td>{script.language || '—'}</td>
                        <td className="text-muted text-small mono" title={script.path}>
                          {truncatePath(script.path, 46)}
                        </td>
                        <td className="nowrap">{formatBytes(script.size)}</td>
                        <td className="nowrap" title={formatDateTime(script.mtime)}>
                          {formatDate(script.mtime)}
                        </td>
                        <td><StatusBadge status={script.status} /></td>
                        <td>
                          {(script.tags || []).map((tag) => <TagChip key={tag} name={tag} />)}
                          {(!script.tags || script.tags.length === 0) && <span className="text-muted">—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={page}
                totalPages={totalPages}
                total={total}
                pageSize={form.page_size}
                onChange={handlePageChange}
              />
            </>
          )}
        </Card>
      )}

      {saveOpen && (
        <SaveSearchModal
          queryParams={form}
          onClose={() => setSaveOpen(false)}
          onSaved={(entry) => {
            setSaved((current) => [...current, entry]);
            setSaveOpen(false);
            toast.success(`Saved search "${entry.name}".`);
          }}
          onError={(message) => toast.error(message)}
        />
      )}
    </div>
  );
}

function SaveSearchModal({ queryParams, onClose, onSaved, onError }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [pinned, setPinned] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await savedSearchesApi.create({
        name: name.trim(),
        description: description.trim() || null,
        query_params: queryParams,
        is_pinned: pinned,
      });
      onSaved(data);
    } catch (err) {
      onError(apiError(err));
      setBusy(false);
    }
  };

  return (
    <Modal title="Save this search" onClose={onClose} size="small">
      <form onSubmit={submit}>
        <Field label="Name" required>
          {(props) => (
            <input {...props} type="text" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
          )}
        </Field>
        <Field label="Description">
          {(props) => (
            <input {...props} type="text" value={description} onChange={(e) => setDescription(e.target.value)} />
          )}
        </Field>
        <div className="checkbox">
          <input id="save-pin" type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} />
          <label htmlFor="save-pin">Pin to the top of the list</label>
        </div>
        <div className="modal__footer">
          <button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="button" disabled={busy || !name.trim()}>
            {busy ? 'Saving…' : 'Save search'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
