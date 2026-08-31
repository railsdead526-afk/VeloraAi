'use client'

import type { AgentActivityItem } from './AgentActivity'

interface ToolActivityCardProps {
  item: AgentActivityItem
  defaultOpen?: boolean
}

export default function ToolActivityCard({ item, defaultOpen = false }: ToolActivityCardProps) {
  const statusLabel = {
    queued: 'Queued',
    running: 'Running',
    completed: 'Completed',
    error: 'Failed',
  }[item.status]

  return (
    <details className={`tool-activity-card tool-activity-card--${item.status}`} open={defaultOpen}>
      <summary>
        <span className="tool-activity-card__status" aria-hidden="true">
          {item.status === 'completed' ? '✓' : item.status === 'error' ? '!' : item.status === 'running' ? '' : '○'}
        </span>
        <span className="tool-activity-card__title">
          <strong>{item.title}</strong>
          <small>{statusLabel}</small>
        </span>
        {item.duration && <time>{item.duration}</time>}
      </summary>

      <div className="tool-activity-card__details">
        {item.detail && <p>{item.detail}</p>}
        {item.meta && <code>{item.meta}</code>}
      </div>
    </details>
  )
}
