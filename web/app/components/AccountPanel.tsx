'use client'

import { FormEvent, useEffect, useState } from 'react'

import { navigateExternal } from '../../lib/navigation'

import {
  changePassword,
  createPayment,
  deleteAccount,
  describePasswordPolicy,
  downloadMyData,
  formatIdr,
  getPaymentConfig,
  listSessions,
  logout as apiLogout,
  resendVerification,
  validatePassword,
  type PaymentConfig,
  type SessionInfo,
  type User,
} from '../../lib/api'

type Tab = 'account' | 'billing' | 'privacy'

export default function AccountPanel({
  user,
  onClose,
  onSignedOut,
  initialTab = 'account',
}: {
  user: User
  onClose: () => void
  onSignedOut: () => void
  initialTab?: Tab
}) {
  const [tab, setTab] = useState<Tab>(initialTab)
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [pricing, setPricing] = useState<PaymentConfig | null>(null)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmDelete, setConfirmDelete] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let active = true

    const load = async () => {
      try {
        const [loadedSessions, loadedPricing] = await Promise.all([
          listSessions(),
          getPaymentConfig().catch(() => null),
        ])
        if (!active) return
        setSessions(loadedSessions)
        setPricing(loadedPricing)
      } catch {
        // Panel stays usable even when these optional reads fail.
      }
    }

    void load()
    return () => {
      active = false
    }
  }, [])

  const run = async (action: () => Promise<void>, success: string) => {
    setError('')
    setNotice('')
    setBusy(true)
    try {
      await action()
      setNotice(success)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const handlePasswordChange = async (event: FormEvent) => {
    event.preventDefault()
    const policyError = validatePassword(newPassword)
    if (policyError) {
      setError(policyError)
      return
    }
    await run(async () => {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      // Changing the password revokes every session, including this one.
      onSignedOut()
    }, 'Password updated. Sign in again.')
  }

  const handleUpgrade = async (plan: 'pro' | 'max') => {
    if (pricing?.enabled === false) return
    await run(async () => {
      const intent = await createPayment(plan)
      navigateExternal(intent.redirect_url)
    }, 'Redirecting to checkout…')
  }

  const handleDelete = async () => {
    if (confirmDelete !== user.email) {
      setError('Type your email address exactly to confirm.')
      return
    }
    await run(async () => {
      await deleteAccount()
      onSignedOut()
    }, 'Account closed.')
  }

  return (
    <div style={styles.backdrop} role="dialog" aria-modal="true" aria-label="Account">
      <div style={styles.panel}>
        <header style={styles.header}>
          <div>
            <h2 style={styles.title}>{user.email}</h2>
            <p style={styles.muted}>
              Plan: <strong>{user.role.toUpperCase()}</strong>
              {!user.email_verified && ' · email not verified'}
            </p>
          </div>
          <button type="button" onClick={onClose} style={styles.close} aria-label="Close">
            ×
          </button>
        </header>

        <nav style={styles.tabs}>
          {(['account', 'billing', 'privacy'] as Tab[]).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setTab(item)}
              style={{ ...styles.tab, ...(tab === item ? styles.tabActive : {}) }}
            >
              {item[0].toUpperCase() + item.slice(1)}
            </button>
          ))}
        </nav>

        {error && <div style={styles.error}>{error}</div>}
        {notice && <div style={styles.notice}>{notice}</div>}

        {tab === 'account' && (
          <section style={styles.section}>
            {!user.email_verified && (
              <div style={styles.warn}>
                <p style={styles.tight}>Your email address is not verified.</p>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void run(resendVerification, 'Verification email sent.')}
                  style={styles.ghost}
                >
                  Resend verification
                </button>
              </div>
            )}

            <form onSubmit={handlePasswordChange} style={styles.form}>
              <h3 style={styles.h3}>Change password</h3>
              <input
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                type="password"
                autoComplete="current-password"
                placeholder="Current password"
                style={styles.input}
                required
              />
              <input
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                type="password"
                autoComplete="new-password"
                placeholder="New password"
                style={styles.input}
                required
              />
              <p style={styles.fine}>{describePasswordPolicy()}</p>
              <p style={styles.fine}>Changing your password signs out every device.</p>
              <button type="submit" disabled={busy} style={styles.primary}>
                Update password
              </button>
            </form>

            <div style={styles.form}>
              <h3 style={styles.h3}>Active sessions ({sessions.length})</h3>
              {sessions.map((session) => (
                <div key={session.id} style={styles.row}>
                  <span style={styles.muted}>
                    {session.user_agent?.slice(0, 60) || 'Unknown device'}
                  </span>
                  <span style={styles.fine}>
                    {session.issued_at ? new Date(session.issued_at).toLocaleString() : ''}
                  </span>
                </div>
              ))}
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    await apiLogout(true)
                    onSignedOut()
                  }, 'Signed out everywhere.')
                }
                style={styles.ghost}
              >
                Sign out of all devices
              </button>
            </div>
          </section>
        )}

        {tab === 'billing' && (
          <section style={styles.section}>
            <p style={styles.muted}>
              Plans run for a fixed period and do not renew automatically. You keep access
              until the period you paid for ends.
            </p>
            {pricing === null ? (
              <p style={styles.muted}>Billing is not configured on this deployment.</p>
            ) : pricing.enabled ? (
              <>
                {pricing.is_production === false && (
                  <div style={styles.warn}>
                    <p style={styles.tight}>
                      Sandbox mode. No real payment will be taken.
                    </p>
                  </div>
                )}
                <div style={styles.row}>
                  <div>
                    <strong>Pro</strong>
                    <div style={styles.fine}>Higher daily and monthly limits.</div>
                  </div>
                  <button
                    type="button"
                    disabled={busy || user.role === 'pro' || user.role === 'max'}
                    onClick={() => void handleUpgrade('pro')}
                    style={styles.primary}
                  >
                    {user.role === 'pro'
                      ? 'Current plan'
                      : pricing.pro_price_idr != null
                        ? formatIdr(pricing.pro_price_idr)
                        : 'Unavailable'}
                  </button>
                </div>
                <div style={styles.row}>
                  <div>
                    <strong>Max</strong>
                    <div style={styles.fine}>Highest limits.</div>
                  </div>
                  <button
                    type="button"
                    disabled={busy || user.role === 'max'}
                    onClick={() => void handleUpgrade('max')}
                    style={styles.primary}
                  >
                    {user.role === 'max'
                      ? 'Current plan'
                      : pricing.max_price_idr != null
                        ? formatIdr(pricing.max_price_idr)
                        : 'Unavailable'}
                  </button>
                </div>
                <p style={styles.fine}>
                  Prices are in IDR and include PPN where applicable.
                </p>
              </>
            ) : (
              <>
                <div style={styles.warn}>
                  <p style={styles.tight}>
                    {pricing.reason ??
                      'Upgrades are not available on this deployment yet.'}
                  </p>
                </div>
                <div style={styles.row}>
                  <div>
                    <strong>Pro</strong>
                    <div style={styles.fine}>Higher daily and monthly limits.</div>
                  </div>
                </div>
                <div style={styles.row}>
                  <div>
                    <strong>Max</strong>
                    <div style={styles.fine}>Highest limits.</div>
                  </div>
                </div>
                <p style={styles.fine}>
                  Your current plan and its limits keep working. Nothing is charged.
                </p>
              </>
            )}
          </section>
        )}

        {tab === 'privacy' && (
          <section style={styles.section}>
            <h3 style={styles.h3}>Download your data</h3>
            <p style={styles.muted}>
              A complete copy of your account, conversations, documents, and billing
              records. Password hashes and connected tokens are never included.
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={() => void run(downloadMyData, 'Export downloaded.')}
              style={styles.ghost}
            >
              Download JSON export
            </button>

            <h3 style={{ ...styles.h3, marginTop: 18 }}>Close account</h3>
            <p style={styles.muted}>
              Your account is deactivated and your email released. Billing and audit
              records are retained as Indonesian law requires. This cannot be undone.
            </p>
            <input
              value={confirmDelete}
              onChange={(event) => setConfirmDelete(event.target.value)}
              placeholder={`Type ${user.email} to confirm`}
              style={styles.input}
              autoComplete="off"
            />
            <button
              type="button"
              disabled={busy || confirmDelete !== user.email}
              onClick={() => void handleDelete()}
              style={styles.danger}
            >
              Permanently close my account
            </button>
          </section>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.6)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    zIndex: 50,
  },
  panel: {
    background: '#101014',
    color: '#f4f4f5',
    border: '1px solid #26262c',
    borderRadius: 14,
    width: 'min(560px, 100%)',
    maxHeight: '90vh',
    overflowY: 'auto',
    padding: 20,
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
  },
  header: { display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' },
  title: { margin: 0, fontSize: 17, wordBreak: 'break-all' },
  h3: { margin: 0, fontSize: 14 },
  muted: { margin: '6px 0 0', color: '#9b9ba4', fontSize: 12, lineHeight: 1.5 },
  fine: { margin: 0, color: '#71717a', fontSize: 11, lineHeight: 1.5 },
  tight: { margin: 0, fontSize: 12 },
  close: {
    background: 'transparent',
    border: 'none',
    color: '#9b9ba4',
    fontSize: 24,
    cursor: 'pointer',
    lineHeight: 1,
  },
  tabs: { display: 'flex', gap: 6, borderBottom: '1px solid #26262c', paddingBottom: 8 },
  tab: {
    background: 'transparent',
    border: 'none',
    color: '#9b9ba4',
    padding: '6px 10px',
    cursor: 'pointer',
    borderRadius: 6,
    fontSize: 13,
  },
  tabActive: { background: '#1d1d23', color: '#f4f4f5' },
  section: { display: 'flex', flexDirection: 'column', gap: 12 },
  form: { display: 'flex', flexDirection: 'column', gap: 8 },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
    padding: '10px 12px',
    border: '1px solid #26262c',
    borderRadius: 10,
  },
  warn: {
    border: '1px solid #4c3a1d',
    background: '#241d10',
    borderRadius: 10,
    padding: '10px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  input: {
    background: '#17171c',
    border: '1px solid #2c2c33',
    borderRadius: 8,
    color: '#f4f4f5',
    padding: '10px 12px',
    fontSize: 14,
  },
  primary: {
    background: '#f4f4f5',
    color: '#101014',
    border: 'none',
    borderRadius: 8,
    padding: '9px 14px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  ghost: {
    background: 'transparent',
    color: '#f4f4f5',
    border: '1px solid #2c2c33',
    borderRadius: 8,
    padding: '9px 14px',
    cursor: 'pointer',
  },
  danger: {
    background: 'transparent',
    color: '#f87171',
    border: '1px solid #4c1d1d',
    borderRadius: 8,
    padding: '9px 14px',
    cursor: 'pointer',
  },
  error: { color: '#f87171', fontSize: 12 },
  notice: { color: '#4ade80', fontSize: 12 },
}
