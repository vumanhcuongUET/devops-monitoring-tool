/**
 * Unit tests for usePolling hook.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { usePolling } from './usePolling'

// Mock @tanstack/react-query
vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn()
}))

import { useQuery } from '@tanstack/react-query'

describe('usePolling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls useQuery with correct parameters', () => {
    const mockFetcher = vi.fn(() => Promise.resolve({ data: 'test' }))
    vi.mocked(useQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn()
    })

    renderHook(() =>
      usePolling(['test-key'], mockFetcher, true)
    )

    expect(useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ['test-key'],
        queryFn: mockFetcher,
        enabled: true
      })
    )
  })

  it('uses polling interval from constants', () => {
    const mockFetcher = vi.fn(() => Promise.resolve({ data: 'test' }))
    vi.mocked(useQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn()
    })

    renderHook(() =>
      usePolling(['test-key'], mockFetcher)
    )

    expect(useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        refetchInterval: expect.any(Number)
      })
    )
  })

  it('respects enabled parameter', () => {
    const mockFetcher = vi.fn(() => Promise.resolve({ data: 'test' }))
    vi.mocked(useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: vi.fn()
    })

    renderHook(() =>
      usePolling(['test-key'], mockFetcher, false)
    )

    expect(useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        enabled: false
      })
    )
  })

  it('returns useQuery result', () => {
    const mockData = { result: 'success' }
    const mockFetcher = vi.fn(() => Promise.resolve(mockData))
    vi.mocked(useQuery).mockReturnValue({
      data: mockData,
      isLoading: false,
      error: null,
      refetch: vi.fn()
    })

    const { result } = renderHook(() =>
      usePolling(['test-key'], mockFetcher)
    )

    expect(result.current).toEqual({
      data: mockData,
      isLoading: false,
      error: null,
      refetch: expect.any(Function)
    })
  })

  it('handles loading state', () => {
    const mockFetcher = vi.fn(() => new Promise(() => {}))
    vi.mocked(useQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn()
    })

    const { result } = renderHook(() =>
      usePolling(['test-key'], mockFetcher)
    )

    expect(result.current.isLoading).toBe(true)
  })

  it('handles error state', () => {
    const mockError = new Error('Fetch failed')
    const mockFetcher = vi.fn(() => Promise.reject(mockError))
    vi.mocked(useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: mockError,
      refetch: vi.fn()
    })

    const { result } = renderHook(() =>
      usePolling(['test-key'], mockFetcher)
    )

    expect(result.current.error).toBe(mockError)
  })

  it('provides refetch function', () => {
    const mockRefetch = vi.fn()
    const mockFetcher = vi.fn(() => Promise.resolve({ data: 'test' }))
    vi.mocked(useQuery).mockReturnValue({
      data: { data: 'test' },
      isLoading: false,
      error: null,
      refetch: mockRefetch
    })

    const { result } = renderHook(() =>
      usePolling(['test-key'], mockFetcher)
    )

    expect(result.current.refetch).toBeDefined()
    expect(typeof result.current.refetch).toBe('function')
  })
})
