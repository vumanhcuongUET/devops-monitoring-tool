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

export async function fetchAction(actionId: string): Promise<Action> {
  const { data } = await api.get<Action>(`/api/v1/actions/${actionId}`);
  return data;
}

export async function approveAction(
  actionId: string,
  request: ApproveActionRequest,
): Promise<Action> {
  const { data } = await api.post<Action>(
    `/api/v1/actions/${actionId}/approve`,
    request,
  );
  return data;
}

export async function rejectAction(
  actionId: string,
  request: RejectActionRequest,
): Promise<Action> {
  const { data } = await api.post<Action>(
    `/api/v1/actions/${actionId}/reject`,
    request,
  );
  return data;
}

export async function executeAction(
  actionId: string,
  request: ExecuteActionRequest,
): Promise<Action> {
  const { data } = await api.post<Action>(
    `/api/v1/actions/${actionId}/execute`,
    request,
  );
  return data;
}

export async function createBulkActions(
  triageCardId: string,
  project: string,
): Promise<{ actions: Action[]; total_created: number; errors: string[] }> {
  const params = new URLSearchParams({ triage_card_id: triageCardId, project });
  const { data } = await api.post<{
    actions: Action[];
    total_created: number;
    errors: string[];
  }>('/api/v1/actions/bulk', null, { params });
  return data;
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
