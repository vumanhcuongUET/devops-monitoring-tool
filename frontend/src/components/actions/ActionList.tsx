/**
 * ActionList component - List and filter actions
 */

import { useActions, useActionStats, type ActionStatus } from '../../hooks/useActions';
import { ActionCard } from './ActionCard';
import { useState } from 'react';
import { getTokenManager } from '../../auth/tokenManager';

interface ActionListProps {
  project?: string;
  /** Override the signed-in identity (tests, previews). Defaults to the session username. */
  currentUser?: string;
}

export function ActionList({ project, currentUser }: ActionListProps) {
  const user = currentUser ?? getTokenManager().getUsername() ?? 'unknown';
  const [statusFilter, setStatusFilter] = useState<ActionStatus | 'all'>('all');
  const { data: actions, isLoading, error } = useActions(
    project,
    statusFilter === 'all' ? undefined : statusFilter,
  );
  const { data: stats } = useActionStats();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--color-accent)]"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded p-4 text-center">
        <p className="text-red-500">Failed to load actions</p>
      </div>
    );
  }

  if (!actions || actions.total === 0) {
    return (
      <div className="bg-gray-500/10 border border-gray-500/30 rounded p-8 text-center">
        <p className="text-[var(--color-text-secondary)]">No actions found</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stats Summary */}
      {stats && (
        <div className="grid grid-cols-6 gap-2 mb-4">
          <div className="bg-gray-500/10 rounded p-2 text-center">
            <div className="text-2xl font-bold text-[var(--color-text)]">{stats.total}</div>
            <div className="text-xs text-[var(--color-text-secondary)]">Total</div>
          </div>
          <div className="bg-yellow-500/10 rounded p-2 text-center">
            <div className="text-2xl font-bold text-yellow-500">{stats.pending}</div>
            <div className="text-xs text-[var(--color-text-secondary)]">Pending</div>
          </div>
          <div className="bg-green-500/10 rounded p-2 text-center">
            <div className="text-2xl font-bold text-green-500">{stats.approved}</div>
            <div className="text-xs text-[var(--color-text-secondary)]">Approved</div>
          </div>
          <div className="bg-red-500/10 rounded p-2 text-center">
            <div className="text-2xl font-bold text-red-500">{stats.rejected}</div>
            <div className="text-xs text-[var(--color-text-secondary)]">Rejected</div>
          </div>
          <div className="bg-blue-500/10 rounded p-2 text-center">
            <div className="text-2xl font-bold text-blue-500">{stats.executed}</div>
            <div className="text-xs text-[var(--color-text-secondary)]">Executed</div>
          </div>
          <div className="bg-red-500/10 rounded p-2 text-center">
            <div className="text-2xl font-bold text-red-500">{stats.failed}</div>
            <div className="text-xs text-[var(--color-text-secondary)]">Failed</div>
          </div>
        </div>
      )}

      {/* Status Filter */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setStatusFilter('all')}
          className={`px-3 py-1 rounded text-sm ${
            statusFilter === 'all'
              ? 'bg-[var(--color-accent)] text-white'
              : 'bg-white/5 text-[var(--color-text-secondary)] hover:bg-white/10'
          }`}
        >
          All ({actions.total})
        </button>
        <button
          onClick={() => setStatusFilter('pending')}
          className={`px-3 py-1 rounded text-sm ${
            statusFilter === 'pending'
              ? 'bg-yellow-500 text-white'
              : 'bg-white/5 text-[var(--color-text-secondary)] hover:bg-white/10'
          }`}
        >
          Pending ({actions.pending})
        </button>
        <button
          onClick={() => setStatusFilter('approved')}
          className={`px-3 py-1 rounded text-sm ${
            statusFilter === 'approved'
              ? 'bg-green-500 text-white'
              : 'bg-white/5 text-[var(--color-text-secondary)] hover:bg-white/10'
          }`}
        >
          Approved ({actions.approved})
        </button>
        <button
          onClick={() => setStatusFilter('executed')}
          className={`px-3 py-1 rounded text-sm ${
            statusFilter === 'executed'
              ? 'bg-blue-500 text-white'
              : 'bg-white/5 text-[var(--color-text-secondary)] hover:bg-white/10'
          }`}
        >
          Executed ({actions.executed})
        </button>
        <button
          onClick={() => setStatusFilter('failed')}
          className={`px-3 py-1 rounded text-sm ${
            statusFilter === 'failed'
              ? 'bg-red-500 text-white'
              : 'bg-white/5 text-[var(--color-text-secondary)] hover:bg-white/10'
          }`}
        >
          Failed ({actions.failed})
        </button>
      </div>

      {/* Actions List */}
      <div className="space-y-2">
        {actions.actions.map((action) => (
          <ActionCard
            key={action.id}
            action={action}
            currentUser={user}
          />
        ))}
      </div>
    </div>
  );
}
