# Database Info: rspjemberjtm

- **Database Name**: `rspjemberjtm_db`
- **Host Container**: `ladock_mysql` (datadir lokal: `docker/db/ladock_mysql/data/`)
- **Port Internal**: 3306
- **Port Host**: 3310
- **Last Backup**: Thu Nov 19 04:29:26 AM WIB 2026
- **Files**:
  - `schema.sql` : Struktur tabel, routines, dan triggers
  - `data.sql`   : Dump lengkap data dan struktur terakhir
  - `backup_20261119_042925.sql` : Snapshot arsip saat backup dijalankan

### Cara Restore Manual:
```bash
# Menggunakan helper script LaDock:
./scripts/db_restore.sh rspjemberjtm

# Atau langsung via docker exec:
docker exec -i ladock_mysql mysql -uroot -p<ROOT_PASS> rspjemberjtm_db < mysql/db/rspjemberjtm/data.sql
```
