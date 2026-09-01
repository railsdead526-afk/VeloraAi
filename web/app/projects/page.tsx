'use client'

import Link from 'next/link'
import { useState } from 'react'
import './projects.css'

const projects = [
  { name: 'Your first project', description: 'Create a project to keep conversations, context, and tools together.', status: 'New', updated: 'Start here' },
]

export default function ProjectsPage() {
  const [query, setQuery] = useState('')
  const filtered = projects.filter((project) => `${project.name} ${project.description}`.toLowerCase().includes(query.toLowerCase()))

  return (
    <main className="projects-page">
      <header className="projects-header">
        <div className="projects-brand">
          <Link href="/app" className="projects-back" aria-label="Back to workspace">←</Link>
          <div>
            <span>Workspace</span>
            <h1>Projects</h1>
          </div>
        </div>
        <Link href="/app" className="projects-primary">Open agent</Link>
      </header>

      <section className="projects-hero">
        <div>
          <p className="projects-kicker">Organize your work</p>
          <h2>Projects give VeloraAi a place to work.</h2>
          <p>Keep conversations, repository context, knowledge, and connected tools together instead of scattering them across tabs like civilized humans apparently enjoy doing.</p>
        </div>
        <div className="projects-hero-card">
          <div className="projects-orbit"><span>V</span></div>
          <div><strong>One agent. One context.</strong><span>Everything your project needs, in one workspace.</span></div>
        </div>
      </section>

      <section className="projects-toolbar">
        <label className="projects-search"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search projects" /></label>
        <button type="button" className="projects-secondary" disabled title="Project creation will be connected when the project API is available">+ New project</button>
      </section>

      <section className="projects-grid" aria-label="Projects">
        {filtered.map((project) => (
          <article className="project-card" key={project.name}>
            <div className="project-card__top"><span className="project-icon">V</span><span className="project-status">{project.status}</span></div>
            <h3>{project.name}</h3>
            <p>{project.description}</p>
            <div className="project-card__footer"><span>{project.updated}</span><Link href="/app">Open agent →</Link></div>
          </article>
        ))}
        {!filtered.length && <div className="projects-empty"><strong>No projects found</strong><span>Try another search.</span></div>}
      </section>
    </main>
  )
}
