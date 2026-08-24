# Panduan Launch Landing Page VeloraAi

Dokumen ini menjelaskan cara memakai landing page VeloraAi untuk validasi pelanggan pertama. Fokusnya bukan menambah fitur, melainkan memastikan calon pelanggan dapat memahami produk, menghubungi pemilik, dan masuk ke proses pilot 30 hari.

## 1. Kondisi yang sudah siap

Landing page publik tersedia di route `/`. Aplikasi AI yang sudah ada tetap tersedia di `/workspace`. CTA pada halaman publik menyediakan dua jalur kontak:

| Tombol | Tujuan |
|---|---|
| Email saya | Membuka email ke `railsdead526@gmail.com` dengan subjek `Velora pilot` |
| WhatsApp | Membuka chat ke nomor `085707203681` dengan pesan pembuka tentang pilot Velora |

Jangan menambahkan checkout atau sistem pembayaran otomatis pada tahap ini. Pilot pertama dapat disepakati secara manual melalui email atau WhatsApp setelah kebutuhan calon pelanggan dipahami.

## 2. Pemeriksaan lokal sebelum publikasi

Jalankan perintah berikut dari folder frontend:

```bash
cd web
npm install
npm run lint
npm run build
npm run dev
```

Buka `http://localhost:3000/` dan pastikan hero, penjelasan manfaat, use case, serta dua tombol CTA terlihat baik. Buka `http://localhost:3000/workspace` dan pastikan route aplikasi lama masih dapat diakses.

Uji CTA email dengan memastikan aplikasi email membuat draft ke `railsdead526@gmail.com`. Uji CTA WhatsApp dengan memastikan URL menggunakan nomor internasional `6285707203681`, tanpa tanda `+`, spasi, atau angka `0` pertama.

## 3. Publikasi dengan biaya serendah mungkin

Gunakan akun hosting yang sudah tersedia atau free tier yang mendukung Next.js. Jangan mengaktifkan paket berbayar sebelum ada pelanggan. Saat membuat project dari repository, gunakan pengaturan berikut:

| Pengaturan | Nilai |
|---|---|
| Root directory | `web` |
| Install command | `npm install` atau default provider |
| Build command | `npm run build` |
| Production branch | `growth/pilot-landing` selama PR #42 belum digabung; setelah merge gunakan `main` |
| Environment variables | Tidak ada yang wajib untuk CTA saat ini karena kontak sudah dikonfigurasi di halaman |

Setelah deploy, uji tiga URL berikut:

```text
https://DOMAIN-KAMU/
https://DOMAIN-KAMU/workspace
https://DOMAIN-KAMU/robots.txt
```

Periksa halaman dari ponsel. Pastikan tombol email dan WhatsApp dapat ditekan, tidak ada teks placeholder, dan halaman tidak menampilkan error di browser. Jika memakai domain sendiri, arahkan domain hanya setelah versi subdomain hosting berhasil diuji.

## 4. Rencana outreach 20 prospek

Jalankan outreach dalam empat gelombang agar pesan dapat diperbaiki berdasarkan respons. Jangan mengirim pesan massal yang sama persis. Setiap pesan harus menyebut alasan mengapa bisnis tersebut kemungkinan memiliki masalah dokumentasi atau SOP.

| Hari | Target | Aktivitas | Hasil yang dicatat |
|---|---:|---|---|
| 1 | 5 prospek | Kirim pesan pertama melalui WhatsApp, LinkedIn, atau email yang tersedia secara publik | Terkirim, dibalas, atau tidak tersambung |
| 2 | 5 prospek | Kirim pesan pertama gelombang kedua | Segmen dan masalah yang paling relevan |
| 3 | 5 prospek | Kirim pesan pertama gelombang ketiga | Keberatan dan pertanyaan umum |
| 4 | 5 prospek | Kirim pesan pertama gelombang keempat | Prospek dengan urgensi tertinggi |
| 5–7 | Semua yang merespons | Lakukan discovery call 15–20 menit | Masalah, dokumen, frekuensi pertanyaan, dan keputusan pembelian |
| 8–10 | Prospek tertarik | Kirim ringkasan pilot dan tawarkan satu use case | Ada atau tidaknya komitmen pilot |
| 11–14 | Prospek belum menjawab | Kirim satu follow-up singkat | Alasan tidak merespons |
| 15–30 | Prospek yang cocok | Jalankan pilot pertama dan ukur hasil | Bukti manfaat serta keputusan lanjut |

Target awal yang realistis adalah **satu pilot berbayar**, bukan jumlah pendaftar yang besar. Jika tidak ada yang bersedia berbicara setelah 20 outreach yang dipersonalisasi, ubah segmen atau pesan penawaran sebelum mengubah produk.

## 5. Kolom pencatatan pipeline

Gunakan file `docs/outreach-tracker.csv` sebagai template. File tersebut dapat diimpor ke Google Sheets, Excel, atau aplikasi spreadsheet lain. Jangan memasukkan kata sandi, isi dokumen pelanggan, token API, atau data pribadi yang tidak diperlukan ke dalam repository publik.

Kolom minimum yang perlu diisi adalah nama bisnis, segmen, kontak publik, tanggal pesan, status, masalah dokumentasi, follow-up berikutnya, dan hasil akhir. Status yang disarankan adalah `Belum dihubungi`, `Pesan terkirim`, `Membalas`, `Discovery terjadwal`, `Pilot ditawarkan`, `Pilot berjalan`, `Berbayar`, atau `Tidak cocok`.

## 6. Urutan legal dan biaya

Gunakan VeloraAi sebagai nama produk terlebih dahulu. Jangan menyatakan bahwa VeloraAi adalah PT sebelum badan usaha benar-benar didaftarkan. Pertimbangkan badan usaha ketika ada pelanggan yang membutuhkan kontrak atau invoice resmi, ketika pilot mulai berbayar secara berulang, atau ketika ada pihak lain yang akan bergabung sebagai pemilik.

Sebelum mendaftarkan nama, lakukan pengecekan ketersediaan nama badan usaha, domain, akun media sosial, dan merek. Pendaftaran badan usaha, NIB, pajak, kontrak, dan pendaftaran merek harus dikonfirmasi berdasarkan kondisi aktual pengguna; dokumen ini bukan pengganti nasihat notaris atau konsultan hukum.

## 7. Definisi berhasil dalam 30 hari

Validasi awal dianggap berhasil jika setidaknya satu tim bersedia membayar pilot, memberikan akses atau contoh dokumen yang aman, menggunakan workspace pada use case yang disepakati, dan memberikan evaluasi setelah periode pilot. Jika hasilnya belum tercapai, kesimpulan yang dicari bukan bahwa VeloraAi gagal, melainkan bagian mana yang harus diperbaiki: segmen, masalah, pesan, alur onboarding, atau nilai yang ditawarkan.
