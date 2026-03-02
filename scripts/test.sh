#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/../backend"

echo "Running backend tests..."
uv run pytest "$@"
