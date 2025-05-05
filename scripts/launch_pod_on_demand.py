#!/usr/bin/env python3
"""
Spin up an on-demand RunPod pod, install Diffusers + PixArt-alpha,
run scripts/generate_pixart.py, and stream the logs.

Revision history
----------------
- default GPU   -> NVIDIA H100 NVL   (was A100 80 GB)
- default WxH   -> 3072 x 1024       (3 x 1024-px ortho panels)
- robust pod ID -> handle list / dict response from RunPod
- pip patch     -> keep Torch 2.3.0 + cu118; prevent accidental upgrade
"""

from __future__ import annotations
import os
import sys
import time
import json
import requests

BASE      = "https://rest.runpod.io/v1"
API_PODS  = f"{BASE}/pods"
POLL_SEC  = 10                     # log-poll interval (seconds)

# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------
def req(key: str) -> str:
    """Read an env var or exit with a clear error."""
    val = os.getenv(key)
    if not val:
        sys.exit(f"[ERROR] env '{key}' is required")
    return val


def image_ref() -> str:
    """Container image to launch (override with IMAGE_NAME)."""
    return os.getenv(
        "IMAGE_NAME",
        "pytorch/pytorch:2.3.1-cuda11.8-cudnn8-runtime"
    )


# ---------------------------------------------------------------------
# main
# ---------------------------------------------------------------------
def main() -> None:
    api_key   = req("RUNPOD_API_KEY")
    gpu_type  = os.getenv("GPU_TYPE", "NVIDIA H100 NVL")
    region    = os.getenv("LINODE_DEFAULT_REGION", "us-se-1")
    volume_gb = int(os.getenv("VOLUME_GB") or 120)

    # Environment passed through to the container
    env = {
        # generation script parameters
        "MODEL_ID":    req("MODEL_ID"),
        "PROMPT_GLOB": req("PROMPT_GLOB"),
        "SEED":        req("SEED"),
        "WIDTH":       os.getenv("WIDTH",  "3072"),   # 3 x 1024
        "HEIGHT":      os.getenv("HEIGHT", "1024"),
        "ORTHO":       os.getenv("ORTHO",  "true"),

        # Linode S3 credentials
        "LINODE_ACCESS_KEY_ID":     os.getenv("LINODE_ACCESS_KEY_ID", ""),
        "LINODE_SECRET_ACCESS_KEY": os.getenv("LINODE_SECRET_ACCESS_KEY", ""),
        "LINODE_S3_ENDPOINT":       os.getenv("LINODE_S3_ENDPOINT", ""),
        "LINODE_DEFAULT_REGION":    region,
    }

    # -----------------------------------------------------------------
    # Start-up command
    # -----------------------------------------------------------------
    start_cmd = (
        # basic OS packages
        "export DEBIAN_FRONTEND=noninteractive && "
        "apt-get update -qq && "
        "apt-get install -y --no-install-recommends git python3-pip tzdata && "

        # 1) install the exact CUDA-11.8 wheels first (pins Torch)
        "python3 -m pip install --no-cache-dir --upgrade "
        "torch==2.3.0+cu118 torchvision==0.18.0+cu118 "
        "--extra-index-url https://download.pytorch.org/whl/cu118 && "

        # 2) install Diffusers stack (no [torch] extra, so Torch stays put)
        "python3 -m pip install --no-cache-dir --upgrade "
        "diffusers==0.33.1 transformers accelerate pillow safetensors xformers && "

        # 3) clone / update repo (cached across pod restarts)
        "[ -d /workspace/repo/.git ] || "
        "git clone --depth 1 https://github.com/CastlesideGameStudio/spec-render-pipeline.git /workspace/repo && "
        "cd /workspace/repo && "

        # 4) run the generator
        "python3 scripts/generate_pixart.py"
    )

    # -----------------------------------------------------------------
    # Create the pod
    # -----------------------------------------------------------------
    payload = {
        "name": "pixart-render-on-demand",
        "cloudType": "SECURE",
        "gpuTypeIds": [gpu_type],
        "gpuCount": 1,
        "volumeInGb": volume_gb,
        "containerDiskInGb": volume_gb,
        "imageName": image_ref(),
        "dockerStartCmd": ["bash", "-c", start_cmd],
        "env": env,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }

    print(f"[INFO] Creating pod -> GPU={gpu_type}, image={image_ref()}, disk={volume_gb} GB")
    resp = requests.post(API_PODS, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        sys.exit(f"[ERROR] RunPod API {resp.status_code}: {resp.text}")

    pod_json = resp.json()
    if isinstance(pod_json, list):          # API sometimes returns a list
        pod_json = pod_json[0]

    pod_id = pod_json.get("id") or sys.exit("[ERROR] no pod id returned")
    print(f"[INFO] Pod created: {pod_id}")

    # -----------------------------------------------------------------
    # Stream logs until the pod finishes
    # -----------------------------------------------------------------
    last_log = ""
    while True:
        time.sleep(POLL_SEC)

        log_resp = requests.get(f"{API_PODS}/{pod_id}/logs",
                                headers=headers, timeout=30)
        if log_resp.ok and log_resp.text != last_log:
            print(log_resp.text[len(last_log):], end="", flush=True)
            last_log = log_resp.text

        status_resp = requests.get(f"{API_PODS}/{pod_id}",
                                   headers=headers, timeout=30)
        status = status_resp.json().get("status", "UNKNOWN")
        if status not in ("Pending", "Running"):
            print(f"\n[INFO] Pod status = {status}")
            break


if __name__ == "__main__":
    main()
