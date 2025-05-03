#!/usr/bin/env bash
set -eEuo pipefail

###############################################################################
# 0. Guard-rails, debug & Linode→AWS shim
###############################################################################
[[ -z "${PROMPTS_NDJSON:-}"        ]] && { echo "[ERROR] PROMPTS_NDJSON empty"; exit 1; }
[[ -z "${LINODE_ACCESS_KEY_ID:-}"  ]] && { echo "[ERROR] LINODE_ACCESS_KEY_ID missing"; exit 1; }
[[ -z "${LINODE_SECRET_ACCESS_KEY:-}" ]] && { echo "[ERROR] LINODE_SECRET_ACCESS_KEY missing"; exit 1; }
[[ -z "${LINODE_S3_ENDPOINT:-}"    ]] && { echo "[ERROR] LINODE_S3_ENDPOINT missing"; exit 1; }
[[ -z "${LINODE_DEFAULT_REGION:-}" ]] && { echo "[ERROR] LINODE_DEFAULT_REGION missing"; exit 1; }

# Export so aws-cli can use them (no “dummy” region fallback).
export AWS_ACCESS_KEY_ID="$LINODE_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$LINODE_SECRET_ACCESS_KEY"
export S3_ENDPOINT="$LINODE_S3_ENDPOINT"
export AWS_S3_ADDRESSING_STYLE=path

export PS4='[\D{%F %T}] ${BASH_SOURCE##*/}:${LINENO}: '
set -x  # ultra-verbose tracing (will show commands as they run)

###############################################################################
# 1. Tool sanity  (jq, inotifywait, awscli)
###############################################################################
export DEBIAN_FRONTEND=noninteractive

command -v jq          >/dev/null || { apt-get update -qq && apt-get install -y --no-install-recommends jq; }
command -v inotifywait >/dev/null || { apt-get update -qq && apt-get install -y --no-install-recommends inotify-tools; }
command -v aws         >/dev/null || python3 -m pip install --no-cache-dir --upgrade 'awscli>=1.32'

###############################################################################
# 1b. Fix TorchAudio mismatch (PyTorch 12.4)
###############################################################################
echo "# Installing matching TorchAudio for CUDA 12.4..."
python3 -m pip install --no-cache-dir --force-reinstall \
  --index-url https://download.pytorch.org/whl/cu124 \
  torchaudio==2.5.1

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
echo "+ aws s3 ls s3://${CHECKPOINT_BUCKET} --endpoint-url '${S3_ENDPOINT}' --region '${LINODE_DEFAULT_REGION}'"

if ! aws s3 ls "s3://${CHECKPOINT_BUCKET}" \
               --endpoint-url "$S3_ENDPOINT" \
               --region "$LINODE_DEFAULT_REGION" >/dev/null 2>&1; then

  echo "[ERROR] Bucket check failed for 's3://${CHECKPOINT_BUCKET}'."
  echo
  echo "Here are some common causes and tips to fix them:"
  echo "  • **Misspelled or non-existent bucket name**."
  echo "    Double-check the bucket name in your script vs. what you see if you run:"
  echo "      aws s3 ls --endpoint-url ${S3_ENDPOINT} --region ${LINODE_DEFAULT_REGION}"
  echo
  echo "  • **Mismatch between bucket region and endpoint**."
  echo "    For example, if the bucket is in Newark (us-east-1.linodeobjects.com),"
  echo "    but you're using us-ord-1.linodeobjects.com (Chicago). You can confirm"
  echo "    the bucket's location by running:"
  echo "      aws s3api get-bucket-location --bucket ${CHECKPOINT_BUCKET} \\"
  echo "        --endpoint-url ${S3_ENDPOINT} --region ${LINODE_DEFAULT_REGION}"
  echo
  echo "  • **Insufficient credentials**."
  echo "    Your Linode key must have permissions for this bucket (list, read, etc.)."
  echo
  echo "Tip: To see the CLI's exact error message, remove '--only-show-errors' or run"
  echo "the same 'aws s3 ls' command manually without redirecting to /dev/null."
  echo
  echo "[FATAL] Exiting due to bucket-access error."
  exit 1
fi

mkdir -p "$COMFY_DIR/models/checkpoints"
echo "+ aws s3 sync s3://${CHECKPOINT_BUCKET}/ $COMFY_DIR/models/checkpoints/ --endpoint-url '${S3_ENDPOINT}' --region '${LINODE_DEFAULT_REGION}' --exclude '*' --include '*.safetensors' --only-show-errors --no-progress"

aws s3 sync "s3://${CHECKPOINT_BUCKET}/" \
            "$COMFY_DIR/models/checkpoints/" \
            --endpoint-url "$S3_ENDPOINT" \
            --region "$LINODE_DEFAULT_REGION" \
            --exclude "*" --include "*.safetensors" \
            --only-show-errors --no-progress

# Debug: Show what actually got synced
echo "# After syncing, here are all files in $COMFY_DIR/models/checkpoints:"
find "$COMFY_DIR/models/checkpoints" -type f

echo "# Specifically, here are any *.safetensors files:"
ls -lah "$COMFY_DIR/models/checkpoints/"*.safetensors || echo "[INFO] No *.safetensors found."

# Verify at least one .safetensors file exists:
if ! ls -1 "$COMFY_DIR/models/checkpoints/"*.safetensors >/dev/null 2>&1; then
  echo "[FATAL] No *.safetensors files downloaded. Did you forget to upload them?"
  exit 1
fi

# ---------------------------------------------------------------------------
# ADDITIONAL CHECK: ensure each graph_BloodMagic.json (etc.) references a ckpt_name
# that actually exists in models/checkpoints.
# ---------------------------------------------------------------------------
echo "# Validating that each 'CheckpointLoaderSimple' node's ckpt_name is present..."
for FLOW_JSON in "$COMFY_DIR/flows"/graph_*.json; do
  if [[ ! -f "$FLOW_JSON" ]]; then
    continue  # skip if none found
  fi
  echo "Checking flow: $FLOW_JSON"
  
  # Extract every 'ckpt_name' from each CheckpointLoaderSimple node:
  # (If no matches, jq returns nothing.)
  while IFS= read -r CKPT; do
    [[ -z "$CKPT" ]] && continue
    if [[ ! -f "$COMFY_DIR/models/checkpoints/$CKPT" ]]; then
      echo "[FATAL] Graph '$FLOW_JSON' references '$CKPT', but that file does not exist in '$COMFY_DIR/models/checkpoints/'."
      exit 1
    else
      echo "  - Found checkpoint '$CKPT' for graph '$FLOW_JSON' ✓"
    fi
  done < <(
    jq -r '.nodes[]? 
             | select(.type=="CheckpointLoaderSimple") 
             | .inputs.ckpt_name // empty' "$FLOW_JSON"
  )
done

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
  echo "+ aws s3 cp $OUT_DIR/${PID}.png ${S3_PREFIX}/${PID}/ --endpoint-url '${S3_ENDPOINT}' --region '${LINODE_DEFAULT_REGION}' --only-show-errors --no-progress"
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
