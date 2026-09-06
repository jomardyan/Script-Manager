import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { apiError, folderRootsApi, scriptsApi, searchApi, tagsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Card, EmptyState, ErrorBanner, Field, PageHeader, Pagination, SortableHeader,
  StatusBadge, TableSkeleton, TagChip,
} from '../components/ui';
import Modal from '../components/Modal';
import { useToast } from '../context/ToastContext';
import { formatBytes, formatDate, formatDateTime, truncatePath } from '../lib/format';

const STATUSES = ['active', 'draft', 'deprecated', 'archived'];
const PAGE_SIZES = [25, 50, 100];

export default function Scripts() {
  const toast = useToast();
  const { can } = useAuth();
  const canEdit = can('scripts.update');

  const [scripts, setScripts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');
  const [language, setLanguage] = useState('');
  const [status, setStatus] = useState('');
  const [rootId, setRootId] = useState('');
  const [roots, setRoots] = useState([]);
  const [languages, setLanguages] = useState([]);
  const [allTags, setAllTags] = useState([]);
  const [selected, setSelected] = useState(() => new Set());
  const [bulkOpen, setBulkOpen] = useState(false);

  // Every list request carries a sequence number; a slow earlier response is
  // discarded instead of overwriting the results of a newer filter.
  const requestId = useRef(0);

  const loadScripts = useCallback(async () => {
    const id = requestId.current + 1;
    requestId.current = id;
    setLoading(true);

    try {
      const { data } = await scriptsApi.list({
        page,
        page_size: pageSize,
        search: appliedSearch || undefined,
        language: language || undefined,
        status: status || undefined,
        root_id: rootId || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      if (requestId.current !== id) return;

      setScripts(data.items);
      setTotalPages(data.total_pages);
      setTotal(data.total);
      setError(null);

      // Deleting or filtering can shrink the result set below the current page.
      if (data.total_pages > 0 && page > data.total_pages) setPage(data.total_pages);
    } catch (err) {
      if (requestId.current !== id) return;
      setError(apiError(err));
    } finally {
      if (requestId.current === id) setLoading(false);
    }
  }, [page, pageSize, appliedSearch, language, status, rootId, sortBy, sortOrder]);

  useEffect(() => { loadScripts(); }, [loadScripts]);

  // Filter options come from the data rather than a hardcoded list, so a
  // language the scanner found is always selectable.
  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([folderRootsApi.list(), tagsApi.list()]).then(([rootsRes, tagsRes]) => {
      if (cancelled) return;
      if (rootsRes.status === 'fulfilled') setRoots(rootsRes.value.data);
      if (tagsRes.status === 'fulfilled') setAllTags(tagsRes.value.data);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    searchApi.getStats()
      .then(({ data }) => {
        if (!cancelled) setLanguages(Object.keys(data.by_language || {}).sort());
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const handleSort = (column) => {
    if (sortBy === column) setSortOrder((order) => (order === 'asc' ? 'desc' : 'asc'));
    else {
      setSortBy(column);
      setSortOrder('asc');
    }
    setPage(1);
  };

  const resetFilters = () => {
    setSearchInput('');
    setAppliedSearch('');
    setLanguage('');
    setStatus('');
    setRootId('');
    setSortBy('name');
    setSortOrder('asc');
    setPage(1);
  };

  const hasFilters = Boolean(appliedSearch || language || status || rootId);

  const toggleSelected = (id) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allOnPageSelected = scripts.length > 0 && scripts.every((s) => selected.has(s.id));
  const toggleAllOnPage = () => {
    setSelected((current) => {
      const next = new Set(current);
      if (allOnPageSelected) scripts.forEach((s) => next.delete(s.id));
      else scripts.forEach((s) => next.add(s.id));
      return next;
    });
  };

  const exportSelection = async () => {
    try {
      const ids = selected.size ? Array.from(selected) : null;
      const { data } = await scriptsApi.export(ids);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `script-manager-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success(`Exported ${data.script_count} script${data.script_count === 1 ? '' : 's'}.`);
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  return (
    <div>
      <PageHeader
        title="Scripts"
        description="Browse, filter and classify your indexed scripts."
        actions={
          <div className="button-group">
            <button type="button" className="button button-secondary" onClick={exportSelection}>
              Export {selected.size ? `(${selected.size})` : 'all'}
            </button>
            {canEdit && (
              <button
                type="button"
                className="button"
                onClick={() => setBulkOpen(true)}
                disabled={selected.size === 0}
                title={selected.size === 0 ? 'Select scripts first' : undefined}
              >
                Bulk edit {selected.size ? `(${selected.size})` : ''}
              </button>
            )}
          </div>
        }
      />

      <ErrorBanner message={error} onRetry={loadScripts} onDismiss={() => setError(null)} />

      <form
        className="search-bar"
        onSubmit={(event) => {
          event.preventDefault();
          setAppliedSearch(searchInput.trim());
          setPage(1);
        }}
        role="search"
      >
        <label className="visually-hidden" htmlFor="script-search">Search scripts</label>
        <input
          id="script-search"
          type="search"
          placeholder="Search by name or path…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <button type="submit" className="button">Search</button>
      </form>

      <div className="filters">
        <Field label="Language">
          {(props) => (
            <select {...props} value={language} onChange={(e) => { setLanguage(e.target.value); setPage(1); }}>
              <option value="">All languages</option>
              {languages.map((lang) => <option key={lang} value={lang}>{lang}</option>)}
            </select>
          )}
        </Field>
        <Field label="Status">
          {(props) => (
            <select {...props} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          )}
        </Field>
        <Field label="Folder root">
          {(props) => (
            <select {...props} value={rootId} onChange={(e) => { setRootId(e.target.value); setPage(1); }}>
              <option value="">All roots</option>
              {roots.map((root) => <option key={root.id} value={root.id}>{root.name}</option>)}
            </select>
          )}
        </Field>
        <Field label="Per page">
          {(props) => (
            <select {...props} value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
              {PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
            </select>
          )}
        </Field>
        {hasFilters && (
          <button type="button" className="button button-secondary" onClick={resetFilters}>
            Clear filters
          </button>
        )}
      </div>

      <Card>
        {loading ? (
          <TableSkeleton rows={8} columns={7} />
        ) : scripts.length === 0 ? (
          <EmptyState
            icon="◈"
            title={hasFilters ? 'No scripts match these filters' : 'No scripts indexed yet'}
            description={
              hasFilters
                ? 'Try widening the filters or clearing the search term.'
                : 'Add a folder root and run a scan to build the index.'
            }
            action={hasFilters
              ? <button type="button" className="button button-secondary" onClick={resetFilters}>Clear filters</button>
              : <Link className="button" to="/folder-roots">Add a folder root</Link>}
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    {canEdit && (
                      <th scope="col" style={{ width: 36 }}>
                        <input
                          type="checkbox"
                          checked={allOnPageSelected}
                          onChange={toggleAllOnPage}
                          aria-label="Select all scripts on this page"
                          style={{ width: 16, height: 16 }}
                        />
                      </th>
                    )}
                    <SortableHeader column="name" label="Name" sortBy={sortBy} sortOrder={sortOrder} onSort={handleSort} />
                    <SortableHeader column="language" label="Language" sortBy={sortBy} sortOrder={sortOrder} onSort={handleSort} />
                    <SortableHeader column="path" label="Path" sortBy={sortBy} sortOrder={sortOrder} onSort={handleSort} />
                    <SortableHeader column="size" label="Size" sortBy={sortBy} sortOrder={sortOrder} onSort={handleSort} />
                    <SortableHeader column="mtime" label="Modified" sortBy={sortBy} sortOrder={sortOrder} onSort={handleSort} />
                    <SortableHeader column="status" label="Status" sortBy={sortBy} sortOrder={sortOrder} onSort={handleSort} />
                    <th scope="col">Tags</th>
                  </tr>
                </thead>
                <tbody>
                  {scripts.map((script) => (
                    <tr key={script.id}>
                      {canEdit && (
                        <td>
                          <input
                            type="checkbox"
                            checked={selected.has(script.id)}
                            onChange={() => toggleSelected(script.id)}
                            aria-label={`Select ${script.name}`}
                            style={{ width: 16, height: 16 }}
                          />
                        </td>
                      )}
                      <td><Link to={`/scripts/${script.id}`}>{script.name}</Link></td>
                      <td>{script.language || '—'}</td>
                      <td className="text-muted text-small mono" title={script.path}>
                        {truncatePath(script.path, 48)}
                      </td>
                      <td className="nowrap">{formatBytes(script.size)}</td>
                      <td className="nowrap" title={formatDateTime(script.mtime)}>{formatDate(script.mtime)}</td>
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
              pageSize={pageSize}
              onChange={setPage}
            />
          </>
        )}
      </Card>

      {bulkOpen && (
        <BulkEditModal
          count={selected.size}
          scriptIds={Array.from(selected)}
          tags={allTags}
          onClose={() => setBulkOpen(false)}
          onDone={(message) => {
            setBulkOpen(false);
            setSelected(new Set());
            toast.success(message);
            loadScripts();
          }}
          onError={(message) => toast.error(message)}
        />
      )}
    </div>
  );
}

/** Bulk tagging and status changes. Both endpoints existed with no UI. */
function BulkEditModal({ count, scriptIds, tags, onClose, onDone, onError }) {
  const [tagIds, setTagIds] = useState([]);
  const [status, setStatus] = useState('');
  const [owner, setOwner] = useState('');
  const [environment, setEnvironment] = useState('');
  const [classification, setClassification] = useState('');
  const [busy, setBusy] = useState(false);

  const nothingToDo = tagIds.length === 0 && !status && !owner && !environment && !classification;

  const submit = async (event) => {
    event.preventDefault();
    if (busy || nothingToDo) return;
    setBusy(true);
    try {
      const messages = [];
      if (tagIds.length) {
        const { data } = await scriptsApi.bulkTags({ script_ids: scriptIds, tag_ids: tagIds });
        messages.push(`${data.added} tag assignment${data.added === 1 ? '' : 's'} added`);
      }
      if (status || owner || environment || classification) {
        const { data } = await scriptsApi.bulkStatus({
          script_ids: scriptIds,
          status: status || undefined,
          owner: owner || undefined,
          environment: environment || undefined,
          classification: classification || undefined,
        });
        messages.push(`${data.updated} script${data.updated === 1 ? '' : 's'} updated`);
      }
      onDone(messages.join('; ') || 'No changes made.');
    } catch (err) {
      onError(apiError(err));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Bulk edit ${count} script${count === 1 ? '' : 's'}`}
      description="Only the fields you fill in are changed. Tags are added, never removed."
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <fieldset>
          <legend>Add tags</legend>
          {tags.length === 0 ? (
            <p className="text-muted text-small">No tags exist yet.</p>
          ) : (
            <div className="check-grid scroll-box">
              {tags.map((tag) => (
                <div className="checkbox" key={tag.id}>
                  <input
                    type="checkbox"
                    id={`bulk-tag-${tag.id}`}
                    checked={tagIds.includes(tag.id)}
                    onChange={() => setTagIds((current) => (
                      current.includes(tag.id)
                        ? current.filter((id) => id !== tag.id)
                        : [...current, tag.id]
                    ))}
                  />
                  <label htmlFor={`bulk-tag-${tag.id}`}>{tag.name}</label>
                </div>
              ))}
            </div>
          )}
        </fieldset>

        <div className="grid-2">
          <Field label="Status">
            {(props) => (
              <select {...props} value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">Leave unchanged</option>
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            )}
          </Field>
          <Field label="Owner">
            {(props) => (
              <input {...props} type="text" value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="Leave blank to keep" />
            )}
          </Field>
          <Field label="Environment">
            {(props) => (
              <input {...props} type="text" value={environment} onChange={(e) => setEnvironment(e.target.value)} placeholder="Leave blank to keep" />
            )}
          </Field>
          <Field label="Classification">
            {(props) => (
              <input {...props} type="text" value={classification} onChange={(e) => setClassification(e.target.value)} placeholder="Leave blank to keep" />
            )}
          </Field>
        </div>

        <div className="modal__footer">
          <button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="button" disabled={busy || nothingToDo}>
            {busy ? 'Applying…' : `Apply to ${count} script${count === 1 ? '' : 's'}`}
          </button>
        </div>
      </form>
    </Modal>
  );
}
