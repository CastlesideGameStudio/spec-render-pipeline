#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spin up one On-Demand RunPod instance and stream logs.

Required:
  RUNPOD_API_KEY      – bearer token from https://runpod.io

Optional env vars consumed here:
  IMAGE_NAME          – full container tag (e.g. valyriantech/comfyui-with-flux:latest)
  PROMPT_GLOB         – NDJSON pattern (default addendums/**/*.ndjson)
  GPU_TYPE            – GPU, e.g. “NVIDIA A40” (default)
  VOLUME_GB           – disk size in GB (default 120)
  CONTAINER_AUTH_ID   – registry-auth ID for private images (not needed if public)
  AWS_*               – forwarded unchanged to the container
"""

import glob
import os
import pathlib
import sys
import time
import requests

BASE = "https://rest.runpod.io/v1"
API_PODS = f"{BASE}/pods"


def image_ref() -> str:
    """
    Prefer IMAGE_NAME if set; otherwise default to valyriantech/comfyui-with-flux:latest.
    """
    name = os.getenv("IMAGE_NAME")
    if name:
        return name
    # fallback if not set:
    return "valyriantech/comfyui-with-flux:latest"


def gather_prompts(pattern: str) -> str:
    """
    Reads all .ndjson lines matching pattern, concatenates them into one string.
    """
    lines = []
    for path in glob.glob(pattern, recursive=True):
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    lines.append(ln)
    if not lines:
        sys.exit(f"[ERROR] No prompts matched '{pattern}'.")
    return "\n".join(lines)


def main() -> None:
    api_key = os.getenv("RUNPOD_API_KEY") or sys.exit("[ERROR] RUNPOD_API_KEY missing.")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    gpu_type  = os.getenv("GPU_TYPE", "NVIDIA A40")
    volume_gb = int(os.getenv("VOLUME_GB", "120"))  # default 120 GB
    image     = image_ref()
    auth_id   = os.getenv("CONTAINER_AUTH_ID", "")

    # Build environment block to pass into the container
    env_block = {
        "PROMPTS_NDJSON": gather_prompts(os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")),
        "AWS_ACCESS_KEY_ID":     os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_DEFAULT_REGION":    os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    }

    # Prepare JSON for RunPod's "Create a Pod" API
    payload = {
        "name":              "spec-render-on-demand",
        "cloudType":         "SECURE",
        "gpuTypeIds":        [gpu_type],
        "gpuCount":          1,
        "volumeInGb":        volume_gb,
        "containerDiskInGb": volume_gb,
        "imageName":         image,
        "env":               env_block,
        # Override the container's entrypoint to clone your repo + run entrypoint.sh
        "containerEntrypoint": ["/bin/bash"],
        "containerCmd": [
            "-c",
            # 1) install any needed packages
            "apt-get update && apt-get install -y git jq git-lfs && "
            # 2) set up Git LFS (remove if you don't need it)
            "git lfs install && "
            # 3) clone your spec-render-pipeline repo
            "git clone https://github.com/CastlesideGameStudio/spec-render-pipeline.git /workspace/pipeline && "
            "cd /workspace/pipeline && git lfs pull && "
            # 4) make entrypoint executable
            "chmod +x /workspace/pipeline/scripts/entrypoint.sh && "
            # 5) run your pipeline script
            "/workspace/pipeline/scripts/entrypoint.sh"
        ],
    }

    # If you need registry auth for private images, add this
    if auth_id:
        payload["containerRegistryAuthId"] = auth_id

    # Create the Pod
    print(f"[INFO] Creating pod – GPU='{gpu_type}'  image='{image}'  disk={volume_gb}GB")
    resp = requests.post(API_PODS, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    pod_id = resp.json().get("id") or sys.exit("[ERROR] No pod ID returned.")
    print(f"[INFO] Pod created: {pod_id}")

    # Log streaming
    last_log = ""
    while True:
        time.sleep(10)
        log_resp = requests.get(f"{API_PODS}/{pod_id}/logs", headers=headers, timeout=30)
        if log_resp.ok and log_resp.text != last_log:
            print(log_resp.text[len(last_log):], end="", flush=True)
            last_log = log_resp.text

        stat = requests.get(f"{API_PODS}/{pod_id}", headers=headers, timeout=30)
        status = stat.json().get("status", "UNKNOWN") if stat.ok else "UNKNOWN"
        if status not in ("Pending", "Running"):
            print(f"\n[INFO] Pod status = {status}")
            break

    print("[INFO] Finished log streaming; pod is no longer running.")


if __name__ == "__main__":
    main()
