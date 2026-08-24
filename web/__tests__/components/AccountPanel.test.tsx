// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AccountPanel from '../../app/components/AccountPanel'

import {
  createPayment,
  getPaymentConfig,
  type PaymentConfig,
  type User,
} from '../../lib/api'
import * as navigation from '../../lib/navigation'

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>()
  return {
    ...actual,
    listSessions: vi.fn().mockResolvedValue([]),
    getPaymentConfig: vi.fn(),
    createPayment: vi.fn(),
    logout: vi.fn().mockResolvedValue(undefined),
  }
})

vi.mock('../../lib/navigation', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/navigation')>()
  return {
    ...actual,
    navigateExternal: vi.fn(),
  }
})

const user: User = {
  id: 1,
  email: 'user@example.com',
  is_active: true,
  role: 'free',
  email_verified: true,
  daily_requests_used: 0,
  daily_request_limit: 10,
  daily_reset_at: null,
}

function renderPanel(initialTab: 'account' | 'billing' | 'privacy' = 'billing') {
  return render(
    <AccountPanel user={user} onClose={() => {}} onSignedOut={() => {}} initialTab={initialTab} />
  )
}

const getConfig = vi.mocked(getPaymentConfig)
const create = vi.mocked(createPayment)
const navigateExternal = vi.mocked(navigation.navigateExternal)

beforeEach(() => {
  getConfig.mockReset()
  create.mockReset()
  navigateExternal.mockReset()
})

afterEach(cleanup)

describe('AccountPanel billing tab', () => {
  it('shows an honest unavailable state instead of prices when payments are off', async () => {
    const disabled: PaymentConfig = {
      provider: 'disabled',
      enabled: false,
      reason: 'Payments are not enabled on this deployment.',
    }
    getConfig.mockResolvedValue(disabled)

    renderPanel('billing')

    expect(await screen.findByText(/not enabled on this deployment/i)).toBeTruthy()
    // No price buttons to click into a dead checkout, and no "Rp NaN".
    expect(screen.queryByText(/Rp/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /Rp/ })).toBeNull()
    await waitFor(() => expect(create).not.toHaveBeenCalled())
  })

  it('never calls checkout when the config is disabled, even if a stale price renders', async () => {
    const disabled: PaymentConfig = {
      provider: 'disabled',
      enabled: false,
    }
    getConfig.mockResolvedValue(disabled)

    renderPanel('billing')

    await screen.findByText(/not available on this deployment/i)
    expect(create).not.toHaveBeenCalled()
  })

  it('renders IDR prices and the sandbox warning when enabled in sandbox', async () => {
    const enabled: PaymentConfig = {
      provider: 'midtrans',
      enabled: true,
      is_production: false,
      pro_price_idr: 19900,
      max_price_idr: 49900,
    }
    getConfig.mockResolvedValue(enabled)

    renderPanel('billing')

    expect(await screen.findByText('Rp 19.900')).toBeTruthy()
    expect(screen.getByText('Rp 49.900')).toBeTruthy()
    expect(screen.getByText(/sandbox mode/i)).toBeTruthy()
  })

  it('hides the sandbox warning in production mode', async () => {
    const enabled: PaymentConfig = {
      provider: 'midtrans',
      enabled: true,
      is_production: true,
      pro_price_idr: 19900,
      max_price_idr: 49900,
    }
    getConfig.mockResolvedValue(enabled)

    renderPanel('billing')

    await screen.findByText('Rp 19.900')
    expect(screen.queryByText(/sandbox mode/i)).toBeNull()
  })

  it('falls back to an honest note when the config endpoint fails', async () => {
    getConfig.mockRejectedValue(new Error('offline'))

    renderPanel('billing')

    expect(await screen.findByText(/not configured on this deployment/i)).toBeTruthy()
    expect(screen.queryByText(/Rp/i)).toBeNull()
  })

  it('sends upgrade clicks through validated external navigation only', async () => {
    const enabled: PaymentConfig = {
      provider: 'midtrans',
      enabled: true,
      is_production: true,
      pro_price_idr: 19900,
      max_price_idr: 49900,
    }
    getConfig.mockResolvedValue(enabled)
    create.mockResolvedValue({
      order_id: 'ORDER-1',
      amount: 19900,
      currency: 'IDR',
      checkout_token: null,
      redirect_url: 'https://checkout.example.com/pay',
    })

    renderPanel('billing')

    const button = await screen.findByRole('button', { name: /19\.900/ })
    button.click()

    await waitFor(() => expect(create).toHaveBeenCalledWith('pro'))
    await waitFor(() =>
      expect(navigateExternal).toHaveBeenCalledWith('https://checkout.example.com/pay')
    )
    // Raw window.location assignment must never happen for external targets.
    expect(window.location.href).not.toContain('checkout.example.com')
  })
})
