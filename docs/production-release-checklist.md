# Production release checklist

Release VeloraAi hanya boleh dilanjutkan setelah semua item **Required** selesai dan dibuktikan dengan output atau link evidence. Test lokal tidak menggantikan verifikasi environment deployment.

## Required code and CI checks

| Check | Evidence | Status |
|---|---|---|
| Backend tests | `pytest -q tests` | Required |
| PostgreSQL migrations and full backend tests | CI job `postgres-migrations` | Required |
| Frontend lint/build | `npm run lint` dan `npm run build` | Required |
| Dependency audit | `pip-audit -r requirements.txt` dan `npm audit --omit=dev` | Required |
| Migration head | `alembic current` menunjukkan head | Required |

## Required deployment checks

| Area | Verification |
|---|---|
| Web process | Health endpoint dapat diakses dan deployment restart policy aktif. |
| RAG worker | Proses `python -m app.worker` berjalan sebagai service terpisah dengan database/provider secret yang sama. |
| Sandbox | Sandbox service berada pada host/runtime terpisah; network isolation, capability drop, no-new-privileges, read-only root, dan resource limits diverifikasi dari runtime, bukan hanya Dockerfile. |
| Database | PostgreSQL schema benar, Alembic dijalankan sebelum traffic, dan `/api/v1/ready` mengembalikan `status=ready`. |
| Rate limit | `RATE_LIMIT_STORAGE_URI` menunjuk Redis/shared store; `TRUSTED_PROXY_IPS` hanya berisi proxy network yang terdokumentasi; behavior diuji dari minimal dua web instance bila autoscaling aktif. |
| Secrets | API key, JWT secret, Midtrans key, sandbox token, dan provider credentials berasal dari deployment secret manager. Tidak ada secret di Git. |

## Non-destructive smoke test

Setelah web deployment aktif, jalankan:

```bash
python scripts/production_smoke_test.py https://api.example.com
```

Script hanya memanggil health/readiness endpoint. Smoke test provider AI, Midtrans, dan sandbox harus dijalankan sebagai test terkontrol pada staging dengan credential staging dan nominal/payment method yang aman. Jangan menjalankan payment smoke test memakai akun customer production tanpa prosedur finance approval.

## Backup and recovery

Sebelum go-live, ambil backup database, lakukan restore ke environment terisolasi, jalankan migration/readiness check, dan verifikasi user, conversation, payment, document metadata, serta audit log. Catat waktu restore dan recovery point. Jadwalkan drill berkala; backup yang belum pernah direstore bukan evidence recovery.

## Go-live approval

Go-live membutuhkan persetujuan engineering untuk CI dan deployment, security untuk secret/sandbox/auth review, serta owner bisnis/finance untuk pricing, Midtrans mode, refund flow, dan webhook reconciliation. Jika worker, backup restore, provider smoke test, atau monitoring belum tervalidasi, status release tetap **blocked**.
