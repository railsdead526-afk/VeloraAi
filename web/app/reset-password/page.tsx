'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { FormEvent, Suspense, useState } from 'react'

import { confirmPasswordReset, describePasswordPolicy, validatePassword } from '../../lib/api'
import { authStyles as styles } from '../components/authStyles'

function ResetPasswordInner() {
  const params = useSearchParams()
  const token = params.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')

    if (password !== confirmation) {
      setError('The two passwords do not match.')
      return
    }
    const policyError = validatePassword(password)
    if (policyError) {
      setError(policyError)
      return
    }

    setBusy(true)
    try {
      await confirmPasswordReset(token, password)
      setDone(true)
    } catch (resetError) {
      setError(
        resetError instanceof Error
          ? resetError.message
          : 'Could not reset the password. Request a new link.',
      )
    } finally {
      setBusy(false)
      // Do not leave the plaintext in component state longer than needed.
      setPassword('')
      setConfirmation('')
    }
  }

  if (!token) {
    return (
      <main style={styles.center}>
        <div style={styles.card}>
          <div style={styles.logo}>VELORAAI</div>
          <h1 style={styles.title}>This link is incomplete</h1>
          <p style={styles.muted}>It is missing its reset token.</p>
          <p style={styles.fine}>
            Some mail clients truncate long links. Try opening it from the original email, or
            request a new one.
          </p>
          <Link href="/" style={styles.primaryLink}>
            Back to sign in
          </Link>
        </div>
      </main>
    )
  }

  if (done) {
    return (
      <main style={styles.center}>
        <div style={styles.card}>
          <div style={styles.logo}>VELORAAI</div>
          <h1 style={styles.title}>Password updated</h1>
          <p style={styles.muted}>
            Every device that was signed in has been signed out, including any session an
            attacker may have had.
          </p>
          <Link href="/" style={styles.primaryLink}>
            Sign in
          </Link>
        </div>
      </main>
    )
  }

  return (
    <main style={styles.center}>
      <form onSubmit={handleSubmit} style={styles.card}>
        <div style={styles.logo}>VELORAAI</div>
        <h1 style={styles.title}>Choose a new password</h1>
        <p style={styles.muted}>{describePasswordPolicy()}</p>

        <input
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          type="password"
          autoComplete="new-password"
          placeholder="New password"
          style={styles.input}
          required
        />
        <input
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          type="password"
          autoComplete="new-password"
          placeholder="Repeat new password"
          style={styles.input}
          required
        />

        {error && <p style={styles.error}>{error}</p>}

        <button type="submit" disabled={busy} style={styles.primary}>
          {busy ? 'Updating…' : 'Update password'}
        </button>
        <p style={styles.fine}>
          This link can be used once and expires shortly after it was sent.
        </p>
      </form>
    </main>
  )
}

export default function ResetPasswordPage() {
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
      <ResetPasswordInner />
    </Suspense>
  )
}
