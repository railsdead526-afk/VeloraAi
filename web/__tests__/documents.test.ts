import { describe, expect, it } from 'vitest'

import {
  DOCUMENT_STATUSES,
  PENDING_DOCUMENT_STATUSES,
  hasPendingDocuments,
  isPendingStatus,
  statusColor,
} from '../lib/documents'

describe('document statuses', () => {
  it('knows the four states the backend emits', () => {
    expect([...DOCUMENT_STATUSES].sort()).toEqual(['failed', 'processing', 'queued', 'ready'])
  })

  it('treats queued as pending', () => {
    // The state every new document starts in. Omitting it meant a freshly
    // uploaded document never triggered polling.
    expect(isPendingStatus('queued')).toBe(true)
  })

  it('treats processing as pending', () => {
    expect(isPendingStatus('processing')).toBe(true)
  })

  it.each(['ready', 'failed'])('treats %s as settled', (status) => {
    expect(isPendingStatus(status)).toBe(false)
  })

  it.each(['pending', 'indexing', 'error', ''])(
    'does not invent the state %p that the backend never sends',
    (status) => {
      expect(PENDING_DOCUMENT_STATUSES.has(status)).toBe(false)
    },
  )
})

describe('hasPendingDocuments', () => {
  it('is false for an empty knowledge base', () => {
    expect(hasPendingDocuments([])).toBe(false)
  })

  it('is false once everything has settled', () => {
    expect(hasPendingDocuments([{ status: 'ready' }, { status: 'failed' }])).toBe(false)
  })

  it('is true when a newly created document is still queued', () => {
    expect(hasPendingDocuments([{ status: 'ready' }, { status: 'queued' }])).toBe(true)
  })

  it('is true while one document is processing', () => {
    expect(hasPendingDocuments([{ status: 'processing' }])).toBe(true)
  })
})

describe('statusColor', () => {
  it('is green only for ready', () => {
    expect(statusColor('ready')).toBe('#4ade80')
  })

  it('is red for failed', () => {
    expect(statusColor('failed')).toBe('#f87171')
  })

  it('treats an unrecognised status as in progress rather than done', () => {
    expect(statusColor('something-new')).toBe('#fbbf24')
    expect(statusColor('queued')).toBe('#fbbf24')
  })
})
