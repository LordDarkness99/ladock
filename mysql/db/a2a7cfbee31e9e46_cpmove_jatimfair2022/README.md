# Database Info: a2a7cfbee31e9e46_cpmove_jatimfair2022

- **Database Name**: `jatimfair2022_db`
- **Host Container**: `ladock_mysql` (datadir lokal: `docker/db/ladock_mysql/data/`)
- **Port Internal**: 3306
- **Port Host**: 3310
- **Last Backup**: Thu Nov 19 08:59:12 AM WIB 2026
- **Files**:
  - `schema.sql` : Struktur tabel, routines, dan triggers
  - `data.sql`   : Dump lengkap data dan struktur terakhir
  - `backup_20261119_085912.sql` : Snapshot arsip saat backup dijalankan

### Cara Restore Manual:
```bash
# Menggunakan helper script LaDock:
./scripts/db_restore.sh a2a7cfbee31e9e46_cpmove_jatimfair2022

# Atau langsung via docker exec:
docker exec -i ladock_mysql mysql -uroot -p<ROOT_PASS> jatimfair2022_db < mysql/db/a2a7cfbee31e9e46_cpmove_jatimfair2022/data.sql
```
