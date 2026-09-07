import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { apiError, scriptsApi, similarityApi } from '../services/api';
import {
  Card, EmptyState, ErrorBanner, PageHeader, TableSkeleton,
} from '../components/ui';
import { useToast } from '../context/ToastContext';

/**
 * Duplicate and near-duplicate scripts.
 *
 * Both backend endpoints existed with no UI at all: exact duplicates
 * (`/scripts/duplicates/list`) and content-similarity groups
 * (`/similarity/groups/all`).
 */
export default function Duplicates() {
  const toast = useToast();
  const [tab, setTab] = useState('exact');

  const [duplicates, setDuplicates] = useState([]);
  const [loadingDuplicates, setLoadingDuplicates] = useState(true);
  const [duplicatesError, setDuplicatesError] = useState(null);

  const [groups, setGroups] = useState(null);
  const [loadingGroups, setLoadingGroups] = useState(false);
  const [groupsError, setGroupsError] = useState(null);
  const [threshold, setThreshold] = useState(0.85);

  const loadDuplicates = useCallback(async () => {
    setLoadingDuplicates(true);
    setDuplicatesError(null);
    try {
      const { data } = await scriptsApi.getDuplicates();
      setDuplicates(data);
    } catch (err) {
      setDuplicatesError(apiError(err));
    } finally {
      setLoadingDuplicates(false);
    }
  }, []);

  useEffect(() => { loadDuplicates(); }, [loadDuplicates]);

  const loadGroups = useCallback(async () => {
    setLoadingGroups(true);
    setGroupsError(null);
    try {
      const { data } = await similarityApi.groups({ threshold, min_group_size: 2 });
      setGroups(data);
      if (data.truncated) {
        toast.warning(
          `Comparison was capped at ${data.max_scripts} scripts; raise the threshold to narrow the sweep.`,
        );
      }
    } catch (err) {
      setGroupsError(apiError(err));
    } finally {
      setLoadingGroups(false);
    }
  }, [threshold, toast]);

  const totalWasted = duplicates.reduce((sum, group) => sum + (group.count - 1), 0);

  return (
    <div>
      <PageHeader
        title="Duplicates"
        description="Find scripts stored more than once, exactly or with small edits."
      />

      <div className="tabs" role="tablist" aria-label="Duplicate detection mode">
        <button
          type="button"
          role="tab"
          className="tab"
          aria-selected={tab === 'exact'}
          onClick={() => setTab('exact')}
        >
          Exact duplicates{duplicates.length ? ` (${duplicates.length})` : ''}
        </button>
        <button
          type="button"
          role="tab"
          className="tab"
          aria-selected={tab === 'similar'}
          onClick={() => setTab('similar')}
        >
          Similar content
        </button>
      </div>

      {tab === 'exact' && (
        <>
          <ErrorBanner message={duplicatesError} onRetry={loadDuplicates} onDismiss={() => setDuplicatesError(null)} />
          <Card
            title="Identical files"
            description="Grouped by SHA-256 content hash, so these files are byte-for-byte identical."
            actions={
              <button type="button" className="button button-secondary button--small" onClick={loadDuplicates} disabled={loadingDuplicates}>
                Refresh
              </button>
            }
          >
            {loadingDuplicates ? (
              <TableSkeleton rows={4} columns={3} />
            ) : duplicates.length === 0 ? (
              <EmptyState
                icon="✓"
                title="No exact duplicates"
                description="Every indexed script has unique content."
              />
            ) : (
              <>
                <p className="text-muted text-small" style={{ marginBottom: 'var(--space-3)' }}>
                  {duplicates.length} group{duplicates.length === 1 ? '' : 's'} covering{' '}
                  {totalWasted} redundant cop{totalWasted === 1 ? 'y' : 'ies'}.
                </p>
                <div className="stack">
                  {duplicates.map((group) => (
                    <div className="note" key={group.hash}>
                      <div className="note__meta">
                        <span>{group.count} identical copies</span>
                        <code className="text-small" title={group.hash}>{group.hash.slice(0, 16)}…</code>
                      </div>
                      <ul className="stack" style={{ listStyle: 'none' }}>
                        {group.paths.map((path, index) => (
                          <li key={group.ids[index] ?? path}>
                            <Link to={`/scripts/${group.ids[index]}`} className="mono text-small">
                              {path}
                            </Link>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Card>
        </>
      )}

      {tab === 'similar' && (
        <>
          <ErrorBanner message={groupsError} onRetry={loadGroups} onDismiss={() => setGroupsError(null)} />
          <Card
            title="Near-duplicate groups"
            description="Compares normalised file contents. Higher thresholds are stricter and faster."
          >
            <div className="filters">
              <div className="field">
                <label className="field__label" htmlFor="similarity-threshold">
                  Similarity threshold: {Math.round(threshold * 100)}%
                </label>
                <input
                  id="similarity-threshold"
                  type="range"
                  min="0.5"
                  max="0.99"
                  step="0.01"
                  value={threshold}
                  onChange={(event) => setThreshold(Number(event.target.value))}
                  style={{ width: 240 }}
                />
              </div>
              <button type="button" className="button" onClick={loadGroups} disabled={loadingGroups}>
                {loadingGroups ? 'Comparing…' : 'Run comparison'}
              </button>
            </div>

            {loadingGroups && (
              <p className="text-muted text-small">
                Reading and comparing file contents. This is heavier than the exact-duplicate
                check, so it runs only when you ask for it.
              </p>
            )}

            {!loadingGroups && groups && (
              groups.groups.length === 0 ? (
                <EmptyState
                  icon="✓"
                  title="No similar groups found"
                  description={`Nothing scored at or above ${Math.round(threshold * 100)}% across ${groups.scripts_compared} scripts.`}
                />
              ) : (
                <>
                  <p className="text-muted text-small" style={{ marginBottom: 'var(--space-3)' }}>
                    {groups.groups.length} group{groups.groups.length === 1 ? '' : 's'} across{' '}
                    {groups.scripts_compared} scripts compared
                    {groups.truncated ? ` (capped at ${groups.max_scripts})` : ''}.
                  </p>
                  <div className="stack">
                    {groups.groups.map((group) => (
                      <div className="note" key={`${group.language}-${group.scripts.map((s) => s.id).join('-')}`}>
                        <div className="note__meta">
                          <span>{group.script_count} similar {group.language} scripts</span>
                        </div>
                        <ul className="stack" style={{ listStyle: 'none' }}>
                          {group.scripts.map((script) => (
                            <li key={script.id}>
                              <Link to={`/scripts/${script.id}`}>{script.name}</Link>
                              <span className="text-muted text-small mono"> {script.path}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </>
              )
            )}

            {!loadingGroups && !groups && (
              <EmptyState
                icon="⧉"
                title="Not run yet"
                description="Choose a threshold and start the comparison."
              />
            )}
          </Card>
        </>
      )}
    </div>
  );
}
