'use client'

import { FormEvent, useEffect, useRef, useState } from 'react'
import {
  clearAuthToken,
  createConversation,
  getAuthToken,
  getCurrentUser,
  getMessages,
  getStreamUrl,
  listConversations,
  login,
  register,
  setAuthToken,
  type Conversation,
  type Message,
  type User,
} from '../../lib/api'

function toClientMessage(message: Message): Message {
  return message
}

export default function Chat() {
  const [user, setUser] = useState<User | null>(null)
  const [chats, setChats] = useState<Conversation[]>([])
  const [activeChat, setActiveChat] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [authLoading, setAuthLoading] = useState(true)
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [authError, setAuthError] = useState('')
  const [error, setError] = useState('')
  const [useRag, setUseRag] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  useEffect(() => {
    const bootstrap = async () => {
      if (!getAuthToken()) {
        setAuthLoading(false)
        return
      }

      try {
        const currentUser = await getCurrentUser()
        const conversations = await listConversations()
        setUser(currentUser)
        setChats(conversations)
        if (conversations.length > 0) setActiveChat(conversations[0].id)
      } catch (bootstrapError) {
        console.error(bootstrapError)
        clearAuthToken()
      } finally {
        setAuthLoading(false)
      }
    }

    bootstrap()
  }, [])

  useEffect(() => {
    if (!activeChat) {
      setMessages([])
      return
    }

    const loadMessages = async () => {
      try {
        const history = await getMessages(activeChat)
        setMessages(history.map(toClientMessage))
        setError('')
      } catch (loadError) {
        console.error(loadError)
        setError(loadError instanceof Error ? loadError.message : 'Failed to load messages')
      }
    }

    void loadMessages()

    if (isMobile) setSidebarOpen(false)
  }, [activeChat, isMobile])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleAuth = async (event: FormEvent) => {
    event.preventDefault()
    setAuthError('')
    setAuthLoading(true)

    try {
      if (authMode === 'login') {
        const token = await login(email.trim(), password)
        setAuthToken(token.access_token)
      } else {
        await register(email.trim(), password)
        const token = await login(email.trim(), password)
        setAuthToken(token.access_token)
      }

      const currentUser = await getCurrentUser()
      const conversations = await listConversations()
      setUser(currentUser)
      setChats(conversations)
      setActiveChat(conversations[0]?.id ?? null)
      setMessages([])
    } catch (authErrorValue) {
      setAuthError(authErrorValue instanceof Error ? authErrorValue.message : 'Authentication failed')
    } finally {
      setAuthLoading(false)
    }
  }

  const logout = () => {
    abortRef.current?.abort()
    abortRef.current = null
    clearAuthToken()
    setUser(null)
    setChats([])
    setMessages([])
    setActiveChat(null)
    setLoading(false)
  }

  const createNewChat = async () => {
    if (!user || loading) return

    try {
      const chat = await createConversation()
      setChats((current) => [chat, ...current])
      setActiveChat(chat.id)
      setMessages([])
      setError('')
      if (isMobile) setSidebarOpen(false)
    } catch (createError) {
      console.error(createError)
      setError(createError instanceof Error ? createError.message : 'Failed to create conversation')
    }
  }

  const selectChat = (chatId: number) => {
    setActiveChat(chatId)
    if (isMobile) setSidebarOpen(false)
  }

  const parseStream = async (response: Response, conversationId: number, userMessage: Message) => {
    if (!response.body) throw new Error('Streaming response is unavailable')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let assistantId = -Date.now()
    let assistantContent = ''

    setMessages((current) => [
      ...current.filter((message) => message.id !== userMessage.id),
      userMessage,
      {
        id: assistantId,
        conversation_id: conversationId,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
      },
    ])

    const processLine = (line: string) => {
      if (!line.startsWith('data: ')) return

      const payload = JSON.parse(line.slice(6)) as {
        type?: 'token' | 'done' | 'error'
        content?: string
        detail?: string
        message_id?: number
      }

      if (payload.type === 'token' && payload.content) {
        assistantContent += payload.content
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId ? { ...message, content: assistantContent } : message,
          ),
        )
      }

      if (payload.type === 'done' && payload.message_id) {
        assistantId = payload.message_id
        setMessages((current) =>
          current.map((message) =>
            message.id === -Date.now() ? { ...message, id: assistantId } : message,
          ),
        )
      }

      if (payload.type === 'error') {
        throw new Error(payload.detail || 'AI request failed')
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const normalized = line.trim()
        if (normalized) processLine(normalized)
      }
    }

    if (buffer.trim()) processLine(buffer.trim())
  }

  const sendMessage = async () => {
    const content = input.trim()
    if (!content || loading || !user) return

    setError('')
    setLoading(true)
    setInput('')

    try {
      let conversationId = activeChat

      if (!conversationId) {
        const conversation = await createConversation(content.slice(0, 80))
        setChats((current) => [conversation, ...current])
        conversationId = conversation.id
        setActiveChat(conversation.id)
      }

      const userMessage: Message = {
        id: -Date.now(),
        conversation_id: conversationId,
        role: 'user',
        content,
        created_at: new Date().toISOString(),
      }

      const controller = new AbortController()
      abortRef.current = controller

      const response = await fetch(getStreamUrl(conversationId), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getAuthToken()}`,
        },
        body: JSON.stringify({
          content,
          use_rag: useRag,
          confirm_tools: false,
        }),
        signal: controller.signal,
      })

      if (!response.ok) {
        let message = `Request failed with status ${response.status}`
        try {
          const data = await response.json()
          if (typeof data?.detail === 'string') message = data.detail
        } catch {
          // Keep status message.
        }
        throw new Error(message)
      }

      await parseStream(response, conversationId, userMessage)
      const freshMessages = await getMessages(conversationId)
      setMessages(freshMessages)
    } catch (sendError) {
      if (sendError instanceof DOMException && sendError.name === 'AbortError') {
        setError('Generation stopped')
      } else {
        console.error(sendError)
        setError(sendError instanceof Error ? sendError.message : 'Failed to send message')
      }
    } finally {
      abortRef.current = null
      setLoading(false)
    }
  }

  const stopGeneration = () => {
    abortRef.current?.abort()
  }

  if (authLoading) {
    return (
      <main style={styles.centerScreen}>
        <div style={styles.authCard}>
          <div style={styles.brand}>VELORAAI</div>
          <p style={styles.muted}>Loading your workspace...</p>
        </div>
      </main>
    )
  }

  if (!user) {
    return (
      <main style={styles.centerScreen}>
        <form onSubmit={handleAuth} style={styles.authCard}>
          <div style={styles.brand}>VELORAAI</div>
          <h1 style={styles.authTitle}>{authMode === 'login' ? 'Welcome back' : 'Create your workspace'}</h1>
          <p style={styles.muted}>
            {authMode === 'login' ? 'Sign in to continue to your AI workspace.' : 'Create an account to start using VeloraAi.'}
          </p>

          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="Email"
            type="email"
            autoComplete="email"
            style={styles.authInput}
            required
          />
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Password"
            type="password"
            autoComplete={authMode === 'login' ? 'current-password' : 'new-password'}
            style={styles.authInput}
            required
            minLength={8}
          />

          {authError && <div style={styles.error}>{authError}</div>}

          <button type="submit" disabled={authLoading} style={styles.primaryButton}>
            {authMode === 'login' ? 'Sign in' : 'Create account'}
          </button>

          <button
            type="button"
            onClick={() => {
              setAuthMode((mode) => (mode === 'login' ? 'register' : 'login'))
              setAuthError('')
            }}
            style={styles.linkButton}
          >
            {authMode === 'login' ? 'Create an account' : 'Back to sign in'}
          </button>
        </form>
      </main>
    )
  }

  return (
    <main style={styles.app}>
      {sidebarOpen && isMobile && <div onClick={() => setSidebarOpen(false)} style={styles.overlay} />}

      <aside
        style={{
          ...styles.sidebar,
          transform: isMobile && !sidebarOpen ? 'translateX(-100%)' : 'translateX(0)',
          position: isMobile ? 'fixed' : 'relative',
        }}
      >
        <div style={styles.sidebarTop}>
          <div>
            <div style={styles.brand}>VELORAAI</div>
            <div style={styles.role}>{user.role.toUpperCase()}</div>
          </div>
          {isMobile && (
            <button onClick={() => setSidebarOpen(false)} style={styles.iconButton} aria-label="Close sidebar">
              ×
            </button>
          )}
        </div>

        <button onClick={createNewChat} disabled={loading} style={styles.newChatButton}>
          + New conversation
        </button>

        <div style={styles.chatList}>
          {chats.map((chat) => (
            <button
              key={chat.id}
              onClick={() => selectChat(chat.id)}
              style={{
                ...styles.chatItem,
                ...(chat.id === activeChat ? styles.chatItemActive : {}),
              }}
            >
              {chat.title}
            </button>
          ))}
        </div>

        <button onClick={logout} style={styles.logoutButton}>
          Sign out
        </button>
      </aside>

      <section style={styles.mainPanel}>
        <header style={styles.header}>
          <button
            onClick={() => setSidebarOpen(true)}
            style={{ ...styles.iconButton, display: isMobile ? 'inline-flex' : 'none' }}
            aria-label="Open sidebar"
          >
            ☰
          </button>
          <div style={styles.headerTitle}>{chats.find((chat) => chat.id === activeChat)?.title || 'New conversation'}</div>
          <label style={styles.ragToggle}>
            <input type="checkbox" checked={useRag} onChange={(event) => setUseRag(event.target.checked)} />
            RAG
          </label>
        </header>

        <div style={styles.messageArea}>
          {messages.length === 0 && (
            <div style={styles.emptyState}>
              <div style={styles.emptyEyebrow}>AI WORKSPACE</div>
              <h1 style={styles.emptyTitle}>Build, search, and think with VeloraAi.</h1>
              <p style={styles.muted}>Your conversations are now backed by the VeloraAi API.</p>
            </div>
          )}

          {messages.map((message) => (
            <article
              key={`${message.id}-${message.created_at}`}
              style={{
                ...styles.messageRow,
                justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start',
              }}
            >
              <div
                style={{
                  ...styles.messageBubble,
                  ...(message.role === 'user' ? styles.userBubble : styles.assistantBubble),
                }}
              >
                <div style={styles.messageRole}>{message.role === 'user' ? 'You' : 'VeloraAi'}</div>
                <div style={styles.messageContent}>{message.content}</div>
              </div>
            </article>
          ))}

          {loading && <div style={styles.typing}>VeloraAi is thinking…</div>}
          {error && <div style={styles.error}>{error}</div>}
          <div ref={chatEndRef} />
        </div>

        <div style={styles.composerWrap}>
          <div style={styles.composer}>
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void sendMessage()
                }
              }}
              placeholder="Message VeloraAi…"
              style={styles.composerInput}
              disabled={loading}
            />
            {loading ? (
              <button onClick={stopGeneration} style={styles.stopButton}>
                Stop
              </button>
            ) : (
              <button onClick={() => void sendMessage()} style={styles.sendButton} disabled={!input.trim()}>
                Send
              </button>
            )}
          </div>
        </div>
      </section>
    </main>
  )
}

const styles: Record<string, React.CSSProperties> = {
  app: {
    display: 'flex',
    minHeight: '100vh',
    background: '#080808',
    color: '#f5f5f5',
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
  },
  sidebar: {
    width: 280,
    minWidth: 280,
    minHeight: '100vh',
    background: '#101010',
    borderRight: '1px solid #242424',
    padding: 20,
    display: 'flex',
    flexDirection: 'column',
    gap: 14,
    zIndex: 30,
    transition: 'transform 180ms ease',
  },
  sidebarTop: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  brand: {
    letterSpacing: '0.16em',
    fontWeight: 800,
    fontSize: 13,
  },
  role: {
    marginTop: 6,
    color: '#9a9a9a',
    fontSize: 10,
    letterSpacing: '0.14em',
  },
  newChatButton: {
    border: '1px solid #3a3a3a',
    background: '#171717',
    color: '#fff',
    borderRadius: 10,
    padding: '12px 14px',
    textAlign: 'left',
    cursor: 'pointer',
  },
  chatList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    overflowY: 'auto',
    flex: 1,
  },
  chatItem: {
    border: 0,
    background: 'transparent',
    color: '#bdbdbd',
    padding: '11px 12px',
    borderRadius: 9,
    textAlign: 'left',
    cursor: 'pointer',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  chatItemActive: {
    background: '#1e1e1e',
    color: '#fff',
  },
  logoutButton: {
    border: 0,
    background: 'transparent',
    color: '#8b8b8b',
    padding: '10px 4px',
    textAlign: 'left',
    cursor: 'pointer',
  },
  mainPanel: {
    flex: 1,
    minWidth: 0,
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: '#0b0b0b',
  },
  header: {
    height: 64,
    borderBottom: '1px solid #242424',
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '0 20px',
    background: '#0b0b0b',
  },
  headerTitle: {
    flex: 1,
    fontSize: 14,
    fontWeight: 600,
  },
  ragToggle: {
    color: '#aaa',
    fontSize: 12,
    display: 'flex',
    gap: 6,
    alignItems: 'center',
  },
  messageArea: {
    flex: 1,
    overflowY: 'auto',
    padding: '28px 20px 140px',
  },
  messageRow: {
    display: 'flex',
    marginBottom: 18,
  },
  messageBubble: {
    maxWidth: 'min(820px, 88%)',
    padding: '14px 16px',
    borderRadius: 16,
    lineHeight: 1.6,
  },
  userBubble: {
    background: '#d97706',
    color: '#111',
  },
  assistantBubble: {
    background: '#151515',
    border: '1px solid #282828',
    color: '#ededed',
  },
  messageRole: {
    fontSize: 10,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    opacity: 0.65,
    marginBottom: 6,
  },
  messageContent: {
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  typing: {
    color: '#8d8d8d',
    fontSize: 13,
    marginBottom: 12,
  },
  composerWrap: {
    position: 'fixed',
    left: 280,
    right: 0,
    bottom: 0,
    padding: 16,
    background: 'linear-gradient(180deg, rgba(11,11,11,0), #0b0b0b 32%)',
  },
  composer: {
    maxWidth: 900,
    margin: '0 auto',
    display: 'flex',
    gap: 10,
    padding: 8,
    border: '1px solid #2c2c2c',
    background: '#111',
    borderRadius: 16,
  },
  composerInput: {
    flex: 1,
    minWidth: 0,
    border: 0,
    outline: 0,
    background: 'transparent',
    color: '#fff',
    padding: '12px 14px',
    fontSize: 15,
  },
  sendButton: {
    border: 0,
    background: '#d97706',
    color: '#111',
    borderRadius: 11,
    padding: '0 18px',
    fontWeight: 700,
    cursor: 'pointer',
  },
  stopButton: {
    border: '1px solid #3a3a3a',
    background: '#1a1a1a',
    color: '#fff',
    borderRadius: 11,
    padding: '0 18px',
    cursor: 'pointer',
  },
  iconButton: {
    border: 0,
    background: 'transparent',
    color: '#fff',
    fontSize: 24,
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 2,
  },
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.65)',
    zIndex: 20,
  },
  centerScreen: {
    minHeight: '100vh',
    background: '#080808',
    color: '#fff',
    display: 'grid',
    placeItems: 'center',
    padding: 20,
  },
  authCard: {
    width: 'min(420px, 100%)',
    padding: 28,
    border: '1px solid #252525',
    borderRadius: 20,
    background: '#111',
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
  },
  authTitle: {
    margin: '6px 0 0',
    fontSize: 28,
  },
  authInput: {
    width: '100%',
    boxSizing: 'border-box',
    border: '1px solid #303030',
    borderRadius: 10,
    background: '#0c0c0c',
    color: '#fff',
    padding: '12px 14px',
    outline: 0,
  },
  primaryButton: {
    border: 0,
    borderRadius: 10,
    padding: '12px 14px',
    background: '#d97706',
    color: '#111',
    fontWeight: 800,
    cursor: 'pointer',
    marginTop: 4,
  },
  linkButton: {
    border: 0,
    background: 'transparent',
    color: '#c4c4c4',
    cursor: 'pointer',
    padding: 8,
  },
  muted: {
    color: '#8c8c8c',
    fontSize: 13,
    lineHeight: 1.5,
    margin: 0,
  },
  error: {
    color: '#ffb4a9',
    background: '#281613',
    border: '1px solid #4a241e',
    borderRadius: 10,
    padding: '10px 12px',
    fontSize: 12,
  },
  emptyState: {
    maxWidth: 720,
    margin: '18vh auto 0',
    textAlign: 'center',
    padding: 20,
  },
  emptyEyebrow: {
    color: '#d97706',
    fontWeight: 800,
    letterSpacing: '0.18em',
    fontSize: 10,
    marginBottom: 14,
  },
  emptyTitle: {
    fontSize: 'clamp(30px, 6vw, 54px)',
    lineHeight: 1.05,
    margin: '0 0 14px',
  },
}
