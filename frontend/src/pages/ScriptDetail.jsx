import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { scriptsApi, notesApi, tagsApi } from '../services/api';

function ScriptDetail() {
  const { id } = useParams();
  const [script, setScript] = useState(null);
  const [notes, setNotes] = useState([]);
  const [history, setHistory] = useState([]);
  const [content, setContent] = useState('');
  const [contentError, setContentError] = useState(null);
  const [allTags, setAllTags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [noteContent, setNoteContent] = useState('');
  const [statusUpdate, setStatusUpdate] = useState({
    status: '',
    classification: '',
    owner: '',
    environment: ''
  });

  useEffect(() => {
    loadData();
  }, [id]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      setContentError(null);

      const [scriptRes, notesRes, tagsRes, contentRes, historyRes] = await Promise.allSettled([
        scriptsApi.get(id),
        notesApi.getScriptNotes(id),
        tagsApi.list(),
        scriptsApi.getContent(id),
        scriptsApi.getHistory(id)
      ]);

      if (scriptRes.status !== 'fulfilled') throw scriptRes.reason;
      if (notesRes.status !== 'fulfilled') throw notesRes.reason;
      if (tagsRes.status !== 'fulfilled') throw tagsRes.reason;

      const scriptData = scriptRes.value.data;
      setScript(scriptData);
      setNotes(notesRes.value.data);
      setAllTags(tagsRes.value.data);
      setStatusUpdate({
        status: scriptData.status || 'active',
        classification: scriptData.classification || '',
        owner: scriptData.owner || '',
        environment: scriptData.environment || ''
      });

      if (contentRes.status === 'fulfilled') {
        setContent(contentRes.value.data.content || '');
      } else {
        setContent('');
        setContentError('Unable to load file content from disk.');
      }

      if (historyRes.status === 'fulfilled') {
        setHistory(historyRes.value.data || []);
      } else {
        setHistory([]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleStatusUpdate = async (e) => {
    e.preventDefault();
    try {
      await scriptsApi.updateStatus(id, statusUpdate);
      alert('Status updated successfully');
      loadData();
    } catch (err) {
      alert('Error updating status: ' + err.message);
    }
  };

  const handleAddNote = async (e) => {
    e.preventDefault();
    if (!noteContent.trim()) return;
    try {
      await notesApi.create(id, { content: noteContent });
      setNoteContent('');
      loadData();
    } catch (err) {
      alert('Error adding note: ' + err.message);
    }
  };

  const handleAddTag = async (tagId) => {
    try {
      await scriptsApi.addTag(id, tagId);
      loadData();
    } catch (err) {
      alert('Error adding tag: ' + err.message);
    }
  };

  const handleRemoveTag = async (tagName) => {
    try {
      const tag = allTags.find((t) => t.name === tagName);
      if (tag) {
        await scriptsApi.removeTag(id, tag.id);
        loadData();
      }
    } catch (err) {
      alert('Error removing tag: ' + err.message);
    }
  };

  const handleCopyContent = async () => {
    try {
      await navigator.clipboard.writeText(content);
      alert('Script content copied to clipboard');
    } catch (err) {
      alert('Copy failed: ' + err.message);
    }
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Error: {error}</div>;
  if (!script) return <div className="error">Script not found</div>;

  return (
    <div>
      <div className="page-header">
        <Link to="/scripts" style={{ color: '#3498db', textDecoration: 'none' }}>← Back to Scripts</Link>
        <h2>{script.name}</h2>
        <p>{script.path}</p>
      </div>

      <div className="script-detail-grid">
        <div>
          <div className="card">
            <h3>File Information</h3>
            <table className="table">
              <tbody>
                <tr>
                  <td><strong>Language</strong></td>
                  <td>{script.language || 'Unknown'}</td>
                </tr>
                <tr>
                  <td><strong>Extension</strong></td>
                  <td>{script.extension || '-'}</td>
                </tr>
                <tr>
                  <td><strong>Size</strong></td>
                  <td>{script.size ? Math.round(script.size / 1024) + ' KB' : '-'}</td>
                </tr>
                <tr>
                  <td><strong>Lines</strong></td>
                  <td>{script.line_count || '-'}</td>
                </tr>
                <tr>
                  <td><strong>Modified</strong></td>
                  <td>{script.mtime ? new Date(script.mtime).toLocaleString() : '-'}</td>
                </tr>
                <tr>
                  <td><strong>Hash</strong></td>
                  <td style={{ fontSize: '12px', fontFamily: 'monospace' }}>{script.hash?.substring(0, 16)}...</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="card">
            <h3>Script Content</h3>
            {contentError ? (
              <p style={{ color: '#c0392b' }}>{contentError}</p>
            ) : (
              <>
                <button className="button button-secondary" onClick={handleCopyContent} style={{ marginBottom: '10px' }}>
                  Copy Content
                </button>
                <pre className="code-view">{content}</pre>
              </>
            )}
          </div>

          <div className="card">
            <h3>Notes</h3>
            {notes.length > 0 && (
              <div style={{ marginBottom: '20px' }}>
                {notes.map(note => (
                  <div key={note.id} style={{ marginBottom: '15px', padding: '10px', background: '#f8f9fa', borderRadius: '5px' }}>
                    <div style={{ fontSize: '12px', color: '#7f8c8d', marginBottom: '5px' }}>
                      {new Date(note.updated_at).toLocaleString()}
                    </div>
                    <div>{note.content}</div>
                  </div>
                ))}
              </div>
            )}
            <form onSubmit={handleAddNote}>
              <div className="form-group">
                <textarea
                  value={noteContent}
                  onChange={(e) => setNoteContent(e.target.value)}
                  placeholder="Add a note..."
                  rows="4"
                />
              </div>
              <button type="submit" className="button">Add Note</button>
            </form>
          </div>
        </div>

        <div>
          <div className="card">
            <h3>Status & Classification</h3>
            <form onSubmit={handleStatusUpdate}>
              <div className="form-group">
                <label>Status</label>
                <select
                  value={statusUpdate.status}
                  onChange={(e) => setStatusUpdate({ ...statusUpdate, status: e.target.value })}
                >
                  <option value="active">Active</option>
                  <option value="draft">Draft</option>
                  <option value="deprecated">Deprecated</option>
                  <option value="archived">Archived</option>
                </select>
              </div>
              <div className="form-group">
                <label>Classification</label>
                <input
                  type="text"
                  value={statusUpdate.classification}
                  onChange={(e) => setStatusUpdate({ ...statusUpdate, classification: e.target.value })}
                  placeholder="e.g., production, staging"
                />
              </div>
              <div className="form-group">
                <label>Owner</label>
                <input
                  type="text"
                  value={statusUpdate.owner}
                  onChange={(e) => setStatusUpdate({ ...statusUpdate, owner: e.target.value })}
                  placeholder="Owner name"
                />
              </div>
              <div className="form-group">
                <label>Environment</label>
                <input
                  type="text"
                  value={statusUpdate.environment}
                  onChange={(e) => setStatusUpdate({ ...statusUpdate, environment: e.target.value })}
                  placeholder="e.g., dev, prod"
                />
              </div>
              <button type="submit" className="button">Update Status</button>
            </form>
          </div>

          <div className="card">
            <h3>Tags</h3>
            <div style={{ marginBottom: '15px' }}>
              {script.tags?.map(tag => (
                <span key={tag} className="tag" style={{ cursor: 'pointer' }} onClick={() => handleRemoveTag(tag)}>
                  {tag} ×
                </span>
              ))}
              {(!script.tags || script.tags.length === 0) && (
                <p style={{ color: '#7f8c8d', fontSize: '14px' }}>No tags</p>
              )}
            </div>
            <div className="form-group">
              <label>Add Tag</label>
              <select onChange={(e) => e.target.value && handleAddTag(e.target.value)}>
                <option value="">Select a tag...</option>
                {allTags.filter(t => !script.tags?.includes(t.name)).map(tag => (
                  <option key={tag.id} value={tag.id}>{tag.name}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="card">
            <h3>Change History</h3>
            {history.length === 0 ? (
              <p style={{ color: '#7f8c8d', fontSize: '14px' }}>No changes logged yet.</p>
            ) : (
              <ul className="history-list">
                {history.slice(0, 25).map((entry) => (
                  <li key={entry.id}>
                    <div><strong>{entry.change_type}</strong></div>
                    <div style={{ color: '#7f8c8d', fontSize: '12px' }}>{new Date(entry.event_time).toLocaleString()}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ScriptDetail;
