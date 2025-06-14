import React, { useState } from 'react';
import API from '../api';
import styles from './login.module.css'; // Ensure the filename matches exactly!

function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      await API.post('/login', { username, password });
      onLogin();
    } catch {
      setError('Login failed');
    }
  };

  return (
    <form className={styles.loginForm} onSubmit={handleLogin}>
      <input
        placeholder="Username"
        value={username}
        onChange={e => setUsername(e.target.value)}
        autoFocus
      />
      <input
        type="password"
        placeholder="Password"
        value={password}
        onChange={e => setPassword(e.target.value)}
      />
      <button type="submit">Login</button>
      {error && <div className={styles.error}>{error}</div>}
    </form>
  );
}

export default Login;
