#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spins up one On-Demand pod on RunPod via the REST API.

Environment variables (from GitHub Actions or local shell):
  RUNPOD_API_KEY       – your "Bearer" token (required)
  PROMPT_GLOB          – NDJSON pattern (default "addendums/**/*.ndjson")
  IMAGE_TAG            – container tag (default "latest")
  GPU_TYPE             – e.g. "NVIDIA GeForce RTX 3090", "NVIDIA A40", etc.
  AWS_ACCESS_KEY_ID    – (optional) if container uploads to S3
  AWS_SECRET_ACCESS_KEY– (optional) if container uploads to S3
  AWS_DEFAULT_REGION   – (optional) region of your S3 bucket
"""

import os
import sys
import glob
import time
import pathlib
import requests

BASE_URL = "https://rest.runpod.io/v1"
API_PODS = f"{BASE_URL}/pods"       # POST or GET for Pod creation/listing
API_LOGS = f"{BASE_URL}/pods/logs"  # GET logs

def main():
    # 1) Validate environment
    runpod_api_key = os.getenv("RUNPOD_API_KEY", "")
    if not runpod_api_key:
        sys.exit("[ERROR] RUNPOD_API_KEY missing or empty.")

    prompt_glob = os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")
    image_tag   = os.getenv("IMAGE_TAG", "latest")
    gpu_type    = os.getenv("GPU_TYPE", "NVIDIA A40")

    # 2) Gather NDJSON lines from local repo
    all_lines = []
    for path in glob.glob(prompt_glob, recursive=True):
        txt = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
        # skip blank lines
        lines = [ln for ln in txt if ln.strip()]
        all_lines.extend(lines)

    if not all_lines:
        sys.exit(f"[ERROR] No prompts found matching '{prompt_glob}'.")

    print(f"[INFO] Found {len(all_lines)} total lines from '{prompt_glob}'")

    # Combine lines into one multiline environment variable
    # so the container can parse them at runtime.
    env_block = {
        "PROMPTS_NDJSON": "\n".join(all_lines),

        # Forward AWS creds if the container needs them for S3 upload
        "AWS_ACCESS_KEY_ID":      os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY":  os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_DEFAULT_REGION":     os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    }

    # 3) Build container reference – e.g. "ghcr.io/owner/repo/spec-render:latest"
    repo_slug  = os.getenv("GITHUB_REPOSITORY", "yourorg/yourrepo").lower()
    image_name = f"ghcr.io/{repo_slug}/spec-render:{image_tag}"

    # 4) Create the Pod (On-Demand) with the v1 REST
    headers = {
        "Authorization": f"Bearer {runpod_api_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "name":              "spec-render-on-demand",
        "cloudType":         "SECURE",         # on-demand
        "gpuTypeIds":        [gpu_type],       # array of GPU type
        "gpuCount":          1,
        "volumeInGb":        20,               # ephemeral disk if needed
        "containerDiskInGb": 20,
        "imageName":         image_name,
        "env":               env_block
    }

    print(f"[INFO] Creating Pod with GPU='{gpu_type}' image='{image_name}'")
    resp = requests.post(API_PODS, json=payload, headers=headers, timeout=60)
    if not resp.ok:
        print("[ERROR] Pod creation failed.")
        print("Status:", resp.status_code)
        print("Response:", resp.text)
        sys.exit(1)

    pod_data = resp.json()
    pod_id   = pod_data.get("id")
    if not pod_id:
        sys.exit("[ERROR] No pod ID returned in the response.")

    print(f"[INFO] Pod created with ID={pod_id}")

    # 5) Poll for status until it's no longer Running
    while True:
        time.sleep(20)
        r_stat = requests.get(f"{API_PODS}/{pod_id}", headers=headers, timeout=30)
        if not r_stat.ok:
            print("[WARN] GET /pods/{podId} failed, ignoring temporarily")
            continue
        status_data = r_stat.json()
        status = status_data.get("status")
        print(f"[INFO] Pod status={status}")
        # If status is "Succeeded" or "Failed" or "Stopped", we're done
        if status not in ("Pending", "Running"):
            print("[INFO] Pod is no longer Running. Breaking out of loop.")
            break

    # 6) Fetch logs if available
    logs_resp = requests.get(f"{API_PODS}/{pod_id}/logs", headers=headers, timeout=30)
    if logs_resp.ok:
        logs_txt = logs_resp.text
        print("------ Pod logs ------")
        # Print last 3000 chars
        print(logs_txt[-3000:])
    else:
        print("[WARN] Could not fetch logs. Status =", logs_resp.status_code)

    sys.exit(0)

if __name__ == "__main__":
    main()
