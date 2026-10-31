#!/usr/bin/env bash
# Throwaway local Postgres 16 on :5433 (no Docker, does not touch any system cluster). Usage: scripts/dev_postgres.sh start|stop
# Then: export REDEEM_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5433/redeem && (cd apps/api && alembic upgrade head)
set -euo pipefail
D=${PGX_DIR:-/tmp/pgx}; B=/usr/lib/postgresql/16/bin
run() { if [ "$(id -u)" = 0 ]; then runuser -u postgres -- "$@"; else "$@"; fi; }
case "${1:-start}" in
  start)
    if [ ! -d "$D/data" ]; then mkdir -p "$D"; [ "$(id -u)" = 0 ] && chown postgres "$D"; run $B/initdb -E UTF8 -D "$D/data" -A trust >/dev/null; fi
    run $B/pg_ctl -D "$D/data" -o "-p 5433 -k $D -c listen_addresses=127.0.0.1" -l "$D/log" -w start
    psql -h 127.0.0.1 -p 5433 -U postgres -tc "select 1 from pg_database where datname='redeem'" | grep -q 1 || psql -h 127.0.0.1 -p 5433 -U postgres -c "create database redeem encoding 'UTF8' template template0" ;;
  stop) run $B/pg_ctl -D "$D/data" -w stop ;;
esac
