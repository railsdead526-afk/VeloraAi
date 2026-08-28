# VeloraAi

VeloraAi adalah backend AI API berbasis FastAPI untuk autentikasi pengguna, percakapan, AI chat, streaming response, dan pencatatan penggunaan AI.

## Fitur

- User registration dan login
- JWT authentication
- Ownership-based conversation access control
- Conversation CRUD
- Message history
- AI chat dengan bounded context
- AI retry dan timeout
- Multi-provider AI: OpenAI, Gemini (via endpoint OpenAI-compatible), Llama, mock
- Pembayaran manual dengan persetujuan admin (tanpa gateway, tanpa kartu kredit)
- Streaming AI melalui Server-Sent Events (SSE)
- AI usage/token tracking
- PostgreSQL support
- Alembic database migrations
- API rate limiting
- Production configuration validation
- Health dan readiness endpoints
- Automated tests dan GitHub Actions CI

## Tech Stack

- FastAPI
- SQLAlchemy
- PostgreSQL / SQLite untuk development dan test
- Alembic
- Pydantic
- HTTPX
- SlowAPI
- JWT
- Pytest

## Setup

```bash
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Untuk production, gunakan PostgreSQL, shared rate-limit storage, `SECRET_KEY` yang kuat, dan konfigurasi AI provider yang valid. Jangan aktifkan debug di production.

Pilih AI provider lewat `AI_PROVIDER`: `gemini` (Google Gemini via endpoint OpenAI-compatible, set `GEMINI_API_KEY`), `openai`, `llama`, atau `mock`. Upgrade dari Gemini ke OpenAI cukup ganti env tanpa mengubah kode.

Pembayaran: set `PAYMENT_PROVIDER=manual` untuk mode manual — user mendapat instruksi transfer, lalu admin menyetujui pembayaran lewat `POST /api/v1/payments/{payment_id}/approve` sehingga langganan dan role user diaktifkan otomatis. Set `PAYMENT_PROVIDER=midtrans` untuk kembali ke Snap gateway.

## Database Migration

```bash
alembic upgrade head
```

Migration membaca `DATABASE_URL` dari environment jika tersedia.

## Run Tests

```bash
python -m pytest -v
```

Dengan coverage:

```bash
python -m pytest -q --cov=app --cov-report=term-missing
```

## API Utama

```text
GET  /api/v1/health
GET  /api/v1/ready

POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me

POST   /api/v1/conversations
GET    /api/v1/conversations
PATCH  /api/v1/conversations/{conversation_id}
DELETE /api/v1/conversations/{conversation_id}

GET  /api/v1/conversations/{conversation_id}/messages
POST /api/v1/conversations/{conversation_id}/messages
POST /api/v1/conversations/{conversation_id}/messages/stream
```

## Struktur Project

```text
app/
  api/
  core/
  crud/
  models/
  schemas/
  services/
  main.py

alembic/
  versions/

tests/
.github/
  workflows/
```

## Catatan

- Database file lokal dan secrets tidak boleh di-commit.
- Production wajib menggunakan secret dan shared rate-limit storage yang sesuai.
- Migration dijalankan melalui Alembic, bukan `create_all()` saat startup.
- Deployment platform belum dikunci. Railway adalah kandidat yang cocok untuk backend FastAPI + PostgreSQL + Redis.
