/**
 * The service worker is a security boundary, not just a performance trick.
 *
 * Cache Storage is shared by everyone who uses the device. If the worker ever
 * cached an authenticated API response, one user's conversations, documents or
 * billing details could be replayed to the next person to open the app -
 * including after logout. These tests load the real public/sw.js and assert
 * that it declines to handle anything user-specific.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import vm from 'node:vm'

import { beforeEach, describe, expect, it } from 'vitest'

type Listener = (event: FakeEvent) => void

interface FakeEvent {
  request: FakeRequest
  respondWith: (value: unknown) => void
  waitUntil: (value: unknown) => void
  handled: boolean
}

class FakeRequest {
  url: string
  method: string
  mode: string
  headers: Headers

  constructor(url: string, init: { method?: string; mode?: string; headers?: HeadersInit } = {}) {
    this.url = url
    this.method = init.method ?? 'GET'
    this.mode = init.mode ?? 'no-cors'
    this.headers = new Headers(init.headers)
  }
}

function loadWorker() {
  const source = readFileSync(join(process.cwd(), 'public', 'sw.js'), 'utf8')
  const listeners = new Map<string, Listener>()

  const self: Record<string, unknown> = {
    addEventListener: (type: string, listener: Listener) => listeners.set(type, listener),
    location: new URL('https://velora.test/sw.js'),
    skipWaiting: async () => undefined,
    clients: { claim: async () => undefined },
    registration: {},
  }
  self.self = self

  const context = vm.createContext({
    self,
    caches: {
      open: async () => ({
        addAll: async () => undefined,
        match: async () => undefined,
        put: async () => undefined,
      }),
      keys: async () => [],
      delete: async () => true,
    },
    fetch: async () => new Response('ok'),
    Response,
    Request,
    Headers,
    URL,
    Promise,
    Set,
    console,
  })

  vm.runInContext(source, context)
  return listeners
}

function dispatchFetch(listeners: Map<string, Listener>, request: FakeRequest): FakeEvent {
  const event: FakeEvent = {
    request,
    handled: false,
    respondWith(value) {
      event.handled = true
      void value
    },
    waitUntil(value) {
      void value
    },
  }
  listeners.get('fetch')?.(event)
  return event
}

describe('service worker caching policy', () => {
  let listeners: Map<string, Listener>

  beforeEach(() => {
    listeners = loadWorker()
  })

  it('registers install, activate and fetch handlers', () => {
    expect([...listeners.keys()].sort()).toEqual(['activate', 'fetch', 'install', 'message'])
  })

  it.each([
    ['a conversation list', 'https://velora.test/api/v1/conversations'],
    ['the current user', 'https://velora.test/api/v1/auth/me'],
    ['billing details', 'https://velora.test/api/v1/payments/config'],
    ['a document', 'https://velora.test/api/v1/rag/documents/1'],
    ['the agent stream', 'https://velora.test/api/v1/conversations/1/messages/stream'],
  ])('never intercepts %s', (_label, url) => {
    const event = dispatchFetch(listeners, new FakeRequest(url))
    expect(event.handled).toBe(false)
  })

  it('never intercepts a request carrying an Authorization header', () => {
    const event = dispatchFetch(
      listeners,
      new FakeRequest('https://velora.test/icons/icon-192.png', {
        headers: { Authorization: 'Bearer token' },
      }),
    )
    expect(event.handled).toBe(false)
  })

  it.each(['POST', 'PUT', 'PATCH', 'DELETE'])('never intercepts a %s', (method) => {
    const event = dispatchFetch(
      listeners,
      new FakeRequest('https://velora.test/icons/icon-192.png', { method }),
    )
    expect(event.handled).toBe(false)
  })

  it('never intercepts another origin', () => {
    const event = dispatchFetch(listeners, new FakeRequest('https://example.com/icons/x.png'))
    expect(event.handled).toBe(false)
  })

  it('handles navigations so an offline fallback can be served', () => {
    const event = dispatchFetch(
      listeners,
      new FakeRequest('https://velora.test/', { mode: 'navigate' }),
    )
    expect(event.handled).toBe(true)
  })

  it('does not intercept a navigation into the API namespace', () => {
    const event = dispatchFetch(
      listeners,
      new FakeRequest('https://velora.test/api/v1/auth/me', { mode: 'navigate' }),
    )
    expect(event.handled).toBe(false)
  })

  it.each([
    'https://velora.test/_next/static/chunks/main.js',
    'https://velora.test/icons/icon-512.png',
  ])('caches the immutable asset %s', (url) => {
    const event = dispatchFetch(listeners, new FakeRequest(url))
    expect(event.handled).toBe(true)
  })

  it('leaves non-hashed same-origin assets to the network', () => {
    const event = dispatchFetch(listeners, new FakeRequest('https://velora.test/robots.txt'))
    expect(event.handled).toBe(false)
  })
})
