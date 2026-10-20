# LaDock — Arsitektur & Manajemen Database Sentral

## Arsitektur Penyimpanan Database

Container Database Sentral LaDock (`ladock_mysql`) berjalan pada port host **3308** (internal **3306**) di dalam network **`ladock_net`**.
Data fisik MySQL disimpan pada folder lokal repo melalui bind mount:

```text
docker/db/ladock_mysql/data -> /var/lib/mysql
```

Container MySQL berjalan sebagai user internal `mysql`; beberapa file datadir mungkin tidak dapat dibaca oleh user host biasa. Gunakan dump SQL di `mysql/db/<app_name>/` untuk melihat atau memindahkan isi database. Jangan mengedit file datadir secara langsung, terutama saat MySQL berjalan.

Pada penggunaan pertama setelah perubahan, `central_db.sh` menyalin datadir dari named volume lama saat container berhenti. Named volume lama tidak dihapus. Jika folder tujuan lokal sudah berisi file tetapi container lama masih memakai penyimpanan berbeda, migrasi berhenti agar tidak menimpa data.

Socket lokal MySQL dikonfigurasi ke `/var/lib/mysql/mysql.sock` agar image tidak membuat symlink socket lama di datadir. Saat konfigurasi ini pertama kali diterapkan, `central_db.sh` akan mengganti container lama tanpa menghapus data di folder `docker/db/ladock_mysql/data/`. Datadir lama di `docker/ladock_mysql/data/` akan disalin ke lokasi baru saat aman.

## Manajemen Dump & Backup Terstruktur (`mysql/db/<app_name>/`)

Dump SQL per aplikasi disimpan secara lokal:

```text
mysql/
└── db/
    ├── app_satu/
    │   ├── schema.sql
    │   ├── data.sql
    │   ├── backups/
    │   └── README.md
    └── app_dua/
        ├── schema.sql
        ├── data.sql
        └── README.md
```

## Cara Akses Database

### 1. Langsung dari Host CLI

```bash
mysql -h 127.0.0.1 -P 3308 -u <db_user> -p<db_password> <db_name>
```

### 2. Dari Dalam Container Docker

```bash
docker exec -it ladock_mysql mysql -uroot -p<ROOT_PASS>
```

### 3. Menggunakan phpMyAdmin (Opsional)

```bash
docker run -d --name ladock_phpmyadmin --restart unless-stopped \
  --network ladock_net -p 8095:80 \
  -e PMA_HOST=ladock_mysql phpmyadmin/phpmyadmin
```

Akses di browser: `http://localhost:8095`.

## Cara Backup Database

```bash
./scripts/db_dump.sh <app_name>
```

Contoh:

```bash
./scripts/db_dump.sh campuscare
```

Hasil backup otomatis disimpan di `mysql/db/<app_name>/data.sql`, `schema.sql`, dan `backups/backup_<timestamp>.sql`.

## Cara Restore Database

```bash
./scripts/db_restore.sh <app_name> [path_ke_file_sql_opsional]
```

Script akan membaca `mysql/db/<app_name>/data.sql` dan mengimpornya kembali ke database container `ladock_mysql`.

Datadir tiap database microservice berada di `docker/db/<project>/<service>/data/`. Pada deploy ulang, data dari named volume lama disalin saat container berhenti; named volume tersebut tidak dihapus dan dipertahankan sebagai cadangan.
