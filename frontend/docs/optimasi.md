# Riwayat dan sinkronisasi display

## Penghapusan riwayat

Admin dapat memilih **Hapus** pada kartu Riwayat Rate dan mengonfirmasi
penghapusan permanen. Versi yang sedang diproses, dijadwalkan, ditugaskan ke
display, atau masih dilaporkan tampil oleh display tidak dapat dihapus.
Ganti tayangan dan tunggu display mengonfirmasi versi baru terlebih dahulu.

Database menghapus versi dan mencatat pekerjaan `cleanup_media` dalam satu
transaksi. Worker kemudian membersihkan PNG, thumbnail, MP4 dan logo yang
sudah tidak digunakan. Logo bersama dipertahankan selama masih dipakai versi
lain. Catatan audit penghapusan tetap tersedia. Arsip hanya menyembunyikan
versi; **Hapus** yang membebaskan penyimpanan.

API dan worker harus sama-sama menjalankan kode terbaru. Jalankan worker
dari folder `backend` dengan `python -m app.workers.runner`. Kegagalan file
sementara dicoba ulang sesuai batas percobaan job; kegagalan akhir muncul
pada ringkasan job dashboard dan log worker. Tidak ada penghapusan otomatis
berdasarkan umur riwayat.

## Display

- Publikasi baru memberi pemberitahuan melalui WebSocket.
- Display memeriksa assignment setiap **5 menit** tanpa reload halaman.
- Heartbeat ringan setiap **30 detik** melaporkan koneksi dan mendeteksi
  pembaruan yang pemberitahuannya terlewat.
- Revisi yang sama menggunakan gambar yang sudah tersedia. Tidak ada
  pengunduhan dan konfirmasi ulang terus-menerus.
- Konfirmasi tayangan yang gagal terkirim dicoba lagi pada heartbeat.
- Saat offline, gambar terakhir tetap tampil selama belum kedaluwarsa.

Interval ada di `src/features/player/PlayerPage.jsx`; default yang diumumkan
backend ada di `backend/app/core/config.py`. Jaga keduanya selaras jika diubah.

## Pengurangan pekerjaan server

Dashboard dan daftar display diperbarui setiap 60 detik. Polling admin berhenti
saat tab tersembunyi atau offline. Request tidak ditumpuk dan request lama
dibatalkan ketika halaman/filter berubah. Thumbnail tetap terpasang saat data
disegarkan, sehingga tidak diunduh ulang hanya karena polling.

Daftar display mengambil relasi secara berkelompok. Dashboard menghitung status
melalui query agregat. Event pump menunggu tanpa polling SQL ketika tidak ada
klien WebSocket. Event lama dibersihkan maksimal 1.000 baris per maintenance;
pemindaian file sementara berlangsung paling sering sekali per jam.

## Verifikasi

Dari folder frontend:

```powershell
npm run lint
npm test
npm run build
```

Tes backend dijalankan dengan `python -m pytest tests -q` dari folder backend.
**Set `TEST_DATABASE_URL` ke database khusus pengujian** dan `STORAGE_DIR` ke
folder khusus pengujian: fixture backend menghapus tabel database tersebut.
Jangan gunakan database atau penyimpanan aplikasi utama.

Pengujian browser dilakukan pada salinan database dan storage: hapus/batal
hapus, proteksi tayangan aktif, unduh PNG, pembersihan worker, sinkronisasi
5 menit, publikasi realtime, pemulihan konfirmasi, dan tampilan saat offline.
