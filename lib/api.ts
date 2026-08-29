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
  return {
    'Content-Type': 'application/json',
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
  return apiFetch<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
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

// Kept as a compatibility shim for callers from the pre-cookie client.
export function getAuthToken(): string | null {
  return null
}

export function setAuthToken(_token: string): void {
  void _token
  // The server stores the token in an HttpOnly cookie during login.
}

export function clearAuthToken(): void {
  // Remove a legacy token if an older client had stored one.
  if (typeof window !== 'undefined') localStorage.removeItem('velora_access_token')
}

export function subscribeAuthExpired(listener: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined
  const handler = () => listener()
  window.addEventListener('velora-auth-expired', handler)
  return () => window.removeEventListener('velora-auth-expired', handler)
}
