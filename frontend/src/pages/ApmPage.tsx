import { useState } from 'react';
import { usePolling } from '../hooks/usePolling';
import { fetchTransactions, fetchApmErrors, fetchApmSummary } from '../api/apm';
import { DataTable, type Column } from '../components/common/DataTable';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import type { Transaction, ApmError, ApmSummary } from '../types';
import { formatDuration } from '../utils/formatters';

export function ApmPage() {
  const [tab, setTab] = useState<'transactions' | 'errors'>('transactions');

  const { data: summary, isLoading: summaryLoading } = usePolling<ApmSummary>(['apm-summary'], fetchApmSummary);
  const { data: transactions, isLoading: txLoading } = usePolling<Transaction[]>(['apm-transactions'], fetchTransactions);
  const { data: errors, isLoading: errLoading } = usePolling<ApmError[]>(['apm-errors'], fetchApmErrors);

  const txColumns: Column<Transaction>[] = [
    { key: 'name', header: 'Transaction' },
    { key: 'latency_p50', header: 'P50', render: (row) => formatDuration(row.latency_p50) },
    { key: 'latency_p95', header: 'P95', render: (row) => formatDuration(row.latency_p95) },
    { key: 'latency_p99', header: 'P99', render: (row) => formatDuration(row.latency_p99) },
    { key: 'throughput', header: 'Throughput', render: (row) => String(row.throughput) },
  ];

  const errColumns: Column<ApmError>[] = [
    { key: 'message', header: 'Message', render: (row) => <span className="line-clamp-2">{row.message}</span> },
    { key: 'type', header: 'Type' },
    { key: 'count', header: 'Count', render: (row) => <span className="text-[var(--color-down)]">{row.count}</span> },
    { key: 'last_seen', header: 'Last Seen' },
  ];

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Application Performance</h2>

      {/* Summary cards */}
      {summaryLoading ? <LoadingSkeleton rows={1} /> : summary && (
        <div className="grid grid-cols-4 gap-4">
          <SummaryCard label="P50 Latency" value={formatDuration(summary.latency_p50)} />
          <SummaryCard label="P95 Latency" value={formatDuration(summary.latency_p95)} />
          <SummaryCard label="Error Rate" value={`${summary.error_rate_percent}%`} />
          <SummaryCard label="Throughput" value={String(summary.throughput)} />
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-[var(--color-bg-secondary)] p-1">
        <button
          onClick={() => setTab('transactions')}
          className={`rounded px-4 py-1.5 text-sm ${tab === 'transactions' ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-secondary)]'}`}
        >
          Transactions
        </button>
        <button
          onClick={() => setTab('errors')}
          className={`rounded px-4 py-1.5 text-sm ${tab === 'errors' ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-secondary)]'}`}
        >
          Errors
        </button>
      </div>

      {tab === 'transactions' ? (
        txLoading ? <LoadingSkeleton /> : <DataTable columns={txColumns} data={transactions || []} />
      ) : (
        errLoading ? <LoadingSkeleton /> : <DataTable columns={errColumns} data={errors || []} />
      )}
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
      <div className="text-xs text-[var(--color-text-secondary)]">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}
