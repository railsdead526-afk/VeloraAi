import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Forward API calls to the backend so the browser sees a single origin.
  // This removes CORS from the picture entirely and lets the client use
  // relative URLs, which is also how it should run in production behind a
  // reverse proxy.
  async rewrites() {
    const backend = process.env.BACKEND_ORIGIN || 'http://127.0.0.1:8000'
    return [{ source: '/api/:path*', destination: `${backend}/api/:path*` }]
  },
  outputFileTracingRoot: process.cwd(),
}

export default nextConfig
