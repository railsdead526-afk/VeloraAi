'use client'

import { useEffect, useState } from 'react'
import { getCurrentUser, subscribeAuthExpired, type User } from '../../lib/api'

function formatResetAt(value: string): string {
  const date = new Date(value)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function QuotaBadge() {
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    let active = true

    const refresh = async () => {
      if (!localStorage.getItem('velora_access_token')) return
      try {
        const current = await getCurrentUser()
        if (active) setUser(current)
      } catch {
        if (active) setUser(null)
      }
    }

    void refresh()
    const interval = window.setInterval(refresh, 15000)
    const unsubscribe = subscribeAuthExpired(() => setUser(null))

    return () => {
      active = false
      window.clearInterval(interval)
      unsubscribe()
    }
  }, [])

  if (!user || user.daily_request_limit === null) return null

  const used = Math.max(0, user.daily_requests_used)
  const limit = Math.max(1, user.daily_request_limit)
  const remaining = Math.max(0, limit - used)
  const percentage = Math.min(100, Math.round((used / limit) * 100))

  return (
    <div
      aria-label={`AI usage: ${remaining} requests remaining today`}
      style={{
        position: 'fixed',
        top: 12,
        right: 12,
        zIndex: 50,
        minWidth: 180,
        padding: '10px 12px',
        borderRadius: 12,
        border: '1px solid rgba(255,255,255,0.12)',
        background: 'rgba(15, 15, 18, 0.92)',
        backdropFilter: 'blur(12px)',
        color: '#fff',
        fontFamily: 'system-ui, sans-serif',
        boxShadow: '0 8px 30px rgba(0,0,0,0.28)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12, opacity: 0.72 }}>
        <span>Daily AI usage</span>
        <strong style={{ opacity: 1 }}>{remaining} left</strong>
      </div>
      <div style={{ marginTop: 7, height: 5, borderRadius: 999, background: 'rgba(255,255,255,0.10)', overflow: 'hidden' }}>
        <div style={{ width: `${percentage}%`, height: '100%', background: 'rgba(255,255,255,0.78)', borderRadius: 999 }} />
      </div>
      <div style={{ marginTop: 6, fontSize: 11, opacity: 0.55 }}>
        {used}/{limit} used
        {user.daily_reset_at ? ` · resets ${formatResetAt(user.daily_reset_at)}` : ''}
      </div>
    </div>
  )
}
