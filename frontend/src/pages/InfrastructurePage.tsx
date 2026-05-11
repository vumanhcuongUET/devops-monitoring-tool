import { usePolling } from '../hooks/usePolling';
import { fetchInfrastructureMetrics } from '../api/infrastructure';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { SparklineChart } from '../components/common/SparklineChart';
import type { NodeMetrics } from '../types';
import { formatPercent } from '../utils/formatters';

export function InfrastructurePage() {
  const { data, isLoading } = usePolling<NodeMetrics[]>(['infra-metrics'], fetchInfrastructureMetrics);

  if (isLoading) return <LoadingSkeleton rows={3} />;

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Infrastructure</h2>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {(data || []).map((node) => (
          <div key={node.name} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
            <h3 className="mb-3 font-semibold">{node.name}</h3>
            <div className="grid grid-cols-3 gap-4">
              <MetricGauge label="CPU" value={node.cpu_percent} />
              <MetricGauge label="Memory" value={node.memory_percent} />
              <MetricGauge label="Disk" value={node.disk_percent} />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-4">
              <div>
                <div className="mb-1 text-xs text-[var(--color-text-secondary)]">CPU History</div>
                <SparklineChart data={node.cpu_history} />
              </div>
              <div>
                <div className="mb-1 text-xs text-[var(--color-text-secondary)]">Memory History</div>
                <SparklineChart data={node.memory_history} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MetricGauge({ label, value }: { label: string; value: number }) {
  const color =
    value > 90 ? 'bg-[var(--color-down)]' :
    value > 80 ? 'bg-[var(--color-degraded)]' :
    'bg-[var(--color-healthy)]';

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-[var(--color-text-secondary)]">{label}</span>
        <span className="font-medium">{formatPercent(value)}</span>
      </div>
      <div className="h-2 rounded-full bg-[var(--color-bg-secondary)]">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
    </div>
  );
}
