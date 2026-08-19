import axios from 'axios';
import { API_URL } from '../utils/constants';

export const api = axios.create({
  baseURL: API_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// Attach API key or Bearer token to every request
//
// SECURITY NOTE:
// - Using import.meta.env.VITE_API_KEY embeds the key in the frontend bundle
// - localStorage is vulnerable to XSS attacks
// - TODO: Migrate to httpOnly cookies with server-side session management
// - TODO: Implement short-lived tokens (5-15 min) with refresh mechanism
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('auth_token'); // Use sessionStorage instead of localStorage (clears on tab close)
  const apiKey = import.meta.env.VITE_API_KEY;

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  } else if (apiKey) {
    config.headers['X-API-Key'] = apiKey;
  }
  return config;
});

// Auto-refresh token on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      error.config._retry = true;
      const apiKey = import.meta.env.VITE_API_KEY;
      if (apiKey) {
        try {
          const res = await axios.post(`${API_URL}/auth/token`, {}, {
            headers: { 'X-API-Key': apiKey },
          });
          const token = res.data.access_token;
          sessionStorage.setItem('auth_token', token);
          error.config.headers.Authorization = `Bearer ${token}`;
          return api(error.config);
        } catch {
          sessionStorage.removeItem('auth_token');
        }
      }
    }
    return Promise.reject(error);
  }
);

// Security: Clear sensitive data on page visibility change (potential XSS detection)
if (typeof document !== 'undefined' && document.addEventListener) {
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      // Page hidden - consider clearing sensitive data
      // Uncomment if you want aggressive security:
      // sessionStorage.removeItem('auth_token');
    }
  });
}
