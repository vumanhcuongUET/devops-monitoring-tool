/**
 * Tests for ActionCard component
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActionCard } from './ActionCard';
import { Action, ActionStatus, RiskLevel } from '../../types';

describe('ActionCard', () => {
  const mockAction: Action = {
    id: 'act-123',
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
  };

  const mockOnApprove = vi.fn();
  const mockOnReject = vi.fn();
  const mockOnExecute = vi.fn();

  describe('Rendering', () => {
    it('renders action details', () => {
      render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(screen.getByText('Check pod status')).toBeInTheDocument();
      expect(screen.getByText(/kubectl get pods/)).toBeInTheDocument();
    });

    it('renders risk level badge', () => {
      const { getByText } = render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/safe/i)).toBeInTheDocument();
    });

    it('renders status badge', () => {
      const { getByText } = render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/pending/i)).toBeInTheDocument();
    });

    it('renders project name', () => {
      const { getByText } = render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/meinvoice/i)).toBeInTheDocument();
    });

    it('renders estimated impact', () => {
      const { getByText } = render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/No impact/i)).toBeInTheDocument();
    });
  });

  describe('Risk Level Styling', () => {
    it('applies safe styling', () => {
      const { container } = render(
        <ActionCard
          action={{ ...mockAction, risk_level: RiskLevel.SAFE }}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(container.querySelector('.risk-safe')).toBeInTheDocument();
    });

    it('applies critical styling', () => {
      const { container } = render(
        <ActionCard
          action={{ ...mockAction, risk_level: RiskLevel.CRITICAL }}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(container.querySelector('.risk-critical')).toBeInTheDocument();
    });

    it('applies high styling', () => {
      const { container } = render(
        <ActionCard
          action={{ ...mockAction, risk_level: RiskLevel.HIGH }}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(container.querySelector('.risk-high')).toBeInTheDocument();
    });
  });

  describe('Action Buttons', () => {
    it('shows approve/reject buttons for pending actions', () => {
      const { getByText } = render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/approve/i)).toBeInTheDocument();
      expect(getByText(/reject/i)).toBeInTheDocument();
    });

    it('shows execute button for approved actions', () => {
      const { getByText, queryByText } = render(
        <ActionCard
          action={{ ...mockAction, status: ActionStatus.APPROVED }}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/execute/i)).toBeInTheDocument();
      expect(queryByText(/approve/i)).not.toBeInTheDocument();
    });

    it('shows executed status for executed actions', () => {
      const { getByText, queryByText } = render(
        <ActionCard
          action={{ ...mockAction, status: ActionStatus.EXECUTED }}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/executed/i)).toBeInTheDocument();
      expect(queryByText(/execute/i)).not.toBeInTheDocument();
    });

    it('shows rejected status for rejected actions', () => {
      const { getByText } = render(
        <ActionCard
          action={{ ...mockAction, status: ActionStatus.REJECTED }}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/rejected/i)).toBeInTheDocument();
    });
  });

  describe('User Interactions', () => {
    it('calls onApprove when approve button clicked', () => {
      const { getByText } = render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      fireEvent.click(getByText(/approve/i));
      expect(mockOnApprove).toHaveBeenCalledWith('act-123');
    });

    it('calls onReject when reject button clicked', () => {
      const { getByText } = render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      fireEvent.click(getByText(/reject/i));
      expect(mockOnReject).toHaveBeenCalledWith('act-123');
    });

    it('calls onExecute when execute button clicked', () => {
      const { getByText } = render(
        <ActionCard
          action={{ ...mockAction, status: ActionStatus.APPROVED }}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      fireEvent.click(getByText(/execute/i));
      expect(mockOnExecute).toHaveBeenCalledWith('act-123');
    });

    it('shows confirmation dialog for high risk actions', () => {
      const { getByText } = render(
        <ActionCard
          action={{ ...mockAction, risk_level: RiskLevel.HIGH }}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      const approveButton = getByText(/approve/i);
      fireEvent.click(approveButton);

      // Should show confirmation
      expect(getByText(/are you sure/i)).toBeInTheDocument();
    });
  });

  describe('Command Display', () => {
    it('displays command in code block', () => {
      const { container } = render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      const codeElement = container.querySelector('code');
      expect(codeElement).toBeInTheDocument();
      expect(codeElement?.textContent).toContain('kubectl get pods');
    });

    it('truncates long commands', () => {
      const longCommand = 'kubectl get pods ' + '-n meinvoice '.repeat(10);
      const { container } = render(
        <ActionCard
          action={{ ...mockAction, command: longCommand }}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
          options={{ truncateLength: 50 }}
        />
      );

      const codeElement = container.querySelector('code');
      expect(codeElement?.textContent?.length).toBeLessThanOrEqual(60); // +10 for '...'
    });
  });

  describe('Timestamps', () => {
    it('displays created timestamp', () => {
      const { getByText } = render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/2026-08-18/)).toBeInTheDocument();
    });

    it('displays relative time', () => {
      const recentAction = {
        ...mockAction,
        created_at: new Date().toISOString(),
      };

      const { getByText } = render(
        <ActionCard
          action={recentAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/just now/i)).toBeInTheDocument();
    });
  });

  describe('Execution Results', () => {
    it('displays execution result when available', () => {
      const actionWithResult: Action = {
        ...mockAction,
        status: ActionStatus.EXECUTED,
        executed_by: 'system',
        executed_at: '2026-08-18T11:00:00Z',
        execution_result: {
          success: true,
          exit_code: 0,
          stdout: 'Pod deleted successfully',
          stderr: '',
          duration_seconds: 1.5,
        },
      };

      const { getByText } = render(
        <ActionCard
          action={actionWithResult}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/Pod deleted successfully/i)).toBeInTheDocument();
      expect(getByText(/1.5s/i)).toBeInTheDocument();
    });

    it('displays error message for failed execution', () => {
      const actionWithFailure: Action = {
        ...mockAction,
        status: ActionStatus.FAILED,
        execution_result: {
          success: false,
          exit_code: 1,
          stdout: '',
          stderr: 'Error: pod not found',
        },
      };

      const { getByText } = render(
        <ActionCard
          action={actionWithFailure}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByText(/Error: pod not found/i)).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA labels', () => {
      const { container } = render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      const card = container.querySelector('[role="article"]');
      expect(card).toBeInTheDocument();
      expect(card?.getAttribute('aria-label')).toContain('act-123');
    });

    it('buttons have accessible labels', () => {
      const { getByLabelText } = render(
        <ActionCard
          action={mockAction}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(getByLabelText(/approve action act-123/i)).toBeInTheDocument();
      expect(getByLabelText(/reject action act-123/i)).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('handles missing description gracefully', () => {
      const actionWithoutDescription = { ...mockAction, description: '' };

      const { container } = render(
        <ActionCard
          action={actionWithoutDescription}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      expect(container.textContent).toContain('Check pod status');
    });

    it('handles missing execution result', () => {
      const actionWithoutResult = {
        ...mockAction,
        status: ActionStatus.EXECUTED,
      };

      const { container } = render(
        <ActionCard
          action={actionWithoutResult}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      // Should not crash
      expect(container.firstChild).toBeInTheDocument();
    });

    it('handles very long title', () => {
      const longTitle = 'A'.repeat(200);
      const { getByText } = render(
        <ActionCard
          action={{ ...mockAction, title: longTitle }}
          onApprove={mockOnApprove}
          onReject={mockOnReject}
          onExecute={mockOnExecute}
        />
      );

      // Should truncate or wrap
      expect(getByText(/A{200}/)).not.toBeInTheDocument();
    });
  });
});
