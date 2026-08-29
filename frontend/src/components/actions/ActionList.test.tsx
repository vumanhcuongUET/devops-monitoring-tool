/**
 * Regression tests for ActionList rendering, stats summary, and filters.
 * Previously deleted as stale (a560f26); rewritten against the current
 * component with the API transport mocked out and real TanStack Query.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'

import { fetchActions, getActionStats, type Action, type ActionListResponse } from '../../api/actions'
import { ActionList } from './ActionList'

vi.mock('../../api/actions', () => ({
  fetchActions: vi.fn(),
  fetchAction: vi.fn(),
  approveAction: vi.fn(),
  rejectAction: vi.fn(),
  executeAction: vi.fn(),
  getActionStats: vi.fn(),
}))

vi.mock('react-hot-toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  default: { success: vi.fn(), error: vi.fn() },
}))

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

const makeList = (overrides: Partial<ActionListResponse> = {}): ActionListResponse => ({
  total: 1,
  pending: 1,
  approved: 0,
  rejected: 0,
  executed: 0,
  failed: 0,
  actions: [makeAction()],
  ...overrides,
})

function renderList(props: { project?: string; currentUser?: string } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ActionList {...props} />
    </QueryClientProvider>,
  )
}

describe('ActionList states', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders a loading spinner while fetching', () => {
    vi.mocked(fetchActions).mockReturnValue(new Promise(() => {}))
    vi.mocked(getActionStats).mockReturnValue(new Promise(() => {}))

    const { container } = renderList()
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
    expect(screen.queryByText('No actions found')).not.toBeInTheDocument()
  })

  it('renders an error state when the fetch fails', async () => {
    vi.mocked(fetchActions).mockRejectedValue(new Error('boom'))
    vi.mocked(getActionStats).mockRejectedValue(new Error('boom'))

    renderList()
    expect(await screen.findByText('Failed to load actions')).toBeInTheDocument()
  })

  it('renders the empty state when there are no actions', async () => {
    vi.mocked(fetchActions).mockResolvedValue(makeList({ total: 0, actions: [] }))
    vi.mocked(getActionStats).mockResolvedValue({ total: 0, pending: 0, approved: 0, rejected: 0, executed: 0, failed: 0 })

    renderList()
    expect(await screen.findByText('No actions found')).toBeInTheDocument()
  })

  it('renders action cards and the stats summary', async () => {
    vi.mocked(fetchActions).mockResolvedValue(
      makeList({ total: 4, pending: 1, approved: 2, rejected: 0, executed: 1, failed: 0 }),
    )
    vi.mocked(getActionStats).mockResolvedValue({ total: 4, pending: 1, approved: 2, rejected: 0, executed: 1, failed: 0 })

    renderList()

    expect(await screen.findByText('Scale api deployment')).toBeInTheDocument()
    expect(screen.getByText('Total')).toBeInTheDocument()
    expect(screen.getAllByText('1')).toHaveLength(2) // pending stat + filter count
    expect(screen.getByText('All (4)')).toBeInTheDocument()
  })
})

describe('ActionList filters', () => {
  beforeEach(() => vi.clearAllMocks())

  it('refetches with the selected status filter', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchActions).mockResolvedValue(makeList())
    vi.mocked(getActionStats).mockResolvedValue({ total: 1, pending: 1, approved: 0, rejected: 0, executed: 0, failed: 0 })

    renderList({ project: 'meinvoice' })
    await screen.findByText('Scale api deployment')

    await user.click(screen.getByRole('button', { name: /Pending/i }))

    await waitFor(() => {
      const calls = vi.mocked(fetchActions).mock.calls
      expect(calls.at(-1)).toEqual(['meinvoice', 'pending', 100])
    })
  })

  it('passes project through to every fetch', async () => {
    vi.mocked(fetchActions).mockResolvedValue(makeList())
    vi.mocked(getActionStats).mockResolvedValue({ total: 1, pending: 1, approved: 0, rejected: 0, executed: 0, failed: 0 })

    renderList({ project: 'meinvoice' })
    await screen.findByText('Scale api deployment')

    expect(fetchActions).toHaveBeenCalledWith('meinvoice', undefined, 100)
  })
})
