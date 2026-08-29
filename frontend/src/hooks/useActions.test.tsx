/**
 * Regression tests for the actions approve/execute path (hook layer).
 * Previously deleted as stale (a560f26); rewritten against the current
 * TanStack Query implementation with the API transport mocked out.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

import {
  fetchActions,
  fetchAction,
  approveAction,
  rejectAction,
  executeAction,
  getActionStats,
  type Action,
} from '../api/actions'
import {
  useActions,
  useAction,
  useActionStats,
  useApproveAction,
  useRejectAction,
  useExecuteAction,
  useActionManagement,
  actionKeys,
} from './useActions'

vi.mock('../api/actions', () => ({
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

import { toast } from 'react-hot-toast'

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

/** Harness that owns the QueryClient so tests can inspect cache invalidation. */
function makeHarness() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, wrapper }
}

describe('useActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches the action list', async () => {
    const list = { total: 1, pending: 1, approved: 0, rejected: 0, executed: 0, failed: 0, actions: [makeAction()] }
    vi.mocked(fetchActions).mockResolvedValue(list)

    const { wrapper } = makeHarness()
    const { result } = renderHook(() => useActions(), { wrapper })

    await waitFor(() => expect(result.current.data).toEqual(list))
  })

  it('passes project/status/limit filters to the API', async () => {
    vi.mocked(fetchActions).mockResolvedValue({
      total: 0, pending: 0, approved: 0, rejected: 0, executed: 0, failed: 0, actions: [],
    })

    const { wrapper } = makeHarness()
    renderHook(() => useActions('meinvoice', 'pending', 50), { wrapper })

    await waitFor(() =>
      expect(fetchActions).toHaveBeenCalledWith('meinvoice', 'pending', 50)
    )
  })

  it('polls every 10 seconds', async () => {
    vi.mocked(fetchActions).mockResolvedValue({
      total: 0, pending: 0, approved: 0, rejected: 0, executed: 0, failed: 0, actions: [],
    })

    const { queryClient, wrapper } = makeHarness()
    renderHook(() => useActions(), { wrapper })

    await waitFor(() => expect(queryClient.getQueryCache().getAll()).toHaveLength(1))
    const options = queryClient.getQueryCache().getAll()[0].options as { refetchInterval?: number }
    expect(options.refetchInterval).toBe(10000)
  })

  it('surfaces fetch errors', async () => {
    vi.mocked(fetchActions).mockRejectedValue(new Error('boom'))

    const { wrapper } = makeHarness()
    const { result } = renderHook(() => useActions(), { wrapper })

    await waitFor(() => expect(result.current.error).toBeTruthy())
  })
})

describe('useAction', () => {
  beforeEach(() => vi.clearAllMocks())

  it('does not fetch without an id', () => {
    const { wrapper } = makeHarness()
    renderHook(() => useAction(''), { wrapper })

    expect(fetchAction).not.toHaveBeenCalled()
  })

  it('fetches a single action by id', async () => {
    const action = makeAction()
    vi.mocked(fetchAction).mockResolvedValue(action)

    const { wrapper } = makeHarness()
    const { result } = renderHook(() => useAction('act-1'), { wrapper })

    await waitFor(() => expect(result.current.data).toEqual(action))
    expect(fetchAction).toHaveBeenCalledWith('act-1')
  })
})

describe('useActionStats', () => {
  beforeEach(() => vi.clearAllMocks())

  it('fetches stats summary', async () => {
    const stats = { total: 2, pending: 1, approved: 1, rejected: 0, executed: 0, failed: 0 }
    vi.mocked(getActionStats).mockResolvedValue(stats)

    const { wrapper } = makeHarness()
    const { result } = renderHook(() => useActionStats(), { wrapper })

    await waitFor(() => expect(result.current.data).toEqual(stats))
  })
})

describe('useApproveAction', () => {
  beforeEach(() => vi.clearAllMocks())

  it('approves, toasts, and invalidates the list cache', async () => {
    const approved = makeAction({ status: 'approved', approved_by: 'alice' })
    vi.mocked(approveAction).mockResolvedValue(approved)

    const { queryClient, wrapper } = makeHarness()
    // Seed the cache so invalidation state is observable after onSuccess.
    queryClient.setQueryData(actionKeys.lists(), 'seed')
    const { result } = renderHook(() => useApproveAction(), { wrapper })

    result.current.mutate({ actionId: 'act-1', request: { approved_by: 'alice' } })

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Action act-1 approved'))
    expect(approveAction).toHaveBeenCalledWith('act-1', { approved_by: 'alice' })
    await waitFor(() =>
      expect(queryClient.getQueryState(actionKeys.lists())?.isInvalidated).toBe(true)
    )
  })

  it('toasts an error on failure', async () => {
    vi.mocked(approveAction).mockRejectedValue(new Error('not allowed'))

    const { wrapper } = makeHarness()
    const { result } = renderHook(() => useApproveAction(), { wrapper })

    result.current.mutate({ actionId: 'act-1', request: { approved_by: 'alice' } })

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Failed to approve action: not allowed')
    )
  })
})

describe('useRejectAction', () => {
  beforeEach(() => vi.clearAllMocks())

  it('rejects and toasts success', async () => {
    const rejected = makeAction({ status: 'rejected', rejected_by: 'alice' })
    vi.mocked(rejectAction).mockResolvedValue(rejected)

    const { wrapper } = makeHarness()
    const { result } = renderHook(() => useRejectAction(), { wrapper })

    result.current.mutate({ actionId: 'act-1', request: { rejected_by: 'alice', reason: 'risky' } })

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Action act-1 rejected'))
    expect(rejectAction).toHaveBeenCalledWith('act-1', { rejected_by: 'alice', reason: 'risky' })
  })

  it('toasts an error on failure', async () => {
    vi.mocked(rejectAction).mockRejectedValue(new Error('blocked'))

    const { wrapper } = makeHarness()
    const { result } = renderHook(() => useRejectAction(), { wrapper })

    result.current.mutate({ actionId: 'act-1', request: { rejected_by: 'alice', reason: 'risky' } })

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Failed to reject action: blocked')
    )
  })
})

describe('useExecuteAction', () => {
  beforeEach(() => vi.clearAllMocks())

  it('toasts success when execution succeeds', async () => {
    const executed = makeAction({ status: 'executed' })
    vi.mocked(executeAction).mockResolvedValue(executed)

    const { wrapper } = makeHarness()
    const { result } = renderHook(() => useExecuteAction(), { wrapper })

    result.current.mutate({ actionId: 'act-1', request: { executed_by: 'alice' } })

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Action act-1 executed successfully')
    )
  })

  it('toasts failure when execution reports failed status', async () => {
    const failed = makeAction({ status: 'failed' })
    vi.mocked(executeAction).mockResolvedValue(failed)

    const { wrapper } = makeHarness()
    const { result } = renderHook(() => useExecuteAction(), { wrapper })

    result.current.mutate({ actionId: 'act-1', request: { executed_by: 'alice' } })

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Action act-1 execution failed')
    )
  })

  it('invalidates list, detail, and stats caches', async () => {
    vi.mocked(executeAction).mockResolvedValue(makeAction({ status: 'executed' }))

    const { queryClient, wrapper } = makeHarness()
    queryClient.setQueryData(actionKeys.lists(), 'seed')
    queryClient.setQueryData(actionKeys.detail('act-1'), 'seed')
    queryClient.setQueryData(actionKeys.stats(), 'seed')
    const { result } = renderHook(() => useExecuteAction(), { wrapper })

    result.current.mutate({ actionId: 'act-1', request: { executed_by: 'alice' } })

    await waitFor(() => {
      for (const key of [actionKeys.lists(), actionKeys.detail('act-1'), actionKeys.stats()]) {
        expect(queryClient.getQueryState(key)?.isInvalidated).toBe(true)
      }
    })
  })

  it('toasts an error on network failure', async () => {
    vi.mocked(executeAction).mockRejectedValue(new Error('timeout'))

    const { wrapper } = makeHarness()
    const { result } = renderHook(() => useExecuteAction(), { wrapper })

    result.current.mutate({ actionId: 'act-1', request: { executed_by: 'alice' } })

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Failed to execute action: timeout')
    )
  })
})

describe('useActionManagement', () => {
  beforeEach(() => vi.clearAllMocks())

  it('wires approve/reject/execute through the mutations', async () => {
    vi.mocked(approveAction).mockResolvedValue(makeAction({ status: 'approved' }))

    const { wrapper } = makeHarness()
    const { result } = renderHook(() => useActionManagement('act-1'), { wrapper })

    await result.current.approveAction({ approved_by: 'alice' })

    expect(approveAction).toHaveBeenCalledWith('act-1', { approved_by: 'alice' })
    expect(result.current.isApproving).toBe(false)
  })
})
