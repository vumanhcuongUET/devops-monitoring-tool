import { Bell } from 'lucide-react';
import type { AlertEvent } from '../../types';
import { formatTimestamp } from '../../utils/formatters';

export function RecentAlerts({ alerts }: { alerts: AlertEvent[] }) {
  if (!alerts.length) {
    return (
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
        <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
          <Bell size={16} />
          No recent alerts
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)]">
      <div className="border-b border-[var(--color-border)] px-4 py-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Bell size={16} />
          Recent Alerts
        </h3>
      </div>
      <div className="divide-y divide-[var(--color-border)]">
        {alerts.slice(0, 10).map((alert) => (
          <div key={alert.id} className="flex items-center justify-between px-4 py-2">
            <div className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${
                  alert.severity === 'critical'
                    ? 'bg-[var(--color-down)]'
                    : alert.severity === 'warning'
                    ? 'bg-[var(--color-degraded)]'
                    : 'bg-blue-400'
                }`}
              />
              <span className="text-sm">{alert.rule_name}</span>
            </div>
            <div className="flex items-center gap-3 text-xs text-[var(--color-text-secondary)]">
              <span
                className={
                  alert.status === 'firing'
                    ? 'text-[var(--color-down)]'
                    : 'text-[var(--color-healthy)]'
                }
              >
                {alert.status.toUpperCase()}
              </span>
              <span>{formatTimestamp(alert.timestamp)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
