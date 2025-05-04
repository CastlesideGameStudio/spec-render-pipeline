#!/usr/bin/env python3
"""
Spin up one On-Demand RunPod pod (H100 NVL by default) and stream logs,
running the deterministic Qwen-3 batch generator.

All required ENV vars are injected by the GitHub workflow.
"""
from __future__ import annotations
import os, sys, time, requests

BASE      = "https://rest.runpod.io/v1"
API_PODS  = f"{BASE}/pods"
POLL_SEC  = 10


# ─── helpers ───────────────────────────────────────────────────────────────
def req_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        sys.exit(f"[ERROR] Required ENV '{key}' is missing or empty.")
    return val

def normalise_gpu(name: str) -> str:
    return name if name.startswith(("NVIDIA ", "AMD ", "Tesla ")) else f"NVIDIA {name}"

def image_ref() -> str:
    return os.getenv("IMAGE_NAME", "pytorch/pytorch:2.3.1-cuda11.8-cudnn8-runtime")


# ─── main ──────────────────────────────────────────────────────────────────
def main() -> None:
    api_key  = req_env("RUNPOD_API_KEY")
    region   = req_env("LINODE_DEFAULT_REGION")
    gpu_type = normalise_gpu(os.getenv("GPU_TYPE", "NVIDIA H100 NVL"))
    volume_gb= int(os.getenv("VOLUME_GB", "120") or 120)
    image    = image_ref()

    # mandatory vars for the generator
    env_block = {
        "MODEL_ID":    req_env("MODEL_ID"),
        "PROMPT_GLOB": req_env("PROMPT_GLOB"),
        "SEED":        req_env("SEED"),

        # optional run-time knobs
        "WIDTH":  os.getenv("WIDTH",  "1920"),
        "HEIGHT": os.getenv("HEIGHT", "1080"),
        "ORTHO":  os.getenv("ORTHO",  "true"),

        # Linode creds
        "LINODE_ACCESS_KEY_ID":     os.getenv("LINODE_ACCESS_KEY_ID", ""),
        "LINODE_SECRET_ACCESS_KEY": os.getenv("LINODE_SECRET_ACCESS_KEY", ""),
        "LINODE_S3_ENDPOINT":       os.getenv("LINODE_S3_ENDPOINT", ""),
        "LINODE_DEFAULT_REGION":    region,
    }

    print("[DEBUG] Container ENV:")
    for k, v in env_block.items():
        trunc = (v[:110] + "…") if len(v) > 110 else v
        print(f"   {k} = {trunc!r}")

    payload = {
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
                # deterministic cuBLAS + minimal deps
                "export CUBLAS_WORKSPACE_CONFIG=:16:8 && "
                "export DEBIAN_FRONTEND=noninteractive && "
                "apt-get update -qq && "
                "apt-get install -y --no-install-recommends git python3-pip tzdata && "
                "python3 -m pip install --no-cache-dir --upgrade "
                "'transformers>=4.51.0' accelerate bitsandbytes pillow && "
                # clone or reuse repo
                "[ -d /workspace/repo/.git ] || "
                "git clone --depth 1 https://github.com/CastlesideGameStudio/spec-render-pipeline.git /workspace/repo && "
                # run deterministic generator
                "python3 /workspace/repo/scripts/generate_qwen3.py"
            ),
        ],
        "env": env_block,
    }

    if (auth := os.getenv("CONTAINER_AUTH_ID")):
        payload["containerRegistryAuthId"] = auth

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    print(f"[INFO] Creating pod → GPU={gpu_type}, image={image}, disk={volume_gb} GB")
    r = requests.post(API_PODS, json=payload, headers=headers, timeout=60)
    if r.status_code >= 400:
        print("[ERROR] Pod creation failed →", r.status_code, r.text); sys.exit(1)

    pod_id = r.json().get("id") or sys.exit("[ERROR] No pod ID returned.")
    print(f"[INFO] Pod created: {pod_id}")

    # ── tail logs until pod exits ─────────────────────────────────────────
    last_log = ""
    while True:
        time.sleep(POLL_SEC)
        log = requests.get(f"{API_PODS}/{pod_id}/logs", headers=headers, timeout=30)
        if log.ok and log.text != last_log:
            print(log.text[len(last_log):], end="", flush=True)
            last_log = log.text
        stat = requests.get(f"{API_PODS}/{pod_id}", headers=headers, timeout=30)
        status = stat.json().get("status", "UNKNOWN") if stat.ok else "UNKNOWN"
        if status not in ("Pending", "Running"):
            print(f"\n[INFO] Pod status = {status}"); break
    print("[INFO] Log stream closed — pod finished.")

if __name__ == "__main__":
    main()
