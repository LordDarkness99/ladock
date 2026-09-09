# Laravel Docker Auto-Deploy

Automation untuk deploy project Laravel ke Docker secara otomatis:
- Build image PHP-FPM khusus untuk project kamu
- Container Nginx sebagai web server
- Container MySQL 8 sebagai database
- Otomatis: `composer install`, `.env` config, `key:generate`, `migrate`
- Auto bersihin container lama tiap kali redeploy (tidak numpuk sampah)

## Struktur

```
laravel-docker-deploy/
├── deploy.sh              <- jalankan ini untuk deploy
├── destroy.sh              <- jalankan ini untuk hapus/cleanup
├── templates/
│   ├── Dockerfile
│   ├── docker-compose.yml.tpl
│   └── nginx.conf.tpl
└── README.md
```

## Syarat

- Docker & Docker Compose sudah terinstall
- Project Laravel yang sudah diunduh/di-extract ke sebuah folder di komputer kamu

## Cara Deploy

```bash
chmod +x deploy.sh destroy.sh

./deploy.sh /path/ke/project-laravel-kamu
```

Otomatis pakai port `8080` untuk web dan `3307` untuk MySQL. Kalau mau custom port:

```bash
./deploy.sh /path/ke/project-laravel-kamu 9000 3308
```

Setelah selesai, script akan menampilkan:
- URL akses web (`http://localhost:PORT`)
- Detail koneksi MySQL (host port, nama DB, user, password)

Semua file Docker (Dockerfile, nginx.conf, docker-compose.yml, credentials.env)
otomatis dibuat **di dalam folder project Laravel itu sendiri**, di subfolder
`.docker/` dan file `.docker-compose.yml` di root project. Jadi cukup jalankan
`deploy.sh` sekali per project, path lain = project lain, tidak akan bentrok.

## Deploy Ulang (Redeploy)

Jalankan `deploy.sh` lagi dengan path yang sama. Script akan:
1. Pakai lagi kredensial DB yang sama (data lama tetap ada)
2. Matikan & hapus container lama punya project itu
3. Build ulang image & jalankan container baru
4. Jalankan migrate lagi (data existing tidak hilang, hanya migration baru yang dijalankan)

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
