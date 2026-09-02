/**
 * ActionCard component - Display action with Approve/Reject buttons
 * Similar to AlertRuleForm pattern (inline card-based form)
 */

import { Clock, User, AlertTriangle, CheckCircle, XCircle, Rocket, Shield } from 'lucide-react';
import { useActionManagement, type Action } from '../../hooks/useActions';
import { useState } from 'react';
import toast from 'react-hot-toast';
import { getTokenManager } from '../../auth/tokenManager';
import type { ExecutionResult } from '../../api/actions';

interface ActionCardProps {
  action: Action;
  /** Override the signed-in identity (tests, previews). Defaults to the session username. */
  currentUser?: string;
  onRefresh?: () => void;
}

export function ActionCard({ action, currentUser, onRefresh }: ActionCardProps) {
  const user = currentUser ?? getTokenManager().getUsername() ?? 'unknown';
  const {
    approveAction,
    rejectAction,
    executeAction,
    isApproving,
    isRejecting,
    isExecuting,
  } = useActionManagement(action.id);

  const [comment, setComment] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [showExecConfirm, setShowExecConfirm] = useState(false);
  const [dryRun, setDryRun] = useState<{
    state: 'idle' | 'running' | 'done' | 'failed';
    result?: ExecutionResult;
  }>({ state: 'idle' });

  // High/critical commands must prove themselves in a dry run before the real one.
  const highRisk = action.risk_level === 'critical' || action.risk_level === 'high';

  const handleApprove = async () => {
    try {
      await approveAction({
        approved_by: user,
        comment: comment || undefined,
      });
      setComment('');
      if (onRefresh) onRefresh();
    } catch {
      // Failure already toasted by the mutation's onError (with server detail)
    }
  };

  const handleReject = async () => {
    if (!rejectReason.trim()) {
      toast.error('Please provide a reason for rejection');
      return;
    }
    try {
      await rejectAction({
        rejected_by: user,
        reason: rejectReason,
      });
      setRejectReason('');
      setShowRejectForm(false);
      if (onRefresh) onRefresh();
    } catch {
      // Failure already toasted by the mutation's onError (with server detail)
    }
  };

  const openExecConfirm = () => {
    setDryRun({ state: 'idle' });
    setShowExecConfirm(true);
  };

  const handleDryRun = async () => {
    setDryRun({ state: 'running' });
    try {
      const result = await executeAction({ executed_by: user, dry_run: true });
      setDryRun({ state: 'done', result: result.execution_result ?? undefined });
    } catch {
      setDryRun({ state: 'failed' });
    }
  };

  const handleExecute = async () => {
    try {
      await executeAction({
        executed_by: user,
        dry_run: false,
      });
      setShowExecConfirm(false);
      if (onRefresh) onRefresh();
    } catch {
      // Failure already toasted by the mutation's onError (with server detail)
    }
  };

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'critical': return 'text-red-500 bg-red-500/10';
      case 'high': return 'text-orange-500 bg-orange-500/10';
      case 'medium': return 'text-yellow-500 bg-yellow-500/10';
      case 'low': return 'text-green-500 bg-green-500/10';
      case 'safe': return 'text-emerald-500 bg-emerald-500/10';
      default: return 'text-gray-500 bg-gray-500/10';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending': return <Clock className="w-4 h-4 text-yellow-500" />;
      case 'approved': return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'rejected': return <XCircle className="w-4 h-4 text-red-500" />;
      case 'executed': return <Rocket className="w-4 h-4 text-blue-500" />;
      case 'failed': return <AlertTriangle className="w-4 h-4 text-red-500" />;
      default: return <Shield className="w-4 h-4 text-gray-500" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending': return 'bg-yellow-500/20 text-yellow-500 border-yellow-500/30';
      case 'approved': return 'bg-green-500/20 text-green-500 border-green-500/30';
      case 'rejected': return 'bg-red-500/20 text-red-500 border-red-500/30';
      case 'executed': return 'bg-blue-500/20 text-blue-500 border-blue-500/30';
      case 'failed': return 'bg-red-500/20 text-red-500 border-red-500/30';
      default: return 'bg-gray-500/20 text-gray-500 border-gray-500/30';
    }
  };

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4 mb-4">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            {getStatusIcon(action.status)}
            <h3 className="font-semibold text-[var(--color-text)]">{action.title}</h3>
            <span className={`text-xs px-2 py-0.5 rounded ${getRiskColor(action.risk_level)}`}>
              {action.risk_level.toUpperCase()}
            </span>
          </div>
          <p className="text-sm text-[var(--color-text-secondary)]">{action.description}</p>
        </div>
        <div className={`text-xs px-2 py-1 rounded border ${getStatusColor(action.status)}`}>
          {action.status.toUpperCase()}
        </div>
      </div>

      {/* Command */}
      <div className="rounded bg-[var(--color-bg-primary)] border border-[var(--color-border)] p-2 mb-3">
        <code className="font-mono text-xs text-[var(--color-text-primary)] break-all">
          {action.command}
        </code>
      </div>

      {/* Estimated Impact */}
      {action.estimated_impact && (
        <div className="text-sm text-[var(--color-text-secondary)] mb-3">
          <strong>Impact:</strong> {action.estimated_impact}
        </div>
      )}

      {/* Metadata */}
      <div className="flex items-center gap-4 text-xs text-[var(--color-text-secondary)] mb-3">
        <div className="flex items-center gap-1">
          <User className="w-3 h-3" />
          <span>{action.project}</span>
        </div>
        <div className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          <span>{new Date(action.created_at).toLocaleString()}</span>
        </div>
        {action.approved_by && (
          <div className="flex items-center gap-1 text-green-500">
            <CheckCircle className="w-3 h-3" />
            <span>By {action.approved_by}</span>
          </div>
        )}
        {action.rejected_by && (
          <div className="flex items-center gap-1 text-red-500">
            <XCircle className="w-3 h-3" />
            <span>By {action.rejected_by}</span>
          </div>
        )}
      </div>

      {/* Action Buttons */}
      {action.status === 'pending' && (
        <div className="flex flex-col gap-2">
          {/* Comment input */}
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Add optional approval comment..."
            className="w-full text-sm p-2 rounded border border-[var(--color-border)] bg-white/5 focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
            rows={2}
          />

          {/* Action buttons */}
          <div className="flex gap-2">
            <button
              onClick={handleApprove}
              disabled={isApproving}
              className="flex-1 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <CheckCircle className="w-4 h-4" />
              {isApproving ? 'Approving...' : 'Approve'}
            </button>
            <button
              onClick={() => setShowRejectForm(!showRejectForm)}
              className="flex-1 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <XCircle className="w-4 h-4" />
              Reject
            </button>
          </div>
        </div>
      )}

      {/* Reject Form */}
      {showRejectForm && (
        <div className="mt-3 p-3 bg-red-500/10 rounded border border-red-500/30">
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Please provide a reason for rejection..."
            className="w-full text-sm p-2 rounded border border-red-500/30 bg-white/5 focus:outline-none focus:ring-1 focus:ring-red-500"
            rows={2}
          />
          <div className="flex gap-2 mt-2">
            <button
              onClick={handleReject}
              disabled={isRejecting || !rejectReason.trim()}
              className="flex-1 bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
            >
              {isRejecting ? 'Rejecting...' : 'Confirm Reject'}
            </button>
            <button
              onClick={() => {
                setShowRejectForm(false);
                setRejectReason('');
              }}
              className="flex-1 bg-gray-600 hover:bg-gray-700 text-white px-3 py-1.5 rounded text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Execution Result */}
      {action.execution_result && (
        <div className={`mt-3 p-3 rounded ${
          action.execution_result.success
            ? 'bg-green-500/10 border border-green-500/30'
            : 'bg-red-500/10 border border-red-500/30'
        }`}>
          <div className="flex items-center gap-2 mb-2">
            {action.execution_result.success ? (
              <CheckCircle className="w-4 h-4 text-green-500" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-red-500" />
            )}
            <span className="text-sm font-semibold">
              {action.execution_result.success ? 'Execution Successful' : 'Execution Failed'}
            </span>
            {action.execution_result.duration_seconds && (
              <span className="text-xs text-[var(--color-text-secondary)]">
                ({action.execution_result.duration_seconds.toFixed(2)}s)
              </span>
            )}
          </div>
          {action.execution_result.stdout && (
            <div className="text-xs bg-black/10 rounded p-2 mb-1">
              <pre className="whitespace-pre-wrap text-[var(--color-text-secondary)]">
                {action.execution_result.stdout.slice(0, 500)}
                {action.execution_result.stdout.length > 500 ? '...' : ''}
              </pre>
            </div>
          )}
          {action.execution_result.stderr && (
            <div className="text-xs bg-red-500/10 rounded p-2">
              <pre className="whitespace-pre-wrap text-red-400">
                {action.execution_result.stderr.slice(0, 500)}
                {action.execution_result.stderr.length > 500 ? '...' : ''}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Execute Confirmation for Approved Actions */}
      {action.status === 'approved' && !showExecConfirm && (
        <button
          onClick={openExecConfirm}
          className="mt-3 w-full bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded flex items-center justify-center gap-2"
        >
          <Rocket className="w-4 h-4" />
          Execute Action
        </button>
      )}

      {action.status === 'approved' && showExecConfirm && (
        <div
          role="dialog"
          aria-label={`Confirm execution of ${action.title}`}
          className="mt-3 rounded border border-blue-500/30 bg-blue-500/5 p-3"
        >
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-orange-500" />
            <span className="text-sm font-semibold">
              {highRisk ? `${action.risk_level.toUpperCase()} RISK — dry run required` : 'Confirm execution'}
            </span>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-[var(--color-text-secondary)] mb-3">
            <dt>Project</dt>
            <dd className="font-medium text-[var(--color-text-primary)]">{action.project}</dd>
            <dt>Executed by</dt>
            <dd className="font-medium text-[var(--color-text-primary)]">{user}</dd>
            {action.estimated_impact && (
              <>
                <dt>Impact</dt>
                <dd className="font-medium text-[var(--color-text-primary)]">{action.estimated_impact}</dd>
              </>
            )}
          </dl>
          <div className="rounded bg-[var(--color-bg-primary)] border border-[var(--color-border)] p-2 mb-3">
            <code className="font-mono text-xs text-[var(--color-text-primary)] break-all">
              {action.command}
            </code>
          </div>

          {highRisk && (
            <div className="mb-3">
              {dryRun.state === 'idle' && (
                <button
                  onClick={handleDryRun}
                  className="w-full rounded border border-[var(--color-border)] bg-white/5 hover:bg-white/10 text-[var(--color-text-primary)] px-3 py-2 text-sm"
                >
                  Run dry run first
                </button>
              )}
              {dryRun.state === 'running' && (
                <p role="status" className="text-xs text-[var(--color-text-secondary)] px-1 py-2">
                  Running dry run…
                </p>
              )}
              {dryRun.state === 'done' && (
                <div role="status" className={`rounded border p-2 text-xs ${
                  dryRun.result?.success
                    ? 'border-[var(--color-healthy)]/30 bg-[var(--color-healthy)]/10 text-[var(--color-text-primary)]'
                    : 'border-[var(--color-down)]/30 bg-[var(--color-down)]/10 text-[var(--color-text-primary)]'
                }`}>
                  <p className="font-semibold mb-1">
                    {dryRun.result?.success ? 'Dry run passed' : 'Dry run failed'}
                    {dryRun.result?.exit_code != null && ` (exit ${dryRun.result.exit_code})`}
                  </p>
                  {(dryRun.result?.stderr || dryRun.result?.stdout) && (
                    <pre className="font-mono whitespace-pre-wrap max-h-32 overflow-y-auto text-[var(--color-text-secondary)]">
                      {(dryRun.result?.stderr || dryRun.result?.stdout || '').slice(0, 500)}
                    </pre>
                  )}
                </div>
              )}
              {dryRun.state === 'failed' && (
                <p role="status" className="text-xs text-[var(--color-down)] px-1 py-2">
                  Dry run could not run — fix the error and try again.
                </p>
              )}
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={handleExecute}
              disabled={isExecuting || (highRisk && dryRun.state !== 'done')}
              className="flex-1 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded text-sm flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <Rocket className="w-4 h-4" />
              {isExecuting ? 'Executing…' : 'Execute for real'}
            </button>
            <button
              onClick={() => setShowExecConfirm(false)}
              className="flex-1 bg-[var(--color-bg-secondary)] border border-[var(--color-border)] hover:bg-white/5 text-[var(--color-text-primary)] px-3 py-2 rounded text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
