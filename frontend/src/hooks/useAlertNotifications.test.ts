/**
 * Unit tests for useAlertNotifications hook.
 */

import { describe, it, expect, vi, beforeEach, afterEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useAlertNotifications } from './useAlertNotifications'
import type { AlertEvent } from '../types'

// Mock toast
vi.mock('react-hot-toast', () => ({
  default: vi.fn()
}))

import toast from 'react-hot-toast'

// Mock WebSocket similar to useWebSocket test
class MockWebSocket {
  url: string
  readyState: number = 0
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    setTimeout(() => {
      this.readyState = 1
    }, 0)
  }

  close() {
    this.readyState = 3
    if (this.onclose) {
      this.onclose(new CloseEvent('close'))
    }
  }

  simulateMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }))
    }
  }
}

let currentWs: MockWebSocket | null = null

describe('useAlertNotifications', () => {
  beforeEach(() => {
    vi.stubGlobal('WebSocket', {
      prototype: MockWebSocket.prototype,
      new: (url: string) => {
        currentWs = new MockWebSocket(url)
        return currentWs
      }
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    currentWs = null
    vi.clearAllMocks()
  })

  it('connects to WebSocket when mounted with handler', async () => {
    const mockHandler = vi.fn()
    renderHook(() => useAlertNotifications(mockHandler))

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })
  })

  it('calls handler when alert_fired message received', async () => {
    const mockHandler = vi.fn()
    renderHook(() => useAlertNotifications(mockHandler))

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })

    const alertData = {
      type: 'alert_fired',
      data: {
        rule_id: 'test-001',
        rule_name: 'High Error Rate',
        message: 'Error rate exceeded threshold'
      } as AlertEvent
    }

    act(() => {
      currentWs!.simulateMessage(alertData)
    })

    expect(mockHandler).toHaveBeenCalledTimes(1)
    expect(mockHandler).toHaveBeenCalledWith(
      expect.objectContaining({
        rule_name: 'High Error Rate'
      })
    )
  })

  it('calls handler when alert_resolved message received', async () => {
    const mockHandler = vi.fn()
    renderHook(() => useAlertNotifications(mockHandler))

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })

    const alertData = {
      type: 'alert_resolved',
      data: {
        rule_id: 'test-001',
        rule_name: 'High Error Rate',
        message: 'Error rate normalized'
      } as AlertEvent
    }

    act(() => {
      currentWs!.simulateMessage(alertData)
    })

    expect(mockHandler).toHaveBeenCalledTimes(1)
  })

  it('shows toast notification for firing alerts', async () => {
    const mockHandler = vi.fn()
    renderHook(() => useAlertNotifications(mockHandler))

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })

    const alertData = {
      type: 'alert_fired',
      data: {
        rule_id: 'test-001',
        rule_name: 'Test Alert',
        message: 'Alert fired'
      } as AlertEvent
    }

    act(() => {
      currentWs!.simulateMessage(alertData)
    })

    expect(toast).toHaveBeenCalledWith(
      expect.stringContaining('🔴'),
      expect.objectContaining({
        duration: 8000
      })
    )
  })

  it('shows toast notification for resolved alerts', async () => {
    const mockHandler = vi.fn()
    renderHook(() => useAlertNotifications(mockHandler))

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })

    const alertData = {
      type: 'alert_resolved',
      data: {
        rule_id: 'test-001',
        rule_name: 'Test Alert',
        message: 'Alert resolved'
      } as AlertEvent
    }

    act(() => {
      currentWs!.simulateMessage(alertData)
    })

    expect(toast).toHaveBeenCalledWith(
      expect.stringContaining('🟢'),
      expect.objectContaining({
        duration: 4000
      })
    )
  })

  it('ignores non-alert message types', async () => {
    const mockHandler = vi.fn()
    renderHook(() => useAlertNotifications(mockHandler))

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })

    const nonAlertData = {
      type: 'overview_update',
      data: { systems: [] }
    }

    act(() => {
      currentWs!.simulateMessage(nonAlertData)
    })

    expect(mockHandler).not.toHaveBeenCalled()
    expect(toast).not.toHaveBeenCalled()
  })

  it('handles malformed messages gracefully', async () => {
    const mockHandler = vi.fn()
    renderHook(() => useAlertNotifications(mockHandler))

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })

    act(() => {
      if (currentWs && currentWs.onmessage) {
        currentWs.onmessage(new MessageEvent('message', { data: 'invalid json{' }))
      }
    })

    // Should not throw error
    expect(mockHandler).not.toHaveBeenCalled()
  })

  it('removes listener on unmount', async () => {
    const mockHandler = vi.fn()
    const { unmount } = renderHook(() => useAlertNotifications(mockHandler))

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })

    unmount()

    // Send message after unmount
    const alertData = {
      type: 'alert_fired',
      data: {
        rule_id: 'test-001',
        rule_name: 'Test',
        message: 'Test'
      } as AlertEvent
    }

    act(() => {
      currentWs!.simulateMessage(alertData)
    })

    // Handler should not be called after unmount
    expect(mockHandler).not.toHaveBeenCalled()
  })

  it('supports multiple concurrent listeners', async () => {
    const handler1 = vi.fn()
    const handler2 = vi.fn()

    const { result: hook1 } = renderHook(() => useAlertNotifications(handler1))
    const { result: hook2 } = renderHook(() => useAlertNotifications(handler2))

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })

    const alertData = {
      type: 'alert_fired',
      data: {
        rule_id: 'test-001',
        rule_name: 'Test',
        message: 'Test'
      } as AlertEvent
    }

    act(() => {
      currentWs!.simulateMessage(alertData)
    })

    expect(handler1).toHaveBeenCalled()
    expect(handler2).toHaveBeenCalled()
  })

  it('disconnects when last listener unmounts', async () => {
    vi.useFakeTimers()

    const { unmount: unmount1 } = renderHook(() => useAlertNotifications(vi.fn()))
    const { unmount: unmount2 } = renderHook(() => useAlertNotifications(vi.fn()))

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })

    const closeSpy = vi.spyOn(currentWs!, 'close')

    unmount1()
    // Should not disconnect yet - one listener remains
    expect(closeSpy).not.toHaveBeenCalled()

    unmount2()
    // Now should disconnect
    await waitFor(() => {
      expect(closeSpy).toHaveBeenCalled()
    })

    vi.useRealTimers()
  })

  it('updates handler reference on change', async () => {
    const handler1 = vi.fn()
    const handler2 = vi.fn()

    const { rerender } = renderHook(
      ({ handler }) => useAlertNotifications(handler),
      { initialProps: { handler: handler1 } }
    )

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })

    const alertData = {
      type: 'alert_fired',
      data: {
        rule_id: 'test-001',
        rule_name: 'Test',
        message: 'Test'
      } as AlertEvent
    }

    act(() => {
      currentWs!.simulateMessage(alertData)
    })

    expect(handler1).toHaveBeenCalled()
    expect(handler2).not.toHaveBeenCalled()

    // Change handler
    rerender({ handler: handler2 })

    act(() => {
      currentWs!.simulateMessage(alertData)
    })

    expect(handler2).toHaveBeenCalled()
  })
})
