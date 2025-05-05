#!/usr/bin/env python3
"""
Spin up an on-demand RunPod pod, install Diffusers + PixArt-α,
run scripts/generate_pixart.py and stream the logs.

Key points
──────────
* Pin Torch/TorchVision 2.3.0 + cu118 first.
* Install diffusers / transformers / accelerate *without* letting pip
  drag in a new Torch.
* OPTIONAL: install xformers 0.0.26.post2 (last cu118 / torch-2.3 wheel).
"""

from __future__ import annotations
import os, sys, time, requests, json

BASE      = "https://rest.runpod.io/v1"
API_PODS  = f"{BASE}/pods"
POLL_SEC  = 10                      # log-poll interval (s)

# ── helpers ───────────────────────────────────────────────────────────────
def req(key: str) -> str:
    v = os.getenv(key)
    if not v:
        sys.exit(f"[ERROR] env '{key}' is required")
    return v

def image_ref() -> str:
    return os.getenv(
        "IMAGE_NAME",
        "pytorch/pytorch:2.3.1-cuda11.8-cudnn8-runtime"
    )

# ── main ──────────────────────────────────────────────────────────────────
def main() -> None:
    api_key   = req("RUNPOD_API_KEY")
    gpu_type  = os.getenv("GPU_TYPE", "NVIDIA H100 NVL")
    region    = os.getenv("LINODE_DEFAULT_REGION", "us-se-1")
    volume_gb = int(os.getenv("VOLUME_GB") or 120)

    # Variables forwarded to the container
    env = {
        "MODEL_ID":    req("MODEL_ID"),
        "PROMPT_GLOB": req("PROMPT_GLOB"),
        "SEED":        req("SEED"),
        "WIDTH":       os.getenv("WIDTH",  "3072"),
        "HEIGHT":      os.getenv("HEIGHT", "1024"),
        "ORTHO":       os.getenv("ORTHO",  "true"),

        # Linode S3
        "LINODE_ACCESS_KEY_ID":     os.getenv("LINODE_ACCESS_KEY_ID", ""),
        "LINODE_SECRET_ACCESS_KEY": os.getenv("LINODE_SECRET_ACCESS_KEY", ""),
        "LINODE_S3_ENDPOINT":       os.getenv("LINODE_S3_ENDPOINT", ""),
        "LINODE_DEFAULT_REGION":    region,
    }

    # ------------------------------------------------------------------- #
    #  Start-up command (ASCII only)                                      #
    # ------------------------------------------------------------------- #
    start_cmd = (
        "export DEBIAN_FRONTEND=noninteractive && "
        "apt-get update -qq && "
        "apt-get install -y --no-install-recommends git python3-pip tzdata && "
        # 1 ─ pin Torch/TorchVision
        "python3 -m pip install --no-cache-dir --upgrade "
        "--extra-index-url https://download.pytorch.org/whl/cu118 "
        "torch==2.3.0+cu118 torchvision==0.18.0+cu118 && "
        # 2 ─ core libs (no deps)
        "python3 -m pip install --no-cache-dir --upgrade --no-deps "
        "diffusers==0.33.1 transformers==4.51.3 accelerate==0.27.2 "
        "pillow==10.3.0 safetensors==0.5.3 && "
        # 3 ─ clone / update repo
        "[ -d /workspace/repo/.git ] || "
        "git clone --depth 1 https://github.com/CastlesideGameStudio/spec-render-pipeline.git "
        "/workspace/repo && "
        "cd /workspace/repo && "
        # 4 ─ run generator
        "python3 scripts/generate_pixart.py"
    )

    # ------------------------------------------------------------------- #
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

    print(f"[INFO] Creating pod → GPU={gpu_type}, image={image_ref()}, disk={volume_gb} GB")
    resp = requests.post(API_PODS, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        sys.exit(f"[ERROR] RunPod API {resp.status_code}: {resp.text}")

    pod = resp.json()[0] if isinstance(resp.json(), list) else resp.json()
    pod_id = pod.get("id") or sys.exit("[ERROR] no pod id returned")
    print(f"[INFO] Pod created: {pod_id}")

    # ── log streaming loop ───────────────────────────────────────────────
    last_log = ""
    while True:
        time.sleep(POLL_SEC)

        log = requests.get(f"{API_PODS}/{pod_id}/logs", headers=headers, timeout=30)
        if log.ok and log.text != last_log:
            print(log.text[len(last_log):], end="", flush=True)
            last_log = log.text

        status = requests.get(f"{API_PODS}/{pod_id}", headers=headers, timeout=30)\
                 .json().get("status", "UNKNOWN")
        if status not in ("Pending", "Running"):
            print(f"\n[INFO] Pod status = {status}")
            break


if __name__ == "__main__":
    main()
