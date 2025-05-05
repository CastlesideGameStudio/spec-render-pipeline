#!/usr/bin/env python3
"""
Spin up an on-demand RunPod pod, install Diffusers + PixArt-α,
run scripts/generate_pixart.py and stream the logs.

Lessons learned
1.  **ALWAYS** pin Torch *before* touching any Hugging Face libs or pip
    will drag in the newest CUDA build and break the container.
2.  Install Diffusers / Transformers / Accelerate with
      pip install --no-deps
    so step 1’s pin cannot be overruled.
3.  diffusers ≥ 0.33 needs **huggingface_hub ≥ 0.27** for the new
    `DDUFEntry` helper → pin **0.29.3** (latest that still tests clean
    on cu118 / Torch 2.3).
4.  xFormers wheels stop at **0.0.26.post2** for cu118 / Torch 2.3.
    Newer wheels silently jump to Torch 2.4 + cu121 — pin if you need it.
5.  Keep the giant Docker “start_cmd” ASCII-only; fancy quotes break YAML.
6.  RunPod logs sometimes repeat; track `last_log` and only print deltas.
7.  transformers ≥ 4.0 requires the ‘regex’ wheel at import-time.
    When installing with --no-deps, remember to `pip install regex`
    explicitly (pin a version that still has pre-built wheels for
    your CUDA / Python combo).

Search this header for **ALWAYS** or **DON’T** next time something tanks.
"""

from __future__ import annotations
import os, sys, time, requests, json   # keep host env lean

BASE      = "https://rest.runpod.io/v1"
API_PODS  = f"{BASE}/pods"
POLL_SEC  = 10                        # log-poll interval (s)

# ── helpers ───────────────────────────────────────────────────────────────
def req(key: str) -> str:
    """Return $key or fail fast with a helpful error."""
    val = os.getenv(key)
    if not val:
        sys.exit(f"[ERROR] env '{key}' is required")
    return val

def image_ref() -> str:
    """Return container image tag (overridable via $IMAGE_NAME)."""
    return os.getenv(
        "IMAGE_NAME",
        "pytorch/pytorch:2.3.1-cuda11.8-cudnn8-runtime",
    )

# ── main ──────────────────────────────────────────────────────────────────
def main() -> None:
    api_key   = req("RUNPOD_API_KEY")
    gpu_type  = os.getenv("GPU_TYPE", "NVIDIA H100 NVL")
    region    = os.getenv("LINODE_DEFAULT_REGION", "us-se-1")
    volume_gb = int(os.getenv("VOLUME_GB") or 120)       # HF cache eats GBs

    # Vars forwarded into the pod
    env = {
        "MODEL_ID":    req("MODEL_ID"),
        "PROMPT_GLOB": req("PROMPT_GLOB"),
        "SEED":        req("SEED"),
        "WIDTH":       os.getenv("WIDTH",  "3072"),
        "HEIGHT":      os.getenv("HEIGHT", "1024"),
        "ORTHO":       os.getenv("ORTHO",  "true"),

        # Linode S3 (optional)
        "LINODE_ACCESS_KEY_ID":     os.getenv("LINODE_ACCESS_KEY_ID", ""),
        "LINODE_SECRET_ACCESS_KEY": os.getenv("LINODE_SECRET_ACCESS_KEY", ""),
        "LINODE_S3_ENDPOINT":       os.getenv("LINODE_S3_ENDPOINT", ""),
        "LINODE_DEFAULT_REGION":    region,
    }

    # ------------------------------------------------------------------- #
    #  Start-up command (single quoted string executed by “bash -c”)      #
    # ------------------------------------------------------------------- #
    start_cmd = (
        "export DEBIAN_FRONTEND=noninteractive && "
        "apt-get update -qq && "
        "apt-get install -y --no-install-recommends git python3-pip tzdata && "

        # 1 ─ Pin Torch / TorchVision first  (Lesson 1)
        "python3 -m pip install --no-cache-dir --upgrade "
        "--extra-index-url https://download.pytorch.org/whl/cu118 "
        "torch==2.3.0+cu118 torchvision==0.18.0+cu118 && "

        # 1½ ─ **Install mandatory single-deps we skipped with --no-deps**
        #     transformers needs ‘regex’; keep it pinned so it stays CU118-compatible.
        "python3 -m pip install --no-cache-dir --upgrade regex==2024.4.16 && "

        # 2 ─ Core HF libs (NO deps → Lessons 2 & 3)
        "python3 -m pip install --no-cache-dir --upgrade --no-deps "
        "diffusers==0.33.1 transformers==4.51.3 accelerate==0.27.2 "
        "pillow==10.3.0 safetensors==0.5.3 huggingface_hub==0.29.3 && "

        # 3 ─ (Optional) xFormers, version-pinned (Lesson 4) – comment out if not needed
        # \"python3 -m pip install --no-cache-dir --upgrade --no-deps "
        # \"xformers==0.0.26.post2\" && "

        # 4 ─ Clone / update repo (idempotent)
        "[ -d /workspace/repo/.git ] || "
        "git clone --depth 1 https://github.com/CastlesideGameStudio/spec-render-pipeline.git "
        "/workspace/repo && "
        "cd /workspace/repo && "

        # 5 ─ Kick off generator script
        "python3 scripts/generate_pixart.py"
    )

    payload = {
        "name": "pixart-render-on-demand",
        "cloudType": "SECURE",              # H100s demand SECURE pods
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

    # ── log tailer (Lesson 6) ───────────────────────────────────────────
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
