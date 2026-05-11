import type { TimeRange } from '../../types';

const presets: TimeRange[] = [
  { start: 'now-5m', end: 'now', label: '5m' },
  { start: 'now-15m', end: 'now', label: '15m' },
  { start: 'now-1h', end: 'now', label: '1h' },
  { start: 'now-6h', end: 'now', label: '6h' },
  { start: 'now-24h', end: 'now', label: '24h' },
];

export function TimeRangePicker({
  value,
  onChange,
}: {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
}) {
  return (
    <div className="flex gap-1 rounded-lg bg-[var(--color-bg-secondary)] p-1">
      {presets.map((p) => (
        <button
          key={p.label}
          onClick={() => onChange(p)}
          className={`rounded px-3 py-1 text-xs transition-colors ${
            value.label === p.label
              ? 'bg-[var(--color-accent)] text-white'
              : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
          }`}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
