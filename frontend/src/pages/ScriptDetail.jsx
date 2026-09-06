import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  apiError, attachmentsApi, notesApi, scriptsApi, similarityApi, tagsApi,
} from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Card, Checkbox, EmptyState, ErrorBanner, Field, PageHeader, Spinner, StatusBadge,
  TagChip,
} from '../components/ui';
import { useConfirm } from '../components/ConfirmDialog';
import { useToast } from '../context/ToastContext';
import { formatBytes, formatDateTime, formatRelative, humanize } from '../lib/format';

const STATUSES = ['active', 'draft', 'deprecated', 'archived'];

export default function ScriptDetail() {
  const { id } = useParams();
  const toast = useToast();
  const { can } = useAuth();
  const { confirm, confirmElement } = useConfirm();

  const canEdit = can('scripts.update');
  const canWriteNotes = can('notes.create');
  const canUpload = can('attachments.upload');

  const [script, setScript] = useState(null);
  const [notes, setNotes] = useState([]);
  const [history, setHistory] = useState([]);
  const [content, setContent] = useState({ text: '', truncated: false, error: null });
  const [allTags, setAllTags] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [fields, setFields] = useState({});
  const [similar, setSimilar] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [savingStatus, setSavingStatus] = useState(false);
  const [statusForm, setStatusForm] = useState({
    status: 'active', classification: '', owner: '', environment: '',
  });
  const baseline = useRef({});

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [
      scriptRes, notesRes, tagsRes, contentRes, historyRes, attachmentsRes, fieldsRes,
    ] = await Promise.allSettled([
      scriptsApi.get(id),
      notesApi.getScriptNotes(id),
      tagsApi.list(),
      scriptsApi.getContent(id),
      scriptsApi.getHistory(id),
      attachmentsApi.forScript(id),
      scriptsApi.getFields(id),
    ]);

    if (scriptRes.status !== 'fulfilled') {
      setError(apiError(scriptRes.reason));
      setLoading(false);
      return;
    }

    const data = scriptRes.value.data;
    setScript(data);
    const initial = {
      status: data.status || 'active',
      classification: data.classification || '',
      owner: data.owner || '',
      environment: data.environment || '',
    };
    setStatusForm(initial);
    baseline.current = initial;

    setNotes(notesRes.status === 'fulfilled' ? notesRes.value.data : []);
    setAllTags(tagsRes.status === 'fulfilled' ? tagsRes.value.data : []);
    setHistory(historyRes.status === 'fulfilled' ? historyRes.value.data || [] : []);
    setAttachments(attachmentsRes.status === 'fulfilled' ? attachmentsRes.value.data : []);
    setFields(fieldsRes.status === 'fulfilled' ? fieldsRes.value.data : {});

    if (contentRes.status === 'fulfilled') {
      setContent({
        text: contentRes.value.data.content || '',
        truncated: Boolean(contentRes.value.data.truncated),
        error: null,
      });
    } else {
      setContent({ text: '', truncated: false, error: apiError(contentRes.reason) });
    }

    setLoading(false);
  }, [id]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleStatusUpdate = async (event) => {
    event.preventDefault();
    if (savingStatus) return;

    // Only send fields that actually changed: the previous version posted all
    // four every time, which wrote four no-op entries into the audit trail.
    const changes = {};
    Object.entries(statusForm).forEach(([key, value]) => {
      if (value !== baseline.current[key]) changes[key] = value;
    });
    if (Object.keys(changes).length === 0) {
      toast.info('No changes to save.');
      return;
    }

    setSavingStatus(true);
    try {
      await scriptsApi.updateStatus(id, changes);
      toast.success('Status updated.');
      await loadData();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setSavingStatus(false);
    }
  };

  const handleAddTag = async (tagId) => {
    try {
      await scriptsApi.addTag(id, tagId);
      await loadData();
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const handleRemoveTag = async (tagName) => {
    const tag = allTags.find((t) => t.name === tagName);
    if (!tag) {
      toast.error(`Tag "${tagName}" no longer exists.`);
      return;
    }
    try {
      await scriptsApi.removeTag(id, tag.id);
      await loadData();
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const handleCopyContent = async () => {
    try {
      await navigator.clipboard.writeText(content.text);
      toast.success('Script content copied to the clipboard.');
    } catch (err) {
      toast.error(`Copy failed: ${err.message}`);
    }
  };

  const loadSimilar = async () => {
    setSimilar({ loading: true, items: [] });
    try {
      const { data } = await similarityApi.forScript(id, { threshold: 0.7, limit: 10 });
      setSimilar({ loading: false, items: data.similar_scripts });
    } catch (err) {
      setSimilar({ loading: false, items: [], error: apiError(err) });
    }
  };

  if (loading) return <Spinner label="Loading script" />;
  if (error) {
    return (
      <div>
        <ErrorBanner message={error} onRetry={loadData} />
        <EmptyState
          icon="◈"
          title="Script unavailable"
          description="It may have been deleted, or its folder root removed."
          action={<Link className="button" to="/scripts">Back to scripts</Link>}
        />
      </div>
    );
  }
  if (!script) return null;

  return (
    <div>
      {confirmElement}
      <PageHeader
        title={script.name}
        description={script.path}
        actions={<Link className="button button-secondary" to="/scripts">← Back to scripts</Link>}
      />

      {script.missing_flag && (
        <div className="banner banner--warning" role="status">
          <span className="banner__message">
            This file was not found during the last scan. The metadata below is retained,
            but the file itself is gone from disk.
          </span>
        </div>
      )}

      <div className="script-detail-grid">
        <div>
          <Card title="File information">
            <dl className="definition-list">
              <dt>Language</dt><dd>{script.language || 'Unknown'}</dd>
              <dt>Extension</dt><dd>{script.extension || '—'}</dd>
              <dt>Size</dt><dd>{formatBytes(script.size)}</dd>
              <dt>Lines</dt><dd>{script.line_count ?? '—'}</dd>
              <dt>Modified</dt><dd title={formatDateTime(script.mtime)}>{formatRelative(script.mtime)}</dd>
              <dt>Indexed</dt><dd title={formatDateTime(script.created_at)}>{formatRelative(script.created_at)}</dd>
              <dt>SHA-256</dt>
              <dd><code className="text-small">{script.hash || '—'}</code></dd>
            </dl>
          </Card>

          <Card
            title="Script content"
            actions={!content.error && (
              <button type="button" className="button button-secondary button--small" onClick={handleCopyContent}>
                Copy
              </button>
            )}
          >
            {content.error ? (
              <EmptyState icon="⚠" title="Content unavailable" description={content.error} />
            ) : (
              <>
                {content.truncated && (
                  <p className="text-small text-muted" style={{ marginBottom: 'var(--space-2)' }}>
                    Showing the first part of a large file.
                  </p>
                )}
                <pre className="code-view">{content.text}</pre>
              </>
            )}
          </Card>

          <NotesCard
            scriptId={id}
            notes={notes}
            canWrite={canWriteNotes}
            canDelete={can('notes.delete')}
            canUpdate={can('notes.update')}
            onChanged={loadData}
            confirm={confirm}
            toast={toast}
          />

          <AttachmentsCard
            scriptId={id}
            attachments={attachments}
            canUpload={canUpload}
            canDelete={can('attachments.delete')}
            onChanged={loadData}
            confirm={confirm}
            toast={toast}
          />
        </div>

        <div>
          <Card title="Status & classification">
            <form onSubmit={handleStatusUpdate}>
              <Field label="Lifecycle status">
                {(props) => (
                  <select
                    {...props}
                    value={statusForm.status}
                    onChange={(e) => setStatusForm({ ...statusForm, status: e.target.value })}
                    disabled={!canEdit}
                  >
                    {STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
                  </select>
                )}
              </Field>
              <Field label="Classification" hint="Free text, for example 'production' or 'internal'.">
                {(props) => (
                  <input
                    {...props}
                    type="text"
                    value={statusForm.classification}
                    onChange={(e) => setStatusForm({ ...statusForm, classification: e.target.value })}
                    disabled={!canEdit}
                  />
                )}
              </Field>
              <Field label="Owner">
                {(props) => (
                  <input
                    {...props}
                    type="text"
                    value={statusForm.owner}
                    onChange={(e) => setStatusForm({ ...statusForm, owner: e.target.value })}
                    disabled={!canEdit}
                  />
                )}
              </Field>
              <Field label="Environment">
                {(props) => (
                  <input
                    {...props}
                    type="text"
                    value={statusForm.environment}
                    onChange={(e) => setStatusForm({ ...statusForm, environment: e.target.value })}
                    disabled={!canEdit}
                  />
                )}
              </Field>
              {canEdit && (
                <button type="submit" className="button" disabled={savingStatus}>
                  {savingStatus ? 'Saving…' : 'Save changes'}
                </button>
              )}
            </form>
          </Card>

          <Card title="Tags">
            <div style={{ marginBottom: 'var(--space-3)' }}>
              {(script.tags || []).map((tag) => (
                <TagChip
                  key={tag}
                  name={tag}
                  onRemove={canEdit ? () => handleRemoveTag(tag) : undefined}
                />
              ))}
              {(!script.tags || script.tags.length === 0) && (
                <p className="text-muted text-small">No tags applied.</p>
              )}
            </div>
            {canEdit && (
              <Field label="Add a tag">
                {(props) => (
                  <select
                    {...props}
                    value=""
                    onChange={(e) => e.target.value && handleAddTag(e.target.value)}
                  >
                    <option value="">Select a tag…</option>
                    {allTags
                      .filter((t) => !(script.tags || []).includes(t.name))
                      .map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}
                  </select>
                )}
              </Field>
            )}
          </Card>

          <CustomFieldsCard
            scriptId={id}
            fields={fields}
            canEdit={canEdit}
            onChanged={loadData}
            toast={toast}
          />

          <Card
            title="Similar scripts"
            description="Compares normalised file contents against other scripts in the same language."
            actions={
              <button type="button" className="button button-secondary button--small" onClick={loadSimilar} disabled={similar?.loading}>
                {similar?.loading ? 'Comparing…' : 'Find similar'}
              </button>
            }
          >
            {!similar && <p className="text-muted text-small">Not compared yet.</p>}
            {similar?.error && <ErrorBanner message={similar.error} />}
            {similar && !similar.loading && !similar.error && (
              similar.items.length === 0 ? (
                <p className="text-muted text-small">No script scored above 70% similarity.</p>
              ) : (
                <ul className="stack" style={{ listStyle: 'none' }}>
                  {similar.items.map((item) => (
                    <li key={item.id} className="row row--between">
                      <Link to={`/scripts/${item.id}`}>{item.name}</Link>
                      <strong className="text-small">{item.similarity_percent}%</strong>
                    </li>
                  ))}
                </ul>
              )
            )}
          </Card>

          <Card title="Change history">
            {history.length === 0 ? (
              <p className="text-muted text-small">No changes recorded yet.</p>
            ) : (
              <ul className="history-list">
                {history.slice(0, 30).map((entry) => (
                  <li key={entry.id}>
                    <div className="row row--between">
                      <strong>{humanize(entry.change_type)}</strong>
                      <span className="text-small text-muted" title={formatDateTime(entry.event_time)}>
                        {formatRelative(entry.event_time)}
                      </span>
                    </div>
                    {(entry.old_value || entry.new_value) && (
                      <div className="history-change">
                        {entry.old_value ? <b>{entry.old_value}</b> : <i>none</i>}
                        {' → '}
                        {entry.new_value ? <b>{entry.new_value}</b> : <i>none</i>}
                      </div>
                    )}
                    {entry.actor && (
                      <div className="text-small text-muted">by {entry.actor}</div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

/** Notes with edit, delete and markdown rendering, none of which existed. */
function NotesCard({ scriptId, notes, canWrite, canUpdate, canDelete, onChanged, confirm, toast }) {
  const [draft, setDraft] = useState({ content: '', is_markdown: false });
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState({ content: '', is_markdown: false });
  const [rendered, setRendered] = useState({});

  // Markdown notes are rendered server-side through bleach, so the HTML here
  // has already been sanitised.
  useEffect(() => {
    let cancelled = false;
    const markdownNotes = notes.filter((note) => note.is_markdown && !(note.id in rendered));
    if (markdownNotes.length === 0) return undefined;

    Promise.allSettled(markdownNotes.map((note) => notesApi.render(note.id)))
      .then((results) => {
        if (cancelled) return;
        const next = {};
        markdownNotes.forEach((note, index) => {
          const result = results[index];
          if (result.status === 'fulfilled') next[note.id] = result.value.data.html;
        });
        setRendered((current) => ({ ...current, ...next }));
      });
    return () => { cancelled = true; };
  }, [notes, rendered]);

  const addNote = async (event) => {
    event.preventDefault();
    if (busy || !draft.content.trim()) return;
    setBusy(true);
    try {
      await notesApi.create(scriptId, draft);
      setDraft({ content: '', is_markdown: false });
      toast.success('Note added.');
      await onChanged();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async (noteId) => {
    setBusy(true);
    try {
      await notesApi.update(noteId, editDraft);
      setEditingId(null);
      setRendered((current) => {
        const next = { ...current };
        delete next[noteId];
        return next;
      });
      toast.success('Note updated.');
      await onChanged();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const deleteNote = async (note) => {
    const ok = await confirm({
      title: 'Delete this note?',
      message: note.content.length > 120 ? `${note.content.slice(0, 120)}…` : note.content,
      confirmLabel: 'Delete note',
    });
    if (!ok) return;
    try {
      await notesApi.delete(note.id);
      toast.success('Note deleted.');
      await onChanged();
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  return (
    <Card title={`Notes${notes.length ? ` (${notes.length})` : ''}`}>
      {notes.length === 0 && <p className="text-muted text-small">No notes yet.</p>}

      {notes.map((note) => (
        <div className="note" key={note.id}>
          <div className="note__meta">
            <span title={formatDateTime(note.updated_at)}>
              Updated {formatRelative(note.updated_at)}
              {note.is_markdown && ' · markdown'}
            </span>
            <span className="row-actions">
              {canUpdate && editingId !== note.id && (
                <button
                  type="button"
                  className="button button-secondary button--small"
                  onClick={() => {
                    setEditingId(note.id);
                    setEditDraft({ content: note.content, is_markdown: note.is_markdown });
                  }}
                >
                  Edit
                </button>
              )}
              {canDelete && (
                <button
                  type="button"
                  className="button button-danger button--small"
                  onClick={() => deleteNote(note)}
                >
                  Delete
                </button>
              )}
            </span>
          </div>

          {editingId === note.id ? (
            <div className="stack">
              <label className="visually-hidden" htmlFor={`edit-note-${note.id}`}>Note content</label>
              <textarea
                id={`edit-note-${note.id}`}
                value={editDraft.content}
                onChange={(e) => setEditDraft({ ...editDraft, content: e.target.value })}
                rows={5}
              />
              <Checkbox
                label="Render as Markdown"
                checked={editDraft.is_markdown}
                onChange={(value) => setEditDraft({ ...editDraft, is_markdown: value })}
              />
              <div className="row row--end">
                <button type="button" className="button button-secondary button--small" onClick={() => setEditingId(null)}>
                  Cancel
                </button>
                <button type="button" className="button button--small" onClick={() => saveEdit(note.id)} disabled={busy}>
                  {busy ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          ) : note.is_markdown && rendered[note.id] ? (
            // Sanitised by bleach on the server before it reaches us.
            <div
              className="note__body note__body--rendered"
              dangerouslySetInnerHTML={{ __html: rendered[note.id] }}
            />
          ) : (
            <div className="note__body">{note.content}</div>
          )}
        </div>
      ))}

      {canWrite && (
        <form onSubmit={addNote} style={{ marginTop: 'var(--space-3)' }}>
          <Field label="Add a note">
            {(props) => (
              <textarea
                {...props}
                value={draft.content}
                onChange={(e) => setDraft({ ...draft, content: e.target.value })}
                placeholder="What should the next person know about this script?"
                rows={4}
              />
            )}
          </Field>
          <Checkbox
            label="Render as Markdown"
            checked={draft.is_markdown}
            onChange={(value) => setDraft({ ...draft, is_markdown: value })}
          />
          <button type="submit" className="button" disabled={busy || !draft.content.trim()}>
            {busy ? 'Saving…' : 'Add note'}
          </button>
        </form>
      )}
    </Card>
  );
}

/** Attachments: the endpoints existed but nothing in the UI called them. */
function AttachmentsCard({ scriptId, attachments, canUpload, canDelete, onChanged, confirm, toast }) {
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      await attachmentsApi.upload(file, { scriptId });
      toast.success(`Uploaded "${file.name}".`);
      if (inputRef.current) inputRef.current.value = '';
      await onChanged();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (attachment) => {
    const ok = await confirm({
      title: 'Delete attachment?',
      message: `"${attachment.original_filename}" will be removed from the server.`,
      confirmLabel: 'Delete attachment',
    });
    if (!ok) return;
    try {
      await attachmentsApi.delete(attachment.id);
      toast.success('Attachment deleted.');
      await onChanged();
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  return (
    <Card title={`Attachments${attachments.length ? ` (${attachments.length})` : ''}`}>
      {attachments.length === 0 ? (
        <p className="text-muted text-small">Nothing attached to this script.</p>
      ) : (
        <ul className="attachment-list">
          {attachments.map((attachment) => (
            <li className="attachment" key={attachment.id}>
              <span style={{ minWidth: 0 }}>
                <a href={attachmentsApi.downloadUrl(attachment.id)} target="_blank" rel="noreferrer">
                  {attachment.original_filename}
                </a>
                <span className="text-small text-muted">
                  {' '}{formatBytes(attachment.file_size)} · {formatRelative(attachment.created_at)}
                </span>
              </span>
              {canDelete && (
                <button
                  type="button"
                  className="button button-danger button--small"
                  onClick={() => remove(attachment)}
                >
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {canUpload && (
        <div style={{ marginTop: 'var(--space-3)' }}>
          <Field label="Upload a file" hint="Up to 10 MB. Documents, images, archives and text files.">
            {(props) => (
              <input
                {...props}
                ref={inputRef}
                type="file"
                onChange={(e) => upload(e.target.files?.[0])}
                disabled={busy}
              />
            )}
          </Field>
          {busy && <p className="text-small text-muted">Uploading…</p>}
        </div>
      )}
    </Card>
  );
}

/** Arbitrary key/value metadata. The endpoints existed with no UI. */
function CustomFieldsCard({ scriptId, fields, canEdit, onChanged, toast }) {
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [busy, setBusy] = useState(false);

  const entries = Object.entries(fields);

  const save = async (event) => {
    event.preventDefault();
    if (busy || !newKey.trim()) return;
    setBusy(true);
    try {
      await scriptsApi.setField(scriptId, newKey.trim(), newValue);
      setNewKey('');
      setNewValue('');
      toast.success('Custom field saved.');
      await onChanged();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (key) => {
    try {
      await scriptsApi.deleteField(scriptId, key);
      toast.success(`Removed "${key}".`);
      await onChanged();
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  return (
    <Card title="Custom fields" description="Arbitrary metadata attached to this script.">
      {entries.length === 0 ? (
        <p className="text-muted text-small">No custom fields.</p>
      ) : (
        <dl className="definition-list" style={{ marginBottom: 'var(--space-3)' }}>
          {entries.map(([key, value]) => (
            <FieldRow key={key} name={key} value={value} canEdit={canEdit} onRemove={() => remove(key)} />
          ))}
        </dl>
      )}

      {canEdit && (
        <form onSubmit={save} className="stack">
          <div className="grid-2">
            <Field label="Key">
              {(props) => (
                <input {...props} type="text" value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="ticket" />
              )}
            </Field>
            <Field label="Value">
              {(props) => (
                <input {...props} type="text" value={newValue} onChange={(e) => setNewValue(e.target.value)} placeholder="OPS-1234" />
              )}
            </Field>
          </div>
          <div>
            <button type="submit" className="button button-secondary button--small" disabled={busy || !newKey.trim()}>
              {busy ? 'Saving…' : 'Add field'}
            </button>
          </div>
        </form>
      )}
    </Card>
  );
}

function FieldRow({ name, value, canEdit, onRemove }) {
  return (
    <>
      <dt>{name}</dt>
      <dd className="row row--between">
        <span>{value || <span className="text-muted">empty</span>}</span>
        {canEdit && (
          <button type="button" className="icon-button" onClick={onRemove} aria-label={`Remove field ${name}`}>
            ×
          </button>
        )}
      </dd>
    </>
  );
}
