#!/usr/bin/env bash
# Start / stop local Redis + PostgreSQL (pgvector) from the pixi env. No Docker, no sudo.
set -euo pipefail
cd "$(dirname "$0")/.."
BIN=.pixi/envs/default/bin
PGDATA=.local/pg
mkdir -p .local
case "${1:-start}" in
  start)
    if [ ! -d "$PGDATA" ]; then $BIN/initdb -D "$PGDATA" -U wmp --auth=trust >/dev/null; fi
    $BIN/pg_ctl -D "$PGDATA" -o "-p 5442 -k /tmp" -l .local/pg.log status >/dev/null 2>&1 || \
      $BIN/pg_ctl -D "$PGDATA" -o "-p 5442 -k /tmp" -l .local/pg.log start >/dev/null
    $BIN/psql -h localhost -p 5442 -U wmp -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='wmp'" | grep -q 1 || \
      $BIN/psql -h localhost -p 5442 -U wmp -d postgres -c "CREATE DATABASE wmp" >/dev/null
    $BIN/redis-cli -p 6390 ping >/dev/null 2>&1 || $BIN/redis-server --port 6390 --daemonize yes --dir .local --logfile redis.log
    echo "postgres :5442, redis :6390 up";;
  stop)
    $BIN/pg_ctl -D "$PGDATA" stop >/dev/null 2>&1 || true
    $BIN/redis-cli -p 6390 shutdown nosave >/dev/null 2>&1 || true
    echo stopped;;
esac
