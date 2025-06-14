
import React, { useState } from 'react';
import API from '../api';
import './query.css';

function Query({ selectedDocument }) {
  const [queryText, setQueryText] = useState('');
  const [answer, setAnswer] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleQuery = async (e) => {
    e.preventDefault();
    if (!selectedDocument) {
      setError('Please select or upload a document.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await API.post('/query', {
        document_id: selectedDocument.id,
        query_text: queryText
      });
      setAnswer(res.data.response_text);
    } catch {
      setError('Query failed');
      setAnswer('');
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setQueryText('');
    setAnswer('');
    setError('');
  };

  return (
    <div className="query-section">
      <form className="query-form" onSubmit={handleQuery}>
        <div className="query-input-row">
          <input
            className="query-input"
            placeholder="Your question"
            value={queryText}
            onChange={e => setQueryText(e.target.value)}
            disabled={loading}
          />
          <button className="query-btn" type="submit" disabled={loading || !queryText}>
            {loading ? "Asking..." : "Ask"}
          </button>
          <button className="clear-btn" type="button" onClick={handleClear}>
            Clear
          </button>
        </div>
      </form>
      {error && <div style={{ color: '#ff6b6b', marginTop: '8px' }}>{error}</div>}
      {answer && <div className="answer-box">{answer}</div>}
    </div>
  );
}

export default Query;
