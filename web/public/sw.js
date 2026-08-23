/*
 * Velora AI service worker.
 *
 * Deliberately conservative. The only thing cached is the static shell:
 * the offline page and the app icons.
 *
 * What is NOT cached, and must never be:
 *
 *   - anything under /api/ - conversations, documents, account and billing
 *     data all belong to one signed-in user. A shared Cache Storage entry
 *     would survive logout and could be served to whoever uses the device
 *     next.
 *   - any request carrying an Authorization header, for the same reason.
 *   - anything that is not a GET.
 *
 * Next.js build assets under /_next/static/ are content-hashed and immutable,
 * so they are cached opportunistically after they have been fetched once.
 */

const VERSION = 'v1'
const SHELL_CACHE = `velora-shell-${VERSION}`
const ASSET_CACHE = `velora-assets-${VERSION}`
const OFFLINE_URL = '/offline.html'

const SHELL_ASSETS = [
  OFFLINE_URL,
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE)
      await cache.addAll(SHELL_ASSETS)
      // Take over as soon as the new worker is ready rather than waiting for
      // every tab to close.
      await self.skipWaiting()
    })(),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keep = new Set([SHELL_CACHE, ASSET_CACHE])
      const names = await caches.keys()
      await Promise.all(names.filter((name) => !keep.has(name)).map((name) => caches.delete(name)))
      await self.clients.claim()
    })(),
  )
})

/** Anything user-specific, mutating, or cross-origin stays off the cache. */
function isCacheable(request, url) {
  if (request.method !== 'GET') return false
  if (url.origin !== self.location.origin) return false
  if (url.pathname.startsWith('/api/')) return false
  if (request.headers.has('Authorization')) return false
  return true
}

function isImmutableAsset(url) {
  return url.pathname.startsWith('/_next/static/') || url.pathname.startsWith('/icons/')
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  if (!isCacheable(request, url)) return

  // Navigations: always try the network so the user gets fresh content and a
  // live session; fall back to the offline page only when the network fails.
  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          return await fetch(request)
        } catch {
          const cache = await caches.open(SHELL_CACHE)
          const offline = await cache.match(OFFLINE_URL)
          return offline ?? Response.error()
        }
      })(),
    )
    return
  }

  if (!isImmutableAsset(url)) return

  // Content-hashed assets: serve from cache, populate it in the background.
  event.respondWith(
    (async () => {
      const cache = await caches.open(ASSET_CACHE)
      const cached = await cache.match(request)
      if (cached) return cached
      try {
        const response = await fetch(request)
        if (response.ok && response.type === 'basic') {
          cache.put(request, response.clone())
        }
        return response
      } catch (error) {
        if (cached) return cached
        throw error
      }
    })(),
  )
})

// Lets a future release tell an old worker to step aside without a reload.
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting()
})
