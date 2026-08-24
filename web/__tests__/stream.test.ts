import { describe, expect, it } from 'vitest'

import { AgentEventParser, parseEventLine } from '../lib/stream'

describe('parseEventLine', () => {
  it('parses a well-formed event', () => {
    expect(parseEventLine('data: {"type":"token","content":"hi"}')).toEqual({
      type: 'token',
      content: 'hi',
    })
  })

  it('accepts a line with no space after the prefix', () => {
    expect(parseEventLine('data:{"type":"tool_end"}')).toEqual({ type: 'tool_end' })
  })

  it.each([
    ['a keep-alive comment', ': ping'],
    ['a blank line', '   '],
    ['a sentinel', 'data: [DONE]'],
    ['an empty payload', 'data:'],
    ['malformed json', 'data: {"type":'],
    ['a json array', 'data: [1,2,3]'],
    ['a json scalar', 'data: 42'],
    ['a non-data field', 'event: message'],
  ])('ignores %s instead of throwing', (_label, line) => {
    expect(parseEventLine(line)).toBeNull()
  })
})

describe('AgentEventParser', () => {
  it('emits only complete lines and keeps the remainder buffered', () => {
    const parser = new AgentEventParser()

    expect(parser.push('data: {"type":"token","content":"he')).toEqual([])
    expect(parser.push('llo"}\n')).toEqual([{ type: 'token', content: 'hello' }])
  })

  it('reassembles an event split across three reads', () => {
    const parser = new AgentEventParser()
    const chunks = ['data: {"type":"to', 'ken","content":"世', '界"}\n']
    const events = chunks.flatMap((chunk) => parser.push(chunk))

    expect(events).toEqual([{ type: 'token', content: '世界' }])
  })

  it('handles several events in one chunk', () => {
    const parser = new AgentEventParser()
    const chunk = ['data: {"type":"token","content":"a"}', 'data: {"type":"token","content":"b"}', ''].join(
      '\n',
    )

    expect(parser.push(chunk)).toEqual([
      { type: 'token', content: 'a' },
      { type: 'token', content: 'b' },
    ])
  })

  it('handles CRLF separators', () => {
    const parser = new AgentEventParser()

    expect(parser.push('data: {"type":"token","content":"a"}\r\n')).toEqual([
      { type: 'token', content: 'a' },
    ])
  })

  it('keeps going after a malformed line', () => {
    const parser = new AgentEventParser()
    const chunk = ['data: {"broken', 'data: {"type":"done","message_id":7}', ''].join('\n')

    expect(parser.push(chunk)).toEqual([{ type: 'done', message_id: 7 }])
  })

  it('drains a final line that arrived without a trailing newline', () => {
    const parser = new AgentEventParser()

    expect(parser.push('data: {"type":"done","message_id":3}')).toEqual([])
    expect(parser.flush()).toEqual([{ type: 'done', message_id: 3 }])
  })

  it('flushes nothing when the buffer is empty', () => {
    const parser = new AgentEventParser()

    parser.push('data: {"type":"token","content":"a"}\n')
    expect(parser.flush()).toEqual([])
  })
})
