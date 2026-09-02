import { toast } from 'react-hot-toast';
import { Menu } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useWebSocket } from '../../hooks/useWebSocket';
import { logout, tokenManager } from '../../api/client';

const routeTitles: Record<string, string> = {
  '/': 'Overview',
  '/logs': 'Logs',
  '/apm': 'APM',
  '/slo': 'SLO',
  '/infrastructure': 'Infrastructure',
  '/kubernetes': 'Kubernetes',
  '/alerts': 'Alerts',
  '/actions': 'Actions',
  '/governance': 'Governance',
  '/skills': 'Skills',
};

export function Header({ onMenuClick }: { onMenuClick?: () => void }) {
  const { connected } = useWebSocket();
  const location = useLocation();

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
    <header className="flex h-14 items-center justify-between gap-4 border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-4 md:px-6">
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onMenuClick}
          aria-label="Toggle navigation"
          className="flex min-h-[40px] min-w-[40px] items-center justify-center rounded border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] md:hidden"
        >
          <Menu size={18} />
        </button>
        <h2 className="text-sm text-[var(--color-text-secondary)] truncate">
          {routeTitles[location.pathname] ?? 'DevOps Monitor'}
        </h2>
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
            className="rounded border border-[var(--color-border)] px-3 py-1.5 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] min-h-[36px]"
          >
            Logout
          </button>
        )}
      </div>
    </header>
  );
}
