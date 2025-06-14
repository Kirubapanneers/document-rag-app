import React, { useState, useEffect } from 'react';
import API from '../api';
import './upload.css';

function Upload({ onSelectDocument }) {
  const [file, setFile] = useState(null);
  const [response, setResponse] = useState('');
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);

  


  // Fetch documents on mount
 


 useEffect(() => {
    API.get('/documents')
      .then(res => setDocuments(res.data))
      .catch(() => setDocuments([]));
  }, []);

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await API.post('/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setResponse('');
      setDocuments(prev => [...prev, res.data]);
      setFile(null);
      if (onSelectDocument) onSelectDocument(res.data); // Select the uploaded doc for querying
    } catch {
      setResponse('Upload failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    // Optionally call backend to delete document
    setDocuments(prev => prev.filter(doc => doc.id !== id));
    if (onSelectDocument) onSelectDocument(null);
  };

  return (
    <div className="upload-section">
      <form onSubmit={handleUpload} className="upload-row">
        <input
          type="file"
          onChange={e => setFile(e.target.files[0])}
          disabled={loading}
        />
        <button className="upload-btn" type="submit" disabled={loading || !file}>
          {loading ? "Uploading..." : "Upload"}
        </button>
      </form>
      {response && <div>{response}</div>}
      <ul className="doc-list">
        {documents.map(doc => (
          <li className="doc-item" key={doc.id}>
            <span className="doc-info">{doc.file_name}</span>
            <button className="delete-btn" onClick={() => handleDelete(doc.id)}>×</button>
            <button
              className="select-btn"
              onClick={() => onSelectDocument && onSelectDocument(doc)}
              style={{ marginLeft: '10px', background: '#7ee787', color: '#181c24', border: 'none', borderRadius: '4px', padding: '2px 10px', cursor: 'pointer' }}
            >
              Use
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default Upload;
