/**
 * Server-sent event parsing for the agent stream.
 *
 * This lives outside the React component so it can be reasoned about and tested
 * on its own. Two properties matter here:
 *
 *  - A malformed line must never kill the stream. Keep-alive comments, blank
 *    lines and anything a proxy decides to inject are skipped rather than
 *    thrown, because an exception mid-stream loses the reply already rendered.
 *  - Chunk boundaries are arbitrary. A single `data:` line can arrive split
 *    across several reads, so the parser keeps a buffer and only emits complete
 *    lines.
 */

export type AgentEventType =
  | 'token'
  | 'tool_start'
  | 'tool_confirmation_required'
  | 'tool_end'
  | 'done'
  | 'error'

export interface AgentEvent {
  type?: AgentEventType
  content?: string
  detail?: string
  message_id?: number
  name?: string
  tool_call_id?: string
  confirmation_token?: string
}

const DATA_PREFIX = 'data:'

/** Parses one already-complete line. Returns null when there is nothing useful. */
export function parseEventLine(line: string): AgentEvent | null {
  const normalized = line.trim()
  if (!normalized || !normalized.startsWith(DATA_PREFIX)) return null

  const raw = normalized.slice(DATA_PREFIX.length).trim()
  // Some providers and proxies terminate a stream with a sentinel rather than
  // JSON. It carries no information for us.
  if (!raw || raw === '[DONE]') return null

  try {
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return parsed as AgentEvent
  } catch {
    return null
  }
}

/**
 * Accumulates decoded chunks and yields whole events.
 *
 * Handles both `\n` and `\r\n` separators; `flush` drains whatever the stream
 * left behind when it closed without a trailing newline.
 */
export class AgentEventParser {
  private buffer = ''

  push(chunk: string): AgentEvent[] {
    this.buffer += chunk
    const lines = this.buffer.split('\n')
    // The final element is either an incomplete line or an empty string.
    this.buffer = lines.pop() ?? ''
    return lines.map(parseEventLine).filter((event): event is AgentEvent => event !== null)
  }

  flush(): AgentEvent[] {
    const remaining = this.buffer
    this.buffer = ''
    const event = parseEventLine(remaining)
    return event ? [event] : []
  }
}
