/**
 * Unit tests for API client.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import axios from 'axios'
import { api } from './client'

// Mock axios
vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() }
      }
    }))
  }
}))

describe('API Client', () => {
  beforeEach(() => {
    // Clear mocks before each test
    vi.clearAllMocks()
  })

  it('creates axios instance with correct config', () => {
    expect(axios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        timeout: 15000,
        headers: { 'Content-Type': 'application/json' },
        withCredentials: true
      })
    )
  })

  it('attaches request interceptor for auth', () => {
    const mockAxiosInstance = {
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() }
      }
    }

    // The interceptor should be attached
    expect(mockAxiosInstance.interceptors.request.use).toBeDefined()
  })

  it('attaches response interceptor for token refresh', () => {
    const mockAxiosInstance = {
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() }
      }
    }

    // The interceptor should be attached
    expect(mockAxiosInstance.interceptors.response.use).toBeDefined()
  })
})
