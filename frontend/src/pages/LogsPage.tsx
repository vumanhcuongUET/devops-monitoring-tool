import { useState } from 'react';
import { usePolling } from '../hooks/usePolling';
import { fetchLogs } from '../api/logs';
import { DataTable, type Column } from '../components/common/DataTable';
import { TimeRangePicker } from '../components/common/TimeRangePicker';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import type { LogQueryParams, LogsResponse, TimeRange } from '../types';

export function LogsPage() {
  const [params, setParams] = useState<LogQueryParams>({ page: 1, size: 50 });
  const [timeRange, setTimeRange] = useState<TimeRange>({ start: 'now-1h', end: 'now', label: '1h' });
  const [filters, setFilters] = useState({ q: '', level: '', service: '' });

  const { data, isLoading } = usePolling<LogsResponse>(
    ['logs', JSON.stringify(params), JSON.stringify(timeRange)],
    () => fetchLogs({ ...params, ...filters, start: timeRange.start, end: timeRange.end }),
  );

  const columns: Column<Record<string, unknown>>[] = [
    { key: '@timestamp', header: 'Timestamp', render: (row) => String(row['@timestamp'] ?? '') },
    {
      key: 'level',
      header: 'Level',
      render: (row) => {
        const level = String(row['level'] ?? '');
        const color =
          level === 'ERROR' ? 'text-[var(--color-down)]' :
          level === 'WARN' ? 'text-[var(--color-degraded)]' :
          'text-[var(--color-text-secondary)]';
        return <span className={`font-medium ${color}`}>{level}</span>;
      },
    },
    { key: 'service', header: 'Service', render: (row) => String(row['service'] ?? '') },
    { key: 'message', header: 'Message', render: (row) => <span className="line-clamp-2">{String(row['message'] ?? '')}</span> },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Logs</h2>
        <TimeRangePicker value={timeRange} onChange={setTimeRange} />
      </div>
      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Search..."
          value={filters.q}
          onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
          className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
        />
        <select
          value={filters.level}
          onChange={(e) => setFilters((f) => ({ ...f, level: e.target.value }))}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm"
        >
          <option value="">All Levels</option>
          <option value="ERROR">ERROR</option>
          <option value="WARN">WARN</option>
          <option value="INFO">INFO</option>
        </select>
      </div>
      {isLoading ? <LoadingSkeleton /> : (
        <>
          <DataTable columns={columns} data={(data?.items || []) as unknown as Record<string, unknown>[]} />
          {data && (
            <div className="flex items-center justify-between text-sm text-[var(--color-text-secondary)]">
              <span>Total: {data.total}</span>
              <div className="flex gap-2">
                <button
                  disabled={data.page <= 1}
                  onClick={() => setParams((p) => ({ ...p, page: p.page! - 1 }))}
                  className="rounded px-3 py-1 hover:bg-white/5 disabled:opacity-30"
                >
                  Previous
                </button>
                <span>Page {data.page}</span>
                <button
                  disabled={data.page * data.size >= data.total}
                  onClick={() => setParams((p) => ({ ...p, page: p.page! + 1 }))}
                  className="rounded px-3 py-1 hover:bg-white/5 disabled:opacity-30"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
