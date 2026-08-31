const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

export interface User {
  id: number
  email: string
  is_active: boolean
  role: 'free' | 'pro' | 'max' | 'admin'
  daily_requests_used: number
  daily_request_limit: number | null
  daily_reset_at: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
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

function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const prefix = `${name}=`
  const cookie = document.cookie.split('; ').find((item) => item.startsWith(prefix))
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null
}

export function getCsrfToken(): string | null {
  return getCookie('velora_csrf')
}

function authHeaders(method = 'GET'): HeadersInit {
  const csrfToken = getCsrfToken()
  const token = getAuthToken()
  return {
    'Content-Type': 'application/json',
    // Bearer auth also skips the server-side CSRF check, which is required
    // because the CSRF cookie lives on the API domain and cannot be read by
    // JavaScript on a different frontend domain (e.g. Vercel).
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())
      ? { 'X-CSRF-Token': csrfToken }
      : {}),
  }
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = options.method || 'GET'
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      ...authHeaders(method),
      ...(options.headers || {}),
    },
  })

  if (response.status === 401) {
    clearAuthToken()
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('velora-auth-expired'))
    }
    throw new Error('Your session has expired. Please sign in again.')
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const data = await response.json()
      if (typeof data?.detail === 'string') message = data.detail
    } catch {
      // Keep the HTTP status message when the response is not JSON.
    }
    throw new Error(message)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const response = await apiFetch<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  setAuthToken(response.access_token)
  return response
}

export async function register(email: string, password: string): Promise<User> {
  return apiFetch<User>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
    method: 'POST',
    credentials: 'include',
    headers: authHeaders('POST'),
  })
  clearAuthToken()
}

export async function getCurrentUser(): Promise<User> {
  return apiFetch<User>('/api/v1/auth/me')
}

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

// Token is stored in localStorage so the frontend can send `Authorization:
// Bearer` on every request. This is required because the CSRF double-submit
// cookie lives on the API domain and cross-domain JavaScript (Vercel ->
// Railway) can never read it.
export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null
  return (
    window.localStorage.getItem('velora_token') ||
    window.localStorage.getItem('velora_access_token')
  )
}

export function setAuthToken(token: string): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem('velora_token', token)
}

export function clearAuthToken(): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem('velora_token')
  window.localStorage.removeItem('velora_access_token')
}

export function subscribeAuthExpired(listener: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined
  const handler = () => listener()
  window.addEventListener('velora-auth-expired', handler)
  return () => window.removeEventListener('velora-auth-expired', handler)
}
