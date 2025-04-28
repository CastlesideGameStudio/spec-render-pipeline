#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spin up one On-Demand RunPod instance.

Required env vars
  RUNPOD_API_KEY   – your bearer token from https://runpod.io
  IMAGE_DIGEST     – sha256:… of the container image to run
Optional
  PROMPT_GLOB      – NDJSON pattern (default: addendums/**/*.ndjson)
  GPU_TYPE         – e.g. “NVIDIA A40” (default)
  CONTAINER_AUTH_ID– RunPod registry-auth ID for private images
  AWS_*            – forwarded unchanged to the container
"""

import glob
import os
import pathlib
import sys
import time
import requests

BASE_URL = "https://rest.runpod.io/v1"
API_PODS = f"{BASE_URL}/pods"

# ---------------------------------------------------------------------------

def image_ref() -> str:
    repo_slug = os.getenv("GITHUB_REPOSITORY", "").lower()
    digest    = os.getenv("IMAGE_DIGEST")
    if not digest:
        sys.exit("[ERROR] IMAGE_DIGEST is mandatory.")
    return f"ghcr.io/{repo_slug}@{digest}"

# ---------------------------------------------------------------------------

def main() -> None:
    key = os.getenv("RUNPOD_API_KEY")
    if not key:
        sys.exit("[ERROR] RUNPOD_API_KEY missing.")

    prompt_glob = os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")
    gpu_type    = os.getenv("GPU_TYPE", "NVIDIA A40")
    auth_id     = os.getenv("CONTAINER_AUTH_ID")  # may be empty
    img         = image_ref()

    # gather prompts ---------------------------------------------------------
    lines: list[str] = []
    for path in glob.glob(prompt_glob, recursive=True):
        lines += [l for l in pathlib.Path(path).read_text().splitlines() if l.strip()]
    if not lines:
        sys.exit(f"[ERROR] No prompts matched '{prompt_glob}'.")
    env_block = {
        "PROMPTS_NDJSON": "\n".join(lines),
        "AWS_ACCESS_KEY_ID":     os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_DEFAULT_REGION":    os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    }

    # create pod -------------------------------------------------------------
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "name":              "spec-render-on-demand",
        "cloudType":         "SECURE",
        "gpuTypeIds":        [gpu_type],
        "gpuCount":          1,
        "volumeInGb":        20,
        "containerDiskInGb": 20,
        "imageName":         img,
        "env":               env_block,
    }
    if auth_id:
        payload["containerRegistryAuthId"] = auth_id

    print(f"[INFO] Creating pod – GPU='{gpu_type}'  image='{img}'")
    r = requests.post(API_PODS, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    pod_id = r.json().get("id") or sys.exit("[ERROR] No pod ID returned.")
    print(f"[INFO] Pod created: {pod_id}")

    # poll status ------------------------------------------------------------
    while True:
        time.sleep(20)
        s = requests.get(f"{API_PODS}/{pod_id}", headers=headers, timeout=30)
        if not s.ok:
            print("[WARN] status check failed; retrying …")
            continue
        status = s.json().get("status", "UNKNOWN")
        print(f"[INFO] Pod status = {status}")
        if status not in ("Pending", "Running"):
            break

    # tail logs --------------------------------------------------------------
    logs = requests.get(f"{API_PODS}/{pod_id}/logs", headers=headers, timeout=30)
    if logs.ok:
        print("------ Pod logs (tail) ------")
        print(logs.text[-3000:])
    else:
        print("[WARN] Could not fetch logs; HTTP", logs.status_code)


if __name__ == "__main__":
    main()
