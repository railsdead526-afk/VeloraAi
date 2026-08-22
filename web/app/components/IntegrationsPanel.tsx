'use client'

import { FormEvent, useEffect, useState } from 'react'

import {
  connectIntegration,
  disconnectIntegration,
  listIntegrations,
  type Integration,
  type IntegrationProvider,
} from '../../lib/api'

interface ProviderMeta {
  id: IntegrationProvider
  label: string
  hint: string
  docs: string
}

const PROVIDERS: ProviderMeta[] = [
  {
    id: 'github',
    label: 'GitHub',
    hint: 'Fine-grained token. Grant only the repositories the assistant should touch.',
    docs: 'https://github.com/settings/tokens',
  },
  {
    id: 'vercel',
    label: 'Vercel',
    hint: 'Account token from Settings → Tokens.',
    docs: 'https://vercel.com/account/tokens',
  },
  {
    id: 'railway',
    label: 'Railway',
    hint: 'Account or project token.',
    docs: 'https://railway.com/account/tokens',
  },
  {
    id: 'cloudflare',
    label: 'Cloudflare',
    hint: 'Scoped API token, not the global API key.',
    docs: 'https://dash.cloudflare.com/profile/api-tokens',
  },
  {
    id: 'supabase',
    label: 'Supabase',
    hint: 'Personal access token.',
    docs: 'https://supabase.com/dashboard/account/tokens',
  },
]

export default function IntegrationsPanel({ onClose }: { onClose: () => void }) {
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [provider, setProvider] = useState<IntegrationProvider>('github')
  const [secret, setSecret] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const refresh = async () => {
    try {
      setIntegrations(await listIntegrations())
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load integrations')
    }
  }

  useEffect(() => {
    let active = true

    const load = async () => {
      try {
        const current = await listIntegrations()
        if (active) setIntegrations(current)
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : 'Failed to load integrations')
        }
      }
    }

    void load()
    return () => {
      active = false
    }
  }, [])

  const connected = new Map(integrations.map((item) => [item.provider, item]))

  const handleConnect = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setNotice('')
    setBusy(true)
    try {
      await connectIntegration(provider, secret.trim(), displayName.trim() || undefined)
      // Never keep the plaintext secret in component state after it is stored.
      setSecret('')
      setDisplayName('')
      setNotice(`${provider} connected.`)
      await refresh()
    } catch (connectError) {
      setError(connectError instanceof Error ? connectError.message : 'Failed to connect provider')
    } finally {
      setBusy(false)
    }
  }

  const handleDisconnect = async (target: IntegrationProvider) => {
    setError('')
    setNotice('')
    setBusy(true)
    try {
      await disconnectIntegration(target)
      setNotice(`${target} disconnected.`)
      await refresh()
    } catch (removeError) {
      setError(removeError instanceof Error ? removeError.message : 'Failed to disconnect')
    } finally {
      setBusy(false)
    }
  }

  const active = PROVIDERS.find((item) => item.id === provider)

  return (
    <div style={styles.backdrop} role="dialog" aria-modal="true" aria-label="Integrations">
      <div style={styles.panel}>
        <header style={styles.header}>
          <div>
            <h2 style={styles.title}>Integrations</h2>
            <p style={styles.muted}>
              The assistant acts with <strong>your</strong> credentials, never a shared one.
              Tokens are encrypted before storage and can never be read back.
            </p>
          </div>
          <button type="button" onClick={onClose} style={styles.close} aria-label="Close">
            ×
          </button>
        </header>

        <section style={styles.list}>
          {PROVIDERS.map((item) => {
            const record = connected.get(item.id)
            return (
              <div key={item.id} style={styles.row}>
                <div>
                  <strong>{item.label}</strong>
                  {record ? (
                    <div style={styles.muted}>
                      {record.secret_fingerprint} · {record.status}
                      {record.last_used_at
                        ? ` · last used ${new Date(record.last_used_at).toLocaleDateString()}`
                        : ' · never used'}
                    </div>
                  ) : (
                    <div style={styles.muted}>Not connected</div>
                  )}
                </div>
                {record ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleDisconnect(item.id)}
                    style={styles.danger}
                  >
                    Disconnect
                  </button>
                ) : (
                  <button type="button" onClick={() => setProvider(item.id)} style={styles.ghost}>
                    Connect
                  </button>
                )}
              </div>
            )
          })}
        </section>

        <form onSubmit={handleConnect} style={styles.form}>
          <label style={styles.label} htmlFor="integration-provider">
            Provider
          </label>
          <select
            id="integration-provider"
            value={provider}
            onChange={(event) => setProvider(event.target.value as IntegrationProvider)}
            style={styles.input}
          >
            {PROVIDERS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>

          {active && (
            <p style={styles.muted}>
              {active.hint}{' '}
              <a href={active.docs} target="_blank" rel="noreferrer" style={styles.link}>
                Create a token
              </a>
            </p>
          )}

          <label style={styles.label} htmlFor="integration-secret">
            Token
          </label>
          <input
            id="integration-secret"
            value={secret}
            onChange={(event) => setSecret(event.target.value)}
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder="Paste the token"
            style={styles.input}
            required
            minLength={8}
          />

          <label style={styles.label} htmlFor="integration-label">
            Label (optional)
          </label>
          <input
            id="integration-label"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            placeholder="e.g. Personal account"
            style={styles.input}
            maxLength={120}
          />

          {error && <div style={styles.error}>{error}</div>}
          {notice && <div style={styles.notice}>{notice}</div>}

          <button type="submit" disabled={busy || !secret.trim()} style={styles.primary}>
            {connected.has(provider) ? 'Replace token' : 'Connect'}
          </button>
          <p style={styles.fine}>
            Grant the narrowest scope that works. Disconnecting deletes the stored token
            immediately.
          </p>
        </form>
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
    gap: 14,
  },
  header: { display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' },
  title: { margin: 0, fontSize: 18 },
  muted: { margin: '6px 0 0', color: '#9b9ba4', fontSize: 12, lineHeight: 1.5 },
  fine: { margin: 0, color: '#71717a', fontSize: 11, lineHeight: 1.5 },
  close: {
    background: 'transparent',
    border: 'none',
    color: '#9b9ba4',
    fontSize: 24,
    cursor: 'pointer',
    lineHeight: 1,
  },
  list: { display: 'flex', flexDirection: 'column', gap: 8 },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
    padding: '10px 12px',
    border: '1px solid #26262c',
    borderRadius: 10,
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    borderTop: '1px solid #26262c',
    paddingTop: 14,
  },
  label: { fontSize: 12, color: '#9b9ba4' },
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
    padding: '10px 14px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  ghost: {
    background: 'transparent',
    color: '#f4f4f5',
    border: '1px solid #2c2c33',
    borderRadius: 8,
    padding: '6px 12px',
    cursor: 'pointer',
  },
  danger: {
    background: 'transparent',
    color: '#f87171',
    border: '1px solid #4c1d1d',
    borderRadius: 8,
    padding: '6px 12px',
    cursor: 'pointer',
  },
  link: { color: '#93c5fd' },
  error: { color: '#f87171', fontSize: 12 },
  notice: { color: '#4ade80', fontSize: 12 },
}
