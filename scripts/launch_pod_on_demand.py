#!/usr/bin/env python3
"""
Spin up an On-Demand RunPod, install Diffusers + PixArt-α,
run scripts/generate_pixart.py and tail the logs.
"""
from __future__ import annotations
import os, sys, time, requests, json

BASE     = "https://rest.runpod.io/v1"
API_PODS = f"{BASE}/pods"
POLL     = 10                              # seconds

# ── helpers ──────────────────────────────────────────────────────────────
def req(key: str) -> str:
    val = os.getenv(key)
    if not val:
        sys.exit(f"[ERROR] env '{key}' is required")
    return val

def image_ref() -> str:
    return os.getenv("IMAGE_NAME",
                     "pytorch/pytorch:2.3.1-cuda11.8-cudnn8-runtime")

# ── main ─────────────────────────────────────────────────────────────────
def main() -> None:
    api_key   = req("RUNPOD_API_KEY")
    gpu_type  = os.getenv("GPU_TYPE", "NVIDIA A100 80GB")
    region    = os.getenv("LINODE_DEFAULT_REGION", "us-se-1")
    volume_gb = int(os.getenv("VOLUME_GB") or 120)

    env = {
        # generation script
        "MODEL_ID":    req("MODEL_ID"),
        "PROMPT_GLOB": req("PROMPT_GLOB"),
        "SEED":        req("SEED"),
        "WIDTH":       os.getenv("WIDTH", "1024"),
        "HEIGHT":      os.getenv("HEIGHT", "1024"),
        "ORTHO":       os.getenv("ORTHO", "true"),

        # S3 passthrough
        "LINODE_ACCESS_KEY_ID":     os.getenv("LINODE_ACCESS_KEY_ID", ""),
        "LINODE_SECRET_ACCESS_KEY": os.getenv("LINODE_SECRET_ACCESS_KEY", ""),
        "LINODE_S3_ENDPOINT":       os.getenv("LINODE_S3_ENDPOINT", ""),
        "LINODE_DEFAULT_REGION":    region,
    }

    start_cmd = (
        "export DEBIAN_FRONTEND=noninteractive && "
        "apt-get update -qq && "
        "apt-get install -y --no-install-recommends git python3-pip tzdata && "
        # lightweight deps
        "python3 -m pip install --no-cache-dir --upgrade "
        "diffusers[torch] transformers accelerate pillow safetensors xformers && "
        # repo (reuse cache when pod restarts)
        "[ -d /workspace/repo/.git ] || "
        "git clone --depth 1 https://github.com/CastlesideGameStudio/spec-render-pipeline.git /workspace/repo && "
        "cd /workspace/repo && "
        "python3 scripts/generate_pixart.py"
    )

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

    hdr = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    print(f"[INFO] Creating pod → GPU={gpu_type}")
    pod = requests.post(API_PODS, headers=hdr, json=payload, timeout=60).json()
    pod_id = pod.get("id") or sys.exit("[ERROR] no pod id")

    last = ""
    while True:
        time.sleep(POLL)
        log = requests.get(f"{API_PODS}/{pod_id}/logs", headers=hdr, timeout=30)
        if log.ok and log.text != last:
            print(log.text[len(last):], end="", flush=True)
            last = log.text
        status = requests.get(f"{API_PODS}/{pod_id}", headers=hdr, timeout=30).json().get("status", "UNKNOWN")
        if status not in ("Pending", "Running"):
            print(f"\n[INFO] Pod status = {status}")
            break

if __name__ == "__main__":
    main()
