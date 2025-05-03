#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spin up one On-Demand RunPod instance and stream logs.

Required ENV
------------
RUNPOD_API_KEY          – bearer token from https://runpod.io
LINODE_DEFAULT_REGION   – must be set (no fallback)

Optional (already wired through the GH workflow)
------------------------------------------------
IMAGE_NAME              – container tag (default: valyriantech/comfyui-with-flux:latest)
PROMPT_GLOB             – NDJSON pattern   (default: addendums/**/*.ndjson)
GPU_TYPE                – GPU type id      (default: NVIDIA A40)
VOLUME_GB               – container + volume disk (default: 120 GB)
CONTAINER_AUTH_ID       – registry-auth for private images (omit if public)
LINODE_ACCESS_KEY_ID    – object-storage key
LINODE_SECRET_ACCESS_KEY– object-storage secret
LINODE_S3_ENDPOINT      – e.g. https://us-ord-1.linodeobjects.com
"""

import glob
import os
import pathlib
import sys
import time
from typing import List

import requests

BASE = "https://rest.runpod.io/v1"
API_PODS = f"{BASE}/pods"
POLL_SEC = 10  # seconds between successive log polls


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
        "Content-Type": "application/json",
    }

    # Require LINODE_DEFAULT_REGION (no fallback)
    region = os.getenv("LINODE_DEFAULT_REGION")
    if not region:
        sys.exit("[ERROR] LINODE_DEFAULT_REGION missing.")

    gpu_type = os.getenv("GPU_TYPE", "NVIDIA A40")
    volume_gb = int(os.getenv("VOLUME_GB", "120") or 120)
    image = image_ref()
    auth_id = os.getenv("CONTAINER_AUTH_ID", "")

    # ---------- environment forwarded into the container -------------------
    env_block = {
        # NDJSON for entrypoint.sh
        "PROMPTS_NDJSON": gather_prompts(os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")),

        # ★ Linode creds only (no AWS_* in GH secrets) ★
        "LINODE_ACCESS_KEY_ID": os.getenv("LINODE_ACCESS_KEY_ID", ""),
        "LINODE_SECRET_ACCESS_KEY": os.getenv("LINODE_SECRET_ACCESS_KEY", ""),
        "LINODE_S3_ENDPOINT": os.getenv("LINODE_S3_ENDPOINT", ""),
        "LINODE_DEFAULT_REGION": region,
    }

    # For transparency, print the env block to logs:
    print("[DEBUG] The container will receive these environment variables:")
    for k, v in env_block.items():
        # Redact secret values in logs if you want. For now, we just print them.
        print(f"   {k} = {v!r}")

    # ---------- pod creation payload --------------------------------------
    payload = {
        "name": "spec-render-on-demand",
        "cloudType": "SECURE",
        "gpuTypeIds": [gpu_type],
        "gpuCount": 1,
        "volumeInGb": volume_gb,
        "containerDiskInGb": volume_gb,
        "imageName": image,
        "dockerStartCmd": [
            "bash",
            "-c",
            (
                # Non-interactive package install
                "export DEBIAN_FRONTEND=noninteractive && "
                "apt-get update -qq && "
                "apt-get install -y --no-install-recommends "
                "jq git python3-pip tzdata && "
                # Fresh AWS CLI (needed to talk to Linode via S3 API)
                "python3 -m pip install --no-cache-dir --upgrade 'awscli>=1.32' && "
                # Clone the repo only once (safe on pod restart)
                "[ -d /workspace/repo/.git ] || "
                "git clone --depth 1 https://github.com/CastlesideGameStudio/"
                "spec-render-pipeline.git /workspace/repo && "
                # Hand off to the batch script
                "bash /workspace/repo/scripts/entrypoint.sh"
            ),
        ],
        "env": env_block,
    }
    if auth_id:
        payload["containerRegistryAuthId"] = auth_id

    # Log the payload without secrets redacted if you want more transparency:
    # import json
    # print("[DEBUG] Full Pod Creation Payload:\n", json.dumps(payload, indent=2))

    # ---------- create the pod --------------------------------------------
    print(f"[INFO] Creating pod → GPU={gpu_type}, image={image}, disk={volume_gb} GB")
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

        log_resp = requests.get(f"{API_PODS}/{pod_id}/logs", headers=headers, timeout=30)
        if log_resp.ok and log_resp.text != last_log:
            print(log_resp.text[len(last_log) :], end="", flush=True)
            last_log = log_resp.text

        stat = requests.get(f"{API_PODS}/{pod_id}", headers=headers, timeout=30)
        status = stat.json().get("status", "UNKNOWN") if stat.ok else "UNKNOWN"
        if status not in ("Pending", "Running"):
            print(f"\n[INFO] Pod status = {status}")
            break

    print("[INFO] Finished log streaming; pod is no longer running.")


if __name__ == "__main__":
    main()
