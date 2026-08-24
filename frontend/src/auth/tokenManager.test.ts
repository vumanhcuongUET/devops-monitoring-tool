/**
 * Token Manager Tests
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  TokenManager,
  getTokenManager,
  resetTokenManager,
  setupTokenRefresh,
  TokenInfo,
} from './tokenManager';

describe('TokenManager', () => {
  let tokenManager: TokenManager;

  beforeEach(() => {
    // Reset global instance before each test
    resetTokenManager();
    // Create fresh instance for testing
    tokenManager = new TokenManager({
      tokenLifetime: 5, // 5 minutes
      refreshBuffer: 30, // 30 seconds
      maxRefreshAttempts: 3,
    });
  });

  afterEach(() => {
    tokenManager.destroy();
    resetTokenManager();
  });

  describe('Token Storage', () => {
    it('should store and retrieve token', () => {
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt: Date.now() + 300000, // 5 minutes from now
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);

      expect(tokenManager.getAccessToken()).toBe('test-token');
      expect(tokenManager.getTokenInfo()).toEqual(tokenInfo);
    });

    it('should clear token', () => {
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt: Date.now() + 300000,
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);
      expect(tokenManager.getAccessToken()).toBe('test-token');

      tokenManager.clear();
      expect(tokenManager.getAccessToken()).toBeNull();
      expect(tokenManager.getTokenInfo()).toBeNull();
    });

    it('should initialize token with expiry calculation', () => {
      const now = Date.now();
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt: 0, // Will be calculated
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);

      const stored = tokenManager.getTokenInfo();
      expect(stored?.expiresAt).toBeGreaterThanOrEqual(now + 290000); // ~5 minutes
      expect(stored?.expiresAt).toBeLessThanOrEqual(now + 310000);
    });
  });

  describe('Token Validation', () => {
    it('should validate non-expired token', () => {
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt: Date.now() + 300000,
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);
      expect(tokenManager.isTokenValid()).toBe(true);
    });

    it('should invalidate expired token', () => {
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt: Date.now() - 1000, // 1 second ago
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);
      expect(tokenManager.isTokenValid()).toBe(false);
    });

    it('should handle missing token', () => {
      expect(tokenManager.isTokenValid()).toBe(false);
      expect(tokenManager.needsRefresh()).toBe(false);
    });
  });

  describe('Refresh Logic', () => {
    it('should detect when refresh is needed', () => {
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt: Date.now() + 35000, // 35 seconds from now (within buffer)
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);
      expect(tokenManager.needsRefresh()).toBe(true);
    });

    it('should not need refresh for fresh token', () => {
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt: Date.now() + 300000, // 5 minutes from now
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);
      expect(tokenManager.needsRefresh()).toBe(false);
    });

    it('should track refresh attempts', () => {
      expect(tokenManager.shouldGiveUp()).toBe(false);

      tokenManager.incrementRefreshAttempts();
      expect(tokenManager.shouldGiveUp()).toBe(false);

      tokenManager.incrementRefreshAttempts();
      expect(tokenManager.shouldGiveUp()).toBe(false);

      tokenManager.incrementRefreshAttempts();
      expect(tokenManager.shouldGiveUp()).toBe(true);

      // Reset should clear attempts
      tokenManager.resetRefreshAttempts();
      expect(tokenManager.shouldGiveUp()).toBe(false);
    });
  });

  describe('Time Calculations', () => {
    it('should calculate time until expiry', () => {
      const expiresAt = Date.now() + 300000; // 5 minutes
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt,
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);
      const timeUntil = tokenManager.getTimeUntilExpiry();

      expect(timeUntil).toBeGreaterThan(290000); // ~4.8 minutes
      expect(timeUntil).toBeLessThan(310000); // ~5.2 minutes
    });

    it('should calculate time until refresh', () => {
      const expiresAt = Date.now() + 60000; // 1 minute
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt,
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);
      const timeUntilRefresh = tokenManager.getTimeUntilRefresh();

      // Should be ~30 seconds (60 - 30 buffer)
      expect(timeUntilRefresh).toBeGreaterThan(25000);
      expect(timeUntilRefresh).toBeLessThan(35000);
    });

    it('should return zero for expired token', () => {
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt: Date.now() - 1000,
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);
      expect(tokenManager.getTimeUntilExpiry()).toBe(0);
      expect(tokenManager.getTimeUntilRefresh()).toBe(0);
    });

    it('should calculate lifetime percentage', () => {
      // Create token with 5 minute lifetime
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt: Date.now() + 300000,
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);

      // At creation, should be near 100%
      const percentage = tokenManager.getLifetimePercentage();
      expect(percentage).toBeGreaterThan(95);
      expect(percentage).toBeLessThanOrEqual(100);
    });
  });

  describe('Configuration', () => {
    it('should update configuration', () => {
      expect(tokenManager['config'].tokenLifetime).toBe(5);

      tokenManager.updateConfig({ tokenLifetime: 10 });
      expect(tokenManager['config'].tokenLifetime).toBe(10);
    });

    it('should merge partial config updates', () => {
      const originalBuffer = tokenManager['config'].refreshBuffer;

      tokenManager.updateConfig({ tokenLifetime: 15 });
      expect(tokenManager['config'].tokenLifetime).toBe(15);
      expect(tokenManager['config'].refreshBuffer).toBe(originalBuffer); // Unchanged
    });
  });

  describe('Singleton Pattern', () => {
    it('should return same instance', () => {
      const instance1 = getTokenManager();
      const instance2 = getTokenManager();

      expect(instance1).toBe(instance2);
    });

    it('should update config on singleton', () => {
      resetTokenManager();
      const instance1 = getTokenManager({ tokenLifetime: 10 });
      const instance2 = getTokenManager();

      expect(instance1['config'].tokenLifetime).toBe(10);
      expect(instance2['config'].tokenLifetime).toBe(10);
      expect(instance1).toBe(instance2);
    });
  });

  describe('Cleanup', () => {
    it('should clear timers on destroy', () => {
      const tokenInfo: TokenInfo = {
        accessToken: 'test-token',
        expiresAt: Date.now() + 300000,
        tokenType: 'Bearer',
      };

      tokenManager.setToken(tokenInfo);
      expect(tokenManager['refreshTimer']).not.toBeNull();

      tokenManager.destroy();
      expect(tokenManager['refreshTimer']).toBeNull();
      expect(tokenManager.getTokenInfo()).toBeNull();
    });
  });
});

describe('setupTokenRefresh', () => {
  beforeEach(() => {
    resetTokenManager();
    vi.useFakeTimers();
  });

  afterEach(() => {
    resetTokenManager();
    vi.useRealTimers();
  });

  it('should call refresh callback when token needs refresh', async () => {
    const refreshCallback = vi.fn().mockResolvedValue('new-token');
    const cleanup = setupTokenRefresh(refreshCallback);

    // Create token that needs immediate refresh
    const tokenManager = getTokenManager();
    const tokenInfo: TokenInfo = {
      accessToken: 'old-token',
      expiresAt: Date.now() + 30000, // 30 seconds (within buffer)
      tokenType: 'Bearer',
    };

    tokenManager.setToken(tokenInfo);

    // Trigger refresh event
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('token-refresh-needed'));
    }

    // Wait for async callback
    await vi.runAllTimersAsync();
    await new Promise(resolve => setImmediate(resolve));

    expect(refreshCallback).toHaveBeenCalled();

    cleanup();
  });

  it('should handle refresh callback failure', async () => {
    const refreshCallback = vi.fn().mockRejectedValue(new Error('Refresh failed'));
    const cleanup = setupTokenRefresh(refreshCallback);

    const tokenManager = getTokenManager();
    const tokenInfo: TokenInfo = {
      accessToken: 'test-token',
      expiresAt: Date.now() + 30000,
      tokenType: 'Bearer',
    };

    tokenManager.setToken(tokenInfo);

    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('token-refresh-needed'));
    }

    await vi.runAllTimersAsync();
    await new Promise(resolve => setImmediate(resolve));

    expect(tokenManager.getRefreshAttempts?.()).toBeGreaterThan(0);

    cleanup();
  });
});
