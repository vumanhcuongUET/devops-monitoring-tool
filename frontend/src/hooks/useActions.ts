/**
 * Custom hook for managing actions with TanStack Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import {
  fetchActions,
  fetchAction,
  approveAction,
  rejectAction,
  executeAction,
  getActionStats,
  type ApproveActionRequest,
  type RejectActionRequest,
  type ExecuteActionRequest,
  type Action,
  type ActionStatus,
} from '../api/actions';

// Type for action query filters
interface ActionFilters {
  project?: string;
  status?: ActionStatus;
  limit?: number;
  sortBy?: 'created_at' | 'updated_at' | 'risk_level';
  sortOrder?: 'asc' | 'desc';
}

// Query keys
export const actionKeys = {
  all: ['actions'] as const,
  lists: () => [...actionKeys.all, 'list'] as const,
  list: (filters?: ActionFilters) => [...actionKeys.lists(), filters] as const,
  details: () => [...actionKeys.all, 'detail'] as const,
  detail: (id: string) => [...actionKeys.details(), id] as const,
  stats: () => [...actionKeys.all, 'stats'] as const,
};

// Hooks
export function useActions(project?: string, status?: ActionStatus, limit = 100) {
  return useQuery({
    queryKey: actionKeys.list({ project, status, limit }),
    queryFn: () => fetchActions(project, status, limit),
    refetchInterval: 10000, // Poll every 10 seconds
  });
}

export function useAction(actionId: string) {
  return useQuery({
    queryKey: actionKeys.detail(actionId),
    queryFn: () => fetchAction(actionId),
    enabled: !!actionId,
  });
}

export function useActionStats() {
  return useQuery({
    queryKey: actionKeys.stats(),
    queryFn: getActionStats,
    refetchInterval: 15000, // Poll every 15 seconds
  });
}

// Mutations
export function useApproveAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ actionId, request }: { actionId: string; request: ApproveActionRequest }) =>
      approveAction(actionId, request),
    onSuccess: (data) => {
      toast.success(`Action ${data.id} approved`);
      queryClient.invalidateQueries({ queryKey: actionKeys.lists() });
      queryClient.invalidateQueries({ queryKey: actionKeys.detail(data.id) });
    },
    onError: (error: Error) => {
      toast.error(`Failed to approve action: ${error.message}`);
    },
  });
}

export function useRejectAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ actionId, request }: { actionId: string; request: RejectActionRequest }) =>
      rejectAction(actionId, request),
    onSuccess: (data) => {
      toast.success(`Action ${data.id} rejected`);
      queryClient.invalidateQueries({ queryKey: actionKeys.lists() });
      queryClient.invalidateQueries({ queryKey: actionKeys.detail(data.id) });
    },
    onError: (error: Error) => {
      toast.error(`Failed to reject action: ${error.message}`);
    },
  });
}

export function useExecuteAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ actionId, request }: { actionId: string; request: ExecuteActionRequest }) =>
      executeAction(actionId, request),
    onSuccess: (data) => {
      if (data.status === 'executed') {
        toast.success(`Action ${data.id} executed successfully`);
      } else if (data.status === 'failed') {
        toast.error(`Action ${data.id} execution failed`);
      }
      queryClient.invalidateQueries({ queryKey: actionKeys.lists() });
      queryClient.invalidateQueries({ queryKey: actionKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: actionKeys.stats() });
    },
    onError: (error: Error) => {
      toast.error(`Failed to execute action: ${error.message}`);
    },
  });
}

// Combined hook for action management
export function useActionManagement(actionId: string) {
  const { data: action, isLoading: isLoadingAction } = useAction(actionId);
  const approveMutation = useApproveAction();
  const rejectMutation = useRejectAction();
  const executeMutation = useExecuteAction();

  const handleApprove = (request: ApproveActionRequest) => {
    return approveMutation.mutateAsync({ actionId, request });
  };

  const handleReject = (request: RejectActionRequest) => {
    return rejectMutation.mutateAsync({ actionId, request });
  };

  const handleExecute = (request: ExecuteActionRequest) => {
    return executeMutation.mutateAsync({ actionId, request });
  };

  return {
    action,
    isLoadingAction,
    approveAction: handleApprove,
    rejectAction: handleReject,
    executeAction: handleExecute,
    isApproving: approveMutation.isPending,
    isRejecting: rejectMutation.isPending,
    isExecuting: executeMutation.isPending,
  };
}

// Re-export types for convenience
export type { Action } from '../api/actions';
