#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# entrypoint.sh – pull checkpoints, render every NDJSON prompt,
#                 upload PNGs to S3, then exit.
# ---------------------------------------------------------------------------
set -euo pipefail

### 0. Guard-rails -----------------------------------------------------------
[[ -z "${PROMPTS_NDJSON:-}"    ]] && { echo "[ERROR] PROMPTS_NDJSON empty"; exit 1; }
[[ -z "${AWS_ACCESS_KEY_ID:-}" ]] && { echo "[ERROR] AWS creds missing";  exit 1; }

### 1. One-time tool sanity (jq + awscli often missing) ----------------------
command -v jq  >/dev/null || { apt-get update -qq && apt-get install -y jq; }

command -v aws >/dev/null || {
    apt-get update -qq && apt-get install -y python3-pip
    python3 -m pip install --no-cache-dir --upgrade 'awscli>=2'
}

### 2. Graph overlays --------------------------------------------------------
# Repo already cloned by dockerStartCmd into /workspace/repo
cp /workspace/repo/graphs/*.json  /workspace/ComfyUI/flows/ || true

### 3. Sync checkpoints from S3 ---------------------------------------------
mkdir -p /workspace/ComfyUI/models/checkpoints
aws s3 sync s3://castlesidegamestudio-checkpoints/ \
            /workspace/ComfyUI/models/checkpoints/ \
            --exclude "*" --include "*.safetensors"

echo "[INFO] Graphs + checkpoints ready."

### 4. Prepare prompt file ---------------------------------------------------
COMFY=/workspace/ComfyUI
OUT_DIR=/tmp/out
mkdir -p /tmp && echo "$PROMPTS_NDJSON" > /tmp/prompts.ndjson
rm -rf "$OUT_DIR" && mkdir -p "$OUT_DIR"

TOTAL=$(wc -l < /tmp/prompts.ndjson); COUNT=0
STAMP=$(date +"%Y-%m-%d_%H-%M-%S")
S3_PREFIX="s3://castlesidegamestudio-spec-sheets/${STAMP}"

echo "[INFO] Prompts : $TOTAL"
echo "[INFO] S3 dest : $S3_PREFIX"

### 5. Start ComfyUI head-less ----------------------------------------------
python "$COMFY/main.py" --dont-print-server --listen 0.0.0.0 --port 8188 \
        --output-directory "$OUT_DIR" &
SERVER_PID=$!
until curl -s http://localhost:8188/system_stats >/dev/null; do sleep 1; done
echo "[INFO] ComfyUI server ready."

wait_new() { local n="$1"; until [[ $(ls -1 "$OUT_DIR" | wc -l) -gt $n ]]; do sleep 1; done; ls -1t "$OUT_DIR" | head -n1; }

### 6. Render loop -----------------------------------------------------------
while IFS= read -r PJ; do
  COUNT=$((COUNT+1))
  PID=$(jq -r '.id // empty' <<<"$PJ"); [[ -z "$PID" || "$PID" == null ]] && PID=$(printf "%03d" "$COUNT")
  STYLE=$(jq -r '.style' <<<"$PJ")
  GRAPH_JSON=$(jq -c . "$COMFY/flows/graph_${STYLE}.json")

  echo "[${COUNT}/${TOTAL}] Rendering ${PID}"

  PAYLOAD=$(jq -c --argjson g "$GRAPH_JSON" --argjson p "$PJ" \
           '{prompt:$g, extra_data:{id:$p.id}}')

  BEFORE=$(ls -1 "$OUT_DIR" | wc -l)
  curl -s -X POST -H 'Content-Type: application/json' -d "$PAYLOAD" \
       http://localhost:8188/prompt >/dev/null

  PNG=$(wait_new "$BEFORE")
  mv "$OUT_DIR/$PNG" "$OUT_DIR/${PID}.png"

  echo "[${COUNT}/${TOTAL}] Uploading to ${S3_PREFIX}/${PID}/"
  aws s3 cp "$OUT_DIR/${PID}.png" "${S3_PREFIX}/${PID}/"
  rm -f "$OUT_DIR/${PID}.png"
done < /tmp/prompts.ndjson

### 7. Cleanup ---------------------------------------------------------------
kill "$SERVER_PID"
echo "[✓] All $TOTAL prompts processed and uploaded."
