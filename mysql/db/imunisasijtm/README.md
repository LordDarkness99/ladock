# Database Info: imunisasijtm

- **Database Name**: `imunisasijtm_db`
- **Host Container**: `ladock_mysql` (datadir lokal: `docker/db/ladock_mysql/data/`)
- **Port Internal**: 3306
- **Port Host**: 3310
- **Last Backup**: Thu Oct 29 11:19:38 AM WIB 2026
- **Files**:
  - `schema.sql` : Struktur tabel, routines, dan triggers
  - `data.sql`   : Dump lengkap data dan struktur terakhir
  - `backup_20261029_111929.sql` : Snapshot arsip saat backup dijalankan

### Cara Restore Manual:
```bash
# Menggunakan helper script LaDock:
./scripts/db_restore.sh imunisasijtm

# Atau langsung via docker exec:
docker exec -i ladock_mysql mysql -uroot -p<ROOT_PASS> imunisasijtm_db < mysql/db/imunisasijtm/data.sql
```
