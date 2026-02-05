#!/bin/bash
set -e

# PostgreSQL setup
PGDATA="/config/postgres"
PG_USER="hmm_user"
PG_DB="hmm"
PG_PASSWORD="${POSTGRES_PASSWORD:-hmm_secure_password}"

echo "🐘 Setting up PostgreSQL..."

# Initialize PostgreSQL data directory if it doesn't exist
if [ ! -d "$PGDATA/base" ]; then
    echo "📁 Initializing PostgreSQL data directory..."
    mkdir -p "$PGDATA"
    chown -R postgres:postgres "$PGDATA"
    su - postgres -c "/usr/lib/postgresql/*/bin/initdb -D $PGDATA"
    
    # Configure PostgreSQL
    echo "⚙️ Configuring PostgreSQL..."
    cat >> "$PGDATA/postgresql.conf" <<EOF
listen_addresses = 'localhost'
port = 5432
max_connections = 100
shared_buffers = 128MB
EOF
    
    # Start PostgreSQL temporarily to create user and database
    su - postgres -c "/usr/lib/postgresql/*/bin/pg_ctl -D $PGDATA -l /config/postgres/logfile start"
    sleep 3
    
    # Create user and database
    su - postgres -c "psql -c \"CREATE USER $PG_USER WITH PASSWORD '$PG_PASSWORD';\""
    su - postgres -c "psql -c \"CREATE DATABASE $PG_DB OWNER $PG_USER;\""
    su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE $PG_DB TO $PG_USER;\""
    
    # Stop PostgreSQL
    su - postgres -c "/usr/lib/postgresql/*/bin/pg_ctl -D $PGDATA stop"
    sleep 2
    
    echo "✅ PostgreSQL initialized"
else
    echo "✅ PostgreSQL data directory exists"
fi

# Start PostgreSQL
echo "🚀 Starting PostgreSQL..."
su - postgres -c "/usr/lib/postgresql/*/bin/pg_ctl -D $PGDATA -l /config/postgres/logfile start"
sleep 3

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if su - postgres -c "psql -U $PG_USER -d $PG_DB -c 'SELECT 1' >/dev/null 2>&1"; then
        echo "✅ PostgreSQL is ready"
        break
    fi
    echo "   Attempt $i/30..."
    sleep 1
done

# Start the main application
echo "🚀 Starting Home Miner Manager..."
uvicorn main:app --host 0.0.0.0 --port ${WEB_PORT}
