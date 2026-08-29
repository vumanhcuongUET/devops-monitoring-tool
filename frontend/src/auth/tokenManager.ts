/**
 * Token Manager for Short-Lived Token Authentication
 *
 * Features:
 * - Short-lived tokens (5-15 minutes)
 * - Automatic refresh before expiry
 * - Secure token storage in memory (with sessionStorage backup)
 * - Token refresh with retry logic
 */

export interface TokenInfo {
  accessToken: string;
  refreshToken?: string;
  expiresAt: number; // Unix timestamp
  tokenType: 'Bearer';
}

export interface TokenManagerConfig {
  tokenLifetime: number; // Token lifetime in minutes (default: 5)
  refreshBuffer: number; // Time before expiry to refresh (default: 30 seconds)
  maxRefreshAttempts: number; // Maximum refresh attempts (default: 3)
}

const DEFAULT_CONFIG: TokenManagerConfig = {
  tokenLifetime: 5, // 5 minutes
  refreshBuffer: 30, // 30 seconds before expiry
  maxRefreshAttempts: 3,
};

class TokenManager {
  private currentToken: TokenInfo | null = null;
  private refreshTimer: NodeJS.Timeout | null = null;
  private refreshAttempts = 0;
  private config: TokenManagerConfig;

  constructor(config?: Partial<TokenManagerConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.initFromStorage();
  }

  /**
   * Initialize from sessionStorage (backup storage)
   */
  private initFromStorage(): void {
    if (typeof sessionStorage === 'undefined') return;

    try {
      const stored = sessionStorage.getItem('token_info');
      if (stored) {
        const tokenInfo = JSON.parse(stored) as TokenInfo;
        // Check if token is still valid
        if (tokenInfo.expiresAt > Date.now()) {
          this.currentToken = tokenInfo;
          this.scheduleRefresh();
        } else {
          // Token expired, clear storage
          this.clear();
        }
      }
    } catch (error) {
      console.error('Failed to restore token from storage:', error);
    }
  }

  /**
   * Store token info in sessionStorage (backup)
   */
  private storeToken(token: TokenInfo): void {
    if (typeof sessionStorage === 'undefined') return;

    try {
      sessionStorage.setItem('token_info', JSON.stringify(token));
    } catch (error) {
      console.error('Failed to store token:', error);
    }
  }

  /**
   * Get current access token
   */
  public getAccessToken(): string | null {
    return this.currentToken?.accessToken || null;
  }

  /**
   * Get current token info
   */
  public getTokenInfo(): TokenInfo | null {
    return this.currentToken;
  }

  /**
   * Check if token is valid and not expired
   */
  public isTokenValid(): boolean {
    if (!this.currentToken) return false;
    return this.currentToken.expiresAt > Date.now();
  }

  /**
   * Check if token needs refresh soon
   */
  public needsRefresh(): boolean {
    if (!this.currentToken) return false;
    const refreshTime = this.currentToken.expiresAt - (this.config.refreshBuffer * 1000);
    return Date.now() >= refreshTime;
  }

  /**
   * Set new token
   */
  public setToken(tokenInfo: TokenInfo): void {
    // Calculate expiry if not provided
    if (!tokenInfo.expiresAt) {
      tokenInfo.expiresAt = Date.now() + (this.config.tokenLifetime * 60 * 1000);
    }

    this.currentToken = tokenInfo;
    this.storeToken(tokenInfo);
    this.refreshAttempts = 0;
    this.scheduleRefresh();
  }

  /**
   * Clear current token
   */
  public clear(): void {
    this.currentToken = null;
    this.refreshAttempts = 0;

    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    }

    if (typeof sessionStorage !== 'undefined') {
      try {
        sessionStorage.removeItem('token_info');
      } catch (error) {
        console.error('Failed to clear token from storage:', error);
      }
    }
  }

  /**
   * Schedule automatic token refresh
   */
  private scheduleRefresh(): void {
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
    }

    if (!this.currentToken) return;

    // Calculate time until refresh (buffer before expiry)
    const refreshTime = this.currentToken.expiresAt - (this.config.refreshBuffer * 1000);
    const timeUntilRefresh = refreshTime - Date.now();

    // Only schedule if refresh time is in the future
    if (timeUntilRefresh > 0) {
      this.refreshTimer = setTimeout(() => {
        this.onTokenRefreshNeeded();
      }, timeUntilRefresh);
    }
  }

  /**
   * Callback when token refresh is needed
   */
  private onTokenRefreshNeeded(): void {
    // Dispatch custom event for token refresh
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('token-refresh-needed'));
    }
  }

  /**
   * Increment refresh attempts (for retry logic)
   */
  public incrementRefreshAttempts(): void {
    this.refreshAttempts++;
  }

  /**
   * Reset refresh attempts
   */
  public resetRefreshAttempts(): void {
    this.refreshAttempts = 0;
  }

  /**
   * Check if max refresh attempts reached
   */
  public shouldGiveUp(): boolean {
    return this.refreshAttempts >= this.config.maxRefreshAttempts;
  }

  /**
   * Get time until token expires (in milliseconds)
   */
  public getTimeUntilExpiry(): number {
    if (!this.currentToken) return 0;
    return Math.max(0, this.currentToken.expiresAt - Date.now());
  }

  /**
   * Get time until refresh needed (in milliseconds)
   */
  public getTimeUntilRefresh(): number {
    if (!this.currentToken) return 0;
    const refreshTime = this.currentToken.expiresAt - (this.config.refreshBuffer * 1000);
    return Math.max(0, refreshTime - Date.now());
  }

  /**
   * Get token lifetime percentage remaining
   */
  public getLifetimePercentage(): number {
    if (!this.currentToken) return 0;
    const totalLifetime = this.config.tokenLifetime * 60 * 1000;
    const remaining = this.getTimeUntilExpiry();
    return Math.max(0, Math.min(100, (remaining / totalLifetime) * 100));
  }

  /**
   * Update configuration
   */
  public updateConfig(config: Partial<TokenManagerConfig>): void {
    this.config = { ...this.config, ...config };
    // Reschedule refresh with new config
    if (this.currentToken) {
      this.scheduleRefresh();
    }
  }

  /**
   * Cleanup (call this when destroying the token manager)
   */
  public destroy(): void {
    this.clear();
  }
}

// Global singleton instance
let tokenManagerInstance: TokenManager | null = null;

/**
 * Get the global token manager instance
 */
export function getTokenManager(config?: Partial<TokenManagerConfig>): TokenManager {
  if (!tokenManagerInstance) {
    tokenManagerInstance = new TokenManager(config);
  } else if (config) {
    tokenManagerInstance.updateConfig(config);
  }
  return tokenManagerInstance;
}

/**
 * Reset the global token manager (for testing)
 */
export function resetTokenManager(): void {
  if (tokenManagerInstance) {
    tokenManagerInstance.destroy();
    tokenManagerInstance = null;
  }
}

/**
 * Token refresh callback type
 */
export type TokenRefreshCallback = () => Promise<string | null>;

/**
 * Set up automatic token refresh with callback
 */
export function setupTokenRefresh(callback: TokenRefreshCallback): () => void {
  const tokenManager = getTokenManager();

  const handleRefresh = async () => {
    if (tokenManager.needsRefresh()) {
      try {
        const newToken = await callback();
        if (newToken) {
          // Update token with same expiry calculation
          tokenManager.setToken({
            accessToken: newToken,
            expiresAt: Date.now() + (tokenManager['config'].tokenLifetime * 60 * 1000),
            tokenType: 'Bearer',
          });
          tokenManager.resetRefreshAttempts();
        } else {
          tokenManager.incrementRefreshAttempts();
          if (tokenManager.shouldGiveUp()) {
            // Max attempts reached, clear token
            tokenManager.clear();
            // Redirect to login or show error
            if (typeof window !== 'undefined') {
              window.dispatchEvent(new Event('token-expired'));
            }
          }
        }
      } catch (error) {
        console.error('Token refresh failed:', error);
        tokenManager.incrementRefreshAttempts();
      }
    }
  };

  // Listen for refresh needed event
  if (typeof window !== 'undefined') {
    window.addEventListener('token-refresh-needed', handleRefresh);
  }

  // Also check periodically (every minute) as backup
  const checkInterval = setInterval(() => {
    if (!tokenManager.isTokenValid()) {
      clearInterval(checkInterval);
      return;
    }

    if (tokenManager.needsRefresh()) {
      handleRefresh();
    }
  }, 60000); // Check every minute

  // Return cleanup function
  return () => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('token-refresh-needed', handleRefresh);
    }
    clearInterval(checkInterval);
  };
}
