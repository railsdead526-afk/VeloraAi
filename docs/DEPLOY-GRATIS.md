# Deploy Gratis (Rp0) — Panduan Lengkap

Panduan ini membuat VeloraAi online **tanpa biaya**, tanpa kartu kredit, dan
tanpa perlu laptop (semua bisa dari HP). Total waktu: ± 30–60 menit.

## Layanan yang dipakai (semua punya free tier)

| Layanan | Kegunaan | Gratis? |
|---|---|---|
| [Render](https://render.com) | Backend FastAPI (Docker) | ✅ |
| [Neon](https://neon.tech) (atau Supabase) | Database PostgreSQL | ✅ |
| [Upstash](https://upstash.com) | Redis untuk rate-limit | ✅ |
| [Vercel](https://vercel.com) | Frontend Next.js | ✅ |
| [Google AI Studio](https://aistudio.google.com) | Gemini API key | ✅ |

---

## Langkah 1 — Gemini API Key

1. Buka <https://aistudio.google.com/apikey> (login akun Google).
2. **Create API key** → salin dan simpan.

## Langkah 2 — Database PostgreSQL (Neon)

1. Daftar di <https://neon.tech> → buat project baru.
2. Salin **connection string** (format `postgresql://user:pass@host/db`).
3. Buka **SQL Editor** di Neon, jalankan sekali:

```sql
CREATE SCHEMA IF NOT EXISTS veloraai;
```

> Aplikasi wajib memakai schema non-`public` di production (divalidasi
> `config.py`). Kita pakai `veloraai` sesuai `docs/production-database.md`.

## Langkah 3 — Redis rate-limit (Upstash)

Production menolak `memory://` untuk rate-limit, jadi perlu Redis bersama:

1. Daftar di <https://upstash.com> → **Create Database** (pilih Regional, plan Free).
2. Salin endpoint **`rediss://...`** (yang ada TLS-nya).

## Langkah 4 — Backend di Render

1. Daftar di <https://render.com> pakai akun GitHub → **New + → Web Service**.
2. Pilih repo `VeloraAi`.
3. **Runtime: Docker** (Dockerfile sudah ada), **Instance Type: Free**.
   (Atau pakai Blueprint: file `render.yaml` sudah disiapkan di root repo.)
4. Isi **Environment Variables**:

| Key | Value |
|---|---|
| `APP_ENV` | `production` |
| `APP_DEBUG` | `false` |
| `DATABASE_URL` | connection string Neon (Langkah 2) |
| `DATABASE_SCHEMA` | `veloraai` |
| `SECRET_KEY` | string acak minimal 32 karakter (Render bisa generate) |
| `AI_PROVIDER` | `gemini` |
| `GEMINI_API_KEY` | key dari Langkah 1 |
| `PAYMENT_PROVIDER` | `manual` |
| `MANUAL_PAYMENT_INSTRUCTIONS` | contoh: `Transfer/GoPay ke 08xx-xxxx a.n Admin VeloraAi, lalu kirim bukti ke admin` |
| `PRO_PRICE_IDR` | `19900` |
| `MAX_PRICE_IDR` | `49900` |
| `RATE_LIMIT_STORAGE_URI` | `rediss://...` dari Upstash (Langkah 3) |
| `CORS_ORIGINS` | URL frontend Vercel, contoh `https://veloraai.vercel.app` (isi dulu, update setelah Langkah 5) |

5. **Create Web Service** → tunggu build & deploy (migrasi Alembic jalan
   otomatis via `docker-entrypoint.sh`).
6. Verifikasi: buka `https://<service>.onrender.com/api/v1/health` dan
   `/api/v1/ready` — keduanya harus `ok`.

> ⚠️ **Keterbatasan free tier Render:** service "tidur" setelah ±15 menit
> tanpa trafik, request pertama berikutnya lambat (±50 detik). Trik opsional:
> pasang ping gratis dari <https://cron-job.org> ke `/api/v1/health` tiap
> 10 menit agar tetap bangun.

> ℹ️ RAG worker (`python -m app.worker`) adalah service terpisah; di free tier
> boleh dilewati dulu — fitur chat tetap jalan, hanya indexing dokumen RAG
> yang tidak diproses otomatis.

## Langkah 5 — Frontend di Vercel

1. Daftar di <https://vercel.com> pakai GitHub → **Add New Project** → pilih repo.
2. **Root Directory:** `web`
3. Environment variable:

| Key | Value |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `https://<service>.onrender.com` (URL backend Langkah 4) |

4. **Deploy** → dapat URL seperti `https://veloraai.vercel.app`.
5. Kembali ke Render, update `CORS_ORIGINS` dengan URL Vercel ini → deploy ulang.

## Langkah 6 — Buat akun admin pertama

1. Register akun lewat aplikasi (atau `POST /api/v1/auth/register`).
2. Di SQL Editor Neon, jalankan:

```sql
UPDATE veloraai.users SET role = 'admin' WHERE email = 'email-kamu@example.com';
```

Login ulang di aplikasi → akunmu sekarang bisa menyetujui pembayaran manual.

## Langkah 7 — Alur pembayaran manual

1. User pilih paket → dapat `order_id` + instruksi transfer.
2. User transfer & kirim bukti ke admin (WhatsApp/Telegram).
3. Admin cek bukti → setujui lewat endpoint admin:

```text
POST /api/v1/payments/{payment_id}/approve   (login sebagai admin)
```

4. Subscription & role user (`pro`/`max`) aktif otomatis.

---

## Biaya & batasan ringkas

- **Total: Rp0.** Semua di atas free tier.
- Batasan utama: Render free tidur saat idle (solusi: cron ping), dan
  performa terbatas — cukup untuk tahap validasi & user pertama.
- Kalau nanti sudah ada pendapatan dari paket Pro/Max, naik ke Railway +
  Postgres managed agar tanpa sleep.
