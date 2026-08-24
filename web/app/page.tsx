import Link from 'next/link'
import styles from './Landing.module.css'

const useCases = [
  {
    number: '01',
    title: 'Jawaban dari SOP',
    copy: 'Berikan tim satu tempat untuk bertanya tentang proses, kebijakan, dan dokumen kerja tanpa membuka banyak folder.',
  },
  {
    number: '02',
    title: 'Onboarding lebih cepat',
    copy: 'Bantu anggota baru memahami cara kerja perusahaan melalui knowledge base yang selalu tersedia.',
  },
  {
    number: '03',
    title: 'Knowledge tetap hidup',
    copy: 'Ubah dokumen yang jarang dibuka menjadi jawaban praktis yang bisa dipakai saat pekerjaan berlangsung.',
  },
]

export default function Home() {
  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <nav className={styles.nav} aria-label="Navigasi utama">
          <Link className={styles.brand} href="/">
            <span className={styles.brandMark} />
            VELORA AI
          </Link>
          <div className={styles.navLinks}>
            <a href="#cara-kerja">Cara kerja</a>
            <a href="#pilot">Pilot</a>
            <Link className={styles.navCta} href="/workspace">Buka workspace</Link>
          </div>
        </nav>

        <section className={styles.hero}>
          <div>
            <div className={styles.eyebrow}>Knowledge assistant untuk tim kecil</div>
            <h1>Berhenti mencari. <em>Mulai bekerja.</em></h1>
            <p className={styles.heroCopy}>
              Velora mengubah SOP, proposal, dan dokumentasi internal menjadi jawaban yang jelas—sehingga tim Anda menghabiskan lebih sedikit waktu mencari konteks dan lebih banyak waktu menyelesaikan pekerjaan.
            </p>
            <div className={styles.heroActions}>
              <a className={styles.primaryCta} href="#pilot">Mulai pilot terbatas</a>
              <a className={styles.secondaryCta} href="#cara-kerja">Lihat cara kerja <span>↓</span></a>
            </div>
            <div className={styles.signal}>
              <div><strong>1 workspace</strong>Semua knowledge di satu tempat</div>
              <div><strong>Jawaban bersumber</strong>Lebih mudah diverifikasi</div>
            </div>
          </div>

          <div className={styles.preview} aria-label="Preview workspace Velora">
            <div className={styles.previewTop}>
              <span>Velora workspace</span>
              <span className={styles.live}>Knowledge online</span>
            </div>
            <div className={styles.previewBody}>
              <aside className={styles.previewSide}>
                <div className={styles.sideLabel}>Workspace</div>
                <div className={`${styles.sideItem} ${styles.sideItemActive}`}>Ask Velora</div>
                <div className={styles.sideItem}>SOP library</div>
                <div className={styles.sideItem}>Team context</div>
              </aside>
              <div className={styles.previewMain}>
                <h3>Good morning, team.</h3>
                <p>Ask anything about your company knowledge.</p>
                <div className={styles.query}>Bagaimana proses handoff proyek dari sales ke delivery?</div>
                <div className={styles.answer}>
                  <div className={styles.answerLabel}>Velora answered</div>
                  <p>Handoff dimulai setelah proposal disetujui. Sales mengisi project brief, lalu delivery lead melakukan kickoff internal dalam 2 hari kerja.</p>
                  <div className={styles.sources}>
                    <span className={styles.source}>Project SOP.pdf</span>
                    <span className={styles.source}>Handoff checklist</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className={styles.section} id="cara-kerja">
          <div className={styles.sectionHeading}>
            <h2>Knowledge yang bekerja saat tim membutuhkannya.</h2>
            <p>Dirancang untuk tim kecil yang sudah memiliki dokumen, tetapi belum memiliki cara cepat untuk menemukan jawabannya. Mulai dari satu folder, satu workflow, dan satu masalah nyata.</p>
          </div>
          <div className={styles.cards}>
            {useCases.map((item) => (
              <article className={styles.card} key={item.number}>
                <div className={styles.cardNumber}>{item.number}</div>
                <h3>{item.title}</h3>
                <p>{item.copy}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section} id="pilot">
          <div className={styles.pilot}>
            <div>
              <h2>Uji satu workflow. Buktikan nilainya.</h2>
              <p>Kami membuka pilot terbatas untuk tim kecil yang ingin mengurangi waktu mencari SOP dan dokumentasi internal.</p>
            </div>
            <div className={styles.pilotBox}>
              <strong>Pilot Knowledge Workspace</strong>
              <span>Setup sederhana, satu use case, dan evaluasi bersama setelah 30 hari.</span>
              <div className={styles.pilotActions}>
                <a className={styles.pilotButton} href="mailto:railsdead526@gmail.com?subject=Velora%20pilot">Email saya →</a>
                <a className={styles.pilotButton} href="https://wa.me/6285707203681?text=Halo%2C%20saya%20tertarik%20dengan%20pilot%20Velora">WhatsApp →</a>
              </div>
            </div>
          </div>
        </section>

        <footer className={styles.footer}>
          <span>© 2026 Velora AI</span>
          <span>Built for teams that value context.</span>
        </footer>
      </div>
    </main>
  )
}
