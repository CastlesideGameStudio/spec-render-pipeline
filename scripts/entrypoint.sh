#!/usr/bin/env bash
set -euo pipefail

# ───────────── sanity checks ────────────────────────────────────────────────
[[ -z "${PROMPTS_NDJSON:-}"       ]] && { echo "[ERROR] PROMPTS_NDJSON empty"; exit 1; }
[[ -z "${AWS_ACCESS_KEY_ID:-}"    ]] && { echo "[ERROR] AWS creds missing";  exit 1; }

# ───────────── workspace ────────────────────────────────────────────────────
mkdir -p /tmp
echo "$PROMPTS_NDJSON" > /tmp/prompts.ndjson
OUT_DIR=/tmp/out; rm -rf "$OUT_DIR" && mkdir -p "$OUT_DIR"

TOTAL=$(wc -l < /tmp/prompts.ndjson); COUNT=0
STAMP=$(date +"%Y-%m-%d_%H-%M-%S")
S3_PREFIX="s3://castlesidegamestudio-spec-sheets/${STAMP}"

echo "[INFO] Prompts : $TOTAL"
echo "[INFO] S3 dest : $S3_PREFIX"

# ───────────── start ComfyUI head-less once ────────────────────────────────
python /app/ComfyUI/main.py --dont-print-server --listen 0.0.0.0 --port 8188 --output-directory "$OUT_DIR" &
SERVER_PID=$!

until curl -s http://localhost:8188/system_stats >/dev/null 2>&1; do sleep 1; done
echo "[INFO] ComfyUI server ready."

# helper: wait for a new PNG to appear
wait_for_new_png() {
    local before="$1"
    until [[ $(ls -1 "$OUT_DIR" | wc -l) -gt $before ]]; do sleep 1; done
    ls -1t "$OUT_DIR" | head -n1
}

# ───────────── main loop ────────────────────────────────────────────────────
while IFS= read -r PROMPT_JSON; do
  COUNT=$((COUNT+1))
  PROMPT_ID=$(jq -r '.id // empty' <<<"$PROMPT_JSON")
  [[ -z "$PROMPT_ID" || "$PROMPT_ID" == "null" ]] && PROMPT_ID=$(printf "%03d" "$COUNT")

  STYLE=$(jq -r '.style' <<<"$PROMPT_JSON")
  GRAPH_PATH="/app/ComfyUI/flows/graph_${STYLE}.json"
  GRAPH_JSON=$(jq -c . "$GRAPH_PATH")          # compact object, not string

  echo "[${COUNT}/${TOTAL}] Rendering ${PROMPT_ID}"

  # build HTTP payload: graph object + prompt metadata
  PAYLOAD=$(jq -c \
      --argjson graph "$GRAPH_JSON" \
      --argjson prompt "$PROMPT_JSON" \
      '{ "prompt": $graph, "extra_data": { "id": $prompt.id } }')

  BEFORE=$(ls -1 "$OUT_DIR" | wc -l)
  curl -s -X POST -H 'Content-Type: application/json' \
       -d "$PAYLOAD" http://localhost:8188/prompt > /dev/null

  PNG=$(wait_for_new_png "$BEFORE")
  mv "$OUT_DIR/$PNG" "$OUT_DIR/${PROMPT_ID}.png"

  echo "[${COUNT}/${TOTAL}] Uploading to ${S3_PREFIX}/${PROMPT_ID}/"
  aws s3 cp "$OUT_DIR/${PROMPT_ID}.png" "${S3_PREFIX}/${PROMPT_ID}/"
  rm -f "$OUT_DIR/${PROMPT_ID}.png"
done < /tmp/prompts.ndjson

kill "$SERVER_PID"
echo "[✓] All $TOTAL prompts processed and uploaded."
