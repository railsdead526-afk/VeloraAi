'use client'

import { useEffect } from 'react'

/**
 * Registers the service worker that makes the app installable.
 *
 * Registration is deliberately skipped in development: a cached shell during
 * hot reload produces confusing stale-content bugs that look like application
 * faults. Any worker left over from a previous dev session is unregistered so
 * a developer never debugs against a stale cache.
 */
export default function ServiceWorkerRegistration() {
  useEffect(() => {
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return

    if (process.env.NODE_ENV !== 'production') {
      void navigator.serviceWorker
        .getRegistrations()
        .then((registrations) => registrations.forEach((registration) => registration.unregister()))
        .catch(() => undefined)
      return
    }

    const register = () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {
        // An unavailable worker must never break the page; the app works
        // perfectly well without it.
      })
    }

    // Wait for load so the worker never competes with the first paint.
    if (document.readyState === 'complete') {
      register()
    } else {
      window.addEventListener('load', register, { once: true })
      return () => window.removeEventListener('load', register)
    }
  }, [])

  return null
}
