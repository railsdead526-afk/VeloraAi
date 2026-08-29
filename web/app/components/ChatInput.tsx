'use client'

import { FormEvent, useState } from 'react'

interface ChatInputProps {
  onSend: (text: string) => void
  disabled?: boolean
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [text, setText] = useState('')

  const handleSend = (e: FormEvent) => {
    e.preventDefault()
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
  }

  return (
    <form onSubmit={handleSend} className="flex items-end gap-2 px-4 py-4 bg-secondary border-t border-color">
      <div className="flex-1 bg-tertiary rounded-2xl border border-color focus-within:border-amber-500/50 focus-within:ring-2 focus-within:ring-amber-500/10 transition-smooth">
        <input
          type="text"
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Type a message..."
          disabled={disabled}
          className="w-full px-4 py-3 bg-transparent text-primary placeholder:text-tertiary focus:outline-none disabled:opacity-50"
        />
      </div>
      <button
        type="submit"
        disabled={disabled || !text.trim()}
        className="flex items-center justify-center w-11 h-11 bg-amber-500 text-black rounded-xl hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed transition-smooth shadow-md shadow-amber-500/20 focus-visible:outline-amber-500"
        aria-label="Send message"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
        </svg>
      </button>
    </form>
  )
}