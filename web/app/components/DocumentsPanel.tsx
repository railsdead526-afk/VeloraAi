'use client'

import { ChangeEvent, FormEvent, useCallback, useEffect, useRef, useState } from 'react'

import {
  createTextDocument,
  deleteDocument,
  listDocuments,
  reindexDocument,
  uploadDocument,
  type Document,
} from '../../lib/api'

/** Indexing is a background job, so poll while anything is still in flight. */
const POLL_INTERVAL_MS = 4000
const PENDING_STATES = new Set(['pending', 'processing', 'indexing'])

function statusColor(status: string): string {
  if (status === 'ready') return '#4ade80'
  if (status === 'failed' || status === 'error') return '#f87171'
  return '#fbbf24'
}

export default function DocumentsPanel({ onClose }: { onClose: () => void }) {
  const [documents, setDocuments] = useState<Document[]>([])
  const [name, setName] = useState('')
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  const load = useCallback(async (): Promise<Document[]> => {
    const current = await listDocuments()
    setDocuments(current)
    return current
  }, [])

  useEffect(() => {
    let active = true
    let timer: number | undefined

    const tick = async () => {
      try {
        const current = await listDocuments()
        if (!active) return
        setDocuments(current)
        // Stop polling once nothing is mid-index; a permanent timer on an idle
        // panel is a battery and quota drain.
        if (current.some((item) => PENDING_STATES.has(item.status))) {
          timer = window.setTimeout(tick, POLL_INTERVAL_MS)
        }
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : 'Failed to load documents')
        }
      }
    }

    void tick()
    return () => {
      active = false
      if (timer) window.clearTimeout(timer)
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

  const handleAddText = async (event: FormEvent) => {
    event.preventDefault()
    await run(async () => {
      await createTextDocument(name.trim(), content)
      setName('')
      setContent('')
      await load()
    }, 'Document queued for indexing.')
  }

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    await run(async () => {
      await uploadDocument(file)
      await load()
    }, `${file.name} queued for indexing.`)
    if (fileInput.current) fileInput.current.value = ''
  }

  return (
    <div style={styles.backdrop} role="dialog" aria-modal="true" aria-label="Documents">
      <div style={styles.panel}>
        <header style={styles.header}>
          <div>
            <h2 style={styles.title}>Knowledge base</h2>
            <p style={styles.muted}>
              Documents you add here are searched automatically when you chat with retrieval
              enabled. Only you can see them.
            </p>
          </div>
          <button type="button" onClick={onClose} style={styles.close} aria-label="Close">
            ×
          </button>
        </header>

        {error && <div style={styles.error}>{error}</div>}
        {notice && <div style={styles.notice}>{notice}</div>}

        <section style={styles.section}>
          <label htmlFor="doc-upload" style={styles.label}>
            Upload a file
          </label>
          <input
            id="doc-upload"
            ref={fileInput}
            type="file"
            accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
            onChange={(event) => void handleUpload(event)}
            disabled={busy}
            style={styles.input}
          />
          <p style={styles.fine}>Plain text, Markdown, or PDF.</p>
        </section>

        <form onSubmit={handleAddText} style={styles.section}>
          <label htmlFor="doc-name" style={styles.label}>
            Or paste text
          </label>
          <input
            id="doc-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Title"
            style={styles.input}
            maxLength={255}
            required
          />
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="Paste the content"
            style={{ ...styles.input, minHeight: 90, resize: 'vertical' }}
            required
          />
          <button type="submit" disabled={busy || !name.trim() || !content.trim()} style={styles.primary}>
            Add document
          </button>
        </form>

        <section style={styles.section}>
          <h3 style={styles.h3}>Your documents ({documents.length})</h3>
          {documents.length === 0 && <p style={styles.muted}>Nothing indexed yet.</p>}
          {documents.map((document) => (
            <div key={document.id} style={styles.row}>
              <div style={styles.grow}>
                <strong style={styles.name}>{document.name}</strong>
                <div style={styles.fine}>
                  <span style={{ color: statusColor(document.status) }}>{document.status}</span>
                  {document.last_index_error && ` · ${document.last_index_error}`}
                  {document.indexing_attempts > 1 &&
                    ` · ${document.indexing_attempts} attempts`}
                </div>
              </div>
              <div style={styles.actions}>
                {document.status !== 'ready' && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        await reindexDocument(document.id)
                        await load()
                      }, 'Reindexing.')
                    }
                    style={styles.ghost}
                  >
                    Retry
                  </button>
                )}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await deleteDocument(document.id)
                      await load()
                    }, 'Document deleted.')
                  }
                  style={styles.danger}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </section>
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
    width: 'min(600px, 100%)',
    maxHeight: '90vh',
    overflowY: 'auto',
    padding: 20,
    display: 'flex',
    flexDirection: 'column',
    gap: 14,
  },
  header: { display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' },
  title: { margin: 0, fontSize: 18 },
  h3: { margin: 0, fontSize: 14 },
  muted: { margin: '6px 0 0', color: '#9b9ba4', fontSize: 12, lineHeight: 1.5 },
  fine: { margin: '4px 0 0', color: '#71717a', fontSize: 11, lineHeight: 1.5 },
  close: {
    background: 'transparent',
    border: 'none',
    color: '#9b9ba4',
    fontSize: 24,
    cursor: 'pointer',
    lineHeight: 1,
  },
  section: {
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
    fontFamily: 'inherit',
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
    padding: '10px 12px',
    border: '1px solid #26262c',
    borderRadius: 10,
  },
  grow: { minWidth: 0, flex: 1 },
  name: { fontSize: 13, wordBreak: 'break-word' },
  actions: { display: 'flex', gap: 6, flexShrink: 0 },
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
    padding: '6px 10px',
    cursor: 'pointer',
    fontSize: 12,
  },
  danger: {
    background: 'transparent',
    color: '#f87171',
    border: '1px solid #4c1d1d',
    borderRadius: 8,
    padding: '6px 10px',
    cursor: 'pointer',
    fontSize: 12,
  },
  error: { color: '#f87171', fontSize: 12 },
  notice: { color: '#4ade80', fontSize: 12 },
}
