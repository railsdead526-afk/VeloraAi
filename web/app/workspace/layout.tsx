import QuotaBadge from '../components/QuotaBadge'

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <QuotaBadge />
    </>
  )
}
