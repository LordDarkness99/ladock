# LaDock — Arsitektur & Manajemen Database Sentral

## Arsitektur Penyimpanan Database

Container Database Sentral LaDock (`ladock_mysql`) berjalan pada port host **3308** (internal **3306**) di dalam network **`ladock_net`**.
Data fisik MySQL disimpan di dalam **Docker Named Volume**:
```
ladock_db_central_data -> /var/lib/mysql
```

### Mengapa Menggunakan Docker Named Volume (Bukan Bind Mount ke Folder Lokal)?

1. **Integritas & Keamanan Data (InnoDB Safety)**:
   Engine MySQL InnoDB sangat sensitif terhadap sistem penguncian berkas (*file locking*) dan fsync. Bind mount host OS (terutama NTFS, NFS, atau perbedaan kernel) dapat memicu *race condition* dan korupsi berkas `.ibd` ketika container di-restart atau dihentikan mendadak.
2. **Permission & User ID Isolation**:
   Di dalam container Linux, MySQL berjalan di bawah user khusus `mysql` (UID:GID `999:999` atau `1001:1001`). Jika menggunakan bind mount ke folder lokal user host, terjadi konflik kepemilikan berkas (*permission denied*), dan berkas database lokal akan menjadi milik root/mysql sehingga menyulitkan manajemen host.
3. **Performa I/O**:
   Docker volume dikelola langsung oleh storage driver Docker pada tingkat filesystem Linux asli, memberikan *throughput* dan latensi I/O database yang jauh lebih tinggi dibandingkan overhead bind mount.

---

## Manajemen Dump & Backup Terstruktur (`mysql/db/<app_name>/`)

Agar database tetap mudah dipantau, diekspor, dan di-restore tanpa mengotori root project aplikasi, LaDock menyediakan struktur folder lokal:

```
mysql/
└── db/
    ├── app_satu/
    │   ├── schema.sql           <- Definisi tabel, trigger, dan view
    │   ├── data.sql             <- Dump data lengkap aplikasi
    │   ├── backup_YYYYMMDD.sql  <- Snapshot backup bertanggal
    │   └── README.md            <- Info koneksi & kredensial
    └── app_dua/
        ├── schema.sql
        ├── data.sql
        └── README.md
```

---

## Cara Akses Database

### 1. Langsung dari Host CLI
```bash
mysql -h 127.0.0.1 -P 3308 -u <db_user> -p<db_password> <db_name>

# Atau akses root:
mysql -h 127.0.0.1 -P 3308 -uroot -p3baa6e5d124af02611fd0efb79ae292d
```

### 2. Dari Dalam Container Docker
```bash
docker exec -it ladock_mysql mysql -uroot -p3baa6e5d124af02611fd0efb79ae292d
```

### 3. Menggunakan phpMyAdmin (Opsional)
Jalankan phpMyAdmin sekali klik yang terhubung ke jaringan LaDock:
```bash
docker run -d --name ladock_phpmyadmin --restart unless-stopped --network ladock_net -p 8095:80 -e PMA_HOST=ladock_mysql phpmyadmin/phpmyadmin
```
Akses di browser: `http://localhost:8095`

---

## Cara Backup Database
Gunakan script pembantu:
```bash
./scripts/db_dump.sh <app_name>

# Contoh:
./scripts/db_dump.sh campuscare
```
Hasil backup otomatis disimpan di `mysql/db/<app_name>/data.sql`, `schema.sql`, dan `backup_<timestamp>.sql`.

---

## Cara Restore Database
Gunakan script restore:
```bash
./scripts/db_restore.sh <app_name> [path_ke_file_sql_opsional]

# Contoh:
./scripts/db_restore.sh campuscare
```
Script akan membaca `mysql/db/<app_name>/data.sql` dan mengimpornya kembali ke database container `ladock_mysql`.
