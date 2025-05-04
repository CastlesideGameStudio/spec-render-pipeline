#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spin up an On-Demand RunPod instance and stream logs,
executing a **Qwen-3 multimodal** image-generation batch job (no Diffusers / ComfyUI).

Required ENV
------------
RUNPOD_API_KEY          – bearer token from https://runpod.io
LINODE_DEFAULT_REGION   – bucket region (no fallback)

Optional (propagated from the GitHub Actions workflow)
-----------------------------------------------------
IMAGE_NAME              – container image tag (default: pytorch/pytorch:2.3.1-cuda11.8-cudnn8-runtime)
PROMPT_GLOB             – NDJSON pattern   (default: addendums/**/*.ndjson)
GPU_TYPE                – GPU type id      (default: H100 NVL)
VOLUME_GB               – container + volume disk (default: 120 GB)
MODEL_ID                – HuggingFace model (default: Qwen/Qwen3-32B)
WIDTH / HEIGHT          – target resolution (default: 1920×1080)
ORTHO                   – "true" / "false" for orthographic projection flag
LINODE_ACCESS_KEY_ID    – object-storage key
LINODE_SECRET_ACCESS_KEY– object-storage secret
LINODE_S3_ENDPOINT      – e.g. https://us-ord-1.linodeobjects.com
"""

from __future__ import annotations

import glob
import json
import os
import pathlib
import sys
import time
from typing import List

import requests

BASE = "https://rest.runpod.io/v1"
API_PODS = f"{BASE}/pods"
POLL_SEC = 10  # seconds between successive log polls

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def image_ref() -> str:
    """Return the chosen container image tag."""
    return os.getenv(
        "IMAGE_NAME",
        "pytorch/pytorch:2.3.1-cuda11.8-cudnn8-runtime",
    )


def gather_prompts(pattern: str) -> str:
    """Concatenate all lines from every *.ndjson file matching *pattern*."""
    lines: List[str] = []
    for path in glob.glob(pattern, recursive=True):
        text = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
        lines.extend(text)
    if not lines:
        sys.exit(f"[ERROR] No prompts matched '{pattern}'.")
    # keep non-blank lines only
    return "\n".join([ln for ln in lines if ln.strip()])


# ----------------------------------------------------------------------------
# main logic
# ----------------------------------------------------------------------------

def main() -> None:
    api_key = os.getenv("RUNPOD_API_KEY") or sys.exit("[ERROR] RUNPOD_API_KEY missing.")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # ----- mandatory Linode region ----------------------------------------
    region = os.getenv("LINODE_DEFAULT_REGION")
    if not region:
        sys.exit("[ERROR] LINODE_DEFAULT_REGION missing.")

    # ----- basic parameters ------------------------------------------------
    gpu_type = os.getenv("GPU_TYPE", "H100 NVL")
    volume_gb = int(os.getenv("VOLUME_GB", "120") or 120)
    image = image_ref()

    # ----- Qwen-3 generation parameters ------------------------------------
    model_id = os.getenv("MODEL_ID", "Qwen/Qwen3-32B")
    width = os.getenv("WIDTH", "1920")
    height = os.getenv("HEIGHT", "1080")
    ortho = os.getenv("ORTHO", "true")

    # ----------------------------------------------------------------------
    # Environment forwarded into the container
    # ----------------------------------------------------------------------
    env_block = {
        # NDJSON prompt batch
        "PROMPTS_NDJSON": gather_prompts(os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")),
        # Generation parameters
        "MODEL_ID": model_id,
        "WIDTH": width,
        "HEIGHT": height,
        "ORTHO": ortho,
        # Linode object-storage creds
        "LINODE_ACCESS_KEY_ID": os.getenv("LINODE_ACCESS_KEY_ID", ""),
        "LINODE_SECRET_ACCESS_KEY": os.getenv("LINODE_SECRET_ACCESS_KEY", ""),
        "LINODE_S3_ENDPOINT": os.getenv("LINODE_S3_ENDPOINT", ""),
        "LINODE_DEFAULT_REGION": region,
    }

    # For transparency, print the env block to logs
    print("[DEBUG] Container environment block:")
    for k, v in env_block.items():
        print(f"   {k} = {v[:80]+'…' if len(v)>80 else v!r}")

    # ----------------------------------------------------------------------
    # Pod creation payload
    # ----------------------------------------------------------------------
    payload: dict[str, object] = {
        "name": "qwen3-render-on-demand",
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
                # Install deps silently
                "export DEBIAN_FRONTEND=noninteractive && "
                "apt-get update -qq && "
                "apt-get install -y --no-install-recommends git python3-pip tzdata && "
                # Python libs for Qwen-3 multimodal generation
                "python3 -m pip install --no-cache-dir --upgrade \
                    transformers>=4.51.0 accelerate pillow bitsandbytes flash-attn --extra-index-url https://pypi.nvidia.com && "
                # Clone (or reuse) the pipeline repo
                "[ -d /workspace/repo/.git ] || \
                 git clone --depth 1 https://github.com/CastlesideGameStudio/spec-render-pipeline.git /workspace/repo && "
                # Run the batch generator
                "python3 /workspace/repo/scripts/generate_qwen3.py"
            ),
        ],
        "env": env_block,
    }

    # Optional private-registry auth
    auth_id = os.getenv("CONTAINER_AUTH_ID")
    if auth_id:
        payload["containerRegistryAuthId"] = auth_id

    # ----------------------------------------------------------------------
    # Create the pod
    # ----------------------------------------------------------------------
    print(f"[INFO] Creating pod → GPU={gpu_type}, image={image}, disk={volume_gb} GB")
    resp = requests.post(API_PODS, json=payload, headers=headers, timeout=60)

    if resp.status_code >= 400:
        print("[ERROR] Pod creation failed → HTTP", resp.status_code)
        print(resp.text)
        sys.exit(1)

    pod_id = resp.json().get("id") or sys.exit("[ERROR] No pod ID returned.")
    print(f"[INFO] Pod created: {pod_id}")

    # ----------------------------------------------------------------------
    # Stream logs until the pod exits
    # ----------------------------------------------------------------------
    last_log = ""
    while True:
        time.sleep(POLL_SEC)

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
