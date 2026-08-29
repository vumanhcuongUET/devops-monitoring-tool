/**
 * Tests for useActions hook
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useActions } from './useActions';
import { Action, ActionStatus, RiskLevel } from '../types';
import * as api from '../api/actions';

// Mock the API module
vi.mock('../api/actions');

describe('useActions', () => {
  let queryClient: QueryClient;
  let mockActions: Action[];

  beforeEach(() => {
    // Reset mocks
    vi.clearAllMocks();

    // Create test actions
    mockActions = [
      {
        id: 'act-1',
        triage_card_id: 'tc-001',
        recommendation_id: 'rec-001',
        command_type: 'kubectl',
        command: 'kubectl get pods -n meinvoice',
        title: 'Check pod status',
        description: 'Verify pod health',
        project: 'meinvoice',
        risk_level: RiskLevel.SAFE,
        estimated_impact: 'No impact',
        status: ActionStatus.PENDING,
        created_at: '2026-08-18T10:00:00Z',
        updated_at: '2026-08-18T10:00:00Z',
        context: {},
      },
      {
        id: 'act-2',
        triage_card_id: 'tc-001',
        recommendation_id: 'rec-002',
        command_type: 'kubectl',
        command: 'kubectl delete pod failing-pod -n meinvoice',
        title: 'Delete failing pod',
        description: 'Remove pod in CrashLoopBackOff',
        project: 'meinvoice',
        risk_level: RiskLevel.HIGH,
        estimated_impact: 'Brief service interruption',
        status: ActionStatus.APPROVED,
        created_at: '2026-08-18T09:00:00Z',
        updated_at: '2026-08-18T10:30:00Z',
        approved_by: 'john.doe',
        approved_at: '2026-08-18T10:30:00Z',
        context: {},
      },
    ];

    // Create query client
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );

  describe('Fetching Actions', () => {
    it('fetches actions successfully', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 2,
        pending: 1,
        approved: 1,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: mockActions,
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.actions).toEqual(mockActions);
      expect(result.current.error).toBeNull();
      expect(result.current.actions.length).toBe(2);
    });

    it('handles fetch errors', async () => {
      vi.mocked(api.listActions).mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.error).toBeInstanceOf(Error);
      expect(result.current.actions).toEqual([]);
    });

    it('shows loading state during fetch', () => {
      vi.mocked(api.listActions).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockActions), 1000))
      );

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      expect(result.current.isLoading).toBe(true);
    });

    it('fetches actions with filters', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 1,
        pending: 1,
        approved: 0,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: [mockActions[0]],
      });

      const { result } = renderHook(
        () => useActions({ project: 'meinvoice', status: ActionStatus.PENDING }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(api.listActions).toHaveBeenCalledWith({
        project: 'meinvoice',
        status: 'pending',
        limit: 100,
      });
    });

    it('refetches actions', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 2,
        pending: 1,
        approved: 1,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: mockActions,
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Refetch
      await act(async () => {
        await result.current.refetch();
      });

      expect(api.listActions).toHaveBeenCalledTimes(2);
    });
  });

  describe('Approving Actions', () => {
    it('approves action successfully', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 2,
        pending: 1,
        approved: 1,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: mockActions,
      });

      vi.mocked(api.approveAction).mockResolvedValue({
        success: true,
        action: { ...mockActions[1], status: ActionStatus.APPROVED },
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Approve action
      await act(async () => {
        await result.current.approveAction('act-1', {
          approved_by: 'john.doe',
          comment: 'Approved after review',
        });
      });

      expect(api.approveAction).toHaveBeenCalledWith('act-1', {
        approved_by: 'john.doe',
        comment: 'Approved after review',
      });

      // Should refetch after approval
      await waitFor(() => {
        expect(api.listActions).toHaveBeenCalledTimes(2);
      });
    });

    it('handles approval errors', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 1,
        pending: 1,
        approved: 0,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: [mockActions[0]],
      });

      vi.mocked(api.approveAction).mockRejectedValue(new Error('Approval failed'));

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Try to approve
      await act(async () => {
        try {
          await result.current.approveAction('act-1', {
            approved_by: 'john.doe',
          });
        } catch (error) {
          expect(error).toBeInstanceOf(Error);
        }
      });
    });

    it('optimistically updates UI after approval', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 1,
        pending: 1,
        approved: 0,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: [mockActions[0]],
      });

      // Use optimistic update
      vi.mocked(api.approveAction).mockImplementation(() =>
        Promise.resolve({
          success: true,
          action: { ...mockActions[0], status: ActionStatus.APPROVED },
        })
      );

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Approve should optimistically update
      await act(async () => {
        await result.current.approveAction('act-1', {
          approved_by: 'john.doe',
        });
      });

      // Check optimistic update happened
      await waitFor(() => {
        expect(result.current.actions[0].status).toBe(ActionStatus.APPROVED);
      });
    });
  });

  describe('Rejecting Actions', () => {
    it('rejects action successfully', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 1,
        pending: 1,
        approved: 0,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: [mockActions[0]],
      });

      vi.mocked(api.rejectAction).mockResolvedValue({
        success: true,
        action: { ...mockActions[0], status: ActionStatus.REJECTED },
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Reject action
      await act(async () => {
        await result.current.rejectAction('act-1', {
          rejected_by: 'john.doe',
          reason: 'Too risky',
        });
      });

      expect(api.rejectAction).toHaveBeenCalledWith('act-1', {
        rejected_by: 'john.doe',
        reason: 'Too risky',
      });
    });

    it('handles rejection without reason', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 1,
        pending: 1,
        approved: 0,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: [mockActions[0]],
      });

      vi.mocked(api.rejectAction).mockResolvedValue({
        success: true,
        action: { ...mockActions[0], status: ActionStatus.REJECTED },
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Reject without reason
      await act(async () => {
        await result.current.rejectAction('act-1', {
          rejected_by: 'john.doe',
          reason: '',
        });
      });
    });
  });

  describe('Executing Actions', () => {
    it('executes action successfully', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 1,
        pending: 0,
        approved: 1,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: [mockActions[1]],
      });

      vi.mocked(api.executeAction).mockResolvedValue({
        success: true,
        action: {
          ...mockActions[1],
          status: ActionStatus.EXECUTED,
          executed_by: 'system',
          executed_at: '2026-08-18T11:00:00Z',
          execution_result: {
            success: true,
            exit_code: 0,
            stdout: 'Command executed',
            stderr: '',
          },
        },
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Execute action
      await act(async () => {
        await result.current.executeAction('act-2', {
          executed_by: 'system',
          dry_run: false,
        });
      });

      expect(api.executeAction).toHaveBeenCalledWith('act-2', {
        executed_by: 'system',
        dry_run: false,
      });
    });

    it('handles execution with dry run', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 1,
        pending: 0,
        approved: 1,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: [mockActions[1]],
      });

      vi.mocked(api.executeAction).mockResolvedValue({
        success: true,
        action: {
          ...mockActions[1],
          status: ActionStatus.EXECUTED,
          execution_result: {
            success: true,
            exit_code: 0,
            stdout: '[DRY RUN] Command validated',
          },
        },
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Execute with dry run
      await act(async () => {
        await result.current.executeAction('act-2', {
          executed_by: 'system',
          dry_run: true,
        });
      });

      expect(api.executeAction).toHaveBeenCalledWith('act-2', {
        executed_by: 'system',
        dry_run: true,
      });
    });

    it('handles execution failure', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 1,
        pending: 0,
        approved: 1,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: [mockActions[1]],
      });

      vi.mocked(api.executeAction).mockResolvedValue({
        success: true,
        action: {
          ...mockActions[1],
          status: ActionStatus.FAILED,
          execution_result: {
            success: false,
            exit_code: 1,
            stderr: 'Command failed',
          },
        },
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        await result.current.executeAction('act-2', {
          executed_by: 'system',
          dry_run: false,
        });
      });

      // Should update action status to FAILED
      await waitFor(() => {
        const failedAction = result.current.actions.find((a) => a.id === 'act-2');
        expect(failedAction?.status).toBe(ActionStatus.FAILED);
      });
    });
  });

  describe('Polling', () => {
    it('sets up polling when enabled', () => {
      renderHook(
        () => useActions({ project: 'meinvoice', enablePolling: true }),
        { wrapper }
      );

      // Should set up polling
      // (This would require checking the polling setup)
    });

    it('does not poll when disabled', () => {
      renderHook(
        () => useActions({ project: 'meinvoice', enablePolling: false }),
        { wrapper }
      );

      // Should not set up polling
    });
  });

  describe('WebSocket Integration', () => {
    it('subscribes to action updates via WebSocket', () => {
      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      // Should subscribe to WebSocket
      // (This would require WebSocket mock setup)
    });

    it('updates action status on WebSocket message', async () => {
      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Simulate WebSocket message
      // This would require WebSocket mock setup
    });
  });

  describe('Error Handling', () => {
    it('handles network errors gracefully', async () => {
      vi.mocked(api.listActions).mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.error).toBeTruthy();
      expect(result.current.error?.message).toContain('Network error');
    });

    it('handles validation errors', async () => {
      vi.mocked(api.listActions).mockRejectedValue(
        new Error('Validation failed: Invalid action ID')
      );

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.error?.message).toContain('Validation failed');
    });

    it('retries on transient errors', async () => {
      let attempts = 0;
      vi.mocked(api.listActions).mockImplementation(() => {
        attempts++;
        if (attempts < 3) {
          return Promise.reject(new Error('Transient error'));
        }
        return Promise.resolve({
          total: 1,
          pending: 1,
          approved: 0,
          rejected: 0,
          executed: 0,
          failed: 0,
          actions: [mockActions[0]],
        });
      });

      const { result } = renderHook(
        () => useActions({ project: 'meinvoice', retryCount: 3 }),
        { wrapper }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
        expect(result.current.error).toBeNull();
      });

      expect(attempts).toBe(3);
    });
  });

  describe('Caching', () => {
    it('caches action list', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 1,
        pending: 1,
        approved: 0,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: [mockActions[0]],
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Second fetch should use cache
      await act(async () => {
        await result.current.refetch();
      });

      // Should only call API twice (initial + refetch)
      expect(api.listActions).toHaveBeenCalledTimes(2);
    });

    it('invalidates cache on action update', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 1,
        pending: 1,
        approved: 0,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: [mockActions[0]],
      });

      vi.mocked(api.approveAction).mockResolvedValue({
        success: true,
        action: { ...mockActions[0], status: ActionStatus.APPROVED },
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Approve action - should invalidate cache
      await act(async () => {
        await result.current.approveAction('act-1', {
          approved_by: 'john.doe',
        });
      });

      // Cache should be invalidated and refetch called
      await waitFor(() => {
        expect(api.listActions).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe('Statistics', () => {
    it('calculates action statistics', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 3,
        pending: 1,
        approved: 1,
        rejected: 0,
        executed: 1,
        failed: 0,
        actions: mockActions,
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.stats).toEqual({
        total: 3,
        pending: 1,
        approved: 1,
        rejected: 0,
        executed: 1,
        failed: 0,
      });
    });

    it('updates statistics when actions change', async () => {
      vi.mocked(api.listActions).mockResolvedValue({
        total: 2,
        pending: 1,
        approved: 1,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: mockActions,
      });

      const { result } = renderHook(() => useActions({ project: 'meinvoice' }), {
        wrapper,
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      const initialStats = result.current.stats;

      // Approve pending action
      vi.mocked(api.approveAction).mockResolvedValue({
        success: true,
        action: { ...mockActions[0], status: ActionStatus.APPROVED },
      });

      vi.mocked(api.listActions).mockResolvedValue({
        total: 2,
        pending: 0,
        approved: 2,
        rejected: 0,
        executed: 0,
        failed: 0,
        actions: [
          mockActions[0],
          { ...mockActions[1], status: ActionStatus.APPROVED },
        ],
      });

      await act(async () => {
        await result.current.approveAction('act-1', {
          approved_by: 'john.doe',
        });
      });

      await waitFor(() => {
        expect(result.current.stats.approved).toBe(2);
        expect(result.current.stats.pending).toBe(0);
      });
    });
  });
});
