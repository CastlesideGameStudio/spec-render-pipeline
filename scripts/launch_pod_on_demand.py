#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spin up one On-Demand RunPod instance and stream logs.

Required env vars
  RUNPOD_API_KEY – bearer token from https://runpod.io
Optional
  IMAGE_NAME     – full container tag (e.g. runpod/comfyui:cu118-py311)   ← NEW
  IMAGE_DIGEST   – sha256:… (used only if IMAGE_NAME absent; legacy path)
  PROMPT_GLOB    – NDJSON pattern (default: addendums/**/*.ndjson)
  GPU_TYPE       – GPU, e.g. “NVIDIA A40” (default)
  CONTAINER_AUTH_ID – registry-auth ID for private images
  AWS_*          – forwarded unchanged to the container
"""

import glob
import os
import pathlib
import sys
import time
import requests

BASE  = "https://rest.runpod.io/v1"
API_PODS = f"{BASE}/pods"


# ─────────────────────────────────────────────────────────────────────────────
def image_ref() -> str:
    """Prefer IMAGE_NAME (template tag); fall back to digest for GHCR images."""
    name = os.getenv("IMAGE_NAME")
    if name:
        return name                                   # runpod/comfyui:cu118-py311
    digest = os.getenv("IMAGE_DIGEST")
    if not digest:
        sys.exit("[ERROR] IMAGE_NAME or IMAGE_DIGEST must be set.")
    repo = os.getenv("GITHUB_REPOSITORY", "").lower()
    return f"ghcr.io/{repo}@{digest}"


def gather_prompts(pattern: str) -> str:
    lines: list[str] = []
    for path in glob.glob(pattern, recursive=True):
        lines += [ln for ln in pathlib.Path(path).read_text().splitlines() if ln.strip()]
    if not lines:
        sys.exit(f"[ERROR] No prompts matched '{pattern}'.")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    api_key = os.getenv("RUNPOD_API_KEY") or sys.exit("[ERROR] RUNPOD_API_KEY missing.")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    gpu_type = os.getenv("GPU_TYPE", "NVIDIA A40")
    image    = image_ref()
    auth_id  = os.getenv("CONTAINER_AUTH_ID")

    env_block = {
        "PROMPTS_NDJSON": gather_prompts(os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")),
        "AWS_ACCESS_KEY_ID":     os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_DEFAULT_REGION":    os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    }

    payload = {
        "name":              "spec-render-on-demand",
        "cloudType":         "SECURE",
        "gpuTypeIds":        [gpu_type],
        "gpuCount":          1,
        "volumeInGb":        20,
        "containerDiskInGb": 20,
        "imageName":         image,
        "env":               env_block,
    }
    if auth_id:
        payload["containerRegistryAuthId"] = auth_id

    print(f"[INFO] Creating pod – GPU='{gpu_type}'  image='{image}'")
    resp = requests.post(API_PODS, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    pod_id = resp.json().get("id") or sys.exit("[ERROR] No pod ID returned.")
    print(f"[INFO] Pod created: {pod_id}")

    # ───── log streaming ────────────────────────────────────────────────────
    last_log = ""
    while True:
        time.sleep(10)

        # incremental logs
        log_resp = requests.get(f"{API_PODS}/{pod_id}/logs", headers=headers, timeout=30)
        if log_resp.ok:
            txt = log_resp.text
            if txt != last_log:
                print(txt[len(last_log):], end="", flush=True)
                last_log = txt

        # status check
        stat = requests.get(f"{API_PODS}/{pod_id}", headers=headers, timeout=30)
        if not stat.ok:
            print("[WARN] Status check failed; retrying …")
            continue
        status = stat.json().get("status", "UNKNOWN")
        if status not in ("Pending", "Running"):
            print(f"\n[INFO] Pod status = {status}")
            break

    print("[INFO] Finished log streaming; pod is no longer running.")


if __name__ == "__main__":
    main()
