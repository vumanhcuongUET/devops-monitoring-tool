/**
 * Minimal token store backed by sessionStorage.
 *
 * The axios layer (api/client.ts) owns refresh/retry logic — this module
 * only stores the current token and answers validity questions.
 */

export interface TokenInfo {
  accessToken: string;
  refreshToken?: string;
  expiresAt: number; // Unix timestamp (ms)
  tokenType: 'Bearer';
  /** Authenticated username (JWT sub) — set at login, preserved across refreshes. */
  username?: string;
}

const STORAGE_KEY = 'token_info';

class TokenManager {
  private currentToken: TokenInfo | null = null;

  constructor() {
    this.restoreFromStorage();
  }

  private restoreFromStorage(): void {
    if (typeof sessionStorage === 'undefined') return;

    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (!stored) return;

      const tokenInfo = JSON.parse(stored) as TokenInfo;
      if (tokenInfo.expiresAt > Date.now()) {
        this.currentToken = tokenInfo;
      } else {
        this.clear();
      }
    } catch (error) {
      console.error('Failed to restore token from storage:', error);
    }
  }

  /** Get current access token */
  public getAccessToken(): string | null {
    return this.currentToken?.accessToken ?? null;
  }

  /** Get current token info */
  public getTokenInfo(): TokenInfo | null {
    return this.currentToken;
  }

  /** Authenticated username for audit trails, or null when signed out */
  public getUsername(): string | null {
    return this.currentToken?.username ?? null;
  }

  /** Check if token is valid and not expired */
  public isTokenValid(): boolean {
    return !!this.currentToken && this.currentToken.expiresAt > Date.now();
  }

  /** Set new token (persisted to sessionStorage) */
  public setToken(tokenInfo: TokenInfo): void {
    this.currentToken = tokenInfo;

    if (typeof sessionStorage === 'undefined') return;
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(tokenInfo));
    } catch (error) {
      console.error('Failed to store token:', error);
    }
  }

  /** Clear current token and its storage */
  public clear(): void {
    this.currentToken = null;

    if (typeof sessionStorage === 'undefined') return;
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch (error) {
      console.error('Failed to clear token from storage:', error);
    }
  }
}

// Global singleton instance
let tokenManagerInstance: TokenManager | null = null;

/** Get the global token manager instance */
export function getTokenManager(): TokenManager {
  if (!tokenManagerInstance) {
    tokenManagerInstance = new TokenManager();
  }
  return tokenManagerInstance;
}

/** Reset the global token manager (for testing) */
export function resetTokenManager(): void {
  tokenManagerInstance?.clear();
  tokenManagerInstance = null;
}
