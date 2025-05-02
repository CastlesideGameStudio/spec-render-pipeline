#!/usr/bin/env bash
set -eEuo pipefail

################################## 0. Guard-rails ##################################
[[ -z "${PROMPTS_NDJSON:-}"    ]] && { echo "[ERROR] PROMPTS_NDJSON empty"; exit 1; }
[[ -z "${AWS_ACCESS_KEY_ID:-}" ]] && { echo "[ERROR] AWS creds missing";  exit 1; }

# ---------- default AWS region (override via env) ----------
: "${AWS_DEFAULT_REGION:=us-east-2}"

################################## 1. Tool sanity ##################################
export DEBIAN_FRONTEND=noninteractive   # silence tz-data prompts

# jq + inotifywait (from inotify-tools) + pip in one pass if anything’s missing
command -v jq >/dev/null && command -v inotifywait >/dev/null || {
  apt-get update -qq && \
  apt-get install -y --no-install-recommends jq python3-pip inotify-tools
}

# AWS CLI (install only if absent)
command -v aws >/dev/null || {
  python3 -m pip install --no-cache-dir --upgrade 'awscli>=1.32'
}

################################## 2. Locate ComfyUI ################################
for d in /workspace/ComfyUI /opt/ComfyUI /ComfyUI; do
  if [[ -d "$d" ]]; then
    COMFY_DIR="$d"
    break
  fi
done
[[ -d "${COMFY_DIR:-}" ]] || { echo "[ERROR] ComfyUI directory not found"; exit 1; }

mkdir -p "$COMFY_DIR/flows"
cp /workspace/repo/graphs/*.json "$COMFY_DIR/flows/" 2>/dev/null || true

################################## 3. Checkpoints from S3 ###########################
: "${CHECKPOINT_BUCKET:=castlesidegamestudio-checkpoints}"

aws s3 ls "s3://${CHECKPOINT_BUCKET}" --region "$AWS_DEFAULT_REGION" >/dev/null 2>&1 || {
  echo "[ERROR] S3 bucket ${CHECKPOINT_BUCKET} not found."
  exit 1
}

mkdir -p "$COMFY_DIR/models/checkpoints"
aws s3 sync "s3://${CHECKPOINT_BUCKET}/" \
            "$COMFY_DIR/models/checkpoints/" \
            --region "$AWS_DEFAULT_REGION" \
            --exclude "*" --include "*.safetensors"

echo "[INFO] Graphs + checkpoints ready."

################################## 4. Prompt file & output dir ######################
OUT_DIR=/tmp/out
mkdir -p /tmp && echo "$PROMPTS_NDJSON" > /tmp/prompts.ndjson
rm -rf "$OUT_DIR" && mkdir -p "$OUT_DIR"

TOTAL=$(wc -l < /tmp/prompts.ndjson); COUNT=0
STAMP=$(date +"%Y-%m-%d_%H-%M-%S")
: "${SPEC_SHEET_BUCKET:=castlesidegamestudio-spec-sheets}"
S3_PREFIX="s3://${SPEC_SHEET_BUCKET}/${STAMP}"

echo "[INFO] Prompts : $TOTAL"
echo "[INFO] S3 dest : $S3_PREFIX"

################################## 5. Start ComfyUI headless ########################
python3 "$COMFY_DIR/main.py" --dont-print-server --listen 0.0.0.0 --port 8188 \
        --output-directory "$OUT_DIR" &
SERVER_PID=$!
trap 'kill "$SERVER_PID"' EXIT          # always clean up on exit

until curl -s --fail --connect-timeout 2 http://localhost:8188/system_stats >/dev/null; do
  sleep 1
done
echo "[INFO] ComfyUI server ready."

# Helper: block until the next file appears in $OUT_DIR, return its name
wait_new() {
  inotifywait -q -e create --format '%f' "$OUT_DIR" | head -n1
}

################################## 6. Render loop ###################################
while IFS= read -r PJ; do
  COUNT=$((COUNT+1))
  PID=$(jq -r '.id // empty' <<<"$PJ")
  [[ -z "$PID" || "$PID" == null ]] && PID=$(printf "%03d" "$COUNT")
  STYLE=$(jq -r '.style' <<<"$PJ")
  GRAPH_JSON=$(jq -c . "$COMFY_DIR/flows/graph_${STYLE}.json")

  echo "[${COUNT}/${TOTAL}] Rendering ${PID}"

  PAYLOAD=$(jq -c --argjson g "$GRAPH_JSON" --argjson p "$PJ" \
            '{prompt:$g, extra_data:{id:$p.id}}')

  curl -s -X POST -H 'Content-Type: application/json' -d "$PAYLOAD" \
       http://localhost:8188/prompt >/dev/null

  PNG=$(wait_new)
  mv "$OUT_DIR/$PNG" "$OUT_DIR/${PID}.png"

  echo "[${COUNT}/${TOTAL}] Uploading to ${S3_PREFIX}/${PID}/"
  aws s3 cp "$OUT_DIR/${PID}.png" "${S3_PREFIX}/${PID}/" --region "$AWS_DEFAULT_REGION"
  rm -f "$OUT_DIR/${PID}.png"
done < /tmp/prompts.ndjson

################################## 7. All done ######################################
echo "[✓] All $TOTAL prompts processed and uploaded."
