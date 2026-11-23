#!/usr/bin/env bash
# Container entrypoint for the Hugging Face Space.
#
# A free Space has no persistent disk: the database, uploads and index live in
# ~/data and are wiped whenever the Space restarts or wakes from sleep. With
# SEED_DEMO=1 (the default) the demo accounts and items are recreated each time.
set -euo pipefail

PORT="${PORT:-7860}"
mkdir -p "$(dirname "${FAISS_INDEX_PATH}")" "${UPLOAD_DIR}"

if [ "${SEED_DEMO:-1}" = "1" ] && [ -d tests/fixtures/images ]; then
  (
    for _ in $(seq 1 150); do
      curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null && break
      sleep 2
    done
    CLF_BASE_URL="http://127.0.0.1:${PORT}" python scripts/seed_demo.py \
      || echo "demo seed failed; the app is still running"
  ) &
fi

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}"
