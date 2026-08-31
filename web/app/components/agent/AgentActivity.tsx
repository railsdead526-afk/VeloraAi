'use client'

import { useMemo } from 'react'

export type AgentActivityStatus = 'queued' | 'running' | 'completed' | 'error'

export type AgentActivityItem = {
  id: string
  title: string
  detail?: string
  status: AgentActivityStatus
  duration?: string
  meta?: string
}

type Props = {
  items: AgentActivityItem[]
  title?: string
}

export default function AgentActivity({ items, title = 'Agent activity' }: Props) {
  const active = useMemo(() => items.some((item) => item.status === 'running'), [items])

  if (!items.length) return null

  return (
    <section className="agent-activity" aria-label={title}>
      <header className="agent-activity__header">
        <div>
          <p className="agent-activity__eyebrow">VeloraAi Agent</p>
          <h2>{title}</h2>
        </div>
        {active && <span className="agent-activity__live"><i /> Working</span>}
      </header>

      <div className="agent-activity__timeline">
        {items.map((item) => (
          <article className={`agent-activity__item agent-activity__item--${item.status}`} key={item.id}>
            <div className="agent-activity__rail" aria-hidden="true">
              <span className="agent-activity__dot">{item.status === 'completed' ? '✓' : item.status === 'error' ? '!' : ''}</span>
            </div>
            <div className="agent-activity__body">
              <div className="agent-activity__row">
                <strong>{item.title}</strong>
                {item.duration && <time>{item.duration}</time>}
              </div>
              {item.detail && <p>{item.detail}</p>}
              {item.meta && <span className="agent-activity__meta">{item.meta}</span>}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
