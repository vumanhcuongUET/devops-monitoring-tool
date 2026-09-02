/**
 * API Client with short-lived token auth.
 *
 * - Attaches the access token from the token manager to every request
 * - On 401: tries one bearer-based token refresh (POST /auth/refresh with
 *   the Authorization header) and retries the request
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
// Phase 15: one in-flight refresh shared by every queued 401 — concurrent
// requests used to race N parallel refresh calls.
let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = _doRefresh().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

// ============================================
// PROACTIVE REFRESH (Phase 16 P1-8)
// ============================================
// The refresh contract needs a still-valid token, but nothing ever refreshed
// before expiry: the request interceptor only attaches the (now expired)
// token, the reactive 401 path re-sent that same expired token, and every
// session hard-logged-out at the 15-minute TTL even during active use.
// Schedule a refresh 30s before expiry instead.
const REFRESH_MARGIN_MS = 30_000;
let refreshTimer: ReturnType<typeof setTimeout> | null = null;

export function scheduleProactiveRefresh(): void {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
  const info = tokenManager.getTokenInfo();
  if (!info) return;

  const delay = info.expiresAt - Date.now() - REFRESH_MARGIN_MS;
  if (delay <= 0) {
    // Already inside the margin (or expired): refresh now if still valid.
    if (tokenManager.isTokenValid()) void refreshAccessToken();
    return;
  }
  refreshTimer = setTimeout(() => {
    refreshTimer = null;
    void refreshAccessToken();
  }, delay);
}

async function _doRefresh(): Promise<string | null> {
  try {
    // Bearer-based refresh contract: the backend reads the Authorization
    // header — no cookies are involved anywhere in the auth flow.
    const response = await axios.post(`${API_URL}/api/v1/auth/refresh`, {}, {
      headers: tokenManager.getAccessToken()
        ? { Authorization: `Bearer ${tokenManager.getAccessToken()}` }
        : {},
    });

    const { access_token, expires_in } = response.data;
    tokenManager.setToken({
      accessToken: access_token,
      expiresAt: Date.now() + (expires_in || 900) * 1000,
      tokenType: 'Bearer',
      username: tokenManager.getUsername() ?? undefined,
    });
    scheduleProactiveRefresh();
    return access_token;
  } catch (error) {
    console.error('Token refresh failed:', error);
    return null;
  }
}

// A restored session (page reload) also needs its timer re-armed.
scheduleProactiveRefresh();

// ============================================
// EXPORTS
// ============================================
export { tokenManager };

/**
 * Logout and clear tokens
 */
export async function logout(): Promise<void> {
  // Phase 15: POST /auth/logout revokes every token issued to this user
  // (per-user min_iat floor). Best-effort — clear locally regardless so a
  // dead backend still ends the session.
  try {
    const accessToken = tokenManager.getAccessToken();
    if (accessToken) {
      await axios.post(
        `${API_URL}/api/v1/auth/logout`,
        {},
        { headers: { Authorization: `Bearer ${accessToken}` } }
      );
    }
  } catch {
    // ignore — local clear happens either way
  }
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
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
