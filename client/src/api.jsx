import axios from 'axios';

// Use Vite environment variable for the API base URL
const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL, // Now uses .env value
  withCredentials: true // Important for session cookies
});

export default API;
