#!/usr/bin/env bash
set -euo pipefail

[[ -z "${PROMPTS_NDJSON:-}" ]] && { echo "[ERROR] PROMPTS_NDJSON empty"; exit 1; }
[[ -z "${AWS_ACCESS_KEY_ID:-}" ]] && { echo "[ERROR] AWS creds missing";  exit 1; }

COMFY=/workspace/ComfyUI                      # fixed path in Flux template
OUT=/tmp/out
echo "$PROMPTS_NDJSON" > /tmp/prompts.ndjson
mkdir -p "$OUT"; rm -f "$OUT"/*

TOTAL=$(wc -l < /tmp/prompts.ndjson); COUNT=0
STAMP=$(date +"%Y-%m-%d_%H-%M-%S")
S3="s3://castlesidegamestudio-spec-sheets/$STAMP"

echo "[INFO] Prompts : $TOTAL"
echo "[INFO] S3 dest : $S3"

python "$COMFY/main.py" --dont-print-server --listen 0.0.0.0 --port 8188 \
        --output-directory "$OUT" &
PID=$!
until curl -s http://localhost:8188/system_stats >/dev/null; do sleep 1; done

next_png() { local n=$1; until [[ $(ls "$OUT"|wc -l) -gt $n ]]; do sleep 1; done; ls -1t "$OUT"|head -n1; }

while IFS= read -r J; do
  COUNT=$((COUNT+1))
  ID=$(jq -r '.id // empty' <<<"$J"); [[ -z $ID || $ID == null ]] && ID=$(printf "%03d" "$COUNT")
  STYLE=$(jq -r '.style' <<<"$J")
  GRAPH=$(jq -c . "$COMFY/flows/graph_${STYLE}.json")

  PAYLOAD=$(jq -c --argjson g "$GRAPH" --argjson p "$J" '{prompt:$g,extra_data:{id:$p.id}}')
  BEFORE=$(ls "$OUT"|wc -l)
  curl -s -X POST -H 'Content-Type: application/json' -d "$PAYLOAD" http://localhost:8188/prompt >/dev/null

  PNG=$(next_png "$BEFORE")
  mv "$OUT/$PNG" "$OUT/${ID}.png"
  aws s3 cp "$OUT/${ID}.png" "$S/${ID}/"
done < /tmp/prompts.ndjson

kill "$PID"
echo "[✓] All $TOTAL prompts uploaded."
