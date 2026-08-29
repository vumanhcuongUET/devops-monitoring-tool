/**
 * Unit tests for useWebSocket hook.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useWebSocket } from './useWebSocket'

// Real class so `new WebSocket()` works (old stub was a plain object — never
// constructible, every test failed to connect)
class MockWebSocket {
  url: string
  readyState: number = 0 // CONNECTING = 0
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    currentWs = this
    // Simulate connection opening
    setTimeout(() => {
      this.readyState = 1 // OPEN
      if (this.onopen) {
        this.onopen(new Event('open'))
      }
    }, 0)
  }

  send(data: string) {
    if (this.readyState !== 1) {
      throw new Error('WebSocket is not open')
    }
  }

  close() {
    this.readyState = 3 // CLOSED
    if (this.onclose) {
      this.onclose(new CloseEvent('close'))
    }
  }

  // Helper to simulate receiving a message
  simulateMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }))
    }
  }

  // Helper to simulate connection error
  simulateError() {
    this.readyState = 3 // CLOSED
    if (this.onerror) {
      this.onerror(new Event('error'))
    }
    if (this.onclose) {
      this.onclose(new CloseEvent('close'))
    }
  }
}

// Store reference to current WebSocket instance
let currentWs: MockWebSocket | null = null

describe('useWebSocket', () => {
  beforeEach(() => {
    // Mock global WebSocket with a constructible class
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    currentWs = null
    vi.clearAllMocks()
  })

  it('initializes with disconnected state', () => {
    const { result } = renderHook(() => useWebSocket())

    expect(result.current.connected).toBe(false)
    expect(result.current.data).toBeNull()
  })

  it('connects to WebSocket on mount', async () => {
    const { result } = renderHook(() => useWebSocket())

    // Wait for connection to open
    await waitFor(() => {
      expect(result.current.connected).toBe(true)
    })
  })

  it('receives and updates data on message', async () => {
    const { result } = renderHook(() => useWebSocket())

    await waitFor(() => {
      expect(result.current.connected).toBe(true)
    })

    const mockData = {
      type: 'overview_update',
      data: {
        timestamp: '2025-01-15T10:00:00Z',
        systems: [
          { name: 'elasticsearch', status: 'healthy' }
        ]
      }
    }

    act(() => {
      currentWs!.simulateMessage(mockData)
    })

    expect(result.current.data).toEqual(mockData.data)
  })

  it('handles status_update messages', async () => {
    const { result } = renderHook(() => useWebSocket())

    await waitFor(() => {
      expect(result.current.connected).toBe(true)
    })

    const mockData = {
      type: 'status_update',
      data: {
        timestamp: '2025-01-15T10:00:00Z',
        systems: []
      }
    }

    act(() => {
      currentWs!.simulateMessage(mockData)
    })

    expect(result.current.data).toEqual(mockData.data)
  })

  it('ignores malformed messages', async () => {
    const { result } = renderHook(() => useWebSocket())

    await waitFor(() => {
      expect(result.current.connected).toBe(true)
    })

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    act(() => {
      // Send invalid JSON
      if (currentWs && currentWs.onmessage) {
        currentWs.onmessage(new MessageEvent('message', { data: 'invalid json{' }))
      }
    })

    // Should not crash and data should remain null
    expect(result.current.data).toBeNull()

    consoleSpy.mockRestore()
  })

  it('sets connected to false when connection closes', async () => {
    const { result } = renderHook(() => useWebSocket())

    await waitFor(() => {
      expect(result.current.connected).toBe(true)
    })

    act(() => {
      currentWs!.close()
    })

    expect(result.current.connected).toBe(false)
  })

  it('sets connected to false on connection error', async () => {
    const { result } = renderHook(() => useWebSocket())

    await waitFor(() => {
      expect(result.current.connected).toBe(true)
    })

    act(() => {
      currentWs!.simulateError()
    })

    expect(result.current.connected).toBe(false)
  })

  it('closes WebSocket on unmount', async () => {
    const { unmount } = renderHook(() => useWebSocket())
    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })

    const closeSpy = vi.spyOn(currentWs!, 'close')

    unmount()

    expect(closeSpy).toHaveBeenCalled()
  })

  it('does not reconnect after unmount', async () => {
    const { unmount } = renderHook(() => useWebSocket())

    await waitFor(() => {
      expect(currentWs).toBeDefined()
    })
    const firstWs = currentWs

    unmount()

    // Intentional close nulls onclose — no reconnect scheduled, no new socket
    await new Promise((r) => setTimeout(r, 50))
    expect(currentWs).toBe(firstWs)
    expect(firstWs!.onclose).toBeNull()
  })

  it('handles multiple data updates', async () => {
    const { result } = renderHook(() => useWebSocket())

    await waitFor(() => {
      expect(result.current.connected).toBe(true)
    })

    const firstData = {
      type: 'overview_update',
      data: { systems: [{ name: 'es', status: 'healthy' }] }
    }

    const secondData = {
      type: 'overview_update',
      data: { systems: [{ name: 'prom', status: 'degraded' }] }
    }

    act(() => {
      currentWs!.simulateMessage(firstData)
    })

    expect(result.current.data).toEqual(firstData.data)

    act(() => {
      currentWs!.simulateMessage(secondData)
    })

    expect(result.current.data).toEqual(secondData.data)
  })
})
