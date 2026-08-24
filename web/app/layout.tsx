export const metadata = {
  title: 'Velora AI — Your team knowledge, finally useful',
  description: 'A focused knowledge assistant for teams that want faster answers from their internal documents.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
      </head>
      <body style={{ margin: 0 }}>{children}</body>
    </html>
  )
}
