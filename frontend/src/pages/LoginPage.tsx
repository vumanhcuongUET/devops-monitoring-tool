import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, tokenManager } from '../api/client'

/**
 * Phase 13 per-user login. On success the backend token (sub=<username>)
 * is stored and the app renders. No API-key fallback — identity is required.
 */
export default function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username || !password || busy) return
    setBusy(true)
    setError(null)
    try {
      const { data } = await api.post('/auth/login', { username, password })
      tokenManager.setToken({
        accessToken: data.access_token,
        expiresAt: Date.now() + (data.expires_in || 900) * 1000,
        tokenType: 'Bearer',
      })
      onLogin()
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setError(
        status === 401
          ? 'Invalid username or password'
          : 'Login failed — is the backend running?'
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-slate-950">
      <form
        onSubmit={submit}
        className="w-full max-w-sm bg-slate-900 border border-slate-800 rounded-xl p-8 space-y-4"
      >
        <h1 className="text-xl font-semibold text-slate-100 text-center">
          DevOps Monitor
        </h1>
        <p className="text-sm text-slate-400 text-center">Sign in to continue</p>

        <label className="block">
          <span className="text-sm text-slate-300">Username</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            className="mt-1 w-full rounded-md bg-slate-800 border border-slate-700 px-3 py-2 text-slate-100 focus:outline-none focus:border-blue-500"
          />
        </label>

        <label className="block">
          <span className="text-sm text-slate-300">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="mt-1 w-full rounded-md bg-slate-800 border border-slate-700 px-3 py-2 text-slate-100 focus:outline-none focus:border-blue-500"
          />
        </label>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={busy || !username || !password}
          className="w-full rounded-md bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white py-2 font-medium"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
