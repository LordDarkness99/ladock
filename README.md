# Laravel Docker Auto-Deploy v2.0

Automation untuk deploy project Laravel ke Docker — mendukung **Monolith** maupun **Microservices**, menggunakan **Apache** secara full (tanpa Nginx).

---

## Fitur

- **Auto-detect mode**: Jika ditemukan 1 project Laravel → Monolith. Jika ≥ 2 sub-project → Microservices otomatis.
- **Deep auto-discovery**: Scanner rekursif cerdas yang menemukan project Laravel di dalam folder dengan struktur apapun (tidak perlu struktur folder tertentu), sampai kedalaman 5 level.
- **Apache API Gateway**: Satu entry point unified (`http://localhost:GATEWAY_PORT/`), routing berbasis path-prefix ke masing-masing service.
- **Direct port access**: Tiap service juga bisa diakses langsung per port untuk kebutuhan debugging.
- **Discovery dashboard**: Halaman HTML otomatis di root Gateway yang menampilkan daftar semua service, route, dan port.
- **Database-per-service**: 1 container MySQL shared, dengan database & user terpisah per service.
- **Inter-service discovery**: URL service lain otomatis diinjeksi ke `.env` masing-masing service (`SERVICE_AUTH_URL`, `SERVICE_ORDER_URL`, dst.)
- **Auto-import dump `.sql`**: Dump database dideteksi dan diimpor otomatis per service.
- **Backward-compatible**: Deploy monolith lama tetap berjalan persis sama seperti sebelumnya.
- **Extract cPanel backup**: Support `--cpmove=` untuk deploy langsung dari arsip backup cPanel.
- **PHP auto-detect**: Versi PHP dideteksi dari `composer.json` masing-masing service.

---

## Struktur

```
ladock/
├── deploy.sh                    <- entry point utama
├── destroy.sh                   <- cleanup container & file
├── templates/
│   ├── Dockerfile               <- image PHP + Apache per service
│   ├── docker-compose.yml.tpl   <- template compose mode monolith
│   ├── apache-vhost.conf.tpl    <- vhost Apache per service app
│   ├── gateway.Dockerfile       <- image Apache Gateway (httpd:alpine)
│   └── gateway-httpd.conf       <- konfigurasi httpd minimal gateway
├── scripts/
│   ├── find_microservices.py    <- scanner rekursif sub-project Laravel
│   ├── generate_compose.py      <- generator docker-compose.yml dinamis
│   ├── generate_gateway_conf.py <- generator konfigurasi Apache Gateway + dashboard
│   ├── detect_php_version.py    <- baca composer.json, tentukan versi PHP
│   ├── find_laravel_projects.py <- scan folder cari project Laravel (monolith)
│   ├── db_import.py             <- cari & import file dump .sql ke container MySQL
│   └── extract_cpmove.py        <- extract project + dump DB dari backup cPanel
└── README.md
```

---

## Syarat

- Docker & Docker Compose sudah terinstall
- **Python 3** sudah terinstall
- openssl tersedia (untuk generate password)

---

## Cara Deploy — Mode Monolith

```bash
chmod +x deploy.sh destroy.sh

# Basic
./deploy.sh /path/ke/project-laravel

# Custom port
./deploy.sh /path/ke/project-laravel 9000 3308

# Dari arsip cPanel
./deploy.sh --cpmove=/path/cpmove-xxx.tar.gz 8083 3308

# Paksa import dump
./deploy.sh /path/ke/project --force-import
```

---

## Cara Deploy — Mode Microservices

Mode microservices **aktif otomatis** jika di dalam folder yang diberikan terdapat ≥ 2 sub-folder yang masing-masing berisi project Laravel (ada file `artisan` + `composer.json`).

```bash
# Otomatis (scanner mendeteksi semua sub-project Laravel di bawah folder ini)
./deploy.sh /path/ke/root-project

# Custom port gateway & MySQL
./deploy.sh /path/ke/root-project 8080 3307

# Paksa mode (override auto-detect)
./deploy.sh /path/ke/root-project --mode=microservice

# Atur kedalaman scan (default: 5)
./deploy.sh /path/ke/root-project --max-depth=3

# Atur base port untuk direct-access per service (default: 8081)
./deploy.sh /path/ke/root-project 8080 3307 --base-app-port=9001
```

### Contoh Struktur Microservices yang Didukung

Tidak ada batasan struktur folder! Scanner akan menemukan project Laravel di mana saja:

```
# Contoh 1: flat di satu level
my-project/
├── auth-service/    (ada artisan + composer.json)
├── user-service/    (ada artisan + composer.json)
└── order-service/   (ada artisan + composer.json)

# Contoh 2: bersarang acak
my-project/
├── backend/
│   ├── auth/        (ada artisan + composer.json)
│   └── user/        (ada artisan + composer.json)
├── payment-svc/     (ada artisan + composer.json)
└── (folder lain tanpa artisan diabaikan)

# Contoh 3: nama folder apapun
my-project/
├── svc-a/           (ada artisan + composer.json)
└── old_code/
    └── svc-b/       (ada artisan + composer.json)
```

---

## Arsitektur Mode Microservices

```
[ Browser / Client ]
        |
   Port: 8080
        |
[ Apache Gateway Container ]  <-- entry point tunggal
        |
   Path-based routing:
   /auth/   -> app_auth:80
   /user/   -> app_user:80
   /order/  -> app_order:80
   /        -> Discovery Dashboard (HTML)
        |
[ Container Network: PROJECT_net ]
   |           |           |
[app_auth] [app_user] [app_order]   <- PHP+Apache per service
       \        |        /
        \       |       /
       [db_PROJECT] <- MySQL 8 shared
        DB: proj_auth_db
        DB: proj_user_db
        DB: proj_order_db
```

### Routing Detail

| Route | Tujuan | Port Direct |
|:---|:---|:---|
| `http://localhost:8080/` | Discovery Dashboard | - |
| `http://localhost:8080/auth/` | Service Auth | `:8081` |
| `http://localhost:8080/user/` | Service User | `:8082` |
| `http://localhost:8080/order/` | Service Order | `:8083` |

---

## File yang Di-generate di Folder Project

```
/project-root/
├── .docker-compose.yml          <- compose file hasil generate
└── .docker/
    ├── Dockerfile               <- image PHP+Apache
    ├── apache-vhost.conf        <- vhost Apache app service
    ├── apache-gateway.conf      <- konfigurasi routing gateway
    ├── gateway/
    │   ├── Dockerfile           <- image gateway
    │   ├── httpd.conf           <- konfigurasi httpd minimal
    │   └── dashboard.html       <- halaman discovery dashboard
    └── credentials/
        ├── .db_root_pass        <- password root MySQL
        ├── auth.env             <- kredensial DB service auth
        ├── user.env             <- kredensial DB service user
        └── order.env            <- kredensial DB service order
```

Semua file credentials dibuat dengan `chmod 600` (hanya bisa dibaca owner).

---

## Deploy Ulang (Redeploy)

```bash
# Cukup jalankan lagi, container lama otomatis dihapus & dibangun ulang
./deploy.sh /path/ke/project
```

Kredensial database dipertahankan (tidak di-generate ulang), sehingga data di dalam MySQL aman.

---

## Cleanup

```bash
# Hapus container + volume DB (data MySQL hilang)
./destroy.sh /path/ke/project

# Hapus container + volume + image + credentials (cleanup total)
./destroy.sh /path/ke/project --with-images
```

---

## Flag Lengkap

| Flag | Keterangan |
|:---|:---|
| `--mode=monolith\|microservice` | Override auto-detect mode |
| `--max-depth=N` | Kedalaman scan microservice (default: 5) |
| `--base-app-port=N` | Port awal direct-access service (default: 8081) |
| `--dump=FILE` | File dump `.sql` eksplisit (monolith saja) |
| `--force-import` | Paksa import dump walau redeploy |
| `--skip-import` | Jangan import dump sama sekali |
| `--cpmove=FILE` | Deploy dari backup cPanel |
| `--cpmove-dest=DIR` | Folder tujuan extract cpmove |

---

## Inter-Service Communication

Dalam mode microservice, setiap service bisa memanggil service lain menggunakan environment variable yang diinjeksi otomatis:

```php
// Di dalam service 'order', memanggil service 'auth':
$authUrl = env('SERVICE_AUTH_URL'); // http://app_auth:80
Http::get("$authUrl/api/validate-token", [...]);
```

Environment variable format: `SERVICE_{NAMA_SERVICE_UPPERCASE}_URL`