import { useState, useEffect } from 'react';
import { tagsApi } from '../services/api';

function Tags() {
  const [tags, setTags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    group_name: '',
    color: '#3498db'
  });

  useEffect(() => {
    loadTags();
  }, []);

  const loadTags = async () => {
    try {
      setLoading(true);
      const response = await tagsApi.list();
      setTags(response.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await tagsApi.create(formData);
      setShowModal(false);
      setFormData({ name: '', group_name: '', color: '#3498db' });
      loadTags();
    } catch (err) {
      alert('Error creating tag: ' + err.message);
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm('Are you sure you want to delete this tag?')) {
      try {
        await tagsApi.delete(id);
        loadTags();
      } catch (err) {
        alert('Error deleting tag: ' + err.message);
      }
    }
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Error: {error}</div>;

  return (
    <div>
      <div className="page-header">
        <h2>Tags</h2>
        <p>Manage tags for organizing scripts</p>
      </div>

      <button className="button" onClick={() => setShowModal(true)}>
        Create Tag
      </button>

      <div className="card" style={{ marginTop: '20px' }}>
        {tags.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Group</th>
                <th>Color</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {tags.map(tag => (
                <tr key={tag.id}>
                  <td>
                    <span className="tag" style={{ backgroundColor: tag.color || '#3498db' }}>
                      {tag.name}
                    </span>
                  </td>
                  <td>{tag.group_name || '-'}</td>
                  <td>
                    <div style={{ 
                      width: '40px', 
                      height: '20px', 
                      backgroundColor: tag.color || '#3498db',
                      borderRadius: '3px' 
                    }}></div>
                  </td>
                  <td>
                    <button
                      className="button button-danger"
                      onClick={() => handleDelete(tag.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No tags created yet. Click "Create Tag" to get started.</p>
        )}
      </div>

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Create Tag</h2>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>Name *</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label>Group</label>
                <input
                  type="text"
                  value={formData.group_name}
                  onChange={(e) => setFormData({ ...formData, group_name: e.target.value })}
                  placeholder="Optional group name"
                />
              </div>
              <div className="form-group">
                <label>Color</label>
                <input
                  type="color"
                  value={formData.color}
                  onChange={(e) => setFormData({ ...formData, color: e.target.value })}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="button button-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="button">
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Tags;
