/**
 * Token Manager Tests — sessionStorage-backed token store.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  getTokenManager,
  resetTokenManager,
  type TokenInfo,
} from './tokenManager';

function makeToken(expiresAt = Date.now() + 300000): TokenInfo {
  return { accessToken: 'test-token', expiresAt, tokenType: 'Bearer' };
}

describe('TokenManager', () => {
  let tokenManager: ReturnType<typeof getTokenManager>;

  beforeEach(() => {
    sessionStorage.clear();
    resetTokenManager();
    tokenManager = getTokenManager();
  });

  afterEach(() => {
    resetTokenManager();
    sessionStorage.clear();
  });

  describe('Token Storage', () => {
    it('should store and retrieve token', () => {
      const tokenInfo = makeToken();

      tokenManager.setToken(tokenInfo);

      expect(tokenManager.getAccessToken()).toBe('test-token');
      expect(tokenManager.getTokenInfo()).toEqual(tokenInfo);
    });

    it('should persist token to sessionStorage', () => {
      tokenManager.setToken(makeToken());

      expect(sessionStorage.getItem('token_info')).toContain('test-token');
    });

    it('should clear token and storage', () => {
      tokenManager.setToken(makeToken());

      tokenManager.clear();

      expect(tokenManager.getAccessToken()).toBeNull();
      expect(tokenManager.getTokenInfo()).toBeNull();
      expect(sessionStorage.getItem('token_info')).toBeNull();
    });

    it('should restore a valid token from sessionStorage on init', async () => {
      sessionStorage.setItem(
        'token_info',
        JSON.stringify(makeToken(Date.now() + 60000))
      );

      // Fresh module instance = simulated app restart (resetTokenManager
      // would wipe sessionStorage, so it can't be used here)
      vi.resetModules();
      const { getTokenManager: freshGetTokenManager } = await import('./tokenManager');
      const restored = freshGetTokenManager();

      expect(restored.getAccessToken()).toBe('test-token');
      expect(restored.isTokenValid()).toBe(true);
    });

    it('should drop an expired token from sessionStorage on init', async () => {
      sessionStorage.setItem(
        'token_info',
        JSON.stringify(makeToken(Date.now() - 1000))
      );

      vi.resetModules();
      const { getTokenManager: freshGetTokenManager } = await import('./tokenManager');
      const restored = freshGetTokenManager();

      expect(restored.getAccessToken()).toBeNull();
      expect(sessionStorage.getItem('token_info')).toBeNull();
    });
  });

  describe('Token Validation', () => {
    it('should validate non-expired token', () => {
      tokenManager.setToken(makeToken());
      expect(tokenManager.isTokenValid()).toBe(true);
    });

    it('should invalidate expired token', () => {
      tokenManager.setToken(makeToken(Date.now() - 1000));
      expect(tokenManager.isTokenValid()).toBe(false);
    });

    it('should handle missing token', () => {
      expect(tokenManager.isTokenValid()).toBe(false);
      expect(tokenManager.getAccessToken()).toBeNull();
      expect(tokenManager.getTokenInfo()).toBeNull();
    });
  });

  describe('Singleton Pattern', () => {
    it('should return same instance', () => {
      const instance1 = getTokenManager();
      const instance2 = getTokenManager();

      expect(instance1).toBe(instance2);
    });

    it('should create a fresh instance after reset', () => {
      tokenManager.setToken(makeToken());
      resetTokenManager();

      expect(getTokenManager().getTokenInfo()).toBeNull();
    });
  });
});
