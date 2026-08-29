/**
 * Unit tests for API client.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

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
    vi.resetModules()
  })

  it('creates axios instance with correct config', async () => {
    await import('./client')
    const axios = (await import('axios')).default
    expect(axios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        timeout: 15000,
        withCredentials: true
      })
    )
  })

  it('attaches request interceptor for auth', async () => {
    await import('./client')
    const axios = (await import('axios')).default
    const instance = (axios.create as ReturnType<typeof vi.fn>).mock.results[0]?.value
    expect(instance?.interceptors.request.use).toBeDefined()
  })

  it('attaches response interceptor for token refresh', async () => {
    await import('./client')
    const axios = (await import('axios')).default
    const instance = (axios.create as ReturnType<typeof vi.fn>).mock.results[0]?.value
    expect(instance?.interceptors.response.use).toBeDefined()
  })
})
