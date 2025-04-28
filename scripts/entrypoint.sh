#!/bin/bash
set -e

# 1) AWS credentials are expected in the environment:
#    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION

# 2) Move into ComfyUI dir (if you need it)
cd /app/ComfyUI

# 3) Check if we have prompt data
if [ -z "$PROMPTS_NDJSON" ]; then
  echo "No PROMPTS_NDJSON provided, nothing to do."
  exit 0
fi

echo "$PROMPTS_NDJSON" > /tmp/prompts.ndjson

mkdir -p /tmp/out

# 4) (Placeholder) Real pipeline might call a script like:
#    python /app/scripts/batch_render.py --prompts /tmp/prompts.ndjson --out /tmp/out
# For now, just simulate two PNG outputs:
touch /tmp/out/demo1.png
touch /tmp/out/demo2.png

# 5) Generate a unique date-based folder for each run
S3_FOLDER=$(date +%Y-%m-%d_%H-%M-%S)
echo "Uploading to s3://castlesidegamestudio-spec-sheets/$S3_FOLDER/"

# 6) Upload results to S3
aws s3 cp /tmp/out "s3://castlesidegamestudio-spec-sheets/$S3_FOLDER/" --recursive

echo "Done uploading. Exiting."
