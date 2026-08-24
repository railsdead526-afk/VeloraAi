'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense, useEffect, useRef, useState } from 'react'

import { verifyEmail } from '../../lib/api'
import { authStyles as styles } from '../components/authStyles'

type State = 'working' | 'done' | 'failed'

function VerifyEmailInner() {
  const params = useSearchParams()
  const token = params.get('token') || ''
  // Derived at render rather than set inside the effect: a missing token is
  // knowable immediately, and setting state synchronously in an effect causes
  // an extra render pass for no reason.
  const [state, setState] = useState<State>(token ? 'working' : 'failed')
  const [message, setMessage] = useState(
    token ? '' : 'This link is missing its verification token.',
  )
  // React StrictMode mounts effects twice in development. These tokens are
  // single use, so a second call would report a spurious failure.
  const attempted = useRef(false)

  useEffect(() => {
    if (!token || attempted.current) return
    attempted.current = true

    let active = true
    const run = async () => {
      try {
        await verifyEmail(token)
        if (active) setState('done')
      } catch (error) {
        if (!active) return
        setState('failed')
        setMessage(
          error instanceof Error ? error.message : 'Verification failed. Request a new link.',
        )
      }
    }

    void run()
    return () => {
      active = false
    }
  }, [token])

  return (
    <main style={styles.center}>
      <div style={styles.card}>
        <div style={styles.logo}>VELORAAI</div>

        {state === 'working' && (
          <>
            <h1 style={styles.title}>Verifying your email…</h1>
            <p style={styles.muted}>One moment.</p>
          </>
        )}

        {state === 'done' && (
          <>
            <h1 style={styles.title}>Email verified</h1>
            <p style={styles.muted}>Your address is confirmed. You can sign in now.</p>
            <Link href="/" style={styles.primaryLink}>
              Continue to VeloraAi
            </Link>
          </>
        )}

        {state === 'failed' && (
          <>
            <h1 style={styles.title}>We could not verify that link</h1>
            <p style={styles.muted}>{message}</p>
            <p style={styles.fine}>
              Verification links expire, and each one can only be used once. Sign in and
              request a fresh link from your account settings.
            </p>
            <Link href="/" style={styles.primaryLink}>
              Back to sign in
            </Link>
          </>
        )}
      </div>
    </main>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <main style={styles.center}>
          <div style={styles.card}>
            <div style={styles.logo}>VELORAAI</div>
            <p style={styles.muted}>Loading…</p>
          </div>
        </main>
      }
    >
      <VerifyEmailInner />
    </Suspense>
  )
}
