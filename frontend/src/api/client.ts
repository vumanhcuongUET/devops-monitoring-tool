/**
 * API Client with short-lived token auth.
 *
 * - Attaches the access token from the token manager to every request
 * - On 401: tries one token refresh (httpOnly cookie) and retries the request
 * - If refresh fails: clears the token and dispatches 'auth-required'
 *   (App.tsx listens for it and drops back to the login screen)
 */

import axios from 'axios';
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { API_URL } from '../utils/constants';
import { getTokenManager } from '../auth/tokenManager';

const tokenManager = getTokenManager();

export const api: AxiosInstance = axios.create({
  baseURL: API_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true, // Enable cookies for httpOnly support
});

// ============================================
// REQUEST INTERCEPTOR - Attach authentication
// ============================================
api.interceptors.request.use(
  (config) => {
    const accessToken = tokenManager.getAccessToken();
    if (accessToken && tokenManager.isTokenValid()) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ============================================
// RESPONSE INTERCEPTOR - Handle auth errors
// ============================================
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // Handle 401 Unauthorized: try one refresh, then retry the request
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      if (tokenManager.getTokenInfo()) {
        try {
          const newToken = await refreshAccessToken();
          if (newToken) {
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return api(originalRequest);
          }
        } catch (refreshError) {
          console.error('Token refresh failed:', refreshError);
        }

        // Refresh failed — the session can't be recovered; drop to login.
        tokenManager.clear();
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('auth-required', {
            detail: { reason: 'token_expired' }
          }));
        }
      }
    }

    return Promise.reject(error);
  }
);

// ============================================
// TOKEN REFRESH
// ============================================
async function refreshAccessToken(): Promise<string | null> {
  try {
    const response = await axios.post(`${API_URL}/api/v1/auth/refresh`, {}, {
      withCredentials: true, // Send httpOnly cookie
      headers: tokenManager.getAccessToken()
        ? { Authorization: `Bearer ${tokenManager.getAccessToken()}` }
        : {},
    });

    const { access_token, expires_in } = response.data;
    tokenManager.setToken({
      accessToken: access_token,
      expiresAt: Date.now() + (expires_in || 900) * 1000,
      tokenType: 'Bearer',
    });
    return access_token;
  } catch (error) {
    console.error('Token refresh failed:', error);
    return null;
  }
}

// ============================================
// EXPORTS
// ============================================
export { tokenManager };

/**
 * Logout and clear tokens
 */
export async function logout(): Promise<void> {
  // No backend logout endpoint exists — tokens are stateless JWTs; clearing
  // the local token is the whole logout.
  tokenManager.clear();
}

/**
 * Get current authentication status
 */
export function getAuthStatus() {
  return {
    isAuthenticated: tokenManager.isTokenValid(),
    tokenExpiry: tokenManager.getTokenInfo()?.expiresAt || null,
  };
}
