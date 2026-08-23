/**
 * A manifest that is subtly wrong still installs, then behaves oddly: a wrong
 * `scope` breaks navigation capture, a missing maskable icon gets letterboxed
 * on Android, and a `start_url` outside the scope silently opens in a browser
 * tab instead of the installed window.
 */

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const manifest = JSON.parse(
  readFileSync(join(process.cwd(), 'public', 'manifest.webmanifest'), 'utf8'),
) as {
  name: string
  short_name: string
  start_url: string
  scope: string
  display: string
  theme_color: string
  background_color: string
  icons: { src: string; sizes: string; type: string; purpose: string }[]
}

describe('web app manifest', () => {
  it('declares the fields an installable app needs', () => {
    expect(manifest.name).toBeTruthy()
    // Home screen labels are truncated past roughly 12 characters.
    expect(manifest.short_name.length).toBeLessThanOrEqual(12)
    expect(manifest.display).toBe('standalone')
    expect(manifest.theme_color).toMatch(/^#[0-9a-f]{6}$/i)
    expect(manifest.background_color).toMatch(/^#[0-9a-f]{6}$/i)
  })

  it('keeps start_url inside the scope', () => {
    expect(manifest.start_url.startsWith(manifest.scope)).toBe(true)
  })

  it('ships both a 192 and a 512 icon', () => {
    const sizes = manifest.icons.map((icon) => icon.sizes)
    expect(sizes).toContain('192x192')
    expect(sizes).toContain('512x512')
  })

  it('ships a maskable icon so Android does not letterbox it', () => {
    const maskable = manifest.icons.filter((icon) => icon.purpose === 'maskable')
    expect(maskable.length).toBeGreaterThanOrEqual(1)
    expect(maskable.some((icon) => icon.sizes === '512x512')).toBe(true)
  })

  it('points every icon at a file that exists', () => {
    for (const icon of manifest.icons) {
      const path = join(process.cwd(), 'public', icon.src)
      expect(existsSync(path), `missing icon: ${icon.src}`).toBe(true)
    }
  })

  it('ships the offline fallback the service worker precaches', () => {
    expect(existsSync(join(process.cwd(), 'public', 'offline.html'))).toBe(true)
  })
})
