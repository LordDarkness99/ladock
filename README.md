# Laravel Docker Auto-Deploy

Automation untuk deploy project Laravel ke Docker secara otomatis:
- Build image PHP + **Apache** khusus untuk project kamu (satu container, tidak ada nginx terpisah)
- Container MySQL 8 sebagai database
- Otomatis: `composer install`, `.env` config, `key:generate`, `migrate`
- **Auto-import dump `.sql`** (kalau ada di dalam project) supaya data lama ikut lengkap, bukan cuma struktur tabel dari migration
- Deteksi versi PHP & pencarian project Laravel dibantu Python (lebih robust daripada grep/sed)
- Auto bersihin container lama tiap kali redeploy (tidak numpuk sampah)

## Struktur

```
laravel-docker-deploy/
├── deploy.sh                   <- jalankan ini untuk deploy
├── destroy.sh                  <- jalankan ini untuk hapus/cleanup
├── templates/
│   ├── Dockerfile              <- image PHP + Apache
│   ├── docker-compose.yml.tpl
│   └── apache-vhost.conf.tpl
├── scripts/
│   ├── detect_php_version.py   <- baca composer.json, tentukan versi PHP
│   ├── find_laravel_projects.py<- scan folder cari project Laravel (punya file 'artisan')
│   └── db_import.py            <- cari & import file dump .sql ke container MySQL
└── README.md
```

## Syarat

- Docker & Docker Compose sudah terinstall
- **Python 3** sudah terinstall (dipakai untuk deteksi PHP version, cari project, dan import database)
- Project Laravel yang sudah diunduh/di-extract ke sebuah folder di komputer kamu

## Cara Deploy

```bash
chmod +x deploy.sh destroy.sh

./deploy.sh /path/ke/project-laravel-kamu
```

Kalau path tidak diisi sama sekali, script akan mencari sendiri project Laravel
di folder tempat kamu menjalankan `deploy.sh` (lewat `find_laravel_projects.py`)
dan menampilkan pilihan kalau ketemu lebih dari satu.

Otomatis pakai port `8080` untuk web dan `3307` untuk MySQL. Kalau mau custom port:

```bash
./deploy.sh /path/ke/project-laravel-kamu 9000 3308
```

Setelah selesai, script akan menampilkan:
- URL akses web (`http://localhost:PORT`)
- Detail koneksi MySQL (host port, nama DB, user, password)

Semua file Docker (Dockerfile, apache-vhost.conf, docker-compose.yml, credentials.env)
otomatis dibuat **di dalam folder project Laravel itu sendiri**, di subfolder
`.docker/` dan file `.docker-compose.yml` di root project. Jadi cukup jalankan
`deploy.sh` sekali per project, path lain = project lain, tidak akan bentrok.

## Import Data Database Otomatis (bukan cuma migration)

`php artisan migrate` cuma membuat **struktur** tabel dari file migration
(mis. `2024_01_01_000001_create_users_table.php`). Kalau kamu punya dump
lengkap (mis. `campus_complaint_system_clean_import.sql`) yang isinya
struktur + data, `deploy.sh` akan cari file `.sql` itu di dalam folder
project secara otomatis dan mengimportnya ke database sebelum menjalankan
migration — jadi data lama ikut lengkap pindah, bukan cuma tabel kosong.

Urutannya: **import dump dulu → baru `artisan migrate`**, supaya migrate
hanya menjalankan migration baru yang belum ada di dalam dump (tidak bentrok
dengan tabel yang sudah diimport).

Perilaku default:
- **Deploy pertama kali** untuk sebuah project → dump `.sql` (kalau ada) otomatis dicari & diimport.
- **Redeploy** (path sama, sudah pernah deploy sebelumnya) → import **dilewati** secara default, supaya data yang sudah kamu ubah lewat aplikasi tidak ketiban/ketimpa dump lama.

Kalau ada lebih dari satu file `.sql` di dalam project, dipakai yang ukurannya
paling besar (asumsi paling lengkap). Daftar semua file `.sql` yang ketemu akan
ditampilkan supaya kamu bisa cek.

Kontrol manual lewat flag (taruh di mana saja setelah path project):

```bash
# tunjuk file dump secara eksplisit
./deploy.sh /path/project 8080 3307 --dump=/path/project/database/backup.sql

# paksa import ulang walau ini redeploy (HATI-HATI: bisa menimpa data yang sudah berubah)
./deploy.sh /path/project --force-import

# jangan pernah import dump sama sekali, walau deploy pertama
./deploy.sh /path/project --skip-import
```

Import dijalankan lewat `scripts/db_import.py`, yang meng-pipe isi file `.sql`
langsung ke `mysql` di dalam container database (lewat `docker compose exec`),
jadi kamu tidak perlu install MySQL client di komputer host.

## Deploy Ulang (Redeploy)

Jalankan `deploy.sh` lagi dengan path yang sama. Script akan:
1. Pakai lagi kredensial DB yang sama (data lama tetap ada)
2. Matikan & hapus container lama punya project itu
3. Build ulang image & jalankan container baru
4. **Tidak** mengimport ulang dump `.sql` (kecuali pakai `--force-import`)
5. Jalankan migrate lagi (data existing tidak hilang, hanya migration baru yang dijalankan)

## Deploy Banyak Project Sekaligus

Karena nama container/network/volume selalu diberi prefix nama folder project
(disanitasi jadi lowercase + underscore), kamu bisa deploy beberapa project
Laravel berbeda di server yang sama tanpa bentrok — asal port HTTP/MySQL yang
dipakai berbeda-beda per project.

```bash
./deploy.sh /path/project-a 8081 3311
./deploy.sh /path/project-b 8082 3312
```

## Membersihkan / Menghapus Deployment

Stop & hapus container + volume database (data DB ikut terhapus):

```bash
./destroy.sh /path/ke/project-laravel-kamu
```

Sekalian hapus image Docker-nya juga:

```bash
./destroy.sh /path/ke/project-laravel-kamu --with-images
```

## Catatan

- Kredensial database tersimpan di `.docker/credentials.env` di dalam project —
  jangan ikut di-commit ke git.
- File `.env` Laravel otomatis diarahkan ke `DB_HOST=db_<nama_project>` sesuai
  container MySQL yang dibuat.
- Kalau project sudah punya `Dockerfile`/`docker-compose.yml` sendiri, script ini
  membuat file terpisah (`.docker-compose.yml`, folder `.docker/`) supaya tidak
  menimpa punya kamu.
- Web server sekarang **Apache** (`php:<versi>-apache`), bukan nginx + PHP-FPM
  terpisah — jadi cuma ada satu container `app_<project>` yang langsung serve
  HTTP, plus container `db_<project>` untuk MySQL.
- File `.docker-compose.yml` (di root project) juga sebaiknya masuk `.gitignore`,
  karena kredensial DB ikut ter-embed di situ lewat template.