import { toast } from 'react-hot-toast';
import { useWebSocket } from '../../hooks/useWebSocket';
import { logout, tokenManager } from '../../api/client';

export function Header() {
  const { connected } = useWebSocket();

  const signedIn = Boolean(tokenManager.getTokenInfo());

  const handleLogout = async () => {
    try {
      // Phase 15: server-side revocation — tokens issued to this user are
      // invalid afterwards, not just removed from this browser.
      await logout();
      toast.success('Logged out');
    } finally {
      // drops the app back to the login screen (same channel as a 401)
      window.dispatchEvent(
        new CustomEvent('auth-required', { detail: { reason: 'logout' } })
      );
    }
  };

  return (
    <header className="flex h-14 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-6">
      <div className="text-sm text-[var(--color-text-secondary)]">
        System Overview
      </div>
      <div className="flex items-center gap-4 text-xs">
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              connected ? 'bg-[var(--color-healthy)]' : 'bg-[var(--color-down)]'
            }`}
          />
          <span className="text-[var(--color-text-secondary)]">
            {connected ? 'Live' : 'Polling'}
          </span>
        </div>
        {signedIn && (
          <button
            onClick={handleLogout}
            className="rounded border border-[var(--color-border)] px-2 py-1 text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
          >
            Logout
          </button>
        )}
      </div>
    </header>
  );
}
