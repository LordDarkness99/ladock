# Database Info: 38640375c6a6995a_cpmove_rspjemberjtm

- **Database Name**: `38640375c6a6995a_cpmove_rspjemberjtm_db`
- **Host Container**: `ladock_mysql` (datadir lokal: `docker/db/ladock_mysql/data/`)
- **Port Internal**: 3306
- **Port Host**: 3310
- **Last Backup**: Tue Nov 17 04:32:11 AM WIB 2026
- **Files**:
  - `schema.sql` : Struktur tabel, routines, dan triggers
  - `data.sql`   : Dump lengkap data dan struktur terakhir
  - `backup_20261117_043211.sql` : Snapshot arsip saat backup dijalankan

### Cara Restore Manual:
```bash
# Menggunakan helper script LaDock:
./scripts/db_restore.sh 38640375c6a6995a_cpmove_rspjemberjtm

# Atau langsung via docker exec:
docker exec -i ladock_mysql mysql -uroot -p<ROOT_PASS> 38640375c6a6995a_cpmove_rspjemberjtm_db < mysql/db/38640375c6a6995a_cpmove_rspjemberjtm/data.sql
```
