# Durable RAG worker

Dokumen yang dibuat melalui `POST /api/v1/rag/documents` atau `/upload` disimpan dengan status `queued`. Indexing tidak lagi dijalankan sebagai FastAPI in-process background task, karena task tersebut dapat hilang ketika web process restart atau crash.

Jalankan satu atau lebih proses worker terpisah dengan command berikut:

```bash
python -m app.worker
```

Worker mengambil dokumen `queued` secara berkala dan memanggil `process_document_index()`. Jika worker mati setelah dokumen berubah ke `processing`, dokumen akan dikembalikan ke `queued` setelah `RAG_PROCESSING_STALE_SECONDS`. Claim dokumen tetap atomic melalui update status bersyarat di `app/services/rag_jobs.py`, sehingga beberapa worker tidak seharusnya memproses dokumen yang sama secara bersamaan.

## Deployment contract

| Process | Command | Scaling guidance |
|---|---|---|
| Web | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | Jalankan sesuai kebutuhan HTTP traffic. |
| RAG worker | `python -m app.worker` | Mulai dari satu worker; tambah worker setelah database/provider capacity diuji. |

Kedua process harus memakai `DATABASE_URL`, `DATABASE_SCHEMA`, embedding provider credentials, dan setting aplikasi yang sama. Worker harus memiliki akses ke database dan embedding provider, tetapi tidak membutuhkan credential browser atau tool platform. Observability deployment sebaiknya memonitor jumlah dokumen `queued`, `processing`, dan `failed`, durasi indexing, serta error provider.

`RAG_PROCESSING_STALE_SECONDS` harus lebih panjang dari timeout indexing normal. Nilai terlalu kecil dapat merequeue indexing yang sebenarnya masih berjalan; nilai terlalu besar memperlambat recovery setelah crash.

## Retry policy

Indexing failure akan dikembalikan ke status `queued` sampai `RAG_MAX_INDEX_ATTEMPTS` tercapai. Nilai default adalah tiga percobaan. Setelah batas tercapai, dokumen menjadi `failed` dan menyimpan nama exception pada `last_index_error`; operator dapat memperbaiki provider lalu menjalankan reindex dari endpoint aplikasi. Monitoring sebaiknya memberi alert untuk jumlah dokumen `failed`, `queued` yang menua, dan worker process yang tidak mengirim log heartbeat.
