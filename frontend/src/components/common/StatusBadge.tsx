import type { HealthStatus } from '../../types';
import { getHealthColor, getHealthLabel } from '../../utils/health';

export function StatusBadge({
  status,
  className = ''
}: {
  status: HealthStatus;
  className?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${className}`}>
      <span
        className="h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: getHealthColor(status) }}
      />
      {getHealthLabel(status)}
    </span>
  );
}
