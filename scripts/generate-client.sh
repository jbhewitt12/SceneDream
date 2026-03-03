#! /usr/bin/env bash

set -e
set -x

cd backend
uv run python -c "import app.main; import json; print(json.dumps(app.main.app.openapi()))" > ../openapi.json
cd ..
cp openapi.json frontend/openapi.json
cd frontend
npm run generate-client
npx biome format --write --no-errors-on-unmatched --files-ignore-unknown=true ./src/client
