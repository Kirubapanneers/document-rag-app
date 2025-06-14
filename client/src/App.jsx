import React, { useState, useEffect } from 'react';
import Register from './components/register';
import Login from './components/login';
import Upload from './components/upload';
import Query from './components/query';
import API from './api';
import './App.css';

function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [showRegister, setShowRegister] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    API.get('/me')
      .then(() => setLoggedIn(true))
      .catch(() => setLoggedIn(false))
      .finally(() => setCheckingSession(false));
  }, []);

  const handleSelectDocument = (doc) => {
    setSelectedDocument(doc);
  };

  const handleLogout = () => {
    setLoggedIn(false);
    setSelectedDocument(null);
  };

  if (checkingSession) {
    return (
      <div className="app-bg">
        <div className="app-card">
          <h1>
            <span className="logo-circle">📄</span> Document RAG App
          </h1>
          <div className="loading-spinner" />
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="app-bg">
      <div className="app-card">
        <h1>
          <span className="logo-circle">📄</span> LexaDoc App
        </h1>
        {!loggedIn ? (
          <>
            {showRegister ? (
              <>
                <Register onRegister={() => setShowRegister(false)} />
                <p>
                  Already have an account?{' '}
                  <button className="link-btn" onClick={() => setShowRegister(false)}>
                    Login
                  </button>
                </p>
              </>
            ) : (
              <>
                <Login onLogin={() => setLoggedIn(true)} />
                <p>
                  Don't have an account?{' '}
                  <button className="link-btn" onClick={() => setShowRegister(true)}>
                    Register
                  </button>
                </p>
              </>
            )}
          </>
        ) : (
          <>
            <div className="logout-row">
              <button className="logout-btn" onClick={handleLogout}>
                Logout
              </button>
            </div>
            <Upload onSelectDocument={handleSelectDocument} />
            <Query selectedDocument={selectedDocument} />
          </>
        )}
      </div>
    </div>
  );
}

export default App;
