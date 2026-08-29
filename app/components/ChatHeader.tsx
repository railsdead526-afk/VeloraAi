'use client'

import { useState } from 'react'

interface ChatHeaderProps {
  onToggleSidebar?: () => void
  activeChatId?: number | null
  setActiveChat?: (id: number | null) => void
}

export default function ChatHeader({ onToggleSidebar, activeChatId, setActiveChat }: ChatHeaderProps) {
  const [showSidebar, setShowSidebar] = useState(true)

  return (
    <header className="flex items-center justify-between border-b border-color px-6 py-3">
      <div className="flex items-center gap-3">
        <div className="flex-shrink-0 rounded-2xl bg-amber-500 w-10 h-10 flex items-center justify-center">
          <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <span className="text-sm font-medium text-primary">VeloraAI</span>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onToggleSidebar}
          className="p-2 rounded-lg hover:bg-tertiary transition-smooth"
          aria-label="Toggle sidebar"
        >
          {showSidebar ? <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg> : <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>}
        </button>
        {activeChatId !== null && activeChatId !== undefined && (
          <button
            onClick={() => setActiveChat?.(null)}
            className="p-2 rounded-lg hover:bg-tertiary transition-smooth"
            aria-label="Close chat"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12-12" /></svg>
          </button>
        )}
      </div>
    </header>
  )
}