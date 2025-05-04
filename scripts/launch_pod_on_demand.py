#!/usr/bin/env python3
"""
Spin up an On-Demand RunPod instance (H100 NVL by default) and stream logs,
running the Qwen-3 multimodal batch generator.

Environment variables are injected by the GitHub workflow.
"""
from __future__ import annotations
import glob, os, pathlib, sys, time
from typing import List
import requests

BASE      = "https://rest.runpod.io/v1"
API_PODS  = f"{BASE}/pods"
POLL_SEC  = 10            # seconds between log polls
# ───────────────────────── helpers ─────────────────────────────────────────
def normalise_gpu(name: str) -> str:
    return name if name.startswith(("NVIDIA ", "AMD ", "Tesla ")) else f"NVIDIA {name}"

def image_ref() -> str:
    return os.getenv("IMAGE_NAME", "pytorch/pytorch:2.3.1-cuda11.8-cudnn8-runtime")

def gather_prompts(pattern: str) -> str:
    lines: List[str] = []
    for path in glob.glob(pattern, recursive=True):
        lines.extend(pathlib.Path(path).read_text(encoding="utf-8").splitlines())
    if not lines:
        sys.exit(f"[ERROR] No prompts matched '{pattern}'.")
    return "\n".join([ln for ln in lines if ln.strip()])

# ───────────────────────── main ────────────────────────────────────────────
def main() -> None:
    api_key = os.getenv("RUNPOD_API_KEY") or sys.exit("[ERROR] RUNPOD_API_KEY missing.")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    region   = os.getenv("LINODE_DEFAULT_REGION") or sys.exit("[ERROR] LINODE_DEFAULT_REGION missing.")
    gpu_type = normalise_gpu(os.getenv("GPU_TYPE", "NVIDIA H100 NVL"))
    volume_gb = int(os.getenv("VOLUME_GB", "120") or 120)
    image     = image_ref()

    env_block = {
        "PROMPTS_NDJSON": gather_prompts(os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")),
        "MODEL_ID": os.getenv("MODEL_ID", "Qwen/Qwen3-32B"),
        "WIDTH":    os.getenv("WIDTH",  "1920"),
        "HEIGHT":   os.getenv("HEIGHT", "1080"),
        "ORTHO":    os.getenv("ORTHO",  "true"),
        # Linode creds
        "LINODE_ACCESS_KEY_ID":     os.getenv("LINODE_ACCESS_KEY_ID", ""),
        "LINODE_SECRET_ACCESS_KEY": os.getenv("LINODE_SECRET_ACCESS_KEY", ""),
        "LINODE_S3_ENDPOINT":       os.getenv("LINODE_S3_ENDPOINT", ""),
        "LINODE_DEFAULT_REGION":    region,
    }

    print("[DEBUG] Container environment block:")
    for k, v in env_block.items():
        print(f"   {k} = {v[:120] + ('…' if len(v) > 120 else '')}")

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
                # ── minimal OS + Python stack (flash-attn removed) ─────────────
                "export DEBIAN_FRONTEND=noninteractive && "
                "apt-get update -qq && "
                "apt-get install -y --no-install-recommends git python3-pip tzdata && "
                "python3 -m pip install --no-cache-dir --upgrade "
                "'transformers>=4.51.0' accelerate bitsandbytes pillow && "
                # ── pipeline repo ────────────────────────────────────────────
                "[ -d /workspace/repo/.git ] || "
                "git clone --depth 1 https://github.com/CastlesideGameStudio/spec-render-pipeline.git /workspace/repo && "
                # ── run batch generator ──────────────────────────────────────
                "python3 /workspace/repo/scripts/generate_qwen3.py"
            ),
        ],
        "env": env_block,
    }

    if (auth_id := os.getenv("CONTAINER_AUTH_ID")):
        payload["containerRegistryAuthId"] = auth_id

    # ── create the pod ─────────────────────────────────────────────────────
    print(f"[INFO] Creating pod → GPU={gpu_type}, image={image}, disk={volume_gb} GB")
    resp = requests.post(API_PODS, json=payload, headers=headers, timeout=60)
    if resp.status_code >= 400:
        print("[ERROR] Pod creation failed → HTTP", resp.status_code)
        print(resp.text)
        sys.exit(1)

    pod_id = resp.json().get("id") or sys.exit("[ERROR] No pod ID returned.")
    print(f"[INFO] Pod created: {pod_id}")

    # ── stream logs until completion ──────────────────────────────────────
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
