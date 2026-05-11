import { useWebSocket } from '../../hooks/useWebSocket';

export function Header() {
  const { connected } = useWebSocket();
  return (
    <header className="flex h-14 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-6">
      <div className="text-sm text-[var(--color-text-secondary)]">
        System Overview
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span
          className={`h-2 w-2 rounded-full ${
            connected ? 'bg-[var(--color-healthy)]' : 'bg-[var(--color-down)]'
          }`}
        />
        <span className="text-[var(--color-text-secondary)]">
          {connected ? 'Live' : 'Polling'}
        </span>
      </div>
    </header>
  );
}
