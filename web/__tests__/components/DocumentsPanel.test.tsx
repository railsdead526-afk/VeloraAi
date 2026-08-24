// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DocumentsPanel from '../../app/components/DocumentsPanel'

import { createTextDocument, listDocuments, type Document } from '../../lib/api'

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>()
  return {
    ...actual,
    listDocuments: vi.fn(),
    createTextDocument: vi.fn(),
  }
})

const mocked = vi.mocked(listDocuments)
const create = vi.mocked(createTextDocument)

function doc(status: Document['status']): Document {
  return {
    id: 7,
    name: 'Panduan',
    source: 'text',
    mime_type: null,
    status,
    indexing_attempts: 1,
    last_index_error: null,
    last_indexed_at: null,
    created_at: '2026-08-24T00:00:00Z',
    updated_at: '2026-08-24T00:00:00Z',
  }
}

/** Flush microtasks without touching (possibly faked) timers. */
const flush = () => act(async () => {})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('DocumentsPanel polling', () => {
  it('polls while a document is pending and stops once everything is ready', async () => {
    vi.useFakeTimers()
    mocked.mockResolvedValueOnce([doc('queued')]).mockResolvedValue([doc('ready')])

    render(<DocumentsPanel onClose={() => {}} />)

    // Initial load renders the queued document, one API call so far.
    await flush()
    expect(mocked).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Panduan')).toBeTruthy()
    expect(screen.getByText('queued')).toBeTruthy()

    // One interval later the poll observes the finished document...
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(mocked).toHaveBeenCalledTimes(2)
    expect(screen.getByText('ready')).toBeTruthy()

    // ...and because nothing is pending, no further poll is scheduled.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(12000)
    })
    expect(mocked).toHaveBeenCalledTimes(2)
  })

  it('re-arms polling when an upload makes a settled list pending again', async () => {
    vi.useFakeTimers()
    mocked
      .mockResolvedValueOnce([doc('ready')]) // initial load: nothing pending
      .mockResolvedValueOnce([doc('queued')]) // reload right after the upload
      .mockResolvedValue([doc('ready')]) // the poll that witnesses completion
    create.mockResolvedValue(doc('queued'))

    render(<DocumentsPanel onClose={() => {}} />)

    await flush()
    expect(mocked).toHaveBeenCalledTimes(1)
    expect(screen.getByText('ready')).toBeTruthy()

    // Add a document through the form, which reloads the list.
    fireEvent.change(screen.getByPlaceholderText('Title'), { target: { value: 'Panduan' } })
    fireEvent.change(screen.getByPlaceholderText('Paste the content'), {
      target: { value: 'isi dokumen' },
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Add document' }))
      await vi.advanceTimersByTimeAsync(0)
    })

    // The reload saw a queued document, so the poll timer must be armed again.
    await flush()
    expect(mocked).toHaveBeenCalledTimes(2)
    expect(screen.getByText('queued')).toBeTruthy()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(mocked).toHaveBeenCalledTimes(3)
    expect(screen.getByText('ready')).toBeTruthy()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(12000)
    })
    expect(mocked).toHaveBeenCalledTimes(3)
  })

  it('shows the indexing error text for failed documents', async () => {
    vi.useRealTimers()
    const failed: Document = {
      ...doc('failed'),
      last_index_error: 'PDF too large',
      indexing_attempts: 2,
    }
    mocked.mockResolvedValueOnce([failed])

    render(<DocumentsPanel onClose={() => {}} />)

    await flush()
    // Status lives in its own span; the error and attempt count are sibling
    // text nodes inside the same row, so assert on the rendered body text.
    expect(screen.getByText('failed')).toBeTruthy()
    expect(document.body.textContent).toContain('PDF too large')
    expect(document.body.textContent).toContain('2 attempts')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy()
  })
})
