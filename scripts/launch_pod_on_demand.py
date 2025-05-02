#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spin up one On-Demand RunPod instance and stream logs.

Required ENV
------------
RUNPOD_API_KEY         – bearer token from https://runpod.io

Optional (already wired through the GH workflow)
------------------------------------------------
IMAGE_NAME             – container tag (default: valyriantech/comfyui-with-flux:latest)
PROMPT_GLOB            – NDJSON pattern   (default: addendums/**/*.ndjson)
GPU_TYPE               – GPU type id      (default: NVIDIA A40)
VOLUME_GB              – container + volume disk (default: 120 GB)
CONTAINER_AUTH_ID      – registry-auth for private images (omit if public)
AWS_*                  – forwarded unchanged into the pod
"""

import glob
import os
import pathlib
import sys
import time
from typing import List

import requests


BASE      = "https://rest.runpod.io/v1"
API_PODS  = f"{BASE}/pods"
POLL_SEC  = 10               # seconds between successive log polls


# --------------------------------------------------------------------------- helpers
def image_ref() -> str:
    """Return IMAGE_NAME if set, otherwise the public Flux image."""
    return os.getenv("IMAGE_NAME", "valyriantech/comfyui-with-flux:latest")


def gather_prompts(pattern: str) -> str:
    """Concatenate all lines from every *.ndjson file matching *pattern*."""
    lines: List[str] = []
    for path in glob.glob(pattern, recursive=True):
        text = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
        lines.extend(text)
    if not lines:
        sys.exit(f"[ERROR] No prompts matched '{pattern}'.")
    return "\n".join([ln for ln in lines if ln.strip()])


# --------------------------------------------------------------------------- main
def main() -> None:
    api_key = os.getenv("RUNPOD_API_KEY") or sys.exit("[ERROR] RUNPOD_API_KEY missing.")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }

    gpu_type   = os.getenv("GPU_TYPE", "NVIDIA A40")
    volume_gb  = int(os.getenv("VOLUME_GB", "120") or 120)
    image      = image_ref()
    auth_id    = os.getenv("CONTAINER_AUTH_ID", "")

    # ---------- environment forwarded into the container -------------------
    env_block = {
        "PROMPTS_NDJSON":        gather_prompts(os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")),
        "AWS_ACCESS_KEY_ID":     os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_SESSION_TOKEN":     os.getenv("AWS_SESSION_TOKEN", ""),
        "AWS_DEFAULT_REGION":    os.getenv("AWS_DEFAULT_REGION", "us-east-2"),
    }

    # ---------- pod creation payload --------------------------------------
    payload = {
        "name":              "spec-render-on-demand",
        "cloudType":         "SECURE",
        "gpuTypeIds":        [gpu_type],
        "gpuCount":          1,
        "volumeInGb":        volume_gb,
        "containerDiskInGb": volume_gb,
        "imageName":         image,
        "dockerStartCmd": [
            "bash", "-c",
            (
                # Non-interactive package install
                "export DEBIAN_FRONTEND=noninteractive && "
                "apt-get update -qq && "
                "apt-get install -y --no-install-recommends "
                "jq git python3-pip tzdata && "                      # ← tzdata added
                # Fresh AWS CLI (v1.32+ → botocore 1.34+; works with urllib3 2.x)
                "python3 -m pip install --no-cache-dir --upgrade 'awscli>=1.32' && "
                # Clone the repo only once (safe on pod restart)
                "[ -d /workspace/repo/.git ] || "
                "git clone --depth 1 https://github.com/CastlesideGameStudio/"
                "spec-render-pipeline.git /workspace/repo && "
                # Hand off to the batch script
                "bash /workspace/repo/scripts/entrypoint.sh"
            )
        ],
        "env": env_block,
    }
    if auth_id:
        payload["containerRegistryAuthId"] = auth_id

    # ---------- create the pod --------------------------------------------
    print(f"[INFO] Creating pod → GPU={gpu_type}  image={image}  disk={volume_gb} GB")
    resp = requests.post(API_PODS, json=payload, headers=headers, timeout=60)

    if resp.status_code >= 400:
        print("[ERROR] Pod creation failed → HTTP", resp.status_code)
        print(resp.text)
        sys.exit(1)

    pod_id = resp.json().get("id") or sys.exit("[ERROR] No pod ID returned.")
    print(f"[INFO] Pod created: {pod_id}")

    # ---------- stream logs until pod exits -------------------------------
    last_log = ""
    while True:
        time.sleep(POLL_SEC)

        log_resp = requests.get(f"{API_PODS}/{pod_id}/logs",
                                headers=headers, timeout=30)
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
