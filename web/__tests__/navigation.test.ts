import { describe, expect, it, vi } from 'vitest'

import { isSafeExternalUrl, navigateExternal } from '../lib/navigation'

/**
 * The checkout redirect comes from the payment gateway and is handed straight
 * to window.location. A `javascript:` URL assigned there runs in our origin,
 * and tokens live in localStorage, so that is session theft rather than a
 * cosmetic bug.
 */
const HOSTILE = [
  'javascript:alert(1)',
  'JavaScript:alert(1)',
  '  javascript:alert(1)  ',
  'data:text/html,<script>alert(1)</script>',
  'vbscript:msgbox(1)',
  'file:///etc/passwd',
  'http://checkout.example.com/pay',
  '//checkout.example.com/pay',
  '/relative/path',
  'checkout.example.com',
  '',
  '   ',
]

describe('isSafeExternalUrl', () => {
  it.each(HOSTILE)('rejects %p', (value) => {
    expect(isSafeExternalUrl(value)).toBe(false)
  })

  it.each([
    'https://app.midtrans.com/snap/v3/redirection/abc123',
    'https://app.sandbox.midtrans.com/snap/v2/vtweb/xyz',
    'https://checkout.example.com/pay?order=1#top',
  ])('accepts the hosted checkout page %p', (value) => {
    expect(isSafeExternalUrl(value)).toBe(true)
  })
})

describe('navigateExternal', () => {
  it('assigns a valid https URL', () => {
    const location = { href: '' }
    vi.stubGlobal('window', { location })

    navigateExternal('https://app.midtrans.com/snap/v3/redirection/abc123')

    expect(location.href).toBe('https://app.midtrans.com/snap/v3/redirection/abc123')
    vi.unstubAllGlobals()
  })

  it.each(HOSTILE)('throws rather than navigating to %p', (value) => {
    const location = { href: 'https://velora.test/' }
    vi.stubGlobal('window', { location })

    expect(() => navigateExternal(value)).toThrow(/will not open/)
    // The critical assertion: nothing was assigned.
    expect(location.href).toBe('https://velora.test/')
    vi.unstubAllGlobals()
  })
})
