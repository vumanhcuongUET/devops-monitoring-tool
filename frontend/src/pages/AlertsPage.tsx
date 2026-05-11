import { useState } from 'react';
import { usePolling } from '../hooks/usePolling';
import { fetchAlertRules, fetchAlertHistory, deleteAlertRule, updateAlertRule } from '../api/alerts';
import { DataTable, type Column } from '../components/common/DataTable';
import { AlertRuleForm } from '../components/alerts/AlertRuleForm';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import type { AlertRule, AlertEvent } from '../types';
import toast from 'react-hot-toast';

export function AlertsPage() {
  const [showForm, setShowForm] = useState(false);
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null);

  const { data: rules, isLoading: rulesLoading, refetch: refetchRules } = usePolling<AlertRule[]>(
    ['alert-rules'],
    fetchAlertRules,
  );
  const { data: history } = usePolling<AlertEvent[]>(['alert-history'], fetchAlertHistory);

  const handleDelete = async (id: string) => {
    await deleteAlertRule(id);
    toast.success('Rule deleted');
    refetchRules();
  };

  const handleToggle = async (rule: AlertRule) => {
    await updateAlertRule(rule.id, { ...rule, enabled: !rule.enabled });
    refetchRules();
  };

  const columns: Column<AlertRule>[] = [
    { key: 'name', header: 'Name' },
    { key: 'source', header: 'Source' },
    { key: 'metric', header: 'Metric' },
    { key: 'condition', header: 'Condition', render: (row) => `${row.condition} ${row.threshold}` },
    { key: 'severity', header: 'Severity', render: (row) => {
      const color = row.severity === 'critical' ? 'text-[var(--color-down)]' : row.severity === 'warning' ? 'text-[var(--color-degraded)]' : 'text-blue-400';
      return <span className={`font-medium ${color}`}>{row.severity}</span>;
    }},
    { key: 'enabled', header: 'Enabled', render: (row) => (
      <button onClick={() => handleToggle(row)} className={`rounded px-2 py-0.5 text-xs ${row.enabled ? 'bg-[var(--color-healthy)]/20 text-[var(--color-healthy)]' : 'bg-white/10 text-[var(--color-text-secondary)]'}`}>
        {row.enabled ? 'ON' : 'OFF'}
      </button>
    )},
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <div className="flex gap-2">
          <button onClick={() => { setEditingRule(row); setShowForm(true); }} className="text-xs text-[var(--color-accent)] hover:underline">Edit</button>
          <button onClick={() => handleDelete(row.id)} className="text-xs text-[var(--color-down)] hover:underline">Delete</button>
        </div>
      ),
    },
  ];

  const historyColumns: Column<AlertEvent>[] = [
    { key: 'timestamp', header: 'Time' },
    { key: 'rule_name', header: 'Rule' },
    { key: 'severity', header: 'Severity', render: (row) => {
      const color = row.severity === 'critical' ? 'text-[var(--color-down)]' : row.severity === 'warning' ? 'text-[var(--color-degraded)]' : 'text-blue-400';
      return <span className={color}>{row.severity}</span>;
    }},
    { key: 'status', header: 'Status', render: (row) => (
      <span className={row.status === 'firing' ? 'text-[var(--color-down)]' : 'text-[var(--color-healthy)]'}>
        {row.status.toUpperCase()}
      </span>
    )},
    { key: 'message', header: 'Message', render: (row) => <span className="line-clamp-2">{row.message}</span> },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Alert Rules</h2>
        <button
          onClick={() => { setEditingRule(null); setShowForm(true); }}
          className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm text-white hover:opacity-90"
        >
          Add Rule
        </button>
      </div>

      {showForm && (
        <AlertRuleForm
          rule={editingRule}
          onClose={() => { setShowForm(false); setEditingRule(null); }}
          onSaved={() => { setShowForm(false); setEditingRule(null); refetchRules(); }}
        />
      )}

      {rulesLoading ? <LoadingSkeleton /> : <DataTable columns={columns} data={rules || []} />}

      <h3 className="text-lg font-semibold">Alert History</h3>
      <DataTable columns={historyColumns} data={history || []} />
    </div>
  );
}
