/**
 * Document indexing states.
 *
 * These names are a contract with the backend: a document moves
 * queued -> processing -> ready | failed, and the panel polls while it is in
 * one of the first two states.
 *
 * Getting this list wrong is silent. The previous version waited for
 * 'pending' | 'processing' | 'indexing' - two of which the backend never emits,
 * and it omitted 'queued', which is the state every new document starts in. The
 * result was a document that sat on "queued" forever in the UI even though the
 * server had finished indexing it.
 *
 * tests/test_document_status_contract.py parses this file and fails if it drifts
 * from app/models/document.py.
 */

export const DOCUMENT_STATUS_QUEUED = 'queued'
export const DOCUMENT_STATUS_PROCESSING = 'processing'
export const DOCUMENT_STATUS_READY = 'ready'
export const DOCUMENT_STATUS_FAILED = 'failed'

/** States from which the status can still change on its own. */
export const PENDING_DOCUMENT_STATUSES: ReadonlySet<string> = new Set([
  DOCUMENT_STATUS_QUEUED,
  DOCUMENT_STATUS_PROCESSING,
])

/** Every value the backend is allowed to send. */
export const DOCUMENT_STATUSES: ReadonlySet<string> = new Set([
  DOCUMENT_STATUS_QUEUED,
  DOCUMENT_STATUS_PROCESSING,
  DOCUMENT_STATUS_READY,
  DOCUMENT_STATUS_FAILED,
])

export function isPendingStatus(status: string): boolean {
  return PENDING_DOCUMENT_STATUSES.has(status)
}

/** True while at least one document could still change state by itself. */
export function hasPendingDocuments(documents: readonly { status: string }[]): boolean {
  return documents.some((document) => isPendingStatus(document.status))
}

/**
 * Colour for a status pill. An unknown status is treated as in-progress rather
 * than as success, so a future backend state is never shown as "done".
 */
export function statusColor(status: string): string {
  if (status === DOCUMENT_STATUS_READY) return '#4ade80'
  if (status === DOCUMENT_STATUS_FAILED) return '#f87171'
  return '#fbbf24'
}
