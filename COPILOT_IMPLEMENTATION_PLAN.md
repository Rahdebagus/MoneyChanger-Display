# Instruksi Copilot — PAM Rate Board & Remote Display

## 1. Tugas dan cara bekerja

Baca seluruh dokumen ini, instruksi repository (termasuk AGENTS.md bila ada), README, manifest dependensi, dan kode aktual sebelum mengubah apa pun. Bertindak sebagai engineer yang mengimplementasikan fitur sampai selesai, bukan hanya memberi saran. Kerjakan bertahap, verifikasi setiap tahap, lalu lanjutkan tanpa meminta konfirmasi untuk pilihan implementasi rutin.

Dokumen ini adalah spesifikasi; struktur dan nama file yang disebut merupakan usulan, bukan klaim bahwa repository sudah diaudit. Gunakan kode aktual sebagai sumber kebenaran. Jika kredensial/server belum tersedia, selesaikan kode dan dokumentasi lokal, lalu laporkan konfigurasi yang masih dibutuhkan. Jangan mengaku fitur sudah diuji jika belum dijalankan.

Tujuan:
1. Mempertahankan generator rate yang sekarang sudah disukai pemilik.
2. Menambahkan login admin/staf, penyimpanan versi rate, dan display jarak jauh.
3. Merapikan folder, penamaan, dependensi, dokumentasi, serta file tidak terpakai.
4. Mengoptimalkan tanpa mengubah desain board atau merusak fitur lama.

Stack tetap Python FastAPI + ReactJS. Tambahkan MySQL, SQLAlchemy, dan Alembic. Jangan migrasi backend ke Node.js atau rewrite frontend ke framework lain.

## 2. Batas perubahan yang wajib dipatuhi

- Pertahankan alur Upload Image → OCR → Edit Rates → Generate → Download PNG/MP4.
- Pertahankan logo, font, warna, ukuran canvas, tabel, bendera, posisi, spacing, format angka, animasi, dan kualitas ekspor board yang sudah ada.
- Jangan menggambar ulang rate board dengan HTML/CSS. Player memakai file PNG/MP4 keluaran generator asli.
- Fitur lama seperti pilihan 3 crop/1 full image, upload logo, judul/company name, nilai turunan USD T/USD K, dan edit manual harus tetap berfungsi sesuai implementasi aktual.
- Tambahkan navigasi/halaman admin seperlunya dengan gaya aplikasi yang sama. Jangan redesign halaman generator.
- Jangan mengubah rumus rate, parsing, pemisah angka, atau nilai kosong menjadi nol tanpa alasan yang dibuktikan oleh bug.
- Jangan auto-upgrade major version dependensi. Konteks terakhir: Python 3.10, PaddleOCR 2.7.3 dan PaddlePaddle 2.6.2 sedang dicoba setelah 3.3.1 menyebabkan masalah. Verifikasi kombinasi aktual lewat smoke test sebelum menguncinya; jangan menganggap perbaikan telah terbukti berhasil.
- Jangan hardcode absolute path laptop. Semua path asset berasal dari lokasi modul/config, semua secret berasal dari environment.

## 3. Audit dan baseline sebelum refactor

1. Periksa git status dan perubahan pengguna. Jangan reset, checkout paksa, atau menimpa perubahan yang belum di-commit. Buat branch kerja jika sesuai kondisi repo; jangan otomatis commit secret atau seluruh file dengan git add .
2. Inventaris entrypoint, API, import, aset dinamis, font, generator, scripts, Dockerfile, manifest, config, dokumentasi, serta ukuran folder besar. Abaikan venv/node_modules ketika pencarian kode.
3. Catat perintah menjalankan frontend/backend yang benar dan versi runtime yang terpakai.
4. Jalankan baseline yang tersedia. Simpan fixture rate sintetis dan output board sebelum perubahan sebagai referensi visual. Gunakan input identik setelah refactor.
5. Buat docs/implementation-status.md berisi tahap, asumsi, hasil audit, progres, dan kendala. Update selama pengerjaan supaya bisa dilanjutkan lintas sesi.
6. Untuk file yang tidak ada di Git, backup konten unik sebelum pembersihan. Backup berada di lokasi lokal yang jelas di luar folder yang akan dihapus; jangan masukkan database/secret ke Git.

## 4. Struktur folder dan penamaan

Adaptasikan struktur berikut terhadap repo aktual. Jangan membuat lapisan kosong atau duplikat modul hanya demi mengikuti contoh.

| Lokasi | Tanggung jawab |
| --- | --- |
| backend/app/main.py | App factory/entrypoint dan registrasi router |
| backend/app/core/ | Config, security, logging |
| backend/app/db/ | Engine/session/base |
| backend/app/models/ | Model database |
| backend/app/schemas/ | Request/response validation |
| backend/app/api/routes/ | Auth, rates, displays, publications, branches, jobs |
| backend/app/services/ | OCR, parser, generator, publishing, pairing, storage |
| backend/app/workers/ | Worker job dan scheduler jika diperlukan |
| backend/assets/ | Font, logo, template, bendera yang digunakan |
| backend/migrations/ | Alembic migrations |
| backend/tests/ | Regression dan integration test bernilai nyata |
| frontend/src/features/ | Generator, auth, history, displays, branches, users |
| frontend/src/components/ | Komponen bersama yang benar-benar reusable |
| frontend/src/services/ | HTTP client dan API access |
| frontend/src/hooks/ | Shared hooks |
| frontend/src/pages/ | Route-level composition jika dibutuhkan |
| scripts/ | Setup/run/maintenance scripts |
| docs/ | Architecture, deployment, operasi, cleanup report |
| storage/ | File runtime; ignored Git dan durable volume saat deploy |

Python: snake_case untuk modul/fungsi, PascalCase untuk class. React: PascalCase untuk komponen, useX untuk hooks. Konsisten pada naming JS yang sudah dominan; jangan migrasi JS ke TS hanya untuk refactor ini. Environment variable UPPER_SNAKE_CASE. API route konsisten dengan resource plural.

Update seluruh import, Docker CMD, test, VS Code config, script, dan README ketika memindahkan main.py. Jika entrypoint menjadi app.main:app, perintah Uvicorn harus ikut berubah. Jangan meninggalkan dokumentasi main:app yang sudah tidak benar. Pertahankan API lama atau adapter sementara sampai semua pemanggil telah diperbarui.

## 5. Cleanup yang benar-benar terverifikasi

Lakukan cleanup awal untuk cache yang aman; cleanup kode/aset final setelah implementasi dan regression check.

- Periksa penggunaan file melalui import, string/path dinamis, konfigurasi, scripts, Docker, tests dan dokumentasi. Hasil pencarian import kosong saja bukan bukti aset tidak dipakai.
- Hapus dead code, file contoh, output sementara, duplikat dan dependensi hanya jika sudah terbukti tidak dibutuhkan.
- Jangan hapus preview_board.png, preview_generator.py, font, bendera atau template hanya berdasarkan namanya. Bisa menjadi fixture atau bagian generator; pindahkan sesuai fungsi bila masih diperlukan.
- Rapikan dokumen Markdown duplikat dengan mempertahankan informasi unik dan memperbarui link. Jangan hapus instruksi repository/Copilot yang masih berlaku.
- __pycache__, .pyc, cache test/lint dan build sementara boleh dibersihkan jika tidak sedang dipakai. Jangan menghapus hasil publikasi atau build yang sedang disajikan.
- Audit .venv, backend/venv, venv_old. Pertahankan satu environment aktif. Hapus yang lama hanya setelah memastikan tidak aktif, dependensi dapat direproduksi, dan aplikasi berjalan dengan environment terpilih. Jangan menyalin/memindahkan venv antar lokasi.
- node_modules bukan dead code. Keluarkan dari Git/deployment context; hapus/reinstall hanya jika diperlukan dan lockfile valid. Pertahankan lockfile.
- Jangan menghapus .env, .git, database, upload pengguna, file rate tersimpan, model OCR aktif, atau data unik. Retensi data pengguna harus berupa kebijakan eksplisit.
- Tidak boleh git clean -fdx, penghapusan wildcard luas, atau mematikan antivirus sebagai solusi cleanup.
- Tambahkan .gitignore dan .dockerignore yang sesuai. Jangan men-track venv, node_modules, secret, upload atau cache model. Bila sudah tracked, tangani index secara terarah tanpa menghilangkan file kerja yang dibutuhkan.
- Buat docs/cleanup-report.md: path lama/baru, tindakan, bukti tidak dipakai, ukuran sebelum/sesudah jika diukur. Bedakan penghematan disk dari peningkatan performa runtime.

## 6. Model data dan integritas

Gunakan MySQL dengan migration Alembic. Bila layanan lokal ternyata MariaDB dari XAMPP, catat versi dan validasi kompatibilitas; jangan menyebutnya MySQL tanpa pengecekan.

| Entitas | Data minimum |
| --- | --- |
| users | id, identity, password_hash, role, active, timestamps |
| branches | id, name, timezone, active |
| user_branches | akses staf ke cabang |
| rate_boards | id, title, owner/branch scope |
| rate_versions | board_id, version, status, creator, timestamp, snapshot config/assets, generated media |
| rate_items | version_id, currency, denomination, DECIMAL value nullable, order, display formatting bila diperlukan |
| media_assets | storage key, MIME, checksum, dimensions, size, status |
| displays | branch_id, name, credential hash, last_seen, desired/reported revision, health |
| pairing_codes | code hash, expiry, consumed_at, device session binding |
| publications | target display, version_id, revision, state, effective/expiry times, creator |
| jobs | type, status, progress, attempts, failure info, timestamps |
| audit_logs | actor, action, target, before/after metadata yang aman, timestamp |

- Simpan rate sebagai DECIMAL dengan precision/scale yang sesuai data nyata, bukan float. JSON/API kirim string desimal jika perlu untuk menjaga presisi. Nilai '-' berbeda dari 0.
- Simpan angka terstruktur, urutan, denominasi, konfigurasi visual dan referensi aset versi tersebut. Edit ulang membuat versi baru; tidak menimpa hasil yang sedang tayang.
- Media di durable file storage, database menyimpan metadata/lokasi. Jangan pakai satu nama preview_board.png bersama untuk semua pengguna; gunakan ID unik dan immutable media URL per versi.
- Generate & Save berhasil hanya jika media selesai dibuat dan versi berstatus ready. Jangan publish versi gagal/pending. Tangani file orphan akibat kegagalan transaksi dengan cleanup terarah.
- Timestamp disimpan UTC; tampilkan/jadwalkan menggunakan Asia/Makassar untuk Bali secara default.
- Gunakan FK, unique constraint version per board, index untuk history/branch/status/schedule dan pagination.
- Publikasi bersamaan memakai transaksi dan revision monotonik; cegah update lama menggantikan update baru. Publish ulang request yang sama harus idempotent.
- Versi yang sedang direferensikan display/jadwal tidak boleh dihapus. Gunakan archive untuk riwayat yang masih dibutuhkan.

## 7. Role dan autentikasi

Admin: kelola akun, cabang, rate, display, jadwal dan publikasi.
Staf: lihat/download rate dan status display hanya cabang yang ditugaskan; dapat membuat draft, tidak publish secara default.
Device: hanya pairing, mengambil assignment/media yang diizinkan, heartbeat dan acknowledgement; tidak boleh mengakses admin API.

Implementasikan authorization di backend setiap request, termasuk media, websocket dan pembatasan objek lintas cabang. Jangan hanya menyembunyikan tombol frontend. Password di-hash, login/pairing diberi rate limit, secret tidak dicatat ke log. Pilih mekanisme session/token yang sesuai origin deployment; jika memakai cookie, atur HttpOnly/Secure/SameSite dan proteksi CSRF untuk operasi mutasi. Hindari token rahasia di URL.

Sediakan bootstrap admin melalui command interaktif/env sekali pakai, bukan password default di source. Sertakan .env.example tanpa secret. Tidak ada register publik secara default.

## 8. Alur rate dan halaman admin

Tetap gunakan generator lama. Tambah tombol Generate & Save dan Tampilkan ke Display di tahap hasil tanpa menghapus Download PNG/MP4.

Alur: upload atau buka riwayat → edit → validasi → preview/generate → simpan versi ready → pilih display/cabang → publish. Editing/saving tidak langsung mengganti display.

Tambahkan halaman:
1. Dashboard: jumlah display online/offline, rate aktif dan perubahan terakhir.
2. Rate History: preview, pembuat, waktu, versi, filter/pagination, buka sebagai versi baru, download, archive.
3. Displays: pairing, nama/cabang, online/offline, last seen, desired vs reported version, publish, refresh player, revoke.
4. Branches dan Users: admin only.
5. Activity: riwayat publish/edit/rollback.

Gunakan API client terpusat, status loading/error yang jelas, validasi rate nonnegatif/format yang sesuai domain, serta pesan error aman. Jangan tampilkan full Python traceback/path internal di UI; log server memakai request ID.

## 9. Pairing dan player display

- Route /display menampilkan kode pairing sementara sebelum terdaftar. Admin memasukkan kode pada dashboard dan memilih nama/cabang.
- Kode sekali pakai, memiliki expiry, dibatasi percobaannya, dan ditukar secara atomik dengan credential device yang scoped/revocable. Jangan menaruh akun admin di TV.
- Setelah pairing, tampilkan PNG/MP4 generator fullscreen secara proporsional memakai contain; jangan stretch/crop, menambah watermark, ticker atau elemen ke desain board.
- Fullscreen melalui interaksi awal pengguna atau kiosk setup. Jangan menjanjikan browser otomatis masuk fullscreen tanpa izin. MP4 muted/loop/playsInline; sediakan fallback jika format tidak didukung.
- Saat update: ambil assignment → download media → validasi file/decode/load → pindah tampilan secara atomik → kirim acknowledgement berisi publication revision dan version ID.
- PNG acknowledgement setelah decode dan dipasang; MP4 setelah siap/dapat diputar. Acknowledgement bukan bukti panel TV fisik menyala.
- Media yang gagal tidak mengganti tampilan terakhir. Laporkan kegagalan ke admin, retry dengan backoff, abaikan assignment yang lebih lama.
- WebSocket memberitahu perubahan. Database tetap sumber kebenaran; reconnect/startup/poll fallback selalu meminta assignment aktif terbaru.
- Default awal yang bisa dikonfigurasi: heartbeat 30 detik, offline setelah 90 detik tanpa heartbeat, fallback polling 30 detik, backoff dengan jitter.
- Gunakan Cache Storage/IndexedDB dan bila perlu service worker untuk app shell/media offline, dengan batas ukuran dan eviction yang menjaga media aktif. Memory/localStorage saja bukan cache offline yang memadai untuk MP4.
- Default offline: teruskan media terakhir yang masih berlaku, tandai stale/offline di dashboard. Bila ada valid_until dan telah lewat, tampilkan halaman netral 'Rate sedang diperbarui'. Expiry null berarti tetap tampil sampai diganti; pilihan ini harus jelas di admin.
- Offline pertama kali tanpa media: layar informasi yang jelas, bukan board kosong. Uji reload saat offline dan reconnect.
- Revoke device menghentikan akses server saat tersambung; perangkat yang offline tidak bisa menerima revoke seketika. Jelaskan keterbatasan ini.

## 10. Publikasi jarak jauh, jadwal dan rollback

Admin dapat publish ke satu display, beberapa display, atau seluruh cabang yang diizinkan. Resolve target cabang menjadi daftar device saat publish; device yang ditambahkan kemudian harus mendapat assignment eksplisit, agar perilaku tidak ambigu.

Status per perangkat: pending/download/loading/displayed/failed/offline. Pisahkan desired version dari reported version. Jangan menandai seluruh batch sukses hanya karena server menerima permintaan.

Rollback membuat publikasi baru yang menunjuk versi ready sebelumnya; tetap ada log dan revision baru. Refresh player adalah perintah one-shot ber-ID dengan acknowledgement, tidak menyebabkan reload loop. Tidak mengklaim dapat menyalakan TV atau restart OS dari browser.

Tambahkan jadwal publish dan pembatalan jadwal, menggunakan waktu server. Scheduler harus tahan restart, tidak menjalankan job dua kali, dan bekerja sekali secara efektif walau worker lebih dari satu. Jika konflik jadwal, aturan urutan deterministik dan terlihat di admin. Manual publish mengganti assignment saat ini; jadwal masa depan tetap aktif kecuali dibatalkan dengan jelas.

## 11. Optimasi yang relevan

- Pertahankan kualitas output. Jangan mengecilkan resolusi PNG/MP4 board utama demi skor performa; gunakan thumbnail terpisah untuk daftar riwayat.
- Jangan menjalankan OCR/generate MP4 di event loop atau setiap heartbeat. Gunakan worker terbatas dengan durable jobs, timeout, retry terkontrol dan recovery job setelah restart. API mengembalikan job ID untuk pekerjaan lama.
- Pilih satu mekanisme worker yang sederhana dan cukup untuk deployment. Jika menambah Redis/queue, sertakan konfigurasi dan jelaskan kebutuhan; jangan menambah banyak layanan tanpa alasan.
- Inisialisasi model OCR terkontrol per worker, periksa thread-safety; hindari load ulang model setiap request serta jumlah worker berlebihan yang menggandakan RAM.
- Job menggunakan working directory unik; concurrent generate tidak boleh menimpa file pengguna lain. Bersihkan temporary file pada success/failure secara aman.
- Pisahkan import berat OCR dari auth, health, history dan display bila memungkinkan. Cache output berdasarkan input/config/assets yang sama bila aman dan tetap mempertahankan metadata versi.
- Gunakan immutable media URL, checksum/ETag dan cache headers; player tidak mengunduh ulang file yang sama setiap polling.
- React route lazy-loading untuk admin/player, pagination history, cleanup websocket/timer, reconnect yang tidak membuat koneksi duplikat. Jangan mengirim library editor/OCR UI besar ke route player tanpa kebutuhan.
- Bila multi-process, jangan mengandalkan daftar websocket in-memory sebagai sumber broadcast lintas proses. Pakai fanout yang sesuai atau polling database yang benar; dokumentasikan batas konfigurasi awal.
- Ukur baseline dan hasil: waktu OCR/generate, ukuran bundle, RAM worker, ukuran repo tanpa dependency/cache, dan waktu pergantian display. Jangan mengarang klaim persentase peningkatan.

## 12. Kontrak API awal

Sesuaikan dengan API existing, gunakan prefix /api untuk endpoint baru jika belum ada konvensi. Dokumentasikan schema via OpenAPI.

- Auth: login, logout, me; admin user management.
- Boards: list/create; versions list/detail; generate job; download media; archive.
- Jobs: status/progress/error aman.
- Branches: list/create/update.
- Devices: initiate pairing (device), approve pairing (admin), claim credential (device), list/update/revoke (admin).
- Device authenticated: current assignment, heartbeat, acknowledgement, websocket events.
- Publications: create to targets, list/status, schedule/cancel, rollback, refresh command.
- Audit: paginated list with authorization.

Jangan mengekspos MySQL langsung ke frontend/TV. Konten media private harus tetap bisa dimuat player melalui akses scoped yang aman, termasuk saat signed URL kedaluwarsa dan perangkat reconnect.

## 13. Setup, deployment dan dokumentasi

- README ringkas: setup Windows PowerShell, environment Python yang dipilih, dependency install, migration, bootstrap admin, backend, worker, frontend, pairing TV.
- Buat .env.example untuk DATABASE_URL, secret/session config, origin/CORS, storage path, public URLs, heartbeat, job settings. Tidak berisi credential nyata.
- Update Dockerfile/.dockerignore; sediakan compose untuk API, worker/scheduler bila diperlukan, MySQL, volume media dan layanan queue jika dipilih. Python env/node_modules host tidak ikut image.
- Frontend production memakai build, backend tidak memakai --reload. HTTPS/WSS di reverse proxy, CORS origin spesifik, DB network privat, health checks dan durable volume.
- Dev boleh memakai localhost. Remote lintas lokasi membutuhkan hosting yang dapat diakses semua perangkat; jangan hardcode localhost pada production bundle.
- Sertakan operasi backup/restore untuk MySQL dan media sebagai satu set, serta pemeriksaan hasil restore. Jangan otomatis mem-publish ke internet atau mengubah server produksi hanya untuk menyelesaikan implementasi lokal.
- Sertakan troubleshooting OCR/version, port, migration, koneksi device dan offline browser. Jangan mematikan keamanan Windows sebagai solusi.
- Docs minimum: architecture.md, deployment.md, cleanup-report.md, implementation-status.md. Konsolidasikan dokumentasi lama yang relevan, jangan menumpuk file panduan berulang.

## 14. Tahapan implementasi

1. Audit repo, baseline visual/functional, lindungi perubahan pengguna.
2. Refactor folder/naming bertahap dan perbaiki entrypoint; smoke test fitur lama.
3. Database + migration + auth + role/cabang.
4. Penyimpanan versi/media + job generate + history + edit dari history.
5. Pairing + player + publikasi + desired/reported state + heartbeat.
6. Reconnect/cache offline + rollback + refresh + jadwal + audit.
7. Cleanup final + optimasi terukur + docs/deployment config.
8. Jalankan acceptance checks; perbaiki kegagalan sebelum menyatakan selesai.

Kerjakan dalam perubahan kecil yang dapat direview. Jangan berhenti setelah membuat skeleton, mock data atau TODO untuk fitur inti. Jika sesi harus berakhir, tulis status konkret dan perintah melanjutkan dalam implementation-status.md.

## 15. Acceptance checks wajib

- Fixture input identik menghasilkan desain board identik dengan baseline. Untuk timestamp/media metadata dinamis, bandingkan region/frame relevan dengan toleransi yang dijelaskan, bukan mengabaikan perbedaan layout.
- OCR mode lama, edit rate, USD T/K, custom logo/title dan download PNG/MP4 masih berfungsi.
- Dua generate bersamaan tidak menimpa file/output masing-masing.
- Save tidak mengganti display. Publish hanya menerima versi ready dan target yang berhak.
- Staf tidak bisa publish atau membaca cabang lain walau memanggil API langsung; device tidak bisa mengakses admin API.
- Pairing expired/used/revoked ditolak; login gagal tidak membocorkan secret.
- Edit versi tayang menghasilkan versi baru. Rollback dan publication log dapat ditelusuri.
- Dua display bisa menerima versi sama atau berbeda. Status desired/reported tidak dipalsukan.
- Update lama tidak mengganti update lebih baru; reconnect memperoleh versi terbaru; retry publish tidak menggandakan efek.
- Media gagal dimuat mempertahankan versi lama dan melaporkan failure.
- Offline reload bekerja dengan cache, expiry diterapkan, reconnect kembali sinkron.
- Jadwal tetap benar setelah restart, pembatalan bekerja, worker tidak publish ganda.
- Migration berhasil pada database baru dan jalur upgrade yang relevan tanpa drop data pengguna.
- Frontend build/lint dan test backend yang relevan lulus. Jalankan integration test MySQL, bukan hanya SQLite jika perilaku SQL penting.
- Instalasi bersih dari manifest/lock yang disediakan berhasil; import/Docker/README sesuai struktur final.
- Konfirmasi visual pada browser desktop dan satu perangkat display target bila tersedia. Jika TV fisik belum tersedia, catat sebagai verifikasi tertunda; jangan klaim kompatibilitas semua Smart TV.

## 16. Laporan akhir yang harus diberikan Copilot

Tuliskan perubahan yang benar-benar dibuat, struktur akhir, perintah setup/run yang persis sesuai repo, migration yang perlu dijalankan, cara bootstrap admin dan pairing display, hasil test/visual, daftar cleanup beserta alasan, hasil pengukuran optimasi, serta keterbatasan yang tersisa. Jangan mencetak secret. Tegaskan bagian desain generator yang telah dibandingkan dengan baseline.

Mulai sekarang dari audit repository, kemudian implementasikan urutan di atas sampai tuntas.
