#!/usr/bin/env bash
# Web-service entrypoint: (optionally) wait for Qdrant, ensure the index, serve.
# Works for both an external Qdrant server (QDRANT_URL=http://...) and embedded
# on-disk Qdrant (QDRANT_PATH=...), e.g. the single-container HF Spaces deploy.
set -euo pipefail

# HF Spaces routes to 7860 by default; Railway/others inject $PORT.
PORT="${PORT:-7860}"

# The container app dir is read-only for the runtime user on HF Spaces, so the
# runtime writers (chat log for /admin, calibration overrides) default to /tmp
# there. Local dev (uvicorn directly, no start.sh) keeps the repo-root files.
export CHAT_LOG_PATH="${CHAT_LOG_PATH:-/tmp/chat_log.jsonl}"
export CALIBRATION_PATH="${CALIBRATION_PATH:-/tmp/calibration.json}"

# Only wait when pointing at a separate Qdrant server.
case "${QDRANT_URL:-}" in
  http*)
    echo "Waiting for Qdrant at ${QDRANT_URL} ..."
    for _ in $(seq 1 30); do
      if curl -sf "${QDRANT_URL}/readyz" >/dev/null 2>&1; then
        echo "Qdrant is ready."
        break
      fi
      sleep 2
    done
    ;;
esac

# Populate the vector store on first boot (rebuilt each boot for embedded mode).
python scripts/ensure_index.py || echo "WARNING: index bootstrap failed; continuing."

exec uvicorn ritaj.api:app --host 0.0.0.0 --port "${PORT}"
