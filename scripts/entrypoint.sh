#!/usr/bin/env bash
set -eEuo pipefail

###############################################################################
# 0. Guard-rails, debug & Linode→AWS shim
###############################################################################
[[ -z "${PROMPTS_NDJSON:-}"           ]] && { echo "[ERROR] PROMPTS_NDJSON empty"; exit 1; }
[[ -z "${LINODE_ACCESS_KEY_ID:-}"     ]] && { echo "[ERROR] LINODE_ACCESS_KEY_ID missing"; exit 1; }
[[ -z "${LINODE_SECRET_ACCESS_KEY:-}" ]] && { echo "[ERROR] LINODE_SECRET_ACCESS_KEY missing"; exit 1; }
[[ -z "${LINODE_S3_ENDPOINT:-}"       ]] && { echo "[ERROR] LINODE_S3_ENDPOINT missing"; exit 1; }
[[ -z "${LINODE_DEFAULT_REGION:-}"    ]] && { echo "[ERROR] LINODE_DEFAULT_REGION missing"; exit 1; }

export AWS_ACCESS_KEY_ID="$LINODE_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$LINODE_SECRET_ACCESS_KEY"
export S3_ENDPOINT="$LINODE_S3_ENDPOINT"
export AWS_S3_ADDRESSING_STYLE=path

export PS4='[\D{%F %T}] ${BASH_SOURCE##*/}:${LINENO}: '
set -x

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
# 2. Verify Qwen-3 generator script
###############################################################################
[[ -f "/workspace/repo/scripts/generate_qwen3.py" ]] || {
  echo "[ERROR] /workspace/repo/scripts/generate_qwen3.py not found"; exit 1;
}

###############################################################################
# 3. Install Qwen-3 text→image dependencies
###############################################################################
echo "[INFO] Installing Qwen-3 text-to-image dependencies…"
python3 -m pip install --no-cache-dir \
  diffusers accelerate transformers safetensors Pillow

# Optional: pre-cache the model to speed up first inference
MODEL_ID=${MODEL_ID:-hahahafofo/Qwen-3-text2image-diffusers}
echo "[INFO] Pre-caching model weights for ${MODEL_ID}…"
python3 -c "from diffusers import DiffusionPipeline; DiffusionPipeline.from_pretrained('${MODEL_ID}', torch_dtype='auto', trust_remote_code=True)"

echo "[INFO] Qwen-3 dependencies installed and model cached."

###############################################################################
# 4. Prompt file & output dir
###############################################################################
OUT_DIR=/tmp/out
mkdir -p /tmp && printf '%s\n' "$PROMPTS_NDJSON" > /tmp/prompts.ndjson
rm -rf "$OUT_DIR" && mkdir -p "$OUT_DIR"

TOTAL=$(wc -l < /tmp/prompts.ndjson)
STAMP=$(date +"%Y-%m-%d_%H-%M-%S")
: "${SPEC_SHEET_BUCKET:=castlesidegamestudio-spec-sheets}"
S3_PREFIX="s3://${SPEC_SHEET_BUCKET}/${STAMP}"

echo "[INFO] Prompts: $TOTAL"
echo "[INFO] Destination: $S3_PREFIX"

###############################################################################
# 5. Run Qwen-3 image generation
###############################################################################
echo "[INFO] Launching Qwen-3 Diffusers batch render…"
python3 /workspace/repo/scripts/generate_qwen3.py
echo "[✓] Qwen-3 batch render complete."

###############################################################################
# 6. Upload results
###############################################################################
echo "[INFO] Uploading outputs to S3…"
aws s3 sync "$OUT_DIR/" "$S3_PREFIX/" \
    --endpoint-url "$S3_ENDPOINT" \
    --region "$LINODE_DEFAULT_REGION" \
    --only-show-errors --no-progress

###############################################################################
# 7. All done
###############################################################################
echo "[✓] All $TOTAL prompts processed and uploaded."
