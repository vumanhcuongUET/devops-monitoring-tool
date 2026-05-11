import { useState } from 'react';
import { usePolling } from '../hooks/usePolling';
import { fetchSloDashboard, fetchSlowApis } from '../api/slo';
import { SloSummaryCards } from '../components/slo/SloSummaryCards';
import { SloTable } from '../components/slo/SloTable';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import type { SloDashboard, SloApiDetail } from '../types';

export function SloPage() {
  const [windowDays, setWindowDays] = useState<number | undefined>(undefined);

  const { data, isLoading } = usePolling<SloDashboard>(
    ['slo-dashboard', String(windowDays)],
    () => fetchSloDashboard(windowDays),
  );

  const services = data ? [...new Set(data.results.map((r) => r.service_name))] : [];

  const { data: slowApisData } = usePolling<Record<string, SloApiDetail[]>>(
    ['slo-slow-apis', ...services],
    async () => {
      const map: Record<string, SloApiDetail[]> = {};
      await Promise.all(
        services.map(async (svc) => {
          try {
            map[svc] = await fetchSlowApis(svc);
          } catch {
            map[svc] = [];
          }
        }),
      );
      return map;
    },
    services.length > 0,
  );

  if (isLoading || !data) {
    return <LoadingSkeleton rows={4} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">SLO Dashboard</h2>
        <div className="flex gap-1 rounded-lg bg-[var(--color-bg-secondary)] p-1">
          <button
            onClick={() => setWindowDays(undefined)}
            className={`rounded px-3 py-1 text-sm ${windowDays === undefined ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-secondary)]'}`}
          >
            All
          </button>
          <button
            onClick={() => setWindowDays(7)}
            className={`rounded px-3 py-1 text-sm ${windowDays === 7 ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-secondary)]'}`}
          >
            7d
          </button>
          <button
            onClick={() => setWindowDays(30)}
            className={`rounded px-3 py-1 text-sm ${windowDays === 30 ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-secondary)]'}`}
          >
            30d
          </button>
        </div>
      </div>

      <SloSummaryCards data={data} />

      <SloTable
        results={data.results}
        slowApisMap={slowApisData || {}}
      />
    </div>
  );
}
