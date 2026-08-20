#!/usr/bin/env bash
# Web-service entrypoint: bind the port immediately, initialize behind it.
#
# This script used to run `python scripts/ensure_index.py` — a full embed of the
# corpus — BEFORE exec'ing uvicorn. Nothing listened on the port until that
# finished, so Hugging Face's health check saw a dead port and eventually killed
# the deployment with "Launch timed out, workload was not healthy after 30 min".
#
# Now the app's lifespan hook (src/ritaj/api.py) starts initialization on a
# background thread after uvicorn is already accepting connections:
#   /live   answers immediately  -> the platform knows the process is healthy
#   /ready  503s until warm      -> traffic is withheld, the container survives
#   chat    503 INITIALIZING     -> clients retry instead of seeing a dead socket
set -euo pipefail

# HF Spaces routes to 7860 by default; Railway/others inject $PORT.
PORT="${PORT:-7860}"

# The container app dir is read-only for the runtime user on HF Spaces, so the
# runtime writers (chat log for /admin, calibration overrides) and the embedded
# Qdrant storage default to /tmp there. Local dev (uvicorn directly, no
# start.sh) keeps the repo-root files.
export CHAT_LOG_PATH="${CHAT_LOG_PATH:-/tmp/chat_log.jsonl}"
export CALIBRATION_PATH="${CALIBRATION_PATH:-/tmp/calibration.json}"
# QDRANT_PATH only means anything in embedded mode. In remote mode it must be
# EMPTY, because config.qdrant_problems refuses a configuration carrying both —
# an ambiguous store is how a deployment ends up silently reading an empty local
# directory while everyone believes it is on the cluster.
#
# Unsetting has to happen here rather than on the host: the Dockerfile bakes
# QDRANT_PATH=/tmp/qdrant into the image as the embedded default, and an image
# ENV cannot be removed by clearing a platform variable — it is already in the
# process environment before anything on the host is applied.
if [ "${QDRANT_MODE:-auto}" = "remote" ]; then
  unset QDRANT_PATH
else
  export QDRANT_PATH="${QDRANT_PATH:-/tmp/qdrant}"
fi

# Only wait when pointing at a separate Qdrant server. Bounded, and never fatal:
# readiness reports the failure, rather than the entrypoint dying before the
# port is bound.
case "${QDRANT_URL:-}" in
  http*)
    echo "Waiting for Qdrant at ${QDRANT_URL} ..."
    for _ in $(seq 1 15); do
      if curl -sf "${QDRANT_URL}/readyz" >/dev/null 2>&1; then
        echo "Qdrant is ready."
        break
      fi
      sleep 2
    done
    ;;
esac

# One worker. Each worker loads its own copy of the embedder (~2 GB) and the
# reranker; two workers on a 2 vCPU / 16 GB Space means two model copies
# competing for two cores, which is slower than one and can OOM.
exec uvicorn ritaj.api:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers 1 \
  --timeout-keep-alive 65 \
  --log-level info
