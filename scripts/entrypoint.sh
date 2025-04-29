#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────── sanity checks ───────────────────────────────────
[[ -z "${PROMPTS_NDJSON:-}"       ]] && { echo "[ERROR] PROMPTS_NDJSON empty"; exit 1; }
[[ -z "${AWS_ACCESS_KEY_ID:-}"    ]] && { echo "[ERROR] AWS creds missing";  exit 1; }

# ────────────────────────── workspace setup ────────────────────────────────
mkdir -p /tmp && echo "$PROMPTS_NDJSON" > /tmp/prompts.ndjson
OUT_DIR=/tmp/out; rm -rf "$OUT_DIR" && mkdir -p "$OUT_DIR"

TOTAL=$(wc -l < /tmp/prompts.ndjson); COUNT=0
STAMP=$(date +"%Y-%m-%d_%H-%M-%S")
S3_PREFIX="s3://castlesidegamestudio-spec-sheets/${STAMP}"   # change if you like

echo "[INFO] Prompts: $TOTAL"
echo "[INFO] S3 dest: $S3_PREFIX"

# ────────────────────────── main loop ───────────────────────────────────────
while IFS= read -r PROMPT_JSON; do
  COUNT=$((COUNT+1))
  PROMPT_ID=$(jq -r '.id // empty' <<<"$PROMPT_JSON")
  [[ -z "$PROMPT_ID" || "$PROMPT_ID" == "null" ]] && PROMPT_ID=$(printf "%03d" "$COUNT")

  echo "[${COUNT}/${TOTAL}] Rendering $PROMPT_ID"

  # ---------- render via ComfyUI headless -----------------------------------
  #
  # The graph is chosen by .style (BloodMagic, Disney, MagicalLines, …)
  # and must exist in /app/ComfyUI/flows/graph_<style>.json
  #
  STYLE=$(jq -r '.style' <<<"$PROMPT_JSON")
  GRAPH="/app/ComfyUI/flows/graph_${STYLE}.json"

  python /app/ComfyUI/main.py \
         --output "$OUT_DIR" \
         --force-filename "${PROMPT_ID}.png" \
         --cli --dont-print-server \
         --extra-models-dir /app/ComfyUI/models \
         --load "${GRAPH}" \
         --prompt "$PROMPT_JSON"

  # -------------------------------------------------------------------------

  echo "[${COUNT}/${TOTAL}] Uploading to ${S3_PREFIX}/${PROMPT_ID}/"
  aws s3 cp "$OUT_DIR/${PROMPT_ID}.png" "${S3_PREFIX}/${PROMPT_ID}/"

  rm -f "$OUT_DIR/${PROMPT_ID}.png"          # clean up
done < /tmp/prompts.ndjson

echo "[✓] All $TOTAL prompts processed and uploaded."
