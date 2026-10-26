#!/usr/bin/env bash
# Meridian deploy: build frontend → bundle deploy (app config + resources) →
# stage clean source → import-dir → apps deploy.
# Usage: ./scripts/deploy.sh   (profile: $DATABRICKS_CONFIG_PROFILE or DEFAULT)
set -euo pipefail
cd "$(dirname "$0")/.."

PROFILE="${DATABRICKS_CONFIG_PROFILE:-DEFAULT}"
APP_NAME="meridian"
WS_SRC="/Workspace/Users/alex.barreto@climb.ai/apps/${APP_NAME}"
STAGE="$(mktemp -d)/src"

echo "==> building frontend"
npm run build

echo "==> bundle deploy (app config + resources)"
databricks bundle deploy -t dev --profile "${PROFILE}"

echo "==> staging deployable source"
mkdir -p "${STAGE}"
cp -R app "${STAGE}/"
cp app.yaml requirements.txt NOTICE "${STAGE}/"
find "${STAGE}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "==> uploading source"
databricks workspace delete "${WS_SRC}" --recursive --profile "${PROFILE}" 2>/dev/null || true
databricks workspace mkdirs "${WS_SRC}" --profile "${PROFILE}"
databricks workspace import-dir "${STAGE}" "${WS_SRC}" --profile "${PROFILE}"

echo "==> deploying"
databricks apps deploy "${APP_NAME}" \
  --source-code-path "${WS_SRC}" \
  --profile "${PROFILE}"

echo "==> status"
databricks apps get "${APP_NAME}" --profile "${PROFILE}" -o json | python3 -c "import json,sys; a=json.load(sys.stdin); print(a.get('url'), a.get('app_status'))"
