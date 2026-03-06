#! /usr/bin/env bash

set -e
set -x

cd backend
uv run python -c "import json; from pathlib import Path; import app.main; Path('../openapi.json').write_text(json.dumps(app.main.app.openapi(), indent=2) + '\n')"
cd ..
cp openapi.json frontend/openapi.json
cd frontend
npm run generate-client
npx biome format --write --no-errors-on-unmatched --files-ignore-unknown=true ./src/client
