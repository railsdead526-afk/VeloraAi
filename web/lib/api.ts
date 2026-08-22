const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

const ACCESS_TOKEN_KEY = 'velora_access_token'
const REFRESH_TOKEN_KEY = 'velora_refresh_token'

export interface User {
  id: number
  email: string
  is_active: boolean
  role: 'free' | 'pro' | 'max' | 'admin'
  email_verified: boolean
  daily_requests_used: number
  daily_request_limit: number | null
  daily_reset_at: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  refresh_token: string | null
}

export interface Conversation {
  id: number
  user_id: number
  title: string
  created_at: string
}

export interface Message {
  id: number
  conversation_id: number
  role: string
  content: string
  created_at: string
}

export interface ChatReplyResponse {
  user_message: Message
  assistant_message: Message
}

export type IntegrationProvider = 'github' | 'vercel' | 'railway' | 'cloudflare' | 'supabase'

export interface Integration {
  provider: IntegrationProvider
  display_name: string | null
  secret_fingerprint: string | null
  scopes: string | null
  status: string
  expires_at: string | null
  last_used_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SessionInfo {
  id: number
  issued_at: string | null
  expires_at: string | null
  user_agent: string | null
}

// --------------------------------------------------------------------------
// Password policy — mirrors app/schemas/user.py so the user sees the rule
// before the server rejects the request.
// --------------------------------------------------------------------------

export const MIN_PASSWORD_LENGTH = 12

export function describePasswordPolicy(): string {
  return 'At least 12 characters, mixing 3 of: lowercase, uppercase, digits, symbols.'
}

export function validatePassword(value: string): string | null {
  if (value.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`
  }
  const classes = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((re) => re.test(value)).length
  if (classes < 3) {
    return 'Password must combine at least three of: lowercase, uppercase, digits, symbols.'
  }
  return null
}

// --------------------------------------------------------------------------
// Token storage
// --------------------------------------------------------------------------

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function storeSession(tokens: TokenResponse): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
  if (tokens.refresh_token) {
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
  }
}

export function getAuthToken(): string | null {
  return getToken()
}

export function setAuthToken(token: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, token)
}

export function clearAuthToken(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

function announceExpiry(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('velora-auth-expired'))
  }
}

export function subscribeAuthExpired(listener: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined
  const handler = () => listener()
  window.addEventListener('velora-auth-expired', handler)
  return () => window.removeEventListener('velora-auth-expired', handler)
}

// --------------------------------------------------------------------------
// Refresh
//
// Access tokens are short lived (15 minutes). A 401 is therefore an expected,
// routine event rather than an error: we rotate the refresh token once and
// replay the original request. Concurrent 401s share a single in-flight
// refresh, because the server treats a replayed refresh token as theft and
// would revoke every session for the account.
// --------------------------------------------------------------------------

let refreshInFlight: Promise<boolean> | null = null

async function refreshSession(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        })
        if (!response.ok) return false
        const tokens = (await response.json()) as TokenResponse
        storeSession(tokens)
        return true
      } catch {
        return false
      } finally {
        // Release on the next tick so callers awaiting this promise all see
        // the same result before a new attempt can start.
        setTimeout(() => {
          refreshInFlight = null
        }, 0)
      }
    })()
  }

  return refreshInFlight
}

async function rawFetch(path: string, options: RequestInit): Promise<Response> {
  const token = getToken()
  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  })
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  { allowRetry = true }: { allowRetry?: boolean } = {},
): Promise<T> {
  let response = await rawFetch(path, options)

  if (response.status === 401 && allowRetry && getRefreshToken()) {
    if (await refreshSession()) {
      response = await rawFetch(path, options)
    }
  }

  if (response.status === 401) {
    clearAuthToken()
    announceExpiry()
    throw new Error('Your session has expired. Please sign in again.')
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const data = await response.json()
      if (typeof data?.detail === 'string') {
        message = data.detail
      } else if (Array.isArray(data?.detail) && data.detail[0]?.msg) {
        // FastAPI validation errors arrive as a list.
        message = String(data.detail[0].msg).replace(/^Value error, /, '')
      }
    } catch {
      // Keep the HTTP status message when the response is not JSON.
    }
    throw new Error(message)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

/** Returns a valid access token, refreshing first when one is available. */
export async function ensureFreshToken(): Promise<string | null> {
  const token = getToken()
  if (!token) return null
  try {
    await apiFetch<User>('/api/v1/auth/me')
  } catch {
    return getToken()
  }
  return getToken()
}

// --------------------------------------------------------------------------
// Auth
// --------------------------------------------------------------------------

export async function login(email: string, password: string): Promise<TokenResponse> {
  const tokens = await apiFetch<TokenResponse>(
    '/api/v1/auth/login',
    { method: 'POST', body: JSON.stringify({ email, password }) },
    { allowRetry: false },
  )
  storeSession(tokens)
  return tokens
}

export async function register(email: string, password: string): Promise<User> {
  return apiFetch<User>(
    '/api/v1/auth/register',
    { method: 'POST', body: JSON.stringify({ email, password }) },
    { allowRetry: false },
  )
}

export async function logout(allSessions = false): Promise<void> {
  const refreshToken = getRefreshToken()
  try {
    await apiFetch<{ status: string }>('/api/v1/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken, all_sessions: allSessions }),
    })
  } catch {
    // Best effort: the local session is cleared regardless.
  } finally {
    clearAuthToken()
  }
}

export async function getCurrentUser(): Promise<User> {
  return apiFetch<User>('/api/v1/auth/me')
}

export async function listSessions(): Promise<SessionInfo[]> {
  return apiFetch<SessionInfo[]>('/api/v1/auth/sessions')
}

export async function requestPasswordReset(email: string): Promise<void> {
  await apiFetch<{ status: string }>(
    '/api/v1/auth/password-reset',
    { method: 'POST', body: JSON.stringify({ email }) },
    { allowRetry: false },
  )
}

export async function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  await apiFetch<{ status: string }>(
    '/api/v1/auth/password-reset/confirm',
    { method: 'POST', body: JSON.stringify({ token, new_password: newPassword }) },
    { allowRetry: false },
  )
}

export async function verifyEmail(token: string): Promise<void> {
  await apiFetch<{ status: string }>(
    '/api/v1/auth/verify-email',
    { method: 'POST', body: JSON.stringify({ token }) },
    { allowRetry: false },
  )
}

export async function resendVerification(): Promise<void> {
  await apiFetch<{ status: string }>('/api/v1/auth/resend-verification', { method: 'POST' })
}

export async function deleteAccount(): Promise<void> {
  await apiFetch<{ status: string }>('/api/v1/auth/me', { method: 'DELETE' })
  clearAuthToken()
}

/** Downloads the UU PDP portability archive in the browser. */
export async function downloadMyData(): Promise<void> {
  await ensureFreshToken()
  const token = getToken()
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/me/export`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    throw new Error(
      response.status === 429
        ? 'Export is rate limited. Try again in an hour.'
        : `Export failed with status ${response.status}`,
    )
  }

  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = match?.[1] || 'veloraai-export.json'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  // Release the object URL, otherwise the blob is pinned for the tab's life.
  URL.revokeObjectURL(url)
}

export async function changePassword(current: string, next: string): Promise<void> {
  await apiFetch<{ status: string }>('/api/v1/auth/password', {
    method: 'POST',
    body: JSON.stringify({ current_password: current, new_password: next }),
  })
}

// --------------------------------------------------------------------------
// Integrations
// --------------------------------------------------------------------------

export async function listIntegrations(): Promise<Integration[]> {
  return apiFetch<Integration[]>('/api/v1/integrations')
}

export async function connectIntegration(
  provider: IntegrationProvider,
  secret: string,
  displayName?: string,
): Promise<Integration> {
  return apiFetch<Integration>('/api/v1/integrations', {
    method: 'PUT',
    body: JSON.stringify({ provider, secret, display_name: displayName || null }),
  })
}

export async function disconnectIntegration(provider: IntegrationProvider): Promise<void> {
  await apiFetch<{ status: string }>(`/api/v1/integrations/${provider}`, { method: 'DELETE' })
}

// --------------------------------------------------------------------------
// Documents (RAG)
// --------------------------------------------------------------------------

export interface Document {
  id: number
  name: string
  source: string
  mime_type: string | null
  status: string
  indexing_attempts: number
  last_index_error: string | null
  last_indexed_at: string | null
  created_at: string
  updated_at: string
}

export interface EmbeddingUsage {
  total_tokens?: number
  total_requests?: number
  [key: string]: unknown
}

export async function listDocuments(): Promise<Document[]> {
  return apiFetch<Document[]>('/api/v1/rag/documents')
}

export async function createTextDocument(name: string, content: string): Promise<Document> {
  return apiFetch<Document>('/api/v1/rag/documents', {
    method: 'POST',
    body: JSON.stringify({ name, content, source: 'text', mime_type: 'text/plain' }),
  })
}

/** Multipart upload. Content-Type must be left to the browser for the boundary. */
export async function uploadDocument(file: File): Promise<Document> {
  await ensureFreshToken()
  const token = getToken()
  const form = new FormData()
  form.append('file', file)

  const response = await fetch(`${API_BASE_URL}/api/v1/rag/documents/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })

  if (!response.ok) {
    let message = `Upload failed with status ${response.status}`
    if (response.status === 413) message = 'That file is larger than the upload limit.'
    if (response.status === 409) message = 'That document has already been uploaded.'
    try {
      const data = await response.json()
      if (typeof data?.detail === 'string') message = data.detail
    } catch {
      // Keep the status-derived message.
    }
    throw new Error(message)
  }
  return response.json() as Promise<Document>
}

export async function reindexDocument(documentId: number): Promise<Document> {
  return apiFetch<Document>(`/api/v1/rag/documents/${documentId}/reindex`, { method: 'POST' })
}

export async function deleteDocument(documentId: number): Promise<void> {
  await apiFetch<void>(`/api/v1/rag/documents/${documentId}`, { method: 'DELETE' })
}

export async function getEmbeddingUsage(): Promise<EmbeddingUsage> {
  return apiFetch<EmbeddingUsage>('/api/v1/rag/usage')
}

// --------------------------------------------------------------------------
// Billing
// --------------------------------------------------------------------------

export interface PaymentConfig {
  provider: string
  is_production: boolean
  pro_price_idr: number
  max_price_idr: number
}

export interface PaymentIntent {
  order_id: string
  amount: number
  currency: string
  snap_token: string
  redirect_url: string
}

export async function getPaymentConfig(): Promise<PaymentConfig> {
  return apiFetch<PaymentConfig>('/api/v1/payments/config')
}

export async function createPayment(plan: 'pro' | 'max'): Promise<PaymentIntent> {
  return apiFetch<PaymentIntent>('/api/v1/payments/create', {
    method: 'POST',
    body: JSON.stringify({ plan }),
  })
}

export function formatIdr(amount: number): string {
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    maximumFractionDigits: 0,
  }).format(amount)
}

// --------------------------------------------------------------------------
// Conversations
// --------------------------------------------------------------------------

export async function listConversations(): Promise<Conversation[]> {
  return apiFetch<Conversation[]>('/api/v1/conversations')
}

export async function createConversation(title = 'New Chat'): Promise<Conversation> {
  return apiFetch<Conversation>('/api/v1/conversations', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

export async function getMessages(conversationId: number): Promise<Message[]> {
  return apiFetch<Message[]>(`/api/v1/conversations/${conversationId}/messages`)
}

export async function sendMessage(
  conversationId: number,
  content: string,
  useRag = true,
  confirmTools = false,
): Promise<ChatReplyResponse> {
  return apiFetch<ChatReplyResponse>(`/api/v1/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content, use_rag: useRag, confirm_tools: confirmTools }),
  })
}

export function getStreamUrl(conversationId: number): string {
  return `${API_BASE_URL}/api/v1/conversations/${conversationId}/messages/stream`
}
