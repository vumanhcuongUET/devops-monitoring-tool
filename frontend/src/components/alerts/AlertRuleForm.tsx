import { useState } from 'react';
import { createAlertRule, updateAlertRule } from '../../api/alerts';
import type { AlertRule } from '../../types';
import toast from 'react-hot-toast';

const sources = ['elasticsearch', 'apm', 'prometheus', 'kubernetes'];
const conditions = ['gt', 'gte', 'lt', 'lte', 'eq'];
const severities = ['info', 'warning', 'critical'];

interface Props {
  rule: AlertRule | null;
  onClose: () => void;
  onSaved: () => void;
}

export function AlertRuleForm({ rule, onClose, onSaved }: Props) {
  const [form, setForm] = useState<Partial<AlertRule>>(
    rule || {
      name: '',
      source: 'prometheus',
      metric: '',
      condition: 'gt',
      threshold: 0,
      duration_seconds: 60,
      severity: 'warning',
      enabled: true,
      notify_slack: true,
      notify_email: false,
      notify_webhook: false,
      labels: {},
    },
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (rule?.id) {
        await updateAlertRule(rule.id, form as AlertRule);
        toast.success('Rule updated');
      } else {
        await createAlertRule(form as Omit<AlertRule, 'id'>);
        toast.success('Rule created');
      }
      onSaved();
    } catch {
      toast.error('Failed to save rule');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-xs text-[var(--color-text-secondary)]">Name</label>
          <input
            value={form.name || ''}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-2 text-sm"
            required
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-[var(--color-text-secondary)]">Source</label>
          <select
            value={form.source}
            onChange={(e) => setForm((f) => ({ ...f, source: e.target.value }))}
            className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-2 text-sm"
          >
            {sources.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-[var(--color-text-secondary)]">Metric</label>
          <input
            value={form.metric || ''}
            onChange={(e) => setForm((f) => ({ ...f, metric: e.target.value }))}
            placeholder="e.g. cpu_percent"
            className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-2 text-sm"
            required
          />
        </div>
        <div className="flex gap-2">
          <div className="flex-1">
            <label className="mb-1 block text-xs text-[var(--color-text-secondary)]">Condition</label>
            <select
              value={form.condition}
              onChange={(e) => setForm((f) => ({ ...f, condition: e.target.value }))}
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-2 text-sm"
            >
              {conditions.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs text-[var(--color-text-secondary)]">Threshold</label>
            <input
              type="number"
              value={form.threshold || 0}
              onChange={(e) => setForm((f) => ({ ...f, threshold: Number(e.target.value) }))}
              className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-2 text-sm"
              required
            />
          </div>
        </div>
        <div>
          <label className="mb-1 block text-xs text-[var(--color-text-secondary)]">Duration (seconds)</label>
          <input
            type="number"
            value={form.duration_seconds || 60}
            onChange={(e) => setForm((f) => ({ ...f, duration_seconds: Number(e.target.value) }))}
            className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-[var(--color-text-secondary)]">Severity</label>
          <select
            value={form.severity}
            onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value as AlertRule['severity'] }))}
            className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-3 py-2 text-sm"
          >
            {severities.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>
      <div className="mt-4 flex gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.notify_slack} onChange={(e) => setForm((f) => ({ ...f, notify_slack: e.target.checked }))} />
          Slack
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.notify_email} onChange={(e) => setForm((f) => ({ ...f, notify_email: e.target.checked }))} />
          Email
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.notify_webhook} onChange={(e) => setForm((f) => ({ ...f, notify_webhook: e.target.checked }))} />
          Webhook
        </label>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" onClick={onClose} className="rounded px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-white/5">
          Cancel
        </button>
        <button type="submit" className="rounded bg-[var(--color-accent)] px-4 py-2 text-sm text-white hover:opacity-90">
          {rule ? 'Update' : 'Create'}
        </button>
      </div>
    </form>
  );
}
