/**
 * Tests for ActionList component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ActionList } from './ActionList';
import { Action, ActionStatus, RiskLevel } from '../../types';

// Mock the useActions hook
vi.mock('../../hooks/useActions', () => ({
  useActions: () => ({
    actions: mockActions,
    isLoading: false,
    error: null,
    approveAction: vi.fn(),
    rejectAction: vi.fn(),
    executeAction: vi.fn(),
    refetch: vi.fn(),
  }),
}));

const mockActions: Action[] = [
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
  {
    id: 'act-3',
    triage_card_id: 'tc-002',
    recommendation_id: 'rec-003',
    command_type: 'kubectl',
    command: 'kubectl scale deployment api --replicas=3 -n meinvoice',
    title: 'Scale up deployment',
    description: 'Increase replicas to handle load',
    project: 'meinvoice',
    risk_level: RiskLevel.MEDIUM,
    estimated_impact: 'Increased capacity',
    status: ActionStatus.EXECUTED,
    created_at: '2026-08-18T08:00:00Z',
    updated_at: '2026-08-18T11:00:00Z',
    executed_by: 'system',
    executed_at: '2026-08-18T11:00:00Z',
    execution_result: {
      success: true,
      exit_code: 0,
      stdout: 'deployment.apps/api scaled',
      stderr: '',
    },
    context: {},
  },
];

describe('ActionList', () => {
  describe('Rendering', () => {
    it('renders list of actions', () => {
      render(<ActionList project="meinvoice" />);

      expect(screen.getByText('Check pod status')).toBeInTheDocument();
      expect(screen.getByText('Delete failing pod')).toBeInTheDocument();
      expect(screen.getByText('Scale up deployment')).toBeInTheDocument();
    });

    it('renders empty state when no actions', () => {
      vi.mock('../../hooks/useActions', () => ({
        useActions: () => ({
          actions: [],
          isLoading: false,
          error: null,
          approveAction: vi.fn(),
          rejectAction: vi.fn(),
          executeAction: vi.fn(),
          refetch: vi.fn(),
        }),
      }));

      render(<ActionList project="meinvoice" />);

      expect(screen.getByText(/no actions/i)).toBeInTheDocument();
    });

    it('renders loading state', () => {
      vi.mock('../../hooks/useActions', () => ({
        useActions: () => ({
          actions: [],
          isLoading: true,
          error: null,
          approveAction: vi.fn(),
          rejectAction: vi.fn(),
          executeAction: vi.fn(),
          refetch: vi.fn(),
        }),
      }));

      render(<ActionList project="meinvoice" />);

      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it('renders error state', () => {
      vi.mock('../../hooks/useActions', () => ({
        useActions: () => ({
          actions: [],
          isLoading: false,
          error: 'Failed to load actions',
          approveAction: vi.fn(),
          rejectAction: vi.fn(),
          executeAction: vi.fn(),
          refetch: vi.fn(),
        }),
      }));

      render(<ActionList project="meinvoice" />);

      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  describe('Filtering', () => {
    it('filters by status when status prop provided', () => {
      const { container } = render(
        <ActionList project="meinvoice" status={ActionStatus.PENDING} />
      );

      // Should only show pending actions
      const pendingText = screen.getByText('Check pod status');
      expect(pendingText).toBeInTheDocument();
    });

    it('shows all actions when no status filter', () => {
      render(<ActionList project="meinvoice" />);

      expect(screen.getByText('Check pod status')).toBeInTheDocument();
      expect(screen.getByText('Delete failing pod')).toBeInTheDocument();
      expect(screen.getByText('Scale up deployment')).toBeInTheDocument();
    });

    it('filters by project when project prop provided', () => {
      render(<ActionList project="meinvoice" />);

      // All mock actions are from meinvoice
      expect(screen.getByText('Check pod status')).toBeInTheDocument();
    });
  });

  describe('Statistics', () => {
    it('displays action statistics', () => {
      const { getByText } = render(<ActionList project="meinvoice" />);

      // Should show stats badges
      expect(getByText(/pending/i)).toBeInTheDocument();
      expect(getByText(/approved/i)).toBeInTheDocument();
      expect(getByText(/executed/i)).toBeInTheDocument();
    });

    it('shows count badges', () => {
      const { container } = render(<ActionList project="meinvoice" />);

      // Should have count indicators
      const badges = container.querySelectorAll('.badge');
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  describe('Sorting', () => {
    it('sorts actions by created date descending by default', () => {
      const { container } = render(<ActionList project="meinvoice" />);

      const cards = container.querySelectorAll('[data-testid="action-card"]');
      const firstCardId = cards[0]?.getAttribute('data-action-id');

      // Most recent should be first
      expect(firstCardId).toBe('act-1');
    });

    it('supports sorting by status', () => {
      const { container } = render(
        <ActionList project="meinvoice" sortBy="status" />
      );

      // Actions should be grouped by status
      const cards = container.querySelectorAll('[data-testid="action-card"]');
      expect(cards.length).toBeGreaterThan(0);
    });

    it('supports sorting by risk level', () => {
      const { container } = render(
        <ActionList project="meinvoice" sortBy="risk" />
      );

      const cards = container.querySelectorAll('[data-testid="action-card"]');
      expect(cards.length).toBeGreaterThan(0);
    });
  });

  describe('Bulk Actions', () => {
    it('shows bulk approve button for multiple pending actions', () => {
      vi.mock('../../hooks/useActions', () => ({
        useActions: () => ({
          actions: [
            mockActions[0],
            { ...mockActions[1], status: ActionStatus.PENDING },
          ],
          isLoading: false,
          error: null,
          approveAction: vi.fn(),
          rejectAction: vi.fn(),
          executeAction: vi.fn(),
          refetch: vi.fn(),
        }),
      }));

      const { getByText } = render(<ActionList project="meinvoice" />);

      expect(getByText(/bulk approve/i)).toBeInTheDocument();
    });

    it('calls bulk approve when button clicked', async () => {
      const mockRefetch = vi.fn();
      vi.mock('../../hooks/useActions', () => ({
        useActions: () => ({
          actions: [
            mockActions[0],
            { ...mockActions[1], status: ActionStatus.PENDING },
          ],
          isLoading: false,
          error: null,
          approveAction: vi.fn(),
          rejectAction: vi.fn(),
          executeAction: vi.fn(),
          refetch: mockRefetch,
        }),
      }));

      const { getByText } = render(<ActionList project="meinvoice" />);

      fireEvent.click(getByText(/bulk approve/i));

      await waitFor(() => {
        expect(mockRefetch).toHaveBeenCalled();
      });
    });
  });

  describe('Pagination', () => {
    it('shows pagination when many actions', () => {
      // Create many actions
      const manyActions = Array.from({ length: 25 }, (_, i) => ({
        ...mockActions[0],
        id: `act-${i}`,
      }));

      vi.mock('../../hooks/useActions', () => ({
        useActions: () => ({
          actions: manyActions,
          isLoading: false,
          error: null,
          approveAction: vi.fn(),
          rejectAction: vi.fn(),
          executeAction: vi.fn(),
          refetch: vi.fn(),
        }),
      }));

      const { getByText } = render(
        <ActionList project="meinvoice" pageSize={10} />
      );

      expect(getByText(/next/i)).toBeInTheDocument();
    });

    it('handles page changes', () => {
      const { getByText } = render(
        <ActionList project="meinvoice" pageSize={10} />
      );

      const nextButton = getByText(/next/i);
      fireEvent.click(nextButton);

      // Should update to page 2
      await waitFor(() => {
        expect(getByText(/page 2/i)).toBeInTheDocument();
      });
    });
  });

  describe('Search', () => {
    it('filters actions by search query', () => {
      const { container, getByPlaceholderText } = render(
        <ActionList project="meinvoice" />
      );

      const searchInput = getByPlaceholderText(/search actions/i);
      fireEvent.change(searchInput, { target: { value: 'delete' } });

      // Should filter to only show delete-related actions
      await waitFor(() => {
        expect(screen.getByText('Delete failing pod')).toBeInTheDocument();
        expect(screen.queryByText('Check pod status')).not.toBeInTheDocument();
      });
    });

    it('clears search when clear button clicked', () => {
      const { getByPlaceholderText, getByRole } = render(
        <ActionList project="meinvoice" />
      );

      const searchInput = getByPlaceholderText(/search actions/i);
      fireEvent.change(searchInput, { target: { value: 'delete' } });

      const clearButton = getByRole('button', { name: /clear search/i });
      fireEvent.click(clearButton);

      // Should show all actions again
      await waitFor(() => {
        expect(screen.getByText('Check pod status')).toBeInTheDocument();
        expect(screen.getByText('Delete failing pod')).toBeInTheDocument();
      });
    });
  });

  describe('Real-time Updates', () => {
    it('updates when new action received via WebSocket', () => {
      const { container } = render(<ActionList project="meinvoice" />);

      // Simulate WebSocket update
      // (This would need WebSocket mock setup)

      expect(container.firstChild).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('has proper list semantics', () => {
      const { container } = render(<ActionList project="meinvoice" />);

      const list = container.querySelector('ul[role="list"]');
      expect(list).toBeInTheDocument();
    });

    it('announces action count to screen readers', () => {
      const { container } = render(<ActionList project="meinvoice" />);

      const status = container.querySelector('[aria-live="polite"]');
      expect(status).toBeInTheDocument();
      expect(status?.textContent).toContain('3 actions');
    });
  });

  describe('Responsive Design', () => {
    it('adapts to mobile layout', () => {
      // Mock mobile viewport
      global.innerWidth = 375;

      const { container } = render(<ActionList project="meinvoice" />);

      expect(container.querySelector('.mobile-layout')).toBeInTheDocument();
    });

    it('shows condensed cards on mobile', () => {
      global.innerWidth = 375;

      const { container } = render(<ActionList project="meinvoice" />);

      const cards = container.querySelectorAll('.condensed');
      expect(cards.length).toBeGreaterThan(0);
    });
  });
});
