/**
 * API client for action and approval endpoints (Phase 2)
 */

import { api } from './client';

// Types
export interface CommandParams {
  command_type: 'kubectl' | 'helm' | 'argocd' | 'script' | 'api';
  resource_type?: string;
  resource_name?: string;
  namespace?: string;
  action?: string;
  flags: Record<string, string>;
  args: string[];
}

export interface ExecutionResult {
  success: boolean;
  exit_code?: number;
  stdout?: string;
  stderr?: string;
  duration_seconds?: number;
  error_message?: string;
  timestamp: string;
}

export interface Action {
  id: string;
  triage_card_id?: string;
  recommendation_id?: string;
  command_type: string;
  command: string;
  parsed_params: CommandParams;
  project: string;
  title: string;
  description: string;
  risk_level: 'critical' | 'high' | 'medium' | 'low' | 'safe';
  estimated_impact: string;
  status: 'pending' | 'approved' | 'rejected' | 'executed' | 'failed' | 'cancelled';
  approved_by?: string;
  approved_at?: string;
  rejected_by?: string;
  rejected_at?: string;
  rejection_reason?: string;
  executed_by?: string;
  executed_at?: string;
  execution_result?: ExecutionResult;
  created_at: string;
  updated_at: string;
  context: Record<string, unknown>;
}

export type ActionStatus = Action['status'];

export interface CreateActionRequest {
  triage_card_id: string;
  recommendation_id: string;
  project: string;
}

export interface ApproveActionRequest {
  approved_by: string;
  comment?: string;
}

export interface RejectActionRequest {
  rejected_by: string;
  reason: string;
}

export interface ExecuteActionRequest {
  executed_by: string;
  dry_run?: boolean;
}

export interface ActionListResponse {
  total: number;
  pending: number;
  approved: number;
  rejected: number;
  executed: number;
  failed: number;
  actions: Action[];
}

/** Backend response envelope for single-action operations (get/approve/reject/execute). */
interface ActionResponse {
  success: boolean;
  action: Action | null;
  error: string | null;
}

// API Functions
export async function fetchActions(
  project?: string,
  status?: string,
  limit = 100,
): Promise<ActionListResponse> {
  const params = new URLSearchParams();
  if (project) params.append('project', project);
  if (status) params.append('status', status);
  params.append('limit', limit.toString());

  const { data } = await api.get<ActionListResponse>('/api/v1/actions', { params });
  return data;
}

/**
 * Backend wraps every single-action response in {success, action, error}
 * and returns HTTP 200 even when the engine rejected the operation — unwrap
 * here and turn failure into a rejection so react-query error paths fire
 * (Phase 16 P1-6: callers used to receive the wrapper itself, so dry-run
 * results read `undefined`, success/failure toasts were dead code, and
 * engine failures vanished).
 */
async function unwrapAction(promise: Promise<{ data: ActionResponse }>): Promise<Action> {
  const { data } = await promise;
  if (!data.success || !data.action) {
    throw new Error(data.error || 'Action operation failed');
  }
  return data.action;
}

export async function fetchAction(actionId: string): Promise<Action> {
  return unwrapAction(api.get(`/api/v1/actions/${actionId}`));
}

export async function approveAction(
  actionId: string,
  request: ApproveActionRequest,
): Promise<Action> {
  return unwrapAction(api.post(`/api/v1/actions/${actionId}/approve`, request));
}

export async function rejectAction(
  actionId: string,
  request: RejectActionRequest,
): Promise<Action> {
  return unwrapAction(api.post(`/api/v1/actions/${actionId}/reject`, request));
}

export async function executeAction(
  actionId: string,
  request: ExecuteActionRequest,
): Promise<Action> {
  return unwrapAction(api.post(`/api/v1/actions/${actionId}/execute`, request));
}

export async function getActionStats(): Promise<{
  total: number;
  pending: number;
  approved: number;
  rejected: number;
  executed: number;
  failed: number;
}> {
  const { data } = await api.get('/api/v1/actions/stats/summary');
  return data;
}
