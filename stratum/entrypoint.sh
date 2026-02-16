#!/bin/sh
set -eu

PG_DATA_DIR="${STRATUM_POSTGRES_DATA_DIR:-/config/stratum-postgres}"
PG_PORT="${STRATUM_POSTGRES_PORT:-5432}"
PG_USER="${STRATUM_POSTGRES_USER:-stratum}"
PG_PASSWORD="${STRATUM_POSTGRES_PASSWORD:-stratum}"
PG_DB="${STRATUM_POSTGRES_DB:-stratum}"

PG_BIN_DIR=""
for candidate in /usr/lib/postgresql/*/bin; do
  if [ -x "${candidate}/initdb" ] && [ -x "${candidate}/pg_ctl" ] && [ -x "${candidate}/psql" ]; then
    PG_BIN_DIR="${candidate}"
    break
  fi
done

if [ -z "${PG_BIN_DIR}" ]; then
  echo "PostgreSQL binaries not found under /usr/lib/postgresql/*/bin" >&2
  exit 1
fi

INITDB_BIN="${PG_BIN_DIR}/initdb"
PG_CTL_BIN="${PG_BIN_DIR}/pg_ctl"
PSQL_BIN="${PG_BIN_DIR}/psql"

mkdir -p "${PG_DATA_DIR}"
chown -R postgres:postgres "${PG_DATA_DIR}"

if [ ! -f "${PG_DATA_DIR}/PG_VERSION" ]; then
  su -s /bin/sh postgres -c "${INITDB_BIN} -D '${PG_DATA_DIR}'"
  {
    echo "listen_addresses = '127.0.0.1'"
    echo "port = ${PG_PORT}"
  } >> "${PG_DATA_DIR}/postgresql.conf"
  echo "host all all 127.0.0.1/32 scram-sha-256" >> "${PG_DATA_DIR}/pg_hba.conf"
fi

su -s /bin/sh postgres -c "${PG_CTL_BIN} -D '${PG_DATA_DIR}' -w start"

cleanup() {
  su -s /bin/sh postgres -c "${PG_CTL_BIN} -D '${PG_DATA_DIR}' -m fast stop" || true
}
trap cleanup EXIT INT TERM

su -s /bin/sh postgres -c "${PSQL_BIN} -h 127.0.0.1 -p '${PG_PORT}' -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \\\$\\\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${PG_USER}') THEN
    CREATE ROLE ${PG_USER} LOGIN PASSWORD '${PG_PASSWORD}';
  ELSE
    ALTER ROLE ${PG_USER} WITH PASSWORD '${PG_PASSWORD}';
  END IF;
END
\\\$\\\$;
SQL"

su -s /bin/sh postgres -c "${PSQL_BIN} -h 127.0.0.1 -p '${PG_PORT}' -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \\\$\\\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${PG_DB}') THEN
    CREATE DATABASE ${PG_DB} OWNER ${PG_USER};
  END IF;
END
\\\$\\\$;
SQL"

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${PG_PORT}/${PG_DB}}"

echo "Starting stratum with DATABASE_URL=${DATABASE_URL}" >&2
exec uvicorn main:app --host 0.0.0.0 --port 8082
