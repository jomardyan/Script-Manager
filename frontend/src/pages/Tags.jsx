import { Fragment, useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { apiError, tagsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Card, EmptyState, ErrorBanner, Field, PageHeader, TableSkeleton, TagChip,
} from '../components/ui';
import Modal from '../components/Modal';
import { useConfirm } from '../components/ConfirmDialog';
import { useToast } from '../context/ToastContext';

export default function Tags() {
  const toast = useToast();
  const { can } = useAuth();
  const { confirm, confirmElement } = useConfirm();

  const [tags, setTags] = useState([]);
  const [usage, setUsage] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [expandedScripts, setExpandedScripts] = useState([]);

  const loadTags = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await tagsApi.list();
      setTags(data);

      // Usage counts make the delete confirmation able to state its impact
      // instead of asking "are you sure?" with no context.
      const counts = await Promise.allSettled(data.map((tag) => tagsApi.getScripts(tag.id)));
      const map = {};
      data.forEach((tag, index) => {
        const result = counts[index];
        map[tag.id] = result.status === 'fulfilled' ? result.value.data.length : null;
      });
      setUsage(map);
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadTags(); }, [loadTags]);

  const handleDelete = async (tag) => {
    const count = usage[tag.id];
    const ok = await confirm({
      title: `Delete tag "${tag.name}"?`,
      message: count
        ? `This tag is applied to ${count} script${count === 1 ? '' : 's'}. Deleting it removes it from all of them.`
        : 'This tag is not applied to any script.',
      detail: 'The scripts themselves are not affected.',
      confirmLabel: 'Delete tag',
    });
    if (!ok) return;

    setBusyId(tag.id);
    try {
      await tagsApi.delete(tag.id);
      toast.success(`Deleted tag "${tag.name}".`);
      if (expanded === tag.id) setExpanded(null);
      await loadTags();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusyId(null);
    }
  };

  const toggleExpand = async (tag) => {
    if (expanded === tag.id) {
      setExpanded(null);
      return;
    }
    setExpanded(tag.id);
    setExpandedScripts([]);
    try {
      const { data } = await tagsApi.getScripts(tag.id);
      setExpandedScripts(data);
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  return (
    <div>
      {confirmElement}
      <PageHeader
        title="Tags"
        description="Labels for organising scripts across folder roots."
        actions={can('tags.create') && (
          <button type="button" className="button" onClick={() => setShowModal(true)}>
            Create tag
          </button>
        )}
      />

      <ErrorBanner message={error} onRetry={loadTags} onDismiss={() => setError(null)} />

      <Card>
        {loading ? (
          <TableSkeleton rows={5} columns={4} />
        ) : tags.length === 0 ? (
          <EmptyState
            icon="◆"
            title="No tags yet"
            description="Tags let you group scripts by purpose, team or anything else that matters to you."
            action={can('tags.create') && (
              <button type="button" className="button" onClick={() => setShowModal(true)}>
                Create your first tag
              </button>
            )}
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Tag</th>
                  <th scope="col">Group</th>
                  <th scope="col">Scripts</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {tags.map((tag) => (
                  <Fragment key={tag.id}>
                    <tr>
                      <td><TagChip name={tag.name} color={tag.color} /></td>
                      <td>{tag.group_name || <span className="text-muted">—</span>}</td>
                      <td>
                        {usage[tag.id] === null || usage[tag.id] === undefined
                          ? <span className="text-muted">—</span>
                          : usage[tag.id]}
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="button button-secondary button--small"
                            onClick={() => toggleExpand(tag)}
                            aria-expanded={expanded === tag.id}
                          >
                            {expanded === tag.id ? 'Hide scripts' : 'Show scripts'}
                          </button>
                          {can('tags.delete') && (
                            <button
                              type="button"
                              className="button button-danger button--small"
                              onClick={() => handleDelete(tag)}
                              disabled={busyId === tag.id}
                            >
                              {busyId === tag.id ? 'Deleting…' : 'Delete'}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {expanded === tag.id && (
                      <tr>
                        <td colSpan={4}>
                          {expandedScripts.length === 0 ? (
                            <p className="text-muted text-small">No scripts carry this tag.</p>
                          ) : (
                            <ul className="stack" style={{ listStyle: 'none' }}>
                              {expandedScripts.map((script) => (
                                <li key={script.id}>
                                  <Link to={`/scripts/${script.id}`}>{script.name}</Link>
                                  <span className="text-muted text-small mono"> {script.path}</span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {showModal && (
        <CreateTagModal
          onClose={() => setShowModal(false)}
          onCreated={(name) => {
            setShowModal(false);
            toast.success(`Created tag "${name}".`);
            loadTags();
          }}
          onError={(message) => toast.error(message)}
        />
      )}
    </div>
  );
}

function CreateTagModal({ onClose, onCreated, onError }) {
  const [form, setForm] = useState({ name: '', group_name: '', color: '#1d6fb8' });
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await tagsApi.create({
        name: form.name.trim(),
        group_name: form.group_name.trim() || null,
        color: form.color,
      });
      onCreated(form.name.trim());
    } catch (err) {
      onError(apiError(err));
      setBusy(false);
    }
  };

  return (
    <Modal title="Create tag" onClose={onClose}>
      <form onSubmit={submit}>
        <Field label="Name" required hint="Must be unique across the collection.">
          {(props) => (
            <input
              {...props}
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              maxLength={100}
              autoFocus
            />
          )}
        </Field>
        <Field label="Group" hint="Optional. Groups related tags together, for example 'team' or 'environment'.">
          {(props) => (
            <input
              {...props}
              type="text"
              value={form.group_name}
              onChange={(e) => setForm({ ...form, group_name: e.target.value })}
              maxLength={100}
            />
          )}
        </Field>
        <Field label="Colour">
          {(props) => (
            <input
              {...props}
              type="color"
              value={form.color}
              onChange={(e) => setForm({ ...form, color: e.target.value })}
              style={{ width: 64, height: 36, padding: 2 }}
            />
          )}
        </Field>

        <div className="modal__footer">
          <button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="button" disabled={busy || !form.name.trim()}>
            {busy ? 'Creating…' : 'Create tag'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
