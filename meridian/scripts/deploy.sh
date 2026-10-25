#!/usr/bin/env bash
# Meridian deploy: build frontend → bundle validate/deploy → apps deploy.
# Usage: ./scripts/deploy.sh [target]   (default: dev)
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:-dev}"
PROFILE="${DATABRICKS_CONFIG_PROFILE:-DEFAULT}"
APP_NAME="meridian"
WS_SRC="/Workspace/Users/alex.barreto@climb.ai/apps/${APP_NAME}"

echo "==> building frontend"
npm run build

echo "==> bundle validate"
databricks bundle validate -t "${TARGET}" --profile "${PROFILE}"

echo "==> uploading source"
databricks workspace mkdirs "${WS_SRC}" --profile "${PROFILE}"
databricks workspace import-dir . "${WS_SRC}" --overwrite --profile "${PROFILE}"

echo "==> ensuring app exists"
databricks apps get "${APP_NAME}" --profile "${PROFILE}" >/dev/null 2>&1 || \
  databricks apps create "${APP_NAME}" --profile "${PROFILE}"

echo "==> deploying"
databricks apps deploy "${APP_NAME}" \
  --source-code-path "${WS_SRC}" \
  --profile "${PROFILE}"

echo "==> status"
databricks apps get "${APP_NAME}" --profile "${PROFILE}" -o json | python3 -c "import json,sys; a=json.load(sys.stdin); print(a.get('url'))"
