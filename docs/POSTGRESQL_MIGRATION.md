# PostgreSQL Migration Guide

## Overview

HMM-Local v1.0.0 has migrated from SQLite to PostgreSQL as the primary database. This change provides:

- **Better concurrency**: Handle multiple miners and high telemetry volume without locking
- **JSONB support**: Efficient storage and querying of pool_config data
- **Production-ready**: Industry standard for multi-user, high-throughput applications
- **Better migration support**: ALTER TABLE with IF NOT EXISTS
- **Advanced features**: Full-text search, better indexing, replication support

## Fresh Installation

### 1. Create Environment File

```bash
cd /path/to/hmm-local
cp .env.example .env
```

### 2. Set Secure Password

Edit `.env` and change the PostgreSQL password:

```bash
# SECURITY: Change this password before deployment!
POSTGRES_PASSWORD=your_secure_password_here
```

**Important**: Use a strong, unique password. This will be used by both the PostgreSQL container and the application.

### 3. Start Services

```bash
docker-compose up -d
```

This will:
1. Start PostgreSQL container
2. Wait for PostgreSQL to be healthy (health check)
3. Start HMM-Local application
4. Run database migrations automatically

### 4. Verify

Check logs:
```bash
docker-compose logs -f
```

Look for:
- `✓ PostgreSQL connection successful`
- `✓ Migration 44: Added pool_type column to pools`
- `✓ Migration 45: Added pool_config column to pools`

Check database:
```bash
docker exec -it hmm-postgres psql -U hmm_user -d hmm -c "\dt"
```

## Migrating from SQLite

If you have an existing HMM-Local installation using SQLite, follow these steps:

### 1. Backup Your Data

```bash
# Stop the container
docker-compose down

# Backup SQLite database
cp config/data.db config/data.db.backup

# Backup configuration
cp config/config.yaml config/config.yaml.backup
```

### 2. Set Up PostgreSQL

Create `.env` file:
```bash
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD
```

### 3. Start PostgreSQL Only

Temporarily modify `docker-compose.yml` to comment out the miner-controller service, then:

```bash
docker-compose up -d postgres
```

Wait for PostgreSQL to be ready:
```bash
docker-compose logs postgres | grep "ready to accept connections"
```

### 4. Run Migration Script

```bash
# Install dependencies
pip install sqlalchemy asyncpg psycopg2-binary

# Set environment variables
export POSTGRES_PASSWORD='your_password_from_env'
export POSTGRES_HOST='localhost'  # Since postgres port is exposed
export SQLITE_PATH='./config/data.db'

# Run migration
python migrate_to_postgres.py
```

The script will:
- Connect to both databases
- Copy all tables and data
- Reset auto-increment sequences
- Report any errors

### 5. Update Configuration

Edit `config/config.yaml`:

```yaml
database:
  active: postgresql  # Change from "sqlite"
  
  postgresql:
    host: postgres  # Use container name
    port: 5432
    database: hmm
    username: hmm_user
    password: "${POSTGRES_PASSWORD}"  # Will be read from environment
```

### 6. Start HMM-Local

Restore `docker-compose.yml` (uncomment miner-controller), then:

```bash
docker-compose up -d
```

### 7. Verify Migration

Check that data is present:
```bash
# Check miners
curl http://localhost:8080/api/miners

# Check pools
curl http://localhost:8080/api/pools

# Check telemetry
curl http://localhost:8080/api/analytics/telemetry?miner_id=YOUR_MINER_ID&hours=24
```

## Database Management

### Connect to PostgreSQL

```bash
docker exec -it hmm-postgres psql -U hmm_user -d hmm
```

Common commands:
```sql
-- List tables
\dt

-- Describe table
\d pools

-- Query data
SELECT * FROM pools;

-- Check database size
SELECT pg_size_pretty(pg_database_size('hmm'));

-- Quit
\q
```

### Backup Database

```bash
# Backup to file
docker exec hmm-postgres pg_dump -U hmm_user hmm > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup with compression
docker exec hmm-postgres pg_dump -U hmm_user hmm | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Restore Database

```bash
# Restore from backup
docker exec -i hmm-postgres psql -U hmm_user hmm < backup_20260123_120000.sql

# Restore from compressed backup
gunzip -c backup_20260123_120000.sql.gz | docker exec -i hmm-postgres psql -U hmm_user hmm
```

### Reset Database

**WARNING**: This will delete ALL data!

```bash
# Stop application
docker-compose down

# Remove PostgreSQL data volume
rm -rf config/postgres

# Start fresh
docker-compose up -d
```

## Troubleshooting

### Connection Refused

**Symptom**: `FATAL: password authentication failed for user "hmm_user"`

**Solutions**:
1. Check `.env` file exists and has correct password
2. Verify `config/config.yaml` has `${POSTGRES_PASSWORD}` placeholder
3. Restart containers: `docker-compose restart`

### Container Won't Start

**Symptom**: `miner-controller` container exits immediately

**Solutions**:
1. Check logs: `docker-compose logs`
2. Verify PostgreSQL is healthy: `docker-compose ps`
3. Ensure health check passes: `docker exec hmm-postgres pg_isready -U hmm_user -d hmm`

### Migration Errors

**Symptom**: `column "pool_type" already exists`

**Solution**: This is expected if migrations have already run. The error is caught and ignored.

### Data Not Migrated

**Symptom**: Empty database after migration

**Solutions**:
1. Check migration script output for errors
2. Verify SQLite database exists: `ls -lh config/data.db`
3. Re-run migration script with verbose logging
4. Check PostgreSQL connection: `docker-compose logs postgres`

### Performance Issues

**Symptom**: Slow queries or high CPU usage

**Solutions**:
1. Check indexes: `\d+ pools` in psql
2. Analyze tables: `ANALYZE;` in psql
3. Check connections: `SELECT count(*) FROM pg_stat_activity;`
4. Increase connection pool: Edit `app/core/database.py` pool_size

## Architecture Details

### Container Setup

HMM-Local uses docker-compose with two services:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    volumes:
      - ./config/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hmm_user -d hmm"]
  
  miner-controller:
    depends_on:
      postgres:
        condition: service_healthy  # Wait for health check
```

### Health Check

PostgreSQL must pass health check before HMM-Local starts:
- Command: `pg_isready -U hmm_user -d hmm`
- Interval: 10 seconds
- Timeout: 5 seconds
- Retries: 5

This ensures database is ready before migrations run.

### Connection Pool

PostgreSQL connection pool settings (in `app/core/database.py`):
```python
create_async_engine(
    database_url,
    pool_size=10,           # Normal connections
    max_overflow=20,        # Burst capacity
    pool_pre_ping=True,     # Check connection before use
    pool_recycle=3600       # Recycle after 1 hour
)
```

### Migrations

Migrations detect database type and use appropriate SQL:

**PostgreSQL**:
```sql
ALTER TABLE pools ADD COLUMN IF NOT EXISTS pool_type VARCHAR(50);
```

**SQLite** (deprecated):
```sql
ALTER TABLE pools ADD COLUMN pool_type VARCHAR(50);
-- No IF NOT EXISTS support
```

## Performance Tuning

### Optimize for High Telemetry Volume

If you have many miners (10+) pushing telemetry every 30 seconds:

1. Increase connection pool:
   ```python
   # In app/core/database.py
   pool_size=20,
   max_overflow=40
   ```

2. Add indexes:
   ```sql
   CREATE INDEX CONCURRENTLY idx_telemetry_timestamp ON telemetry(timestamp DESC);
   CREATE INDEX CONCURRENTLY idx_telemetry_miner_time ON telemetry(miner_id, timestamp DESC);
   ```

3. Partition telemetry table (future enhancement):
   ```sql
   CREATE TABLE telemetry_2026_01 PARTITION OF telemetry
       FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
   ```

### Monitor Performance

Check slow queries:
```sql
-- Enable slow query log
ALTER DATABASE hmm SET log_min_duration_statement = 1000;  -- 1 second

-- View slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Security Best Practices

1. **Change default password**: Never use the example password in production
2. **Restrict network access**: Don't expose PostgreSQL port (5432) to the internet
3. **Regular backups**: Automate daily backups with cron
4. **Update regularly**: Keep PostgreSQL image up to date
5. **Use SSL**: Enable SSL for production (add to `docker-compose.yml`)

### Enable SSL (Production)

```yaml
postgres:
  image: postgres:16-alpine
  command: >
    postgres
    -c ssl=on
    -c ssl_cert_file=/etc/ssl/certs/server.crt
    -c ssl_key_file=/etc/ssl/private/server.key
  volumes:
    - ./certs:/etc/ssl/certs:ro
    - ./keys:/etc/ssl/private:ro
```

## Rollback to SQLite

If you need to rollback to SQLite (not recommended):

1. Stop containers:
   ```bash
   docker-compose down
   ```

2. Edit `config/config.yaml`:
   ```yaml
   database:
     active: sqlite
   ```

3. Restore backup:
   ```bash
   cp config/data.db.backup config/data.db
   ```

4. Comment out PostgreSQL service in `docker-compose.yml`

5. Start container:
   ```bash
   docker-compose up -d
   ```

**Note**: SQLite is deprecated and will be removed in a future version.

## Future Enhancements

- [ ] Automatic daily backups via cron
- [ ] Replication for high availability
- [ ] Read replicas for analytics queries
- [ ] Table partitioning for telemetry data
- [ ] Connection pooler (PgBouncer) for very high concurrency
- [ ] Monitoring with Prometheus/Grafana

## Support

For issues or questions:
- Check logs: `docker-compose logs`
- Review troubleshooting section above
- Open issue on GitHub with logs and configuration (redact passwords!)
