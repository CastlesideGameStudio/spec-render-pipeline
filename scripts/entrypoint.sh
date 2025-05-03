#!/usr/bin/env bash
set -eEuo pipefail

###############################################################################
# 0. Guard-rails, debug & Linode→AWS shim
###############################################################################
[[ -z "${PROMPTS_NDJSON:-}"        ]] && { echo "[ERROR] PROMPTS_NDJSON empty"; exit 1; }
[[ -z "${LINODE_ACCESS_KEY_ID:-}"  ]] && { echo "[ERROR] LINODE creds missing";  exit 1; }
[[ -z "${LINODE_SECRET_ACCESS_KEY:-}" ]] && { echo "[ERROR] LINODE creds missing";  exit 1; }
[[ -z "${LINODE_S3_ENDPOINT:-}"    ]] && { echo "[ERROR] LINODE_S3_ENDPOINT missing"; exit 1; }

: "${LINODE_DEFAULT_REGION:=us-east-1}"   # arbitrary placeholder for awscli

# ── internal-only export so the AWS CLI can run; you never set AWS_* in GH Actions
export AWS_ACCESS_KEY_ID="$LINODE_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$LINODE_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="$LINODE_DEFAULT_REGION"
export S3_ENDPOINT="$LINODE_S3_ENDPOINT"

export PS4='[\D{%F %T}] ${BASH_SOURCE##*/}:${LINENO}: '
set -x                                    # ultra-verbose tracing

###############################################################################
# 1. Tool sanity  (jq, inotifywait, awscli)
###############################################################################
export DEBIAN_FRONTEND=noninteractive

command -v jq          >/dev/null || { apt-get update -qq && apt-get install -y --no-install-recommends jq; }
command -v inotifywait >/dev/null || { apt-get update -qq && apt-get install -y --no-install-recommends inotify-tools; }
command -v aws         >/dev/null || python3 -m pip install --no-cache-dir --upgrade 'awscli>=1.32'

###############################################################################
# 2. Locate ComfyUI
###############################################################################
for d in /workspace/ComfyUI /opt/ComfyUI /ComfyUI; do
  [[ -d "$d" ]] && { COMFY_DIR="$d"; break; }
done
[[ -d "${COMFY_DIR:-}" ]] || { echo "[ERROR] ComfyUI directory not found"; exit 1; }

mkdir -p "$COMFY_DIR/flows"
cp /workspace/repo/graphs/*.json "$COMFY_DIR/flows/" 2>/dev/null || true

###############################################################################
# 3. Sync checkpoints from Linode Object Storage
###############################################################################
: "${CHECKPOINT_BUCKET:=castlesidegamestudio-checkpoints}"

echo "# sanity-check bucket access:"
echo "+ aws s3 ls s3://${CHECKPOINT_BUCKET}"
if ! aws s3 ls "s3://${CHECKPOINT_BUCKET}" \
               --endpoint-url "$S3_ENDPOINT" \
               --region "$LINODE_DEFAULT_REGION" \
               --only-show-errors >/dev/null 2>&1; then
  echo "[FATAL] Cannot ListBucket on '${CHECKPOINT_BUCKET}'. Check your Linode keys."
  exit 1
fi

mkdir -p "$COMFY_DIR/models/checkpoints"
aws s3 sync "s3://${CHECKPOINT_BUCKET}/" \
            "$COMFY_DIR/models/checkpoints/" \
            --endpoint-url "$S3_ENDPOINT" \
            --region "$LINODE_DEFAULT_REGION" \
            --exclude "*" --include "*.safetensors" \
            --only-show-errors --no-progress

echo "[INFO] Graphs + checkpoints ready."

###############################################################################
# 4. Prompt file & output dir
###############################################################################
OUT_DIR=/tmp/out
mkdir -p /tmp && printf '%s\n' "$PROMPTS_NDJSON" > /tmp/prompts.ndjson
rm -rf "$OUT_DIR" && mkdir -p "$OUT_DIR"

TOTAL=$(wc -l < /tmp/prompts.ndjson); COUNT=0
STAMP=$(date +"%Y-%m-%d_%H-%M-%S")
: "${SPEC_SHEET_BUCKET:=castlesidegamestudio-spec-sheets}"
S3_PREFIX="s3://${SPEC_SHEET_BUCKET}/${STAMP}"

echo "[INFO] Prompts : $TOTAL"
echo "[INFO] Linode dest : $S3_PREFIX"

###############################################################################
# 5. Start ComfyUI headless
###############################################################################
python3 "$COMFY_DIR/main.py" --dont-print-server --listen 0.0.0.0 --port 8188 \
        --output-directory "$OUT_DIR" &
SERVER_PID=$!
trap 'kill "$SERVER_PID"' EXIT

until curl -s --fail --connect-timeout 2 http://localhost:8188/system_stats >/dev/null; do
  sleep 1
done
echo "[INFO] ComfyUI server ready."

wait_new() { inotifywait -q -e create --format '%f' "$OUT_DIR" | head -n1; }

###############################################################################
# 6. Render loop
###############################################################################
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

  echo "[${COUNT}/${TOTAL}] Uploading → ${S3_PREFIX}/${PID}/"
  aws s3 cp "$OUT_DIR/${PID}.png" "${S3_PREFIX}/${PID}/" \
           --endpoint-url "$S3_ENDPOINT" \
           --region "$LINODE_DEFAULT_REGION" \
           --only-show-errors --no-progress
  rm -f "$OUT_DIR/${PID}.png"
done < /tmp/prompts.ndjson

###############################################################################
# 7. All done
###############################################################################
echo "[✓] All $TOTAL prompts processed and uploaded."
