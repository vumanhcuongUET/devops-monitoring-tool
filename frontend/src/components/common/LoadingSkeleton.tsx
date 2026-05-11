export function LoadingSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-10 animate-pulse rounded bg-[var(--color-bg-secondary)]" />
      ))}
    </div>
  );
}
