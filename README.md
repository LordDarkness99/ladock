# LaDock — Universal Application Docker Automation v3.0

Otomasi modern untuk men-deploy aplikasi web dan hasil migrasi cPanel ke Docker secara instan — mendukung mode **Monolith** maupun **Microservices**, dengan **layout folder bersih**, **deteksi stack luas**, **manajemen database sentral**, dan **Web Control Center**.

---

## 🌟 Fitur Utama

1. **Dukungan Ekstraksi Arsip Universal**:
   - Ekstraksi otomatis arsip **`.zip`**, **`.tar.gz`**, **`.tgz`**, dan **`cpmove`**.
   - Validasi integritas berkas (corrupt check).
   - Pencegahan kerentanan keamanan **Path Traversal / Zip-Slip** (`../`).
2. **Deteksi Stack & Dependensi Komprehensif (`stack.json`)**:
   - Bahasa/Runtime: PHP, Node.js, Python, Go, Ruby, Java.
   - Framework: Laravel, CodeIgniter, Symfony, WordPress, Express, Next.js, Django, Flask, dll.
   - Package manager: Composer, npm, yarn, pnpm, pip, poetry, bundler, go modules.
   - Versi runtime, ekstensi PHP yang dibutuhkan, web server, dan jenis database tersimpan di `stack.json`.
3. **Restrukturisasi Folder Hasil Deployment yang Bersih**:
   - Tidak lagi mengotori folder dengan berkas hidden `.docker/` atau `.docker-compose-app.yml`.
   - Kode aplikasi tertata rapi di dalam subfolder `src/`.
   - `docker-compose.yml`, `Dockerfile`, `apache-vhost.conf`, `.dockerignore`, `.env`, `stack.json`, dan `logs/` berada di root aplikasi.
   - File sementara seperti `.env.bak` tidak lagi dibuat/ditinggalkan.
4. **Penyimpanan Database Sentral Terstruktur**:
   - Data fisik MySQL tetap tersimpan aman di **Docker Named Volume (`ladock_db_central_data`)** (bukan bind mount) untuk performa dan integritas InnoDB.
   - File dump `.sql` diorganisir rapi di **`mysql/db/<app_name>/`** (`data.sql`, `schema.sql`, snapshot bertanggal, dan `README.md`).
   - Tersedia helper script: `./scripts/db_dump.sh` dan `./scripts/db_restore.sh`.
5. **Web Control Center & Monitoring Dashboard**:
   - Dashboard web modern (port default `9090`).
   - Monitor status container, CPU & RAM realtime, probe port HTTP.
   - **Deploy Hub**: Upload arsip `.zip`/`.tar.gz`, konfigurasi port, dan tombol deploy dengan **streaming log terminal realtime via SSE**.
   - **Database Manager**: 1-klik Backup dan Restore database.
   - **Editor Konfigurasi**: Edit `config.json` dan `.ladock_db.env` langsung dari web browser.
   - **Log Viewer & Riwayat**: Cari, filter, dan download log container serta riwayat deployment.

---

## 📁 Struktur Repositori & Hasil Deployment

### 1. Struktur Repositori LaDock
```text
automasi/
├── config.json                  <- Konfigurasi utama terpusat
├── .ladock_db.env               <- Konfigurasi environment MySQL sentral
├── deploy.sh                    <- Script utama deployment otomatis
├── destroy.sh                   <- Cleanup container & project
├── monitor.sh                   <- Launcher web control center
├── central_db.sh                <- Inisialisasi & manager MySQL sentral
├── mysql/
│   ├── README.md                <- Dokumentasi arsitektur volume DB sentral
│   └── db/                      <- Folder penyimpanan dump SQL per aplikasi
│       └── <app_name>/
│           ├── schema.sql
│           ├── data.sql
│           └── README.md
├── scripts/
│   ├── extract_archive.py       <- Ekstraksi aman .zip, .tar.gz (Zip-Slip safe)
│   ├── detect_stack.py          <- Deteksi stack & dependensi -> stack.json
│   ├── db_dump.sh               <- Script backup DB dari volume ke mysql/db/<app>/
│   ├── db_restore.sh            <- Script restore DB ke volume dari mysql/db/<app>/
│   ├── db_import.py             <- Utilitas impor dump SQL ke container MySQL
│   ├── normalize_assets.py      <- Normalisasi URL aset hardcoded ke lokal
│   ├── start_ui.sh              <- Launcher server control center
│   └── ...
├── monitor/
│   ├── server.js                <- Backend API & SSE streaming (Node.js)
│   ├── server.py                <- Fallback backend server (Python 3)
│   └── public/                  <- Antarmuka frontend (HTML5/CSS3/Vanilla JS)
├── templates/
│   ├── Dockerfile               <- Template image PHP-Apache universal
│   ├── docker-compose-app.yml.tpl
│   └── apache-vhost.conf.tpl
└── tests/
    ├── test_archive.py          <- Unit test ekstraksi & proteksi zip-slip
    ├── test_normalize_assets.py  <- Unit test normalisasi path aset & URL
    ├── test_stack_detection.py  <- Unit test deteksi multi-stack
    └── test_deploy_structure.sh <- Test simulasi struktur deployment
```

### 2. Struktur Folder Hasil Deployment (`deployed/<app_name>/`)
```text
deployed/<app_name>/
├── src/                         <- Seluruh source code aplikasi (Laravel/PHP/dll)
│   ├── app/
│   ├── public/
│   ├── vendor/
│   └── .env
├── docker-compose.yml           <- File compose utama yang bersih
├── Dockerfile                   <- Dockerfile aplikasi
├── apache-vhost.conf            <- Konfigurasi VirtualHost Apache
├── stack.json                   <- Spesifikasi stack & dependensi hasil deteksi
├── logs/                        <- Direktori log aplikasi
├── .dockerignore
└── .env
```

---

## 🚀 Panduan Penggunaan CLI

### 1. Deploy Aplikasi

```bash
chmod +x deploy.sh destroy.sh central_db.sh monitor.sh

# Dari File Arsip (.zip / .tar.gz / cpmove):
./deploy.sh /path/ke/aplikasi.zip 8080 3308

# Dari Folder Source Code Langsung:
./deploy.sh /path/ke/folder-project 8080 3308

# Dengan Opsi Lengkap:
./deploy.sh --archive=/path/arsip.zip --dest=./deployed/myapp 8080 3308 --force-import
```

### 2. Menghentikan & Membersihkan Container

```bash
# Hentikan container aplikasi (tanpa menghapus image/DB)
./destroy.sh ./deployed/<app_name>

# Hentikan dan hapus image Docker terkait:
./destroy.sh ./deployed/<app_name> --with-images
```

---

## 🗄️ Manajemen Database Sentral & Named Volume

Data fisik MySQL disimpan di **Docker Named Volume (`ladock_db_central_data`)**:
- Port Host: **`3308`** (Internal: `3306`)
- Container: **`ladock_mysql`**
- Network: **`ladock_net`**

### Mengapa Menggunakan Docker Named Volume (Bukan Bind Mount)?
1. **Keamanan Mesin InnoDB**: Bind mount lokal pada host OS rawan mengalami *file locking race condition* dan *fsync corruption* saat container mati mendadak.
2. **Isolasi Permission**: MySQL berjalan dengan UID internal `mysql:mysql` (999/1001). Bind mount lokal menyebabkan konflik kepemilikan berkas dengan user host.
3. **Performa I/O**: Docker volume dikelola langsung oleh storage driver kernel Linux, memberikan performa I/O database tertinggi.

### Perintah Backup & Restore
```bash
# Backup database ke mysql/db/<app_name>/
./scripts/db_dump.sh <app_name>

# Restore database dari mysql/db/<app_name>/data.sql
./scripts/db_restore.sh <app_name>
```

---

## 🖥️ Web Control Center & Monitoring

Jalankan dashboard interaktif untuk mengontrol seluruh sistem:

```bash
# Jalankan di background (port 9090):
./monitor.sh start

# Atau tentukan custom port:
./monitor.sh start 8888

# Cek status / hentikan:
./monitor.sh status
./monitor.sh stop
```
Akses di browser: **`http://localhost:9090`**

### Fitur Dashboard Web:
- **Overview**: Status kesehatan cluster, Central DB status pill, grafik CPU & RAM.
- **Deploy Hub**: Drag-and-drop upload arsip `.zip` / `.tar.gz`, konfigurasi port, dan live terminal streaming output via **Server-Sent Events (SSE)**.
- **Aplikasi**: Daftar aplikasi ter-deploy beserta badge stack, path, tombol redeploy, dan destroy.
- **Database Sentral**: Tinjau direktori `mysql/db/` dan jalankan backup / restore 1-klik.
- **Konfigurasi**: Editor visual untuk `config.json` dan `.ladock_db.env`.
- **Logs**: Streaming log realtime tiap container dengan filter teks dan tombol download.

---

## 🔧 Cara Menambah Stack Baru

Untuk menambahkan dukungan runtime atau framework baru (misalnya Python FastAPI atau Go):
1. Buka [scripts/detect_stack.py](file:///home/nizar/Documents/myCode/maDiskominfo/proyek/automasi/scripts/detect_stack.py).
2. Tambahkan pemeriksaan berkas penanda pada fungsi `detect_stack()`:
   ```python
   if "main.go" in files_in_root:
       stack["primary_language"] = "Go"
       stack["web_server"] = "Go HTTP"
   ```
3. Siapkan template Dockerfile terkait di folder `templates/` jika ingin menyediakan runtime container baru selain PHP/Apache.

---

## 🧪 Menjalankan Testing

Projek ini dilengkapi dengan test suite otomatis:

```bash
# Jalankan test ekstraksi arsip & proteksi zip-slip
python3 tests/test_archive.py

# Jalankan test deteksi multi-stack
python3 tests/test_stack_detection.py

# Jalankan simulasi struktur deployment
bash tests/test_deploy_structure.sh
```

---

## ❓ Troubleshooting

| Gejala | Penyebab Umum | Solusi |
|---|---|---|
| **Port conflict (3308 sudah terpakai)** | Ada service MySQL host lokal atau container lain di port 3308 | Ubah `LADOCK_DB_PORT` di `.ladock_db.env` dan `config.json` |
| **Aplikasi tidak bisa konek database** | Container aplikasi belum terhubung ke network `ladock_net` | Pastikan `networks: ladock_net` terdefinisi di `docker-compose.yml` |
| **Dump SQL tidak otomatis terimpor** | Database sudah berisi tabel dari deploy sebelumnya | Jalankan deploy dengan flag `--force-import` |
| **Zip-Slip Warning saat extract** | Berkas arsip mengandung entri dengan `../` | Sistem secara otomatis mengabaikan entri berbahaya demi keamanan |