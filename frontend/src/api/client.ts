import axios from 'axios';
import { API_URL } from '../utils/constants';

export const api = axios.create({
  baseURL: API_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// Attach API key or Bearer token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
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
          localStorage.setItem('auth_token', token);
          error.config.headers.Authorization = `Bearer ${token}`;
          return api(error.config);
        } catch {
          localStorage.removeItem('auth_token');
        }
      }
    }
    return Promise.reject(error);
  }
);
