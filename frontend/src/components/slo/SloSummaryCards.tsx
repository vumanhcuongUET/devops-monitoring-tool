import type { SloDashboard } from '../../types';

export function SloSummaryCards({ data }: { data: SloDashboard }) {
  const cards = [
    {
      label: 'SLOs Met',
      value: `${data.healthy_count}/${data.total_slos}`,
      color: data.breached_count === 0 ? 'var(--color-healthy)' : 'var(--color-degraded)',
    },
    {
      label: 'Breached',
      value: String(data.breached_count),
      color: data.breached_count > 0 ? 'var(--color-down)' : 'var(--color-healthy)',
    },
    {
      label: 'Warning',
      value: String(data.warning_count),
      color: data.warning_count > 0 ? 'var(--color-degraded)' : 'var(--color-healthy)',
    },
    {
      label: 'Avg Budget Remaining',
      value: `${data.avg_budget_remaining}%`,
      color: data.avg_budget_remaining > 50 ? 'var(--color-healthy)' : data.avg_budget_remaining > 20 ? 'var(--color-degraded)' : 'var(--color-down)',
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {cards.map((card) => (
        <div key={card.label} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
          <div className="text-xs text-[var(--color-text-secondary)]">{card.label}</div>
          <div className="mt-1 text-2xl font-bold" style={{ color: card.color }}>{card.value}</div>
        </div>
      ))}
    </div>
  );
}
