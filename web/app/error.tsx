'use client'

export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        background: '#080808',
        color: '#f5f5f5',
        fontFamily: 'system-ui, sans-serif',
        padding: 20,
      }}
    >
      <div style={{ textAlign: 'center', maxWidth: 420 }}>
        <p style={{ color: '#ffb4a9', marginBottom: 8 }}>
          Something went wrong.
        </p>
        <button
          onClick={reset}
          style={{
            border: '1px solid #3a3a3a',
            background: '#171717',
            color: '#fff',
            borderRadius: 10,
            padding: '10px 14px',
            cursor: 'pointer',
          }}
        >
          Reload
        </button>
      </div>
    </div>
  )
}