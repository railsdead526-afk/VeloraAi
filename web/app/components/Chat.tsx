'use client'

import { FormEvent, useEffect, useRef, useState } from 'react'

import IntegrationsPanel from './IntegrationsPanel'
import {
  MIN_PASSWORD_LENGTH,
  clearAuthToken,
  createConversation,
  describePasswordPolicy,
  ensureFreshToken,
  getAuthToken,
  getCurrentUser,
  getMessages,
  getStreamUrl,
  listConversations,
  login,
  logout as apiLogout,
  register,
  subscribeAuthExpired,
  validatePassword,
  type Conversation,
  type Message,
  type User,
} from '../../lib/api'

interface PendingConfirmation {
  conversationId: number
  content: string
  useRag: boolean
  toolName: string
  toolCallId?: string
  confirmationToken: string
  tempMessageId: number
}

interface StreamResult {
  confirmationRequired: boolean
  toolName?: string
  toolCallId?: string
  confirmationToken?: string
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
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null)
  const [toolActivity, setToolActivity] = useState('')
  const [showIntegrations, setShowIntegrations] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const bootstrap = async () => {
      if (!getAuthToken()) {
        setAuthLoading(false)
        return
      }
      try {
        setUser(await getCurrentUser())
        const conversations = await listConversations()
        setChats(conversations)
        if (conversations[0]) setActiveChat(conversations[0].id)
      } catch (bootstrapError) {
        console.error(bootstrapError)
        clearAuthToken()
      } finally {
        setAuthLoading(false)
      }
    }
    void bootstrap()
  }, [])

  useEffect(() => {
    const unsubscribe = subscribeAuthExpired(() => {
      abortRef.current?.abort()
      abortRef.current = null
      setUser(null)
      setChats([])
      setMessages([])
      setActiveChat(null)
      setPendingConfirmation(null)
      setToolActivity('')
      setLoading(false)
      setError('Your session has expired. Please sign in again.')
    })
    return unsubscribe
  }, [])

  useEffect(() => {
    if (!activeChat) return
    const load = async () => {
      try {
        setMessages(await getMessages(activeChat))
        setPendingConfirmation(null)
        setToolActivity('')
        setError('')
      } catch (loadError) {
        console.error(loadError)
        setError(loadError instanceof Error ? loadError.message : 'Failed to load messages')
      }
    }
    void load()
  }, [activeChat])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pendingConfirmation])

  const parseStream = async (response: Response, userMessage: Message): Promise<StreamResult> => {
    if (!response.body) throw new Error('Streaming response is unavailable')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    const assistantPlaceholderId = -(Date.now() + 1)
    let assistantId = assistantPlaceholderId
    let assistantContent = ''
    let assistantStarted = false
    let buffer = ''
    let confirmationRequired = false
    let confirmationToolName = ''
    let confirmationToolCallId = ''
    let confirmationToken = ''

    setMessages((current) => [...current.filter((message) => message.id !== userMessage.id), userMessage])

    const processLine = (line: string) => {
      if (!line.startsWith('data: ')) return
      const payload = JSON.parse(line.slice(6)) as {
        type?: 'token' | 'tool_start' | 'tool_confirmation_required' | 'tool_end' | 'done' | 'error'
        content?: string
        detail?: string
        message_id?: number
        name?: string
        tool_call_id?: string
        confirmation_token?: string
      }

      if (payload.type === 'token' && payload.content) {
        assistantContent += payload.content
        if (!assistantStarted) {
          assistantStarted = true
          setMessages((current) => [
            ...current,
            {
              id: assistantPlaceholderId,
              conversation_id: userMessage.conversation_id,
              role: 'assistant',
              content: assistantContent,
              created_at: new Date().toISOString(),
            },
          ])
        } else {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId ? { ...message, content: assistantContent } : message,
            ),
          )
        }
      }

      if (payload.type === 'tool_start') {
        setToolActivity(payload.name ? `Using ${payload.name}…` : 'Using a tool…')
      }

      if (payload.type === 'tool_confirmation_required') {
        confirmationRequired = true
        confirmationToolName = payload.name || 'protected tool'
        confirmationToolCallId = payload.tool_call_id || ''
        confirmationToken = payload.confirmation_token || ''
        setToolActivity('')
      }

      if (payload.type === 'tool_end') setToolActivity('')

      if (payload.type === 'done' && payload.message_id) {
        assistantId = payload.message_id
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantPlaceholderId ? { ...message, id: assistantId } : message,
          ),
        )
      }

      if (payload.type === 'error') throw new Error(payload.detail || 'AI request failed')
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

    return {
      confirmationRequired,
      toolName: confirmationToolName || undefined,
      toolCallId: confirmationToolCallId || undefined,
      confirmationToken: confirmationToken || undefined,
    }
  }

  const streamConversation = async (
    conversationId: number,
    content: string,
    useRagValue: boolean,
    confirmationToken?: string,
    tempMessageId?: number,
  ) => {
    const userMessage: Message = {
      id: tempMessageId ?? -Date.now(),
      conversation_id: conversationId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    }

    const controller = new AbortController()
    abortRef.current = controller

    // Access tokens live 15 minutes, so refresh before opening a stream that
    // may run for a while. apiFetch cannot retry a half-consumed SSE body.
    const streamToken = (await ensureFreshToken()) ?? getAuthToken()

    const response = await fetch(getStreamUrl(conversationId), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${streamToken}`,
      },
      body: JSON.stringify({
        content,
        use_rag: useRagValue,
        confirm_tools: false,
        ...(confirmationToken ? { tool_confirmation_token: confirmationToken } : {}),
      }),
      signal: controller.signal,
    })

    if (!response.ok) {
      let message = `Request failed with status ${response.status}`
      try {
        const data = await response.json()
        if (typeof data?.detail === 'string') message = data.detail
      } catch {
        // Keep HTTP status text.
      }
      throw new Error(message)
    }

    const result = await parseStream(response, userMessage)

    if (result.confirmationRequired) {
      if (!result.confirmationToken) throw new Error('Server did not provide a confirmation token')
      setPendingConfirmation({
        conversationId,
        content,
        useRag: useRagValue,
        toolName: result.toolName || 'protected tool',
        toolCallId: result.toolCallId,
        confirmationToken: result.confirmationToken,
        tempMessageId: userMessage.id,
      })
      return
    }

    setMessages(await getMessages(conversationId))
    setPendingConfirmation(null)
  }

  const sendMessage = async () => {
    const content = input.trim()
    if (!content || !user || loading || pendingConfirmation) return

    setError('')
    setInput('')
    setLoading(true)
    setToolActivity('')

    try {
      let conversationId = activeChat
      if (!conversationId) {
        const conversation = await createConversation(content.slice(0, 80))
        setChats((current) => [conversation, ...current])
        conversationId = conversation.id
        setActiveChat(conversation.id)
      }
      await streamConversation(conversationId, content, useRag)
    } catch (sendError) {
      console.error(sendError)
      setError(sendError instanceof Error ? sendError.message : 'Failed to send message')
    } finally {
      abortRef.current = null
      setToolActivity('')
      setLoading(false)
    }
  }

  const confirmPendingTool = async () => {
    if (!pendingConfirmation || loading) return
    const confirmation = pendingConfirmation
    setError('')
    setPendingConfirmation(null)
    setMessages((current) => current.filter((message) => message.id !== confirmation.tempMessageId))
    setLoading(true)
    setToolActivity(`Using ${confirmation.toolName}…`)

    try {
      await streamConversation(
        confirmation.conversationId,
        confirmation.content,
        confirmation.useRag,
        confirmation.confirmationToken,
      )
    } catch (confirmError) {
      console.error(confirmError)
      setError(confirmError instanceof Error ? confirmError.message : 'Tool confirmation failed')
      setPendingConfirmation(confirmation)
    } finally {
      abortRef.current = null
      setToolActivity('')
      setLoading(false)
    }
  }

  const cancelPendingTool = async () => {
    if (!pendingConfirmation || loading) return
    const conversationId = pendingConfirmation.conversationId
    const tempMessageId = pendingConfirmation.tempMessageId
    setPendingConfirmation(null)
    setMessages((current) => current.filter((message) => message.id !== tempMessageId))
    setToolActivity('')
    try {
      setMessages(await getMessages(conversationId))
      setError('Tool execution cancelled.')
    } catch (loadError) {
      console.error(loadError)
      setError('Tool execution cancelled.')
    }
  }

  const handleAuth = async (event: FormEvent) => {
    event.preventDefault()
    setAuthError('')
    setError('')
    setAuthLoading(true)
    try {
      if (authMode === 'register') {
        const policyError = validatePassword(password)
        if (policyError) throw new Error(policyError)
        await register(email.trim(), password)
      }
      // login() stores the access and refresh tokens.
      await login(email.trim(), password)
      setUser(await getCurrentUser())
      const conversations = await listConversations()
      setChats(conversations)
      setActiveChat(conversations[0]?.id ?? null)
    } catch (authErrorValue) {
      setAuthError(authErrorValue instanceof Error ? authErrorValue.message : 'Authentication failed')
    } finally {
      setAuthLoading(false)
    }
  }

  const handleLogout = async () => {
    abortRef.current?.abort()
    // Revokes the access token's jti and the refresh session server side.
    await apiLogout()
    setUser(null)
    setChats([])
    setMessages([])
    setActiveChat(null)
    setPendingConfirmation(null)
    setToolActivity('')
    setLoading(false)
  }

  const createNewChat = async () => {
    if (!user || loading || pendingConfirmation) return
    try {
      const chat = await createConversation()
      setChats((current) => [chat, ...current])
      setActiveChat(chat.id)
      setMessages([])
    } catch (createError) {
      console.error(createError)
      setError(createError instanceof Error ? createError.message : 'Failed to create conversation')
    }
  }

  if (authLoading) return <main style={styles.center}><div style={styles.card}><strong>VELORAAI</strong><span>Loading your workspace...</span></div></main>

  if (!user) {
    return (
      <main style={styles.center}>
        <form onSubmit={handleAuth} style={styles.card}>
          <div style={styles.logo}>VELORAAI</div>
          <h1 style={styles.title}>{authMode === 'login' ? 'Welcome back' : 'Create your workspace'}</h1>
          <p style={styles.muted}>{authMode === 'login' ? 'Sign in to continue.' : 'Create an account to start using VeloraAi.'}</p>
          <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" type="email" autoComplete="email" style={styles.input} required />
          <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" autoComplete={authMode === 'login' ? 'current-password' : 'new-password'} style={styles.input} required minLength={authMode === 'register' ? MIN_PASSWORD_LENGTH : 1} />
          {authMode === 'register' && <p style={styles.muted}>{describePasswordPolicy()}</p>}
          {authError && <div style={styles.error}>{authError}</div>}
          <button type="submit" style={styles.primary}>{authMode === 'login' ? 'Sign in' : 'Create account'}</button>
          <button type="button" onClick={() => setAuthMode((mode) => (mode === 'login' ? 'register' : 'login'))} style={styles.link}>
            {authMode === 'login' ? 'Create an account' : 'Back to sign in'}
          </button>
        </form>
      </main>
    )
  }

  return (
    <main style={styles.app}>
      {showIntegrations && <IntegrationsPanel onClose={() => setShowIntegrations(false)} />}
      <aside style={styles.sidebar}>
        <div>
          <div style={styles.logo}>VELORAAI</div>
          <div style={styles.role}>{user.role.toUpperCase()}</div>
        </div>
        <button onClick={() => void createNewChat()} disabled={loading || Boolean(pendingConfirmation)} style={styles.secondary}>+ New conversation</button>
        <div style={styles.chatList}>
          {chats.map((chat) => (
            <button key={chat.id} onClick={() => setActiveChat(chat.id)} disabled={loading || Boolean(pendingConfirmation)} style={{ ...styles.chatItem, ...(activeChat === chat.id ? styles.chatItemActive : {}) }}>
              {chat.title}
            </button>
          ))}
        </div>
        <button onClick={() => setShowIntegrations(true)} style={styles.link}>Integrations</button>
        <button onClick={() => void handleLogout()} style={styles.link}>Sign out</button>
      </aside>

      <section style={styles.main}>
        <header style={styles.header}>
          <strong>{chats.find((chat) => chat.id === activeChat)?.title || 'New conversation'}</strong>
          <label style={styles.rag}><input type="checkbox" checked={useRag} onChange={(event) => setUseRag(event.target.checked)} disabled={Boolean(pendingConfirmation)} /> RAG</label>
        </header>

        <div style={styles.messages}>
          {messages.length === 0 && <div style={styles.empty}><div style={styles.logo}>VELORAAI</div><h2>Build, search, and think.</h2><p style={styles.muted}>Your workspace is connected to the VeloraAi agent.</p></div>}
          {messages.map((message) => (
            <div key={`${message.id}-${message.created_at}`} style={{ ...styles.row, justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div style={{ ...styles.bubble, ...(message.role === 'user' ? styles.userBubble : styles.assistantBubble) }}>
                <div style={styles.messageRole}>{message.role === 'user' ? 'You' : 'VeloraAi'}</div>
                <div>{message.content}</div>
              </div>
            </div>
          ))}

          {toolActivity && <div style={styles.typing}>{toolActivity}</div>}
          {pendingConfirmation && (
            <div style={styles.confirmation}>
              <strong>Approval required</strong>
              <p style={styles.muted}>VeloraAi wants to run <strong>{pendingConfirmation.toolName}</strong> for this request.</p>
              <div style={styles.actions}>
                <button onClick={() => void cancelPendingTool()} disabled={loading} style={styles.secondary}>Cancel</button>
                <button onClick={() => void confirmPendingTool()} disabled={loading} style={styles.primary}>Confirm</button>
              </div>
            </div>
          )}
          {loading && !toolActivity && !pendingConfirmation && <div style={styles.typing}>VeloraAi is thinking…</div>}
          {error && <div style={styles.error}>{error}</div>}
          <div ref={chatEndRef} />
        </div>

        <div style={styles.composerWrap}>
          <div style={styles.composer}>
            <input value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); void sendMessage() } }} placeholder={pendingConfirmation ? 'Approve the requested tool above…' : 'Message VeloraAi…'} style={styles.composerInput} disabled={loading || Boolean(pendingConfirmation)} />
            {loading ? <button onClick={() => abortRef.current?.abort()} style={styles.secondary}>Stop</button> : <button onClick={() => void sendMessage()} disabled={!input.trim() || Boolean(pendingConfirmation)} style={styles.primary}>Send</button>}
          </div>
        </div>
      </section>
    </main>
  )
}

const styles: Record<string, React.CSSProperties> = {
  app: { display: 'flex', minHeight: '100vh', background: '#080808', color: '#f5f5f5', fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif' },
  sidebar: { width: 260, minWidth: 260, minHeight: '100vh', background: '#101010', borderRight: '1px solid #242424', padding: 20, display: 'flex', flexDirection: 'column', gap: 12 },
  main: { flex: 1, minWidth: 0, minHeight: '100vh', display: 'flex', flexDirection: 'column' },
  header: { height: 64, borderBottom: '1px solid #242424', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px' },
  messages: { flex: 1, overflowY: 'auto', padding: '28px 20px 120px' },
  row: { display: 'flex', marginBottom: 16 },
  bubble: { maxWidth: 'min(820px, 88%)', padding: '14px 16px', borderRadius: 16, lineHeight: 1.6 },
  userBubble: { background: '#d97706', color: '#111' },
  assistantBubble: { background: '#151515', border: '1px solid #282828' },
  messageRole: { fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', opacity: 0.65, marginBottom: 6 },
  chatList: { display: 'flex', flexDirection: 'column', gap: 6, overflowY: 'auto', flex: 1 },
  chatItem: { border: 0, background: 'transparent', color: '#bdbdbd', padding: '10px 12px', borderRadius: 9, textAlign: 'left', cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  chatItemActive: { background: '#1e1e1e', color: '#fff' },
  logo: { letterSpacing: '0.16em', fontWeight: 800, fontSize: 13 },
  role: { marginTop: 6, color: '#929292', fontSize: 10, letterSpacing: '0.14em' },
  rag: { color: '#aaa', fontSize: 12, display: 'flex', gap: 6, alignItems: 'center' },
  composerWrap: { position: 'fixed', left: 260, right: 0, bottom: 0, padding: 16, background: 'linear-gradient(180deg, rgba(8,8,8,0), #080808 38%)' },
  composer: { maxWidth: 900, margin: '0 auto', display: 'flex', gap: 10, padding: 8, border: '1px solid #2c2c2c', background: '#111', borderRadius: 16 },
  composerInput: { flex: 1, minWidth: 0, border: 0, outline: 0, background: 'transparent', color: '#fff', padding: '12px 14px', fontSize: 15 },
  secondary: { border: '1px solid #3a3a3a', background: '#171717', color: '#fff', borderRadius: 10, padding: '10px 14px', cursor: 'pointer' },
  primary: { border: 0, background: '#d97706', color: '#111', borderRadius: 10, padding: '10px 14px', fontWeight: 800, cursor: 'pointer' },
  link: { border: 0, background: 'transparent', color: '#9a9a9a', cursor: 'pointer', padding: 8, textAlign: 'left' },
  typing: { color: '#8d8d8d', fontSize: 13, marginBottom: 12 },
  confirmation: { maxWidth: 620, margin: '8px auto 16px', border: '1px solid #5a4724', background: '#17130b', borderRadius: 14, padding: 16 },
  actions: { display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 },
  error: { color: '#ffb4a9', background: '#281613', border: '1px solid #4a241e', borderRadius: 10, padding: '10px 12px', fontSize: 12, marginBottom: 12 },
  center: { minHeight: '100vh', background: '#080808', color: '#fff', display: 'grid', placeItems: 'center', padding: 20 },
  card: { width: 'min(420px, 100%)', padding: 28, border: '1px solid #252525', borderRadius: 20, background: '#111', display: 'flex', flexDirection: 'column', gap: 12 },
  title: { margin: '6px 0 0', fontSize: 28 },
  input: { width: '100%', boxSizing: 'border-box', border: '1px solid #303030', borderRadius: 10, background: '#0c0c0c', color: '#fff', padding: '12px 14px', outline: 0 },
  muted: { color: '#8c8c8c', fontSize: 13, lineHeight: 1.5, margin: 0 },
  empty: { maxWidth: 720, margin: '18vh auto 0', textAlign: 'center', padding: 20 },
}
