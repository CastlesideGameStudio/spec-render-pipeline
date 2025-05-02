#!/usr/bin/env bash
set -euo pipefail

################################## 0. Guard-rails ##################################
[[ -z "${PROMPTS_NDJSON:-}"    ]] && { echo "[ERROR] PROMPTS_NDJSON empty"; exit 1; }
[[ -z "${AWS_ACCESS_KEY_ID:-}" ]] && { echo "[ERROR] AWS creds missing";  exit 1; }

################################## 1. Tool sanity ##################################
command -v jq  >/dev/null || { apt-get update -qq && apt-get install -y --no-install-recommends jq; }

command -v aws >/dev/null || {
    apt-get update -qq && apt-get install -y --no-install-recommends python3-pip
    python3 -m pip install --no-cache-dir --upgrade 'awscli>=1.32'
}

################################## 2. Locate ComfyUI ################################
# Community image paths in priority order
for d in /workspace/ComfyUI /opt/ComfyUI /ComfyUI; do
    if [[ -d "$d" ]]; then COMFY_DIR="$d"; break; fi
done

[[ -d "${COMFY_DIR:-}" ]] || { echo "[ERROR] ComfyUI directory not found"; exit 1; }

# be sure the flows folder exists so `cp` never complains
mkdir -p "$COMFY_DIR/flows"

# repo was cloned by dockerStartCmd → /workspace/repo
cp /workspace/repo/graphs/*.json "$COMFY_DIR/flows/" 2>/dev/null || true

################################## 3. Checkpoint bucket ################################
: "${CHECKPOINT_BUCKET:=castlesidegamestudio-checkpoints}"   # override in workflow if needed
aws s3 ls "s3://${CHECKPOINT_BUCKET}" >/dev/null 2>&1 || {
    echo "[ERROR] S3 bucket ${CHECKPOINT_BUCKET} not found."
    exit 1
}

mkdir -p "$COMFY_DIR/models/checkpoints"
aws s3 sync "s3://${CHECKPOINT_BUCKET}/" \
            "$COMFY_DIR/models/checkpoints/" \
            --exclude "*" --include "*.safetensors"

echo "[INFO] Graphs + checkpoints ready."

################################## 4. Prompt file & output dir #######################
OUT_DIR=/tmp/out
mkdir -p /tmp && echo "$PROMPTS_NDJSON" > /tmp/prompts.ndjson
rm -rf "$OUT_DIR" && mkdir -p "$OUT_DIR"

TOTAL=$(wc -l < /tmp/prompts.ndjson); COUNT=0
STAMP=$(date +"%Y-%m-%d_%H-%M-%S")
: "${SPEC_SHEET_BUCKET:=castlesidegamestudio-spec-sheets}"   # override if desired
S3_PREFIX="s3://${SPEC_SHEET_BUCKET}/${STAMP}"

echo "[INFO] Prompts : $TOTAL"
echo "[INFO] S3 dest : $S3_PREFIX"

################################## 5. Start ComfyUI headless #########################
python "$COMFY_DIR/main.py" --dont-print-server --listen 0.0.0.0 --port 8188 \
        --output-directory "$OUT_DIR" &
SERVER_PID=$!
until curl -s http://localhost:8188/system_stats >/dev/null; do sleep 1; done
echo "[INFO] ComfyUI server ready."

wait_new() { local n="$1"; until [[ $(ls -1 "$OUT_DIR" | wc -l) -gt $n ]]; do sleep 1; done; ls -1t "$OUT_DIR" | head -n1; }

################################## 6. Render loop ####################################
while IFS= read -r PJ; do
  COUNT=$((COUNT+1))
  PID=$(jq -r '.id // empty' <<<"$PJ"); [[ -z "$PID" || "$PID" == null ]] && PID=$(printf "%03d" "$COUNT")
  STYLE=$(jq -r '.style' <<<"$PJ")
  GRAPH_JSON=$(jq -c . "$COMFY_DIR/flows/graph_${STYLE}.json")

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

################################## 7. Cleanup ########################################
kill "$SERVER_PID"
echo "[✓] All $TOTAL prompts processed and uploaded."
