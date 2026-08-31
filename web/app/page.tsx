import Link from 'next/link'
import styles from './Landing.module.css'

const capabilities = [
  ['01', 'Reason through the task', 'VeloraAi turns a request into a clear plan before it starts touching your workspace.'],
  ['02', 'Use the right tools', 'Connect GitHub, Vercel, Railway, Supabase, and more when the task needs real context.'],
  ['03', 'Keep project context', 'Conversations, knowledge, and project context stay together instead of being scattered across tabs.'],
]

const toolStates = [
  ['✓', 'Analyzing request', 'complete'],
  ['✓', 'Searching project context', 'complete'],
  ['●', 'GitHub · Reading repository', 'active'],
  ['○', 'Analyzing code', 'idle'],
  ['○', 'Preparing solution', 'idle'],
]

export default function Home() {
  return (
    <main className={styles.site}>
      <div className={styles.gridGlow} aria-hidden="true" />

      <div className={styles.shell}>
        <header className={styles.navbar}>
          <Link href="/" className={styles.brand} aria-label="VeloraAi home">
            <span className={styles.brandMark} aria-hidden="true">
              <span />
              <i />
            </span>
            <span>VeloraAi</span>
          </Link>

          <nav className={styles.navLinks} aria-label="Primary navigation">
            <a href="#product">Product</a>
            <a href="#tools">Tools</a>
            <a href="#how-it-works">How it works</a>
            <a href="#pricing">Pricing</a>
          </nav>

          <div className={styles.navActions}>
            <Link href="/workspace" className={styles.textButton}>Sign in</Link>
            <Link href="/workspace" className={styles.smallButton}>Get started</Link>
          </div>
        </header>

        <section className={styles.hero}>
          <div className={styles.heroCopy}>
            <div className={styles.eyebrow}><span className={styles.dot} /> AI agent for real work</div>
            <h1>
              Build with an AI that <span>actually works.</span>
            </h1>
            <p>
              VeloraAi combines reasoning, project context, knowledge retrieval, and connected tools in one focused workspace for developers and builders.
            </p>

            <div className={styles.heroActions}>
              <Link href="/workspace" className={styles.primaryButton}>Start building <b>→</b></Link>
              <a href="#product" className={styles.secondaryButton}>Explore the workspace <span>↓</span></a>
            </div>

            <div className={styles.heroMeta}>
              <span><b>01</b> Think</span>
              <span><b>02</b> Act</span>
              <span><b>03</b> Deliver</span>
            </div>
          </div>

          <div className={styles.heroVisual} aria-label="VeloraAi workspace preview">
            <div className={styles.windowBar}>
              <div className={styles.windowDots}><span /><span /><span /></div>
              <span>velora.ai / workspace</span>
              <span className={styles.secure}>● Connected</span>
            </div>

            <div className={styles.workspacePreview}>
              <aside className={styles.miniSidebar}>
                <div className={styles.miniBrand}><span className={styles.brandMarkSmall}><span /><i /></span> VeloraAi</div>
                <div className={styles.miniSection}>WORKSPACE</div>
                <div className={`${styles.miniItem} ${styles.miniActive}`}>✦ New chat</div>
                <div className={styles.miniItem}>◌ Projects</div>
                <div className={styles.miniItem}>⌘ Tools</div>
                <div className={styles.miniItem}>▧ Knowledge</div>
                <div className={styles.miniSection}>ACCOUNT</div>
                <div className={styles.miniItem}>◔ Usage</div>
                <div className={styles.miniItem}>⚙ Settings</div>
              </aside>

              <div className={styles.miniChat}>
                <div className={styles.chatHeader}>
                  <div><strong>Authentication bug</strong><small>VeloraAi project</small></div>
                  <span className={styles.contextBadge}>RAG on</span>
                </div>

                <div className={styles.chatBody}>
                  <div className={styles.messageUser}>
                    <span className={styles.avatar}>D</span>
                    <p>Find the authentication issue in my project and explain the safest fix.</p>
                  </div>

                  <div className={styles.agentBlock}>
                    <div className={styles.agentHeader}><span className={styles.aiGlyph}>✦</span><strong>VeloraAi</strong><span className={styles.statusText}>working</span></div>
                    <p className={styles.agentLead}>I’ll inspect the repository, check project context, and trace the auth flow before suggesting a change.</p>
                    <div className={styles.toolStack}>
                      {toolStates.map(([icon, label, state]) => (
                        <div key={label} className={`${styles.toolRow} ${styles[`tool_${state}`]}`}>
                          <span>{icon}</span><span>{label}</span><small>{state === 'active' ? 'running' : state === 'complete' ? 'done' : ''}</small>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className={styles.composer}>
                  <span>Ask VeloraAi anything…</span>
                  <div><span>＋</span><span>Tools</span><button aria-label="Send message">↑</button></div>
                </div>
              </div>

              <aside className={styles.agentPanel}>
                <div className={styles.panelTitle}><span>Agent activity</span><span className={styles.livePill}>LIVE</span></div>
                <div className={styles.panelCard}>
                  <div className={styles.panelIcon}>⌘</div>
                  <div><strong>GitHub</strong><span>Reading repository</span></div>
                </div>
                <div className={styles.panelMeta}><span>14 files</span><span>2.4s</span></div>
                <div className={styles.panelDivider} />
                <div className={styles.contextTitle}>PROJECT CONTEXT</div>
                <div className={styles.contextRow}><span>Framework</span><strong>Next.js</strong></div>
                <div className={styles.contextRow}><span>Language</span><strong>TypeScript</strong></div>
                <div className={styles.contextRow}><span>Knowledge</span><strong>12 sources</strong></div>
              </aside>
            </div>
          </div>
        </section>

        <section className={styles.trustStrip}>
          <span>BUILT FOR PEOPLE WHO SHIP</span>
          <div><span>AI AGENT</span><span>PROJECT CONTEXT</span><span>RAG</span><span>TOOL-ENABLED</span></div>
        </section>

        <section className={styles.section} id="product">
          <div className={styles.sectionIntro}>
            <div className={styles.sectionKicker}>01 / PRODUCT</div>
            <h2>Less prompting. More doing.</h2>
            <p>VeloraAi is designed around the work between your prompt and the result: context, tools, verification, and a clear handoff.</p>
          </div>

          <div className={styles.capabilityGrid}>
            {capabilities.map(([number, title, copy]) => (
              <article key={number} className={styles.capabilityCard}>
                <span className={styles.cardNumber}>{number}</span>
                <h3>{title}</h3>
                <p>{copy}</p>
                <div className={styles.cardLine} />
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section} id="tools">
          <div className={styles.toolFeature}>
            <div>
              <div className={styles.sectionKicker}>02 / TOOLS</div>
              <h2>When the AI needs to act, you can see it.</h2>
              <p>Tool execution is a first-class part of the interface. Users can understand what VeloraAi is doing, why it is doing it, and whether it succeeded.</p>
              <div className={styles.toolList}>
                <span>GitHub</span><span>Vercel</span><span>Railway</span><span>Supabase</span><span>Cloudflare</span><span>Terminal</span>
              </div>
            </div>

            <div className={styles.executionCard}>
              <div className={styles.executionTop}><span>Working on your request</span><span className={styles.executionDot}>●</span></div>
              {toolStates.map(([icon, label, state]) => (
                <div key={`execution-${label}`} className={styles.executionRow}>
                  <span className={`${styles.executionIcon} ${styles[`execution_${state}`]}`}>{icon}</span>
                  <span>{label}</span>
                  <small>{state === 'active' ? 'in progress' : state === 'complete' ? 'complete' : 'queued'}</small>
                </div>
              ))}
              <div className={styles.executionFoot}>The activity panel can expand for tool input, output, files, and duration.</div>
            </div>
          </div>
        </section>

        <section className={styles.section} id="how-it-works">
          <div className={styles.sectionIntro}>
            <div className={styles.sectionKicker}>03 / HOW IT WORKS</div>
            <h2>From intent to useful output.</h2>
          </div>
          <div className={styles.steps}>
            <div><span>01</span><strong>Connect context</strong><p>Link your project, knowledge, and tools.</p></div>
            <div><span>02</span><strong>Describe the task</strong><p>Tell VeloraAi what outcome you need.</p></div>
            <div><span>03</span><strong>Review the work</strong><p>See agent activity, results, and next steps.</p></div>
          </div>
        </section>

        <section className={styles.ctaSection} id="pricing">
          <div>
            <div className={styles.sectionKicker}>EARLY ACCESS</div>
            <h2>Give your AI the tools to build with you.</h2>
            <p>Start with the workspace today. Pricing and usage limits can evolve with the product.</p>
          </div>
          <Link href="/workspace" className={styles.primaryButton}>Open VeloraAi <b>→</b></Link>
        </section>

        <footer className={styles.footer}>
          <div className={styles.brand}><span className={styles.brandMark}><span /><i /></span><span>VeloraAi</span></div>
          <div><span>Product</span><span>Tools</span><span>Privacy</span><span>Terms</span></div>
          <small>© 2026 VeloraAi</small>
        </footer>
      </div>
    </main>
  )
}
