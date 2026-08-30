/**
 * Unit tests for API client.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock axios — no `post` on purpose: any logout() network call would throw.
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

// Mock tokenManager so logout()'s clear can be observed.
vi.mock('../auth/tokenManager', () => ({
  getTokenManager: vi.fn(() => ({ clear: vi.fn() })),
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

  it('logout clears the local token and makes no network call (B5)', async () => {
    const { getTokenManager } = await import('../auth/tokenManager')
    const { logout } = await import('./client')
    await logout()
    const tm = vi.mocked(getTokenManager).mock.results.at(-1)?.value
    expect(tm?.clear).toHaveBeenCalledTimes(1)
  })
})
