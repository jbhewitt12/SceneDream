#! /usr/bin/env bash

# Exit in case of error
set -e

if [ "${ALLOW_DB_RESET:-}" = "1" ]; then
    docker-compose down -v --remove-orphans # Remove possibly previous broken stacks left hanging after an error
else
    echo "Skipping 'docker-compose down -v'; set ALLOW_DB_RESET=1 to delete volumes" >&2
    docker-compose down --remove-orphans
fi

if [ $(uname -s) = "Linux" ]; then
    echo "Remove __pycache__ files"
    sudo find . -type d -name __pycache__ -exec rm -r {} \+
fi

docker-compose build
docker-compose up -d
docker-compose exec -T backend bash scripts/tests-start.sh "$@"
