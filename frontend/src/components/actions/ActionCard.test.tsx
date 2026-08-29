/**
 * Regression tests for ActionCard approve/reject/execute interactions.
 * Previously deleted as stale (a560f26); rewritten against the current
 * component with the API transport mocked out and real TanStack Query.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'

import { approveAction, rejectAction, executeAction, type Action } from '../../api/actions'
import { ActionCard } from './ActionCard'

vi.mock('../../api/actions', () => ({
  approveAction: vi.fn(),
  rejectAction: vi.fn(),
  executeAction: vi.fn(),
}))

vi.mock('react-hot-toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  default: { success: vi.fn(), error: vi.fn() },
}))

import toast from 'react-hot-toast'

const makeAction = (overrides: Partial<Action> = {}): Action => ({
  id: 'act-1',
  command_type: 'kubectl',
  command: 'kubectl scale deployment api --replicas=3',
  parsed_params: { command_type: 'kubectl', flags: {}, args: [] },
  project: 'meinvoice',
  title: 'Scale api deployment',
  description: 'Scale up to handle load',
  risk_level: 'low',
  estimated_impact: '3 pods',
  status: 'pending',
  created_at: '2026-08-30T00:00:00Z',
  updated_at: '2026-08-30T00:00:00Z',
  context: {},
  ...overrides,
})

function renderCard(action: Action, props: { currentUser?: string; onRefresh?: () => void } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <ActionCard action={action} {...props} />
    </QueryClientProvider>,
  )
  return view
}

describe('ActionCard rendering', () => {
  it('renders title, description, command, and impact', () => {
    renderCard(makeAction())

    expect(screen.getByText('Scale api deployment')).toBeInTheDocument()
    expect(screen.getByText('Scale up to handle load')).toBeInTheDocument()
    expect(screen.getByText('kubectl scale deployment api --replicas=3')).toBeInTheDocument()
    expect(screen.getByText('3 pods')).toBeInTheDocument()
    expect(screen.getByText(/Impact:/)).toBeInTheDocument()
  })

  it('renders risk level badge uppercased', () => {
    renderCard(makeAction({ risk_level: 'critical' }))
    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
  })

  it('renders status badge uppercased', () => {
    renderCard(makeAction({ status: 'executed' }))
    expect(screen.getByText('EXECUTED')).toBeInTheDocument()
  })

  it('renders approved-by line when approved', () => {
    renderCard(makeAction({ status: 'approved', approved_by: 'alice' }))
    expect(screen.getByText('By alice')).toBeInTheDocument()
  })

  it('renders rejected-by line when rejected', () => {
    renderCard(makeAction({ status: 'rejected', rejected_by: 'bob' }))
    expect(screen.getByText('By bob')).toBeInTheDocument()
  })

  it('shows execution result success block with duration', () => {
    renderCard(makeAction({
      status: 'executed',
      execution_result: { success: true, stdout: 'deployment.apps/api scaled', duration_seconds: 1.5, timestamp: '2026-08-30T00:00:00Z' },
    }))

    expect(screen.getByText('Execution Successful')).toBeInTheDocument()
    expect(screen.getByText(/1\.50s/)).toBeInTheDocument()
    expect(screen.getByText('deployment.apps/api scaled')).toBeInTheDocument()
  })

  it('shows execution result failure block with stderr', () => {
    renderCard(makeAction({
      status: 'failed',
      execution_result: { success: false, stderr: 'forbidden', timestamp: '2026-08-30T00:00:00Z' },
    }))

    expect(screen.getByText('Execution Failed')).toBeInTheDocument()
    expect(screen.getByText('forbidden')).toBeInTheDocument()
  })

  it('truncates long stdout at 500 chars', () => {
    renderCard(makeAction({
      status: 'executed',
      execution_result: { success: true, stdout: 'x'.repeat(600), timestamp: '2026-08-30T00:00:00Z' },
    }))

    expect(screen.getByText(/x{499}\.\.\./)).toBeInTheDocument()
  })
})

describe('ActionCard buttons per status', () => {
  it('pending: shows approve/reject and comment box, no execute', () => {
    renderCard(makeAction({ status: 'pending' }))

    expect(screen.getByRole('button', { name: /Approve/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reject/i })).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/optional approval comment/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Execute Action/i })).not.toBeInTheDocument()
  })

  it('approved: shows execute, no approve/reject', () => {
    renderCard(makeAction({ status: 'approved' }))

    expect(screen.getByRole('button', { name: /Execute Action/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Approve$/i })).not.toBeInTheDocument()
  })

  it('rejected: no action buttons', () => {
    renderCard(makeAction({ status: 'rejected' }))

    expect(screen.queryByRole('button', { name: /Approve/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Execute Action/i })).not.toBeInTheDocument()
  })
})

describe('ActionCard interactions', () => {
  beforeEach(() => vi.clearAllMocks())

  it('approve calls the API with the typed comment and current user', async () => {
    const user = userEvent.setup()
    vi.mocked(approveAction).mockResolvedValue(makeAction({ status: 'approved', approved_by: 'alice' }))
    const onRefresh = vi.fn()

    renderCard(makeAction({ status: 'pending' }), { currentUser: 'alice', onRefresh: onRefresh })
    await user.type(screen.getByPlaceholderText(/optional approval comment/i), 'looks good')
    await user.click(screen.getByRole('button', { name: /Approve/i }))

    await waitFor(() =>
      expect(approveAction).toHaveBeenCalledWith('act-1', { approved_by: 'alice', comment: 'looks good' })
    )
    await waitFor(() => expect(onRefresh).toHaveBeenCalled())
  })

  it('approve API failure shows the card-level error toast', async () => {
    const user = userEvent.setup()
    vi.mocked(approveAction).mockRejectedValue(new Error('denied'))

    renderCard(makeAction({ status: 'pending' }))
    await user.click(screen.getByRole('button', { name: /Approve/i }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Failed to approve action'))
  })

  it('reject requires a reason before confirming', async () => {
    const user = userEvent.setup()
    vi.mocked(rejectAction).mockResolvedValue(makeAction({ status: 'rejected' }))

    renderCard(makeAction({ status: 'pending' }))
    await user.click(screen.getByRole('button', { name: /Reject/i }))

    const confirm = screen.getByRole('button', { name: /Confirm Reject/i })
    expect(confirm).toBeDisabled()

    await user.type(screen.getByPlaceholderText(/reason for rejection/i), 'wrong target')
    expect(confirm).toBeEnabled()

    await user.click(confirm)
    await waitFor(() =>
      expect(rejectAction).toHaveBeenCalledWith('act-1', { rejected_by: 'user', reason: 'wrong target' })
    )
  })

  it('execute calls the API with dry_run=false', async () => {
    const user = userEvent.setup()
    vi.mocked(executeAction).mockResolvedValue(makeAction({ status: 'executed' }))

    renderCard(makeAction({ status: 'approved' }), { currentUser: 'alice' })
    await user.click(screen.getByRole('button', { name: /Execute Action/i }))

    await waitFor(() =>
      expect(executeAction).toHaveBeenCalledWith('act-1', { executed_by: 'alice', dry_run: false })
    )
  })

  it('execute API failure shows the card-level error toast', async () => {
    const user = userEvent.setup()
    vi.mocked(executeAction).mockRejectedValue(new Error('boom'))

    renderCard(makeAction({ status: 'approved' }))
    await user.click(screen.getByRole('button', { name: /Execute Action/i }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Failed to execute action'))
  })
})
