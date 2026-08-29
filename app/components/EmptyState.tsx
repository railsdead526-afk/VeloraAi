'use client'

import { useState } from 'react'

interface EmptyStateProps {
  onNewChat: () => void
}

export default function EmptyState({ onNewChat }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 px-6 text-center animate-fade-up">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-500 to-amber-600 flex items-center justify-center mb-6 shadow-lg shadow-amber-500/20">
        <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      </div>
      <h1 className="text-2xl font-semibold text-primary mb-2">Start a new conversation</h1>
      <p className="text-secondary max-w-md mb-8 leading-relaxed">
        Ask questions, get help with tasks, or just explore what VeloraAI can do.
      </p>
      <button
        onClick={onNewChat}
        className="inline-flex items-center gap-2 px-6 py-3 bg-amber-500 text-black font-semibold rounded-xl hover:bg-amber-400 transition-smooth shadow-md shadow-amber-500/20 focus-visible:outline-amber-500"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        New Chat
      </button>
    </div>
  )
}