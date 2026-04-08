import { useState, useEffect } from 'react';
import { folderRootsApi } from '../services/api';

function FolderRoots() {
  const [roots, setRoots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [scanning, setScanning] = useState({});
  const [formData, setFormData] = useState({
    name: '',
    path: '',
    recursive: true,
    include_patterns: '',
    exclude_patterns: '',
    follow_symlinks: false,
    max_file_size: 10485760
  });

  useEffect(() => {
    loadRoots();
  }, []);

  const loadRoots = async () => {
    try {
      setLoading(true);
      const response = await folderRootsApi.list();
      setRoots(response.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await folderRootsApi.create(formData);
      setShowModal(false);
      setFormData({
        name: '',
        path: '',
        recursive: true,
        include_patterns: '',
        exclude_patterns: '',
        follow_symlinks: false,
        max_file_size: 10485760
      });
      loadRoots();
    } catch (err) {
      alert('Error creating folder root: ' + err.message);
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm('Are you sure you want to delete this folder root? All associated scripts will be removed.')) {
      try {
        await folderRootsApi.delete(id);
        loadRoots();
      } catch (err) {
        alert('Error deleting folder root: ' + err.message);
      }
    }
  };

  const handleScan = async (id) => {
    try {
      setScanning(prev => ({ ...prev, [id]: true }));
      
      // Start the scan (returns immediately)
      const scanResponse = await folderRootsApi.scan(id, false);
      const scanId = scanResponse.data.scan_id;
      
      // Poll for scan status
      const pollInterval = setInterval(async () => {
        try {
          const statusResponse = await folderRootsApi.getScanStatus(id, scanId);
          const status = statusResponse.data;
          
          if (status.status === 'completed' || status.status === 'failed') {
            clearInterval(pollInterval);
            setScanning(prev => ({ ...prev, [id]: false }));
            
            if (status.status === 'completed') {
              alert(`Scan completed!\nNew: ${status.new_count}\nUpdated: ${status.updated_count}\nDeleted: ${status.deleted_count}`);
              loadRoots();
            } else {
              alert(`Scan failed: ${status.error_message}`);
            }
          }
        } catch (err) {
          console.error('Error polling scan status:', err);
        }
      }, 2000); // Poll every 2 seconds
      
    } catch (err) {
      alert('Error starting scan: ' + err.message);
      setScanning(prev => ({ ...prev, [id]: false }));
    }
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Error: {error}</div>;

  return (
    <div>
      <div className="page-header">
        <h2>Folder Roots</h2>
        <p>Manage directories to scan for scripts</p>
      </div>

      <button className="button" onClick={() => setShowModal(true)}>
        Add Folder Root
      </button>

      <div className="card" style={{ marginTop: '20px' }}>
        {roots.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Path</th>
                <th>Recursive</th>
                <th>Last Scan</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {roots.map(root => (
                <tr key={root.id}>
                  <td>{root.name}</td>
                  <td>{root.path}</td>
                  <td>{root.recursive ? 'Yes' : 'No'}</td>
                  <td>{root.last_scan_time ? new Date(root.last_scan_time).toLocaleString() : 'Never'}</td>
                  <td>
                    <button
                      className="button"
                      onClick={() => handleScan(root.id)}
                      disabled={scanning[root.id]}
                      style={{ marginRight: '10px' }}
                    >
                      {scanning[root.id] ? 'Scanning...' : 'Scan'}
                    </button>
                    <button
                      className="button button-danger"
                      onClick={() => handleDelete(root.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No folder roots configured. Click "Add Folder Root" to get started.</p>
        )}
      </div>

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Add Folder Root</h2>
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
                <label>Path *</label>
                <input
                  type="text"
                  value={formData.path}
                  onChange={(e) => setFormData({ ...formData, path: e.target.value })}
                  required
                  placeholder="/path/to/scripts"
                />
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={formData.recursive}
                    onChange={(e) => setFormData({ ...formData, recursive: e.target.checked })}
                  />
                  Scan Recursively
                </label>
              </div>
              <div className="form-group">
                <label>Include Patterns (comma-separated)</label>
                <input
                  type="text"
                  value={formData.include_patterns}
                  onChange={(e) => setFormData({ ...formData, include_patterns: e.target.value })}
                  placeholder="*.py, *.sh"
                />
              </div>
              <div className="form-group">
                <label>Exclude Patterns (comma-separated)</label>
                <input
                  type="text"
                  value={formData.exclude_patterns}
                  onChange={(e) => setFormData({ ...formData, exclude_patterns: e.target.value })}
                  placeholder="*test*, *tmp*"
                />
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={formData.follow_symlinks}
                    onChange={(e) => setFormData({ ...formData, follow_symlinks: e.target.checked })}
                  />
                  Follow Symbolic Links
                </label>
              </div>
              <div className="modal-actions">
                <button type="button" className="button button-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="button">
                  Add
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default FolderRoots;
