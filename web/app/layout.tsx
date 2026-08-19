export const metadata = {
  title: "Velora AI",
  description: "AI Chat by Velora AI",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
      </head>
      <body style={{ margin: 0, overflow: "hidden" }}>{children}</body>
    </html>
  )
}
