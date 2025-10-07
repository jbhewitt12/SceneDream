#! /usr/bin/env sh

# Exit in case of error
set -e
set -x

docker compose build

if [ "${ALLOW_DB_RESET:-}" = "1" ]; then
    docker compose down -v --remove-orphans # Remove possibly previous broken stacks left hanging after an error
else
    echo "Skipping 'docker compose down -v'; set ALLOW_DB_RESET=1 to delete volumes" >&2
    docker compose down --remove-orphans
fi
docker compose up -d
docker compose exec -T backend bash scripts/tests-start.sh "$@"

if [ "${ALLOW_DB_RESET:-}" = "1" ]; then
    docker compose down -v --remove-orphans
else
    echo "Skipping 'docker compose down -v'; set ALLOW_DB_RESET=1 to delete volumes" >&2
    docker compose down --remove-orphans
fi
