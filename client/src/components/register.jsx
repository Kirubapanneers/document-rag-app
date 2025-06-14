import React, { useState } from 'react';
import API from '../api';
import styles from './register.module.css'; // Make sure the filename matches exactly!

function Register({ onRegister }) {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');

  const handleRegister = async (e) => {
    e.preventDefault();
    try {
      await API.post('/register', { username, email, password });
      setMessage('Registration successful! Please log in.');
      onRegister(); // Optionally auto-switch to login form
    } catch (err) {
      setMessage('Registration failed');
    }
  };

  return (
    <form className={styles.registerForm} onSubmit={handleRegister}>
      <input
        placeholder="Username"
        value={username}
        onChange={e => setUsername(e.target.value)}
        autoFocus
      />
      <input
        placeholder="Email"
        value={email}
        onChange={e => setEmail(e.target.value)}
        type="email"
      />
      <input
        type="password"
        placeholder="Password"
        value={password}
        onChange={e => setPassword(e.target.value)}
      />
      <button type="submit">Register</button>
      {message && <div className={styles.message}>{message}</div>}
    </form>
  );
}

export default Register;
