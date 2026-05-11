import { useState } from 'react';
import { DataTable, type Column } from '../common/DataTable';
import type { SloResult, SloApiDetail } from '../../types';
import { formatDuration, formatPercent } from '../../utils/formatters';

interface Props {
  results: SloResult[];
  slowApisMap: Record<string, SloApiDetail[]>;
}

export function SloTable({ results, slowApisMap }: Props) {
  const [expandedService, setExpandedService] = useState<string | null>(null);

  const columns: Column<SloResult>[] = [
    {
      key: 'service_name',
      header: 'Service',
      render: (row) => (
        <button
          onClick={() => setExpandedService(expandedService === row.service_name ? null : row.service_name)}
          className="text-left hover:text-[var(--color-accent)]"
        >
          {row.service_name} {slowApisMap[row.service_name]?.length ? `(${slowApisMap[row.service_name].length} slow)` : ''}
        </button>
      ),
    },
    {
      key: 'slo_type',
      header: 'Type',
      render: (row) => (
        <span className="rounded bg-[var(--color-bg-secondary)] px-2 py-0.5 text-xs">
          {row.slo_type === 'availability' ? 'Avail' : 'Latency'} {row.window_days}d
        </span>
      ),
    },
    { key: 'target', header: 'Target', render: (row) => `${row.target}%` },
    {
      key: 'current_value',
      header: 'Current',
      render: (row) => {
        const met = row.current_value >= row.target;
        return (
          <span className={met ? 'text-[var(--color-healthy)]' : 'text-[var(--color-down)]'}>
            {formatPercent(row.current_value)}
          </span>
        );
      },
    },
    {
      key: 'error_budget_remaining_percent',
      header: 'Budget Left',
      render: (row) => {
        const v = row.error_budget_remaining_percent;
        const color = v > 50 ? 'text-[var(--color-healthy)]' : v > 20 ? 'text-[var(--color-degraded)]' : 'text-[var(--color-down)]';
        return <span className={color}>{formatPercent(v)}</span>;
      },
    },
    {
      key: 'bad_requests',
      header: 'Bad/Total',
      render: (row) => (
        <span>
          <span className="text-[var(--color-down)]">{row.bad_requests}</span>
          {' / '}
          {row.total_requests}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => {
        const colors: Record<string, string> = {
          healthy: 'bg-[var(--color-healthy)]/20 text-[var(--color-healthy)]',
          warning: 'bg-[var(--color-degraded)]/20 text-[var(--color-degraded)]',
          critical: 'bg-[var(--color-down)]/20 text-[var(--color-down)]',
          breached: 'bg-[var(--color-down)]/20 text-[var(--color-down)]',
        };
        return (
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${colors[row.status] || ''}`}>
            {row.status.toUpperCase()}
          </span>
        );
      },
    },
  ];

  const slowApiColumns: Column<SloApiDetail>[] = [
    { key: 'transaction_name', header: 'API', render: (row) => <code className="text-xs">{row.transaction_name}</code> },
    { key: 'total_requests', header: 'Requests' },
    {
      key: 'error_count',
      header: 'Errors',
      render: (row) => row.error_count > 0 ? <span className="text-[var(--color-down)]">{row.error_count}</span> : <span>{row.error_count}</span>,
    },
    {
      key: 'latency_p95',
      header: 'P95',
      render: (row) => {
        const threshold = row.slo_type === 'latency' ? row.target : 200;
        const met = row.latency_p95 <= threshold;
        return <span className={met ? '' : 'text-[var(--color-down)]'}>{formatDuration(row.latency_p95)}</span>;
      },
    },
    {
      key: 'availability_percent',
      header: 'Availability',
      render: (row) => formatPercent(row.availability_percent),
    },
    {
      key: 'slo_met',
      header: 'SLO Met?',
      render: (row) => (
        <span className={row.slo_met ? 'text-[var(--color-healthy)]' : 'text-[var(--color-down)]'}>
          {row.slo_met ? 'YES' : 'NO'}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <DataTable columns={columns} data={results} />

      {expandedService && slowApisMap[expandedService] && (
        <div className="rounded-lg border border-[var(--color-degraded)]/30 bg-[var(--color-bg-card)]">
          <div className="border-b border-[var(--color-border)] px-4 py-3">
            <h3 className="text-sm font-semibold">
              Slow APIs — {expandedService}
              <span className="ml-2 text-xs text-[var(--color-down)]">
                {slowApisMap[expandedService].filter((a) => !a.slo_met).length} not meeting SLO
              </span>
            </h3>
          </div>
          <div className="p-4">
            <DataTable
              columns={slowApiColumns}
              data={slowApisMap[expandedService].filter((a) => !a.slo_met)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
