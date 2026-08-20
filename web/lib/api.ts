const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

export interface User {
  id: number
  email: string
  is_active: boolean
  role: 'free' | 'pro' | 'max' | 'admin'
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

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('velora_access_token')
}

function authHeaders(): HeadersInit {
  const token = getToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...authHeaders(),
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

export function getAuthToken(): string | null {
  return getToken()
}

export function setAuthToken(token: string): void {
  localStorage.setItem('velora_access_token', token)
}

export function clearAuthToken(): void {
  localStorage.removeItem('velora_access_token')
}

export function subscribeAuthExpired(listener: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined
  const handler = () => listener()
  window.addEventListener('velora-auth-expired', handler)
  return () => window.removeEventListener('velora-auth-expired', handler)
}
