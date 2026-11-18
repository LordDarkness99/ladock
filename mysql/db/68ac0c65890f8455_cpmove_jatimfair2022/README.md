# Database Info: 68ac0c65890f8455_cpmove_jatimfair2022

- **Database Name**: `jatimfair2022_db`
- **Host Container**: `ladock_mysql` (datadir lokal: `docker/db/ladock_mysql/data/`)
- **Port Internal**: 3306
- **Port Host**: 3310
- **Last Backup**: Tue Nov 17 07:59:21 AM WIB 2026
- **Files**:
  - `schema.sql` : Struktur tabel, routines, dan triggers
  - `data.sql`   : Dump lengkap data dan struktur terakhir
  - `backup_20261117_075920.sql` : Snapshot arsip saat backup dijalankan

### Cara Restore Manual:
```bash
# Menggunakan helper script LaDock:
./scripts/db_restore.sh 68ac0c65890f8455_cpmove_jatimfair2022

# Atau langsung via docker exec:
docker exec -i ladock_mysql mysql -uroot -p<ROOT_PASS> jatimfair2022_db < mysql/db/68ac0c65890f8455_cpmove_jatimfair2022/data.sql
```
