import type { Metadata, Viewport } from 'next'

import QuotaBadge from './components/QuotaBadge'
import ServiceWorkerRegistration from './components/ServiceWorkerRegistration'

export const metadata: Metadata = {
  title: 'Velora AI',
  description: 'AI chat, retrieval and agent tools by Velora AI.',
  applicationName: 'Velora AI',
  manifest: '/manifest.webmanifest',
  icons: {
    icon: [
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [{ url: '/icons/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }],
  },
  appleWebApp: {
    capable: true,
    title: 'Velora AI',
    statusBarStyle: 'black-translucent',
  },
  formatDetection: { telephone: false },
}

export const viewport: Viewport = {
  themeColor: '#121214',
  colorScheme: 'dark',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  // Lets the chat surface reach under the notch and home indicator when the
  // app is launched from the home screen.
  viewportFit: 'cover',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, overflow: 'hidden' }}>
        {children}
        <QuotaBadge />
        <ServiceWorkerRegistration />
      </body>
    </html>
  )
}
