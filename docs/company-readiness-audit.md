# VeloraAi — Audit Kesiapan Perusahaan & Aset Jangka Panjang

Tanggal audit: 2026-08-22
Commit dasar: `5a2f9f6` (feat: isolate Alembic migrations by database schema)
Metode: pembacaan seluruh source, eksekusi test suite + coverage, `pip-audit`, pemeriksaan CI GitHub Actions, review konfigurasi deploy.

---

## 1. Vonis singkat

**Sebagai fondasi teknis: kuat di atas rata-rata. Sebagai perusahaan: belum siap.**

| Dimensi | Skor | Catatan |
|---|---|---|
| Arsitektur & struktur kode | 8/10 | Layering bersih, batas modul jelas |
| Kualitas & disiplin engineering | 7/10 | 196 test, coverage 70%, tapi `main` sedang merah |
| Keamanan aplikasi | 6/10 | Kontrol bagus, tapi ada lubang arsitektural besar (lihat §3.1) |
| Kesiapan produksi (ops) | 4/10 | Belum ada monitoring, backup, runbook, platform terkunci |
| Kelayakan bisnis / monetisasi | 3/10 | Langganan tidak punya masa berlaku — bocor pendapatan |
| Kelayakan hukum & aset | 2/10 | Tidak ada LICENSE, ToS, Privacy Policy, entitas |
| **Rata-rata tertimbang** | **≈ 5/10** | Produk bagus, perusahaan belum ada |

Analogi: Anda punya **mesin mobil yang dirakit rapi**, tapi belum punya bodi, plat nomor, STNK, asuransi, dan bengkel.

---

## 2. Yang sudah benar (aset nyata Anda)

Ini bukan basa-basi — hal-hal berikut jarang ditemukan di repo tahap awal:

1. **Struktur modular disiplin.** `api / core / crud / models / schemas / services / tools` dipisah konsisten. 5.600 baris app, tidak ada file raksasa. Ini yang membuat kode bisa diwariskan ke tim.
2. **Test suite serius.** 196 test, 3.702 baris, coverage 70%. Ada test khusus untuk isolasi keamanan, matriks izin peran, redaksi kredensial, idempotensi webhook billing, dan batas kuota.
3. **Validasi konfigurasi produksi yang keras.** `Settings.validate()` menolak SQLite, `SECRET_KEY` lemah, debug on, `memory://` rate limit, CORS wildcard, provider mock, dan harga nol di produksi. Ini mencegah kelas kesalahan deploy yang paling sering membunuh startup.
4. **Migrasi Alembic 14 versi, bukan `create_all()`.** Plus job CI khusus yang memvalidasi migrasi terhadap PostgreSQL + pgvector asli.
5. **Batas eksekusi kode yang dipikirkan.** Terminal tidak jalan di host — dirutekan lewat `SandboxClient` ke service terpisah yang memakai `docker run --network=none --read-only --cap-drop=ALL --no-new-privileges --pids-limit --memory=512m --user=1000`. Ini desain yang benar.
6. **Billing tidak naif.** Webhook Midtrans memverifikasi signature SHA-512 dengan `hmac.compare_digest`, **lalu tetap re-verifikasi ke API Midtrans**, mencocokkan `gross_amount`, memakai `SELECT ... FOR UPDATE`, dan punya status terminal anti-replay. Banyak startup Indonesia gagal di titik ini.
7. **Isolasi tenant di data path konsisten.** Setiap query conversation, document, dan RAG chunk difilter `user_id`. Vector search pun difilter di level SQL.
8. **Audit log, request ID, structured JSON logging, security headers, kuota berbasis reservasi dengan TTL.**
9. **CI 4 job:** test SQLite, migrasi Postgres, sandbox service, lint+build frontend.
10. **Kejujuran dokumentasi.** `docs/hardening-audit.md` secara eksplisit menyatakan "ini bukan klaim bahwa infrastruktur sudah diaudit pihak ketiga" dan mendaftar gate yang masih terbuka. Kedewasaan seperti ini langka.

---

## 3. Penghambat kritis (harus beres sebelum menyebut diri perusahaan)

### 3.1 🔴 BLOKER: Kredensial tool bersifat global, bukan per-pengguna

Ini **cacat arsitektur paling serius** di repo.

```python
# app/tools/providers.py, github_tools.py, supabase_tools.py, cloudflare_tools.py, platform_tools.py
token = os.getenv("GITHUB_TOKEN", "")
```

Token GitHub, Vercel, Railway, Cloudflare, dan Supabase diambil dari **environment variable proses**. Artinya:

- Setiap pengguna yang memanggil tool GitHub akan mengakses **repo milik Anda**, bukan miliknya.
- Pengguna A bisa membaca/mengubah resource yang dilihat pengguna B.
- Satu akun jahat = akses penuh ke seluruh infrastruktur Anda.

Produk ini secara struktural adalah **aplikasi single-tenant** yang dipasangi login multi-user dan billing multi-user. Selama ini belum diperbaiki, **membuka pendaftaran publik adalah insiden keamanan yang menunggu terjadi**, bukan risiko teoretis.

**Perbaikan wajib:** tabel `user_integrations` (user_id, provider, ciphertext token, scope, expiry), enkripsi at-rest (KMS / envelope encryption), alur OAuth per provider, dan semua fungsi tool menerima kredensial dari konteks pengguna — bukan `os.getenv`. Ini pekerjaan 2–4 minggu dan tidak bisa dilewati.

### 3.2 🔴 BLOKER: Langganan tidak pernah kedaluwarsa — pendapatan bocor

`billing_service.apply_payment_notification()` membuat `Subscription(status="active")` dan **tidak pernah mengisi `current_period_start` / `current_period_end`**, padahal kolomnya sudah ada di model. Tidak ada scheduler, cron, atau job renewal di seluruh repo.

Konsekuensi bisnis: **pengguna bayar sekali Rp99.000, lalu menjadi Pro selamanya.** Tidak ada penagihan bulan kedua, tidak ada downgrade otomatis, tidak ada dunning.

Ini bukan bug kecil — ini berarti model bisnis subscription Anda **belum ada implementasinya**. Yang ada baru "pembelian sekali bayar".

**Perbaikan:** isi periode saat settlement, job harian yang menurunkan plan saat `current_period_end` lewat, alur recurring/tokenisasi kartu Midtrans, dan status `past_due` + notifikasi.

### 3.3 🔴 `main` sedang MERAH di CI

CI run terakhir di `main` (`32568526148`) **failure**. Saya reproduksi lokal:

```
FAILED tests/test_production_ai_provider.py::test_production_rejects_mock_provider
FAILED tests/test_production_ai_provider.py::test_production_openai_provider_requires_key
2 failed, 193 passed, 3 skipped
```

Penyebab: commit `5a2f9f6` menambahkan pemeriksaan `DATABASE_SCHEMA must not be public in production` **di baris pertama blok produksi** di `config.py:79`, sehingga ia melempar lebih dulu sebelum pemeriksaan yang diuji. Test helper `_production_settings()` tidak diperbarui.

Fakta yang lebih penting daripada bug-nya: **commit yang merah tetap mendarat di `main`.** Itu berarti branch protection tidak aktif atau tidak ditegakkan. Untuk aset jangka panjang, `main` yang bisa merah adalah kegagalan proses, bukan kegagalan kode.

### 3.4 🔴 Tidak ada LICENSE — status kepemilikan repo ambigu

Repo ini **publik** dan **tanpa file LICENSE**. Secara hukum default hak cipta tetap milik Anda, tetapi:

- Tidak ada CLA/DCO → kontribusi luar menciptakan klaim kepemilikan yang berantakan.
- Investor dan akuisitor dalam due diligence akan menandai ini sebagai temuan.
- Tidak ada `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, `CODEOWNERS`.

Untuk produk komersial, pilihan paling waras: **jadikan repo private sekarang**, tambahkan `LICENSE` proprietary, dan tetapkan kebijakan kontribusi.

### 3.5 🟠 55 kerentanan dependensi diketahui di 7 paket

Hasil `pip-audit`:

| Paket | Versi | Jumlah CVE | Fix |
|---|---|---|---|
| pypdf | 6.0.0 | 34 | ≥6.15.0 |
| starlette | 0.46.2 | 9 | ≥1.3.1 |
| python-multipart | 0.0.20 | 6 | ≥0.0.31 |
| ecdsa | 0.19.2 | 1 | (tidak ada fix) |
| python-dotenv, pytest, mako | — | 3 | tersedia |

`pypdf` dan `python-multipart` adalah **jalur upload dokumen RAG Anda** — persis permukaan yang menerima file tidak tepercaya dari pengguna. Ini bukan risiko teoretis.

Selain itu: **tidak ada Dependabot/Renovate**, tidak ada `pip-audit`/`npm audit` di CI, tidak ada scanning secret, tidak ada SAST. Untuk perusahaan, keamanan supply chain harus otomatis, bukan manual.

### 3.6 🟠 Autentikasi masih tingkat prototipe

Yang **tidak ada** di `auth.py` / `deps.py` / `security.py`:

- Refresh token — hanya access token 30 menit, sesi mati mendadak
- Logout / revokasi token (JWT stateless tanpa denylist = token curian valid sampai expired)
- Reset password
- Verifikasi email — siapa pun bisa daftar dengan email palsu
- MFA / 2FA
- Lockout setelah gagal login (hanya rate limit 10/menit per IP)
- Riwayat perangkat/sesi

Hashing memakai `pbkdf2_sha256` (aman, tapi Argon2id lebih baik untuk 2026). Frontend menyimpan token di `localStorage` → rentan XSS; cookie `httpOnly` + `SameSite` lebih tepat.

Untuk produk B2C berbayar, "tidak ada reset password" saja sudah cukup memblokir peluncuran.

### 3.7 🟠 Nol observabilitas operasional

Yang ada: JSON log + request ID. Bagus, tapi berhenti di situ.

Tidak ada: metrik Prometheus/OpenTelemetry, distributed tracing, error tracking (Sentry), alerting, dashboard, SLO, uptime monitoring, log aggregation. Endpoint `/ready` hanya `SELECT 1` — tidak mengecek Redis, provider AI, Midtrans, atau sandbox.

Konsekuensi praktis: **saat produksi rusak jam 2 pagi, Anda tahu dari komplain pengguna.** Dan Anda tidak akan tahu berapa biaya token AI per pengguna sampai tagihan OpenAI datang.

### 3.8 🟠 Tidak ada disaster recovery

Tidak ada dokumen backup, tidak ada uji restore, tidak ada RPO/RTO, tidak ada prosedur rollback, tidak ada runbook insiden. `docs/production-database.md` ada tapi ini belum tercakup.

Untuk sistem yang memegang **data pembayaran dan dokumen pengguna**, ini adalah risiko eksistensial. Satu `DROP` yang salah = perusahaan tamat.

### 3.9 🟡 Frontend belum menjadi produk

`web/` hanya 805 baris: `page.tsx` 5 baris, `Chat.tsx` 512 baris, plus `QuotaBadge`. Tidak ada halaman login/register, tidak ada halaman billing/upgrade, tidak ada pengelolaan dokumen RAG, tidak ada pengaturan akun, tidak ada admin panel, tidak ada landing page, tidak ada test frontend sama sekali.

Backend Anda mengekspos RAG, tools, audit, refund, kuota — **frontend tidak mengekspos hampir semuanya**. Pengguna tidak bisa membeli tanpa halaman checkout yang layak (yang ada hanya `app/static/checkout.html` — HTML statis yang di-serve backend, bukan bagian dari aplikasi Next.js).

### 3.10 🟡 Celah hukum & finansial untuk operasi di Indonesia

Tidak ada di repo maupun sebagai artefak: Terms of Service, Privacy Policy, kebijakan refund, entitas PT/CV, NPWP, **penanganan PPN 12%**, faktur/invoice, kepatuhan UU PDP No. 27/2022 (hak akses, hak hapus, notifikasi kebocoran 3×24 jam), dan kebijakan retensi data.

Menerima uang dari publik tanpa ToS dan tanpa entitas adalah eksposur pribadi bagi Anda.

### 3.11 🟡 Detail teknis lain

- **`.env.example` tidak mencantumkan `DATABASE_SCHEMA`**, padahal produksi *wajib* diisi non-`public`. Deploy pertama akan crash tanpa petunjuk. Perbaikan 1 baris.
- **Bug refund:** `payments.py` menaikkan `payment.refund_amount = refund_amount` (menimpa) alih-alih `+=` — refund parsial berulang akan salah hitung.
- **Tidak ada model organisasi/tim.** Hanya `User` datar dengan `role`. Penjualan B2B mustahil tanpa workspace/tim/seat.
- **Tidak ada soft delete** di mana pun — penghapusan akun bersifat kaskade destruktif, menyulitkan pemenuhan audit dan pemulihan.
- **Tidak ada API versioning strategy** selain prefix `/v1` (belum ada kebijakan deprecation).
- **Duplikasi router:** `agent_stream` dan `conversations` sama-sama mendaftarkan `/messages/stream`, "legacy" dibiarkan sebagai fallback. Utang teknis yang harus dibersihkan.
- **`docs/hardening-plan.md` dan `docs/hardening-audit.md` isinya nyaris identik** (duplikat).
- **Coverage tidak merata:** `github_tools` 17%, `platform_tools` 19%, `cloudflare_tools` 18%, `terminal_tools` 40%, `midtrans_service` 46% — justru modul paling berbahaya yang paling sedikit diuji.
- **Formatter/linter Python tidak ada** (tidak ada ruff/black/mypy di CI). Frontend punya ESLint, backend tidak punya apa-apa.

---

## 4. Jawaban langsung atas pertanyaan Anda

**"Apakah sudah siap jadi sebuah perusahaan?"**
Belum. Yang Anda punya adalah **produk teknis yang menjanjikan**, bukan perusahaan. Perusahaan butuh: entitas legal, ToS/Privacy, penagihan berulang yang benar-benar menagih, isolasi tenant yang benar, dan kemampuan bangun jam 2 pagi saat sistem mati. Lima-limanya belum ada.

**"Apakah sudah siap jadi aset jangka panjang?"**
Berpotensi kuat, dengan dua syarat.
- **Yang membuatnya aset:** arsitektur bersih, test serius, migrasi disiplin, batas keamanan yang dipikirkan, dan dokumentasi yang jujur. Kode ini bisa diserahkan ke engineer baru dan dia akan paham dalam sehari. Itu definisi aset.
- **Yang mengancamnya:** tanpa LICENSE, kepemilikan ambigu. Tanpa isolasi kredensial per-pengguna, produk tidak bisa tumbuh melewati pengguna tunggal. Tanpa CI hijau yang ditegakkan, kualitas akan luruh seiring waktu.

Nilai aset Anda hari ini terletak pada **fondasi arsitekturnya**, bukan pada kesiapan komersialnya.

---

## 5. Rencana aksi berurutan

### Minggu ini (hentikan pendarahan)
1. Perbaiki 2 test yang gagal → `main` hijau kembali.
2. Aktifkan branch protection di `main`: wajib CI lulus, wajib PR, larang force-push.
3. Jadikan repo **private**.
4. Tambahkan `LICENSE` (proprietary), `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS`.
5. Tambahkan `DATABASE_SCHEMA` ke `.env.example`.
6. Perbaiki bug `refund_amount +=`.
7. Upgrade `pypdf`, `starlette`, `python-multipart`, `python-dotenv`, `mako`; aktifkan Dependabot.

### Bulan 1 (jadikan aman)
8. **Kredensial per-pengguna terenkripsi + OAuth** — hapus semua `os.getenv` di `app/tools/`. Ini prioritas nomor satu.
9. Refresh token + logout/revokasi + reset password + verifikasi email.
10. Pindahkan token dari `localStorage` ke cookie `httpOnly`.
11. Tambahkan `ruff` + `mypy` + `pip-audit` + `npm audit` ke CI.
12. Naikkan coverage modul tools & midtrans ke ≥70%.

### Bulan 2 (jadikan bisa dijalankan)
13. Sentry + OpenTelemetry + metrik Prometheus + alerting.
14. `/ready` mendalam (DB, Redis, provider AI, Midtrans, sandbox).
15. Kunci platform deploy; tulis runbook, prosedur rollback, dan **uji restore backup sungguhan**.
16. Redis untuk rate limit bersama.
17. Dashboard biaya AI per pengguna.

### Bulan 3 (jadikan bisnis)
18. **Siklus langganan penuh:** periode, renewal, downgrade otomatis, `past_due`, dunning, invoice.
19. Halaman auth, billing, dokumen, pengaturan, dan admin di Next.js.
20. Dirikan PT, terbitkan ToS + Privacy Policy, siapkan PPN & faktur, patuhi UU PDP.
21. Model organisasi/tim untuk jalur B2B.
22. Penetration test eksternal sebelum peluncuran publik.

---

## 6. Penutup

Kualitas rekayasa di repo ini **jelas di atas rata-rata untuk proyek solo**. Disiplin test, isolasi tenant di data layer, verifikasi ganda webhook pembayaran, dan sandbox Docker yang dikonfigurasi benar menunjukkan Anda paham apa yang Anda kerjakan.

Kelemahannya bukan pada kemampuan menulis kode, melainkan pada **hal-hal yang bukan kode**: legalitas, operasional, siklus penagihan, dan model multi-tenancy. Empat hal itulah yang memisahkan proyek dari perusahaan.

Kerjakan §3.1 (kredensial per-pengguna) dan §3.2 (siklus langganan) lebih dulu. Keduanya bersifat arsitektural — makin lama ditunda, makin mahal.
