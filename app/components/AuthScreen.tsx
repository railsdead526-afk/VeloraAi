'use client'

import { FormEvent, useState } from 'react'
import type { User } from '../../lib/api'

interface AuthScreenProps { onAuth: (user: User) => void }

export default function AuthScreen({ onAuth }: AuthScreenProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const base = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
      const res = await fetch(`${base}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `Login failed (${res.status})`)
      }
      const userRes = await fetch(`${base}/api/v1/auth/me`, { credentials: 'include' })
      if (!userRes.ok) throw new Error('Failed to get user info')
      const user: User = await userRes.json()
      onAuth(user)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-primary">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-500 to-amber-600 mb-4 shadow-lg shadow-amber-500/20">
            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <h1 className="text-2xl font-semibold text-primary">VeloraAI</h1>
          <p className="text-secondary mt-1 text-sm">Sign in to continue</p>
        </div>

        <div className="bg-secondary rounded-2xl border border-color p-8 shadow-xl">
          <div className="flex rounded-xl bg-tertiary p-1 mb-6">
            <button type="button" onClick={() => { setMode('login'); setError('') }} className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-smooth ${mode === 'login' ? 'bg-primary text-primary shadow-sm' : 'text-secondary hover:text-primary'}`}>
              Sign In
            </button>
            <button type="button" onClick={() => { setMode('register'); setError('') }} className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-smooth ${mode === 'register' ? 'bg-primary text-primary shadow-sm' : 'text-secondary hover:text-primary'}`}>
              Register
            </button>
          </div>

          {error && (
            <div className="mb-4 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-secondary mb-2">Email address</label>
              <input id="email" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required className="w-full px-4 py-3 bg-tertiary border border-color rounded-xl text-primary placeholder:text-tertiary focus:outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/10 transition-smooth" />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-secondary mb-2">Password</label>
              <input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Min. 8 characters" required minLength={8} className="w-full px-4 py-3 bg-tertiary border border-color rounded-xl text-primary placeholder:text-tertiary focus:outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/10 transition-smooth" />
            </div>
            <button type="submit" disabled={loading} className="w-full py-3.5 bg-amber-500 text-black font-semibold rounded-xl hover:bg-amber-400 disabled:opacity-50 disabled:cursor-not-allowed transition-smooth shadow-md shadow-amber-500/20 focus-visible:outline-amber-500 mt-2">
              {loading ? <span className="inline-flex items-center gap-2"><svg className="w-4 h-4 spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg> Please wait...</span> : mode === 'login' ? 'Sign In' : 'Create Account'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-tertiary mt-6">By continuing, you agree to our Terms of Service and Privacy Policy.</p>
      </div>
    </div>
  )
}