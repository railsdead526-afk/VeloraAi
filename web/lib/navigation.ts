/**
 * Safe external navigation.
 *
 * The checkout redirect arrives from the payment gateway, is passed through the
 * backend, and is then handed to `window.location`. Assigning a `javascript:`
 * or `data:` URL there executes it in our own origin - and with tokens in
 * localStorage that is full session theft.
 *
 * The backend validates this too (app/services/payments/base.py). This is the
 * second layer, at the point of use, because that is the line that actually
 * navigates.
 */

/** True only for an absolute https URL with a host. */
export function isSafeExternalUrl(value: string): boolean {
  if (!value) return false
  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    // Not absolute, so it cannot be a hosted checkout page.
    return false
  }
  return parsed.protocol === 'https:' && parsed.hostname !== ''
}

/**
 * Navigate to an externally supplied URL, or throw.
 *
 * Throwing rather than silently ignoring keeps the failure visible: the user
 * sees an error instead of a button that does nothing.
 */
export function navigateExternal(value: string): void {
  if (!isSafeExternalUrl(value)) {
    throw new Error('The payment provider returned an address we will not open.')
  }
  window.location.href = value
}
