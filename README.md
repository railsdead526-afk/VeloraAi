# VeloraAi

VeloraAi adalah backend AI API berbasis FastAPI untuk autentikasi pengguna, percakapan, AI chat, streaming response, pencatatan penggunaan AI, RAG, dan tool execution terisolasi.

## Status arsitektur

- Backend production target: **Railway**
- Frontend target: **Vercel**
- Production database: **PostgreSQL**
- Production shared rate limiting: **Redis-compatible storage**
- AI providers: **OpenAI, Llama-compatible, mock untuk development/test**
- Terminal/tool execution: **dedicated isolated sandbox service**
- Payments: **Midtrans**, sandbox untuk development dan live endpoints hanya untuk production

## Fitur

- User registration dan login
- JWT authentication
- Ownership-based conversation access control
- Conversation CRUD
- Message history
- AI chat dengan bounded context
- AI retry dan timeout
- Streaming AI melalui Server-Sent Events (SSE)
- AI usage/token tracking
- RAG document indexing dan search
- Capability-based tool policy
- Risk-aware tool approval
- Isolated terminal sandbox
- PostgreSQL support
- Alembic database migrations
- API rate limiting
- Production configuration validation
- Health dan readiness endpoints
- Automated tests dan GitHub Actions CI

## Tech Stack

- FastAPI
- Pydantic v2
- SQLAlchemy
- PostgreSQL / SQLite untuk development dan test
- Alembic
- HTTPX
- SlowAPI
- JWT
- Pytest
- Docker

## Setup development

```bash
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Development dapat menggunakan SQLite dan `AI_PROVIDER=mock`. Production **tidak boleh** memakai mock provider, SQLite, in-memory rate limiting, atau endpoint Midtrans sandbox.

## Production

Backend dideploy ke Railway menggunakan `Dockerfile` dan `railway.toml`. Railway melakukan health check pada `/api/v1/health`.

Production wajib menyediakan:

- PostgreSQL `DATABASE_URL`
- Redis-compatible `RATE_LIMIT_STORAGE_URI`
- Strong `SECRET_KEY`
- Real AI provider credentials
- CORS origins production yang eksplisit
- Midtrans live credentials dan live endpoints
- Nilai Pro/Max yang nyata, bukan `0`
- `TERMINAL_SANDBOX_URL` dan `TERMINAL_SANDBOX_TOKEN`

Jangan simpan secret deployment di repository.

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
  tools/
  main.py

sandbox-service/
  app/
  tests/

alembic/
  versions/

tests/
.github/
  workflows/
```

## Security

Baseline audit dan pekerjaan yang tersisa dicatat di `docs/hardening-plan.md`.
