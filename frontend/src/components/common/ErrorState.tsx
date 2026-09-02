interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

/** Inline error box with optional retry — the non-empty twin of EmptyState. */
export function ErrorState({ message = 'Failed to load data', onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-[var(--color-down)]/30 bg-[var(--color-down)]/10 p-4 text-center"
    >
      <p className="text-sm text-[var(--color-text-primary)]">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 rounded border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm text-[var(--color-text-primary)] hover:bg-white/5"
        >
          Retry
        </button>
      )}
    </div>
  );
}
