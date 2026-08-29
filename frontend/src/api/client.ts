/**
 * API Client with Enhanced Authentication
 *
 * Features:
 * - Short-lived tokens (5-15 minutes)
 * - Automatic token refresh
 * - httpOnly cookie support
 * - Secure token management
 */

import axios from 'axios';
import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { API_URL } from '../utils/constants';
import { getTokenManager, setupTokenRefresh } from '../auth/tokenManager';
import type { TokenManagerConfig } from '../auth/tokenManager';

// Token manager configuration (5-minute tokens by default)
const tokenConfig: Partial<TokenManagerConfig> = {
  tokenLifetime: 5, // 5 minutes
  refreshBuffer: 30, // Refresh 30 seconds before expiry
  maxRefreshAttempts: 3,
};

// Initialize token manager
const tokenManager = getTokenManager(tokenConfig);

// API key from environment (for development)
const getApiKey = (): string | undefined => {
  return import.meta.env.VITE_API_KEY;
};

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
    // Priority 1: Use short-lived token from token manager
    const accessToken = tokenManager.getAccessToken();
    if (accessToken && tokenManager.isTokenValid()) {
      config.headers.Authorization = `Bearer ${accessToken}`;
      return config;
    }

    // Priority 2: Fall back to API key (for development)
    const apiKey = getApiKey();
    if (apiKey) {
      config.headers['X-API-Key'] = apiKey;
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

    // Handle 401 Unauthorized
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      // Try to refresh token if we have one
      if (tokenManager.getTokenInfo()) {
        try {
          const newToken = await refreshAccessToken();
          if (newToken) {
            // Update token manager
            tokenManager.setToken({
              accessToken: newToken,
              expiresAt: Date.now() + (tokenConfig.tokenLifetime! * 60 * 1000),
              tokenType: 'Bearer',
            });

            // Update request header
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return api(originalRequest);
          }
        } catch (refreshError) {
          console.error('Token refresh failed:', refreshError);
        }

        // Refresh failed, clear token
        tokenManager.clear();
      }

      // Try to get new token with API key
      const apiKey = getApiKey();
      if (apiKey) {
        try {
          const response = await axios.post(`${API_URL}/auth/token`, {}, {
            headers: { 'X-API-Key': apiKey },
            withCredentials: true, // Enable cookies
          });

          const { access_token, expires_in } = response.data;

          // Store in token manager
          tokenManager.setToken({
            accessToken: access_token,
            expiresAt: Date.now() + (expires_in || 300) * 1000,
            tokenType: 'Bearer',
          });

          // Retry original request
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
          return api(originalRequest);
        } catch (tokenError) {
          console.error('Failed to get new token:', tokenError);
          tokenManager.clear();
        }
      }
    }

    return Promise.reject(error);
  }
);

// ============================================
// TOKEN REFRESH FUNCTION
// ============================================
async function refreshAccessToken(): Promise<string | null> {
  const tokenInfo = tokenManager.getTokenInfo();

  // Check if refresh is even needed
  if (!tokenManager.needsRefresh()) {
    return tokenInfo?.accessToken || null;
  }

  try {
    // Call backend refresh endpoint
    const response = await axios.post(`${API_URL}/auth/refresh`, {}, {
      withCredentials: true, // Send httpOnly cookie
      headers: {
        ...(tokenManager.getAccessToken()
          ? { Authorization: `Bearer ${tokenManager.getAccessToken()}` }
          : {}
        )
      },
    });

    const { access_token, expires_in } = response.data;

    // Update token manager
    tokenManager.setToken({
      accessToken: access_token,
      expiresAt: Date.now() + (expires_in || 300) * 1000,
      tokenType: 'Bearer',
    });

    return access_token;
  } catch (error) {
    console.error('Token refresh failed:', error);
    tokenManager.incrementRefreshAttempts();

    if (tokenManager.shouldGiveUp()) {
      tokenManager.clear();
      // Dispatch event for UI to handle
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('token-expired'));
      }
    }

    return null;
  }
}

// ============================================
// AUTOMATIC TOKEN REFRESH SETUP
// ============================================
const cleanupTokenRefresh = setupTokenRefresh(async () => {
  return await refreshAccessToken();
});

// ============================================
// TOKEN EXPIRED EVENT HANDLER
// ============================================
if (typeof window !== 'undefined') {
  window.addEventListener('token-expired', () => {
    // Redirect to login or show login modal
    console.warn('Token expired and refresh failed');
    // You can dispatch a custom event here for your app to handle
    window.dispatchEvent(new CustomEvent('auth-required', {
      detail: { reason: 'token_expired' }
    }));
  });

  // Listen for visibility changes to check token validity
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && tokenManager.isTokenValid() && tokenManager.needsRefresh()) {
      // Token is valid but needs refresh, do it now
      refreshAccessToken().catch(console.error);
    }
  });
}

// ============================================
// EXPORTS
// ============================================
export { tokenManager, tokenConfig };

/**
 * Initialize authentication with API key
 * Call this on app startup to get initial token
 */
export async function initializeAuth(): Promise<void> {
  const apiKey = getApiKey();

  if (apiKey && !tokenManager.isTokenValid()) {
    try {
      const response = await axios.post(`${API_URL}/auth/token`, {}, {
        headers: { 'X-API-Key': apiKey },
        withCredentials: true,
      });

      const { access_token, expires_in } = response.data;

      tokenManager.setToken({
        accessToken: access_token,
        expiresAt: Date.now() + (expires_in || 300) * 1000,
        tokenType: 'Bearer',
      });
    } catch (error) {
      console.error('Failed to initialize auth:', error);
    }
  }
}

/**
 * Logout and clear tokens
 */
export async function logout(): Promise<void> {
  try {
    // Call backend logout endpoint (if available)
    await axios.post(`${API_URL}/auth/logout`, {}, {
      withCredentials: true,
    });
  } catch (error) {
    console.error('Logout request failed:', error);
  } finally {
    // Always clear local token
    tokenManager.clear();
  }
}

/**
 * Get current authentication status
 */
export function getAuthStatus() {
  return {
    isAuthenticated: tokenManager.isTokenValid(),
    tokenExpiry: tokenManager.getTokenInfo()?.expiresAt || null,
    needsRefresh: tokenManager.needsRefresh(),
    lifetimePercentage: tokenManager.getLifetimePercentage(),
    timeUntilExpiry: tokenManager.getTimeUntilExpiry(),
    timeUntilRefresh: tokenManager.getTimeUntilRefresh(),
  };
}

/**
 * Cleanup function (call when app unmounts)
 */
export function cleanupAuth(): void {
  cleanupTokenRefresh();
  tokenManager.destroy();
}

// Export for testing
export { resetTokenManager } from '../auth/tokenManager';
