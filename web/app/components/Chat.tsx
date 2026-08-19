"use client"

import { useEffect, useRef, useState } from "react"

interface Message {
  id: string
  role: string
  content: string
  createdAt: string
}

interface Chat {
  id: string
  title: string
}

export default function Chat() {
  const [chats, setChats] = useState<Chat[]>([])
  const [activeChat, setActiveChat] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768)

    checkMobile()
    window.addEventListener("resize", checkMobile)

    return () => window.removeEventListener("resize", checkMobile)
  }, [])

  useEffect(() => {
    fetch("/api/chat")
      .then((res) => res.json())
      .then(setChats)
      .catch(console.error)
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    if (!activeChat) return

    fetch(`/api/chat/${activeChat}/messages`)
      .then((res) => res.json())
      .then(setMessages)
      .catch(console.error)
  }, [activeChat])

  const selectChat = (chatId: string) => {
    setActiveChat(chatId)

    if (isMobile) {
      setSidebarOpen(false)
    }
  }

  const createNewChat = async () => {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: input.slice(0, 30) || "New Chat",
      }),
    })

    const chat = await res.json()

    setChats((prev) => [chat, ...prev])
    setActiveChat(chat.id)
    setMessages([])

    if (isMobile) {
      setSidebarOpen(false)
    }
  }

  const sendMessage = async () => {
    if (!input.trim() || loading) return

    const message = input.trim()
    let chatId = activeChat

    if (!chatId) {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: message.slice(0, 30),
        }),
      })

      const chat = await res.json()

      setChats((prev) => [chat, ...prev])
      chatId = chat.id
      setActiveChat(chat.id)
    }

    setLoading(true)
    setInput("")

    setMessages((prev) => [
      ...prev,
      {
        id: Date.now().toString(),
        role: "user",
        content: message,
        createdAt: new Date().toISOString(),
      },
    ])

    try {
      await fetch(`/api/chat/${chatId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role: "user",
          content: message,
        }),
      })

      setTimeout(async () => {
        await fetch(`/api/chat/${chatId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            role: "assistant",
            content: `This is a simulated response to: "${message}"`,
          }),
        })

        const res = await fetch(`/api/chat/${chatId}/messages`)
        const updated = await res.json()

        setMessages(updated)
        setLoading(false)
      }, 1000)
    } catch (error) {
      console.error(error)
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        fontFamily: "sans-serif",
        position: "relative",
      }}
    >
      {sidebarOpen && isMobile && (
        <div
          onClick={() => setSidebarOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.5)",
            zIndex: 10,
          }}
        />
      )}

      <div
        style={{
          width: 280,
          background: "#1a1a1a",
          color: "#fff",
          padding: 16,
          display: "flex",
          flexDirection: "column",
          position: isMobile ? "fixed" : "relative",
          left: sidebarOpen || !isMobile ? 0 : "-280px",
          top: 0,
          bottom: 0,
          transition: "left 0.3s ease",
          zIndex: 20,
          overflowY: "auto",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 20 }}>Velora AI</h2>

          {isMobile && (
            <button
              onClick={() => setSidebarOpen(false)}
              style={{
                background: "transparent",
                border: "none",
                color: "#fff",
                fontSize: 24,
                cursor: "pointer",
                padding: 0,
              }}
            >
              ✕
            </button>
          )}
        </div>

        <button
          onClick={createNewChat}
          style={{
            padding: "12px",
            background: "#0070f3",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            cursor: "pointer",
            marginBottom: 16,
            fontSize: 14,
            fontWeight: 500,
          }}
        >
          + New Chat
        </button>

        <div style={{ flex: 1, overflowY: "auto" }}>
          {chats.map((chat) => (
            <div
              key={chat.id}
              onClick={() => selectChat(chat.id)}
              style={{
                padding: "10px 12px",
                cursor: "pointer",
                borderRadius: 6,
                background:
                  chat.id === activeChat ? "#333" : "transparent",
                marginBottom: 4,
                fontSize: 14,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {chat.title}
            </div>
          ))}
        </div>
      </div>

      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          background: "#fff",
          width: "100%",
        }}
      >
        {isMobile && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              padding: 16,
              borderBottom: "1px solid #e0e0e0",
              background: "#fff",
            }}
          >
            <button
              onClick={() => setSidebarOpen(true)}
              style={{
                background: "transparent",
                border: "none",
                fontSize: 24,
                cursor: "pointer",
                padding: 0,
                marginRight: 12,
              }}
            >
              ☰
            </button>

            <h1
              style={{
                margin: 0,
                fontSize: 18,
                fontWeight: 600,
              }}
            >
              {activeChat
                ? chats.find((c) => c.id === activeChat)?.title
                : "Velora AI"}
            </h1>
          </div>
        )}

        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: 16,
            paddingBottom: 80,
          }}
        >
          {messages.length === 0 && (
            <div
              style={{
                textAlign: "center",
                color: "#888",
                marginTop: "20vh",
              }}
            >
              <h1
                style={{
                  fontSize: "clamp(24px, 5vw, 48px)",
                  marginBottom: 8,
                }}
              >
                Velora AI
              </h1>

              <p
                style={{
                  fontSize: "clamp(14px, 3vw, 16px)",
                }}
              >
                Start a conversation...
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              style={{
                marginBottom: 16,
                display: "flex",
                justifyContent:
                  msg.role === "user" ? "flex-end" : "flex-start",
              }}
            >
              <div
                style={{
                  maxWidth: "85%",
                  padding: "10px 14px",
                  borderRadius: 12,
                  background:
                    msg.role === "user" ? "#0070f3" : "#f0f0f0",
                  color: msg.role === "user" ? "#fff" : "#000",
                  fontSize: "clamp(14px, 3vw, 16px)",
                  wordWrap: "break-word",
                }}
              >
                {msg.content}
              </div>
            </div>
          ))}

          {loading && (
            <div
              style={{
                color: "#888",
                fontSize: 14,
              }}
            >
              AI is typing...
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        <div
          style={{
            position: "fixed",
            bottom: 0,
            left: !isMobile ? 280 : 0,
            right: 0,
            padding: 16,
            borderTop: "1px solid #e0e0e0",
            background: "#fff",
            display: "flex",
            gap: 8,
          }}
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                sendMessage()
              }
            }}
            placeholder="Type a message..."
            style={{
              flex: 1,
              padding: "12px 16px",
              borderRadius: 24,
              border: "1px solid #ccc",
              fontSize: "clamp(14px, 3vw, 16px)",
              outline: "none",
            }}
          />

          <button
            onClick={sendMessage}
            disabled={loading}
            style={{
              padding: "12px 20px",
              background: loading ? "#ccc" : "#0070f3",
              color: "#fff",
              border: "none",
              borderRadius: 24,
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: "clamp(14px, 3vw, 16px)",
              whiteSpace: "nowrap",
            }}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
