#!/usr/bin/env python3
"""
Spin up an on-demand RunPod pod, install Diffusers + PixArt-α,
run scripts/generate_pixart.py and stream the logs.

Lessons learned
1.  ALWAYS pin Torch + TorchVision before touching *any* Hugging Face
    packages, or pip will happily drag in the newest CUDA build
    (breaking the pre-built container).
2.  ALWAYS install Diffusers / Transformers / Accelerate with
       pip install --no-deps
    so that step 1’s pin cannot be overruled.
3.  diffusers ≥ 0.33 now imports `huggingface_hub`; if it’s missing you
    get `ModuleNotFoundError: huggingface_hub`.  Pin a version that
    still supports cu118 (0.23.3 at time of writing).
4.  xFormers wheels stop at 0.0.26.post2 for cu118 / torch-2.3.
    Newer wheels silently switch to torch-2.4 + cu121 — so **DON’T**
    `pip install xformers` without an explicit version.
5.  Make the long Docker “start_cmd” ASCII-only; curly quotes, emojis
    or non-ASCII dashes break yaml / JSON escaping in GitHub Actions.
6.  RunPod’s log endpoint sometimes repeats chunks; track `last_log`
    and only print deltas to avoid flooding the action log.

You can search the comment blocks (grep “ALWAYS” or “DON’T”) if you need a
quick refresher the next time something blows up.
"""

from __future__ import annotations
import os, sys, time, requests, json     # DON’T add heavy deps here—keep host thin

BASE     = "https://rest.runpod.io/v1"
API_PODS = f"{BASE}/pods"
POLL_SEC = 10                            # seconds between log polls (short = chatty)

# ── helpers ───────────────────────────────────────────────────────────────
def req(key: str) -> str:
    """Return environment variable *key* or exit with a helpful error."""
    v = os.getenv(key)
    if not v:
        sys.exit(f"[ERROR] env '{key}' is required")
    return v

def image_ref() -> str:
    """Default container image (override with $IMAGE_NAME if needed)."""
    return os.getenv(
        "IMAGE_NAME",
        "pytorch/pytorch:2.3.1-cuda11.8-cudnn8-runtime"  # → cu118 / CUDNN 8 base
    )

# ── main ──────────────────────────────────────────────────────────────────
def main() -> None:
    # REQUIRED secrets (failing fast beats mysterious HTTP-401 later)
    api_key   = req("RUNPOD_API_KEY")

    # Optional tweaks
    gpu_type  = os.getenv("GPU_TYPE", "NVIDIA H100 NVL")     # trusted profile
    region    = os.getenv("LINODE_DEFAULT_REGION", "us-se-1")
    volume_gb = int(os.getenv("VOLUME_GB") or 120)           # DON’T go <50 GB (HF cache)

    # Environment forwarded into the container
    env = {
        "MODEL_ID":    req("MODEL_ID"),
        "PROMPT_GLOB": req("PROMPT_GLOB"),
        "SEED":        req("SEED"),
        "WIDTH":       os.getenv("WIDTH",  "3072"),          # 3×1024 sprite-sheet
        "HEIGHT":      os.getenv("HEIGHT", "1024"),
        "ORTHO":       os.getenv("ORTHO",  "true"),

        # Linode S3 creds (leave blank to skip S3 upload step inside the pod)
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

        # 1 ─ Pin Torch / TorchVision first  (see Lesson 1)
        "python3 -m pip install --no-cache-dir --upgrade "
        "--extra-index-url https://download.pytorch.org/whl/cu118 "
        "torch==2.3.0+cu118 torchvision==0.18.0+cu118 && "

        # 2 ─ Core HF libs (NO deps → Lessons 2 & 3)
        "python3 -m pip install --no-cache-dir --upgrade --no-deps "
        "diffusers==0.33.1 transformers==4.51.3 accelerate==0.27.2 "
        "pillow==10.3.0 safetensors==0.5.3 huggingface_hub==0.23.3 && "

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

    # ------------------------------------------------------------------- #
    payload = {
        "name": "pixart-render-on-demand",
        "cloudType": "SECURE",               # DON’T use “ON_DEMAND” for H100s
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
    last_log = ""                         # Lesson 6: stream only the delta
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
