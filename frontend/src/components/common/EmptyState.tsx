/**
 * Fallback UI when the monitoring API is down or unreachable.
 */

export function ApiDownEmptyState({ onRetry }: { onRetry?: () => void }) {
  return (
    <div
      className="
        flex flex-col items-center justify-center
        text-center
        bg-slate-900/50
        rounded-lg border border-slate-700
        py-12 px-6
      "
      data-testid="empty-state"
      data-type="api-down"
    >
      <div className="text-5xl mb-4 opacity-70">🔌</div>

      <h3 className="text-lg font-semibold text-slate-100 mb-2">
        Unable to connect to server
      </h3>

      <p className="text-sm text-slate-400 max-w-md mb-6">
        We couldn't reach the monitoring backend. Please check your connection
        or try again later.
      </p>

      {onRetry && (
        <button
          onClick={onRetry}
          className="
            px-4 py-2 rounded-lg font-medium text-sm
            transition-colors duration-200
            bg-blue-600 text-white hover:bg-blue-700
          "
          data-testid="empty-state-action"
        >
          Retry Connection
        </button>
      )}
    </div>
  );
}
