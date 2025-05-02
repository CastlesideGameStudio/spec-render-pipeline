#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spin up one On-Demand RunPod instance and stream logs.

Required env var:
  RUNPOD_API_KEY      – bearer token from https://runpod.io

Optional env vars:
  IMAGE_NAME          – container tag (default: valyriantech/comfyui-with-flux:latest)
  PROMPT_GLOB         – NDJSON pattern (default: addendums/**/*.ndjson)
  GPU_TYPE            – GPU type, e.g. "NVIDIA A40" (default)
  VOLUME_GB           – disk size in GB (default: 120; ignored if blank)
  CONTAINER_AUTH_ID   – registry-auth ID for private images (skip if public)
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


# --------------------------------------------------------------------------- helpers
def image_ref() -> str:
    """IMAGE_NAME if set, otherwise default to the public Flux image."""
    return os.getenv("IMAGE_NAME", "valyriantech/comfyui-with-flux:latest")


def gather_prompts(pattern: str) -> str:
    """Concatenate all lines from every *.ndjson file matching *pattern*."""
    lines = []
    for path in glob.glob(pattern, recursive=True):
        text = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
        lines += [ln for ln in text if ln.strip()]
    if not lines:
        sys.exit(f"[ERROR] No prompts matched '{pattern}'.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- main
def main() -> None:
    api_key = os.getenv("RUNPOD_API_KEY") or sys.exit("[ERROR] RUNPOD_API_KEY missing.")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    gpu_type  = os.getenv("GPU_TYPE", "NVIDIA A40")
    vol_env   = os.getenv("VOLUME_GB", "").strip()
    volume_gb = int(vol_env) if vol_env else 120
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
        "dockerStartCmd":    ["bash", "-c", "/workspace/entrypoint.sh"],
        "env":               env_block,
    }
    # If you need registry auth for private images
    if auth_id:
        payload["containerRegistryAuthId"] = auth_id

    # ------------------------------------------------------------------- create-pod call
    print(f"[INFO] Creating pod → GPU={gpu_type}  image={image}  disk={volume_gb}GB")
    resp = requests.post(API_PODS, json=payload, headers=headers, timeout=60)

    # If there's an HTTP error, print the response body and exit
    if resp.status_code >= 400:
        print("[ERROR] Pod creation failed → HTTP", resp.status_code)
        print(resp.text)
        sys.exit(1)

    # Grab the ID
    pod_id = resp.json().get("id") or sys.exit("[ERROR] No pod ID returned.")
    print(f"[INFO] Pod created: {pod_id}")

    # ------------------------------------------------------------------- log streaming
    last_log = ""
    while True:
        time.sleep(10)

        # Fetch logs
        log_resp = requests.get(f"{API_PODS}/{pod_id}/logs", headers=headers, timeout=30)
        if log_resp.ok and log_resp.text != last_log:
            print(log_resp.text[len(last_log):], end="", flush=True)
            last_log = log_resp.text

        # Check pod status
        stat = requests.get(f"{API_PODS}/{pod_id}", headers=headers, timeout=30)
        status = stat.json().get("status", "UNKNOWN") if stat.ok else "UNKNOWN"
        if status not in ("Pending", "Running"):
            print(f"\n[INFO] Pod status = {status}")
            break

    print("[INFO] Finished log streaming; pod is no longer running.")


if __name__ == "__main__":
    main()
