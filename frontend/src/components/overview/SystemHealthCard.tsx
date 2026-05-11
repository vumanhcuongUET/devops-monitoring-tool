import type { HealthStatus } from '../../types';
import { getHealthColor } from '../../utils/health';
import { StatusBadge } from '../common/StatusBadge';

interface Props {
  title: string;
  status: HealthStatus;
  icon: React.ReactNode;
  metrics: { label: string; value: string }[];
  onClick?: () => void;
}

export function SystemHealthCard({ title, status, icon, metrics, onClick }: Props) {
  return (
    <div
      onClick={onClick}
      className={`cursor-pointer rounded-lg border-2 bg-[var(--color-bg-card)] p-5 transition-shadow hover:shadow-lg ${
        onClick ? '' : ''
      }`}
      style={{ borderColor: getHealthColor(status) }}
    >
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <h3 className="font-semibold">{title}</h3>
        </div>
        <StatusBadge status={status} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        {metrics.map((m) => (
          <div key={m.label}>
            <div className="text-xs text-[var(--color-text-secondary)]">{m.label}</div>
            <div className="text-sm font-medium">{m.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
