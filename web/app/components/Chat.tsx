'use client'

import { FormEvent, useEffect, useRef, useState } from 'react'
import {
  clearAuthToken,
  createConversation,
  getCurrentUser,
  getCsrfToken,
  getAuthToken,
  getMessages,
  getStreamUrl,
  listConversations,
  login,
  register,
  subscribeAuthExpired,
  logout as logoutApi,
  type Conversation,
  type Message,
  type User,
} from '../../lib/api'
import AgentActivity, { type AgentActivityItem } from './agent/AgentActivity'
import './agent/AgentActivity.css'
import './Chat.css'

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
  const [activityItems, setActivityItems] = useState<AgentActivityItem[]>([])
  const activityStartedAt = useRef(new Map<string, number>())
  const abortRef = useRef<AbortController | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)

  const resetActivity = () => {
    setToolActivity('')
    setActivityItems([])
    activityStartedAt.current.clear()
  }

  const startActivity = (name: string) => {
    const id = `tool-${Date.now()}-${name}`
    activityStartedAt.current.set(id, performance.now())
    setActivityItems((items) => [
      ...items,
      { id, title: name, detail: 'VeloraAi is using this tool to complete your request.', status: 'running' },
    ])
    return id
  }

  const finishLatestActivity = (status: 'completed' | 'error', detail?: string) => {
    setActivityItems((items) => {
      const index = [...items].reverse().findIndex((item) => item.status === 'running')
      if (index < 0) return items
      const actualIndex = items.length - 1 - index
      const item = items[actualIndex]
      const started = activityStartedAt.current.get(item.id)
      const duration = started ? `${((performance.now() - started) / 1000).toFixed(1)}s` : undefined
      return items.map((current, currentIndex) =>
        currentIndex === actualIndex
          ? { ...current, status, duration, detail: detail || current.detail }
          : current,
      )
    })
  }

  useEffect(() => {
    const bootstrap = async () => {
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
      resetActivity()
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
        resetActivity()
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
  }, [messages, pendingConfirmation, activityItems])

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
          setMessages((current) => [...current, {
            id: assistantPlaceholderId,
            conversation_id: userMessage.conversation_id,
            role: 'assistant',
            content: assistantContent,
            created_at: new Date().toISOString(),
          }])
        } else {
          setMessages((current) => current.map((message) =>
            message.id === assistantId ? { ...message, content: assistantContent } : message,
          ))
        }
      }

      if (payload.type === 'tool_start') {
        const name = payload.name || 'Tool'
        setToolActivity(`Using ${name}…`)
        startActivity(name)
      }

      if (payload.type === 'tool_confirmation_required') {
        confirmationRequired = true
        confirmationToolName = payload.name || 'protected tool'
        confirmationToolCallId = payload.tool_call_id || ''
        confirmationToken = payload.confirmation_token || ''
        finishLatestActivity('completed', 'Waiting for your approval before continuing.')
        setToolActivity('')
      }

      if (payload.type === 'tool_end') {
        finishLatestActivity('completed', payload.detail || 'Tool completed successfully.')
        setToolActivity('')
      }

      if (payload.type === 'done' && payload.message_id) {
        assistantId = payload.message_id
        setMessages((current) => current.map((message) =>
          message.id === assistantPlaceholderId ? { ...message, id: assistantId } : message,
        ))
      }

      if (payload.type === 'error') {
        finishLatestActivity('error', payload.detail || 'The agent encountered an error.')
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

    return {
      confirmationRequired,
      toolName: confirmationToolName || undefined,
      toolCallId: confirmationToolCallId || undefined,
      confirmationToken: confirmationToken || undefined,
    }
  }

  const streamConversation = async (conversationId: number, content: string, useRagValue: boolean, confirmationToken?: string, tempMessageId?: number) => {
    const userMessage: Message = {
      id: tempMessageId ?? -Date.now(),
      conversation_id: conversationId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    }

    const controller = new AbortController()
    abortRef.current = controller

    const response = await fetch(getStreamUrl(conversationId), {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}),
        ...(getCsrfToken() ? { 'X-CSRF-Token': getCsrfToken() as string } : {}),
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
    resetActivity()
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
    resetActivity()
    try {
      await streamConversation(confirmation.conversationId, confirmation.content, confirmation.useRag, confirmation.confirmationToken)
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
    resetActivity()
    try {
      setMessages(await getMessages(conversationId))
      setError('Action cancelled.')
    } catch (loadError) {
      console.error(loadError)
      setError('Action cancelled.')
    }
  }

  const handleAuth = async (event: FormEvent) => {
    event.preventDefault()
    setAuthError('')
    setError('')
    setAuthLoading(true)
    try {
      if (authMode === 'login') await login(email.trim(), password)
      else {
        await register(email.trim(), password)
        await login(email.trim(), password)
      }
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

  const logout = () => {
    void logoutApi()
    abortRef.current?.abort()
    clearAuthToken()
    setUser(null)
    setChats([])
    setMessages([])
    setActiveChat(null)
    setPendingConfirmation(null)
    resetActivity()
    setLoading(false)
  }

  const createNewChat = async () => {
    if (!user || loading || pendingConfirmation) return
    try {
      const chat = await createConversation()
      setChats((current) => [chat, ...current])
      setActiveChat(chat.id)
      setMessages([])
      resetActivity()
    } catch (createError) {
      console.error(createError)
      setError(createError instanceof Error ? createError.message : 'Failed to create conversation')
    }
  }

  if (authLoading) return <main className="velora-auth"><div className="velora-auth__card"><strong>VeloraAi</strong><span>Loading…</span></div></main>

  if (!user) {
    return (
      <main className="velora-auth">
        <form onSubmit={handleAuth} className="velora-auth__card">
          <div className="velora-wordmark">VeloraAi</div>
          <h1>{authMode === 'login' ? 'Welcome back' : 'Create your account'}</h1>
          <p>{authMode === 'login' ? 'Continue where your agent left off.' : 'Start building with one intelligent agent.'}</p>
          <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" type="email" autoComplete="email" required />
          <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" autoComplete={authMode === 'login' ? 'current-password' : 'new-password'} required minLength={8} maxLength={128} />
          {authError && <div className="velora-error">{authError}</div>}
          <button type="submit" className="velora-primary">{authMode === 'login' ? 'Sign in' : 'Create account'}</button>
          <button type="button" onClick={() => setAuthMode((mode) => mode === 'login' ? 'register' : 'login')} className="velora-link">{authMode === 'login' ? 'Create an account' : 'Back to sign in'}</button>
        </form>
      </main>
    )
  }

  const activeTitle = chats.find((chat) => chat.id === activeChat)?.title || 'New conversation'

  return (
    <main className="velora-app">
      <aside className="velora-sidebar">
        <div className="velora-sidebar__top">
          <div className="velora-wordmark">VeloraAi</div>
          <span className="velora-agent-badge">ONE AGENT</span>
        </div>
        <button onClick={() => void createNewChat()} disabled={loading || Boolean(pendingConfirmation)} className="velora-new-chat">+ New conversation</button>
        <div className="velora-sidebar__label">Conversations</div>
        <div className="velora-chat-list">
          {chats.map((chat) => (
            <button key={chat.id} onClick={() => setActiveChat(chat.id)} disabled={loading || Boolean(pendingConfirmation)} className={`velora-chat-item ${activeChat === chat.id ? 'is-active' : ''}`}>
              {chat.title}
            </button>
          ))}
        </div>
        <button onClick={logout} className="velora-link">Sign out</button>
      </aside>

      <section className="velora-main">
        <header className="velora-header">
          <div>
            <strong>{activeTitle}</strong>
            <span>VeloraAi Agent</span>
          </div>
          <label className="velora-rag"><input type="checkbox" checked={useRag} onChange={(event) => setUseRag(event.target.checked)} disabled={Boolean(pendingConfirmation)} /> Knowledge context</label>
        </header>

        <div className="velora-content">
          <div className="velora-messages">
            {messages.length === 0 && (
              <div className="velora-empty">
                <div className="velora-orb">V</div>
                <p className="velora-eyebrow">ONE INTELLIGENT AGENT</p>
                <h1>What are we building?</h1>
                <p>Ask VeloraAi to research, code, debug, analyze, or use your connected tools. You never need to choose a mode.</p>
              </div>
            )}
            {messages.map((message) => (
              <div key={`${message.id}-${message.created_at}`} className={`velora-message ${message.role === 'user' ? 'is-user' : 'is-assistant'}`}>
                <div className="velora-message__role">{message.role === 'user' ? 'You' : 'VeloraAi'}</div>
                <div className="velora-message__body">{message.content}</div>
              </div>
            ))}

            {pendingConfirmation && (
              <div className="velora-confirmation">
                <div className="velora-confirmation__icon">!</div>
                <div>
                  <strong>Approval needed</strong>
                  <p>VeloraAi wants to run <strong>{pendingConfirmation.toolName}</strong> on your connected data before continuing.</p>
                  <div className="velora-actions">
                    <button onClick={() => void cancelPendingTool()} disabled={loading} className="velora-secondary">Cancel</button>
                    <button onClick={() => void confirmPendingTool()} disabled={loading} className="velora-primary">Approve action</button>
                  </div>
                </div>
              </div>
            )}
            {loading && !pendingConfirmation && !activityItems.length && <div className="velora-thinking"><span /> VeloraAi is working…</div>}
            {error && <div className="velora-error">{error}</div>}
            <div ref={chatEndRef} />
          </div>

          <aside className={`velora-activity-panel ${activityItems.length ? 'has-activity' : ''}`}>
            {activityItems.length ? <AgentActivity items={activityItems} /> : <div className="velora-context-empty"><span>Agent activity</span><p>Tool work will appear here while VeloraAi is working.</p></div>}
          </aside>
        </div>

        <div className="velora-composer-wrap">
          <div className="velora-composer">
            <input value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void sendMessage() } }} placeholder={pendingConfirmation ? 'Approve the requested action above…' : 'Ask VeloraAi to build, analyze, research, or fix…'} disabled={loading || Boolean(pendingConfirmation)} />
            <div className="velora-composer__bottom">
              <span>＋ Attach</span><span>Tools</span><span>Context {useRag ? 'On' : 'Off'}</span>
              {loading ? <button onClick={() => abortRef.current?.abort()} className="velora-secondary">Stop</button> : <button onClick={() => void sendMessage()} disabled={!input.trim() || Boolean(pendingConfirmation)} className="velora-primary">Send ↑</button>}
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}
