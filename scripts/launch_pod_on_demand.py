#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spins up one On-Demand pod on RunPod via the REST API.

Environment variables (from GitHub Actions or local shell)

  # --- required --------------------------------------------------------------
  RUNPOD_API_KEY          – your “Bearer …” token from https://runpod.io
  # --- optional / have defaults ---------------------------------------------
  PROMPT_GLOB             – NDJSON pattern         (default: addendums/**/*.ndjson)
  IMAGE_TAG               – container tag          (default: latest)
  IMAGE_DIGEST            – full image digest      (overrides IMAGE_TAG if set)
  GPU_TYPE                – e.g. “NVIDIA A40”      (default: NVIDIA A40)
  CONTAINER_AUTH_ID       – RunPod registry-auth ID (if image is private)
  # S3 credentials (only forwarded to the container)
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_DEFAULT_REGION      – (default: us-east-1)
"""

import glob
import os
import pathlib
import sys
import time
import requests

BASE_URL   = "https://rest.runpod.io/v1"
API_PODS   = f"{BASE_URL}/pods"
API_LOGS   = f"{BASE_URL}/pods/logs"


def build_image_ref() -> str:
    """
    Build the GHCR reference.  The image lives exactly at
    ghcr.io/<owner>/<repo>:<tag>  (or @<digest> if IMAGE_DIGEST is set).
    """
    repo_slug   = os.getenv("GITHUB_REPOSITORY", "").lower()     # owner/repo
    digest      = os.getenv("IMAGE_DIGEST")                      # sha256:…
    image_tag   = os.getenv("IMAGE_TAG", "latest")

    if digest:                                                   # immutable pin
        return f"ghcr.io/{repo_slug}@{digest}"
    else:
        return f"ghcr.io/{repo_slug}:{image_tag}"


def main() -> None:

    # ------------------------------------------------------------------ config
    runpod_api_key = os.getenv("RUNPOD_API_KEY", "")
    if not runpod_api_key:
        sys.exit("[ERROR] RUNPOD_API_KEY missing or empty.")

    prompt_glob = os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")
    gpu_type    = os.getenv("GPU_TYPE", "NVIDIA A40")
    image_name  = build_image_ref()
    auth_id     = os.getenv("CONTAINER_AUTH_ID")  # optional

    # ---------------------------------------------------------------- prompts
    all_lines: list[str] = []
    for path in glob.glob(prompt_glob, recursive=True):
        lines = [
            ln for ln in pathlib.Path(path).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        all_lines.extend(lines)

    if not all_lines:
        sys.exit(f"[ERROR] No prompts found matching '{prompt_glob}'.")

    print(f"[INFO] Found {len(all_lines)} total prompt lines")

    env_block = {
        "PROMPTS_NDJSON": "\n".join(all_lines),
        "AWS_ACCESS_KEY_ID":     os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_DEFAULT_REGION":    os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    }

    # ----------------------------------------------------------------- create pod
    headers = {
        "Authorization": f"Bearer {runpod_api_key}",
        "Content-Type":  "application/json",
    }

    payload: dict = {
        "name":              "spec-render-on-demand",
        "cloudType":         "SECURE",     # on-demand
        "gpuTypeIds":        [gpu_type],
        "gpuCount":          1,
        "volumeInGb":        20,
        "containerDiskInGb": 20,
        "imageName":         image_name,
        "env":               env_block,
    }
    if auth_id:
        payload["containerRegistryAuthId"] = auth_id

    print(f"[INFO] Creating pod – GPU='{gpu_type}'  image='{image_name}'")
    resp = requests.post(API_PODS, json=payload, headers=headers, timeout=60)
    if not resp.ok:
        print("[ERROR] Pod creation failed:", resp.status_code)
        print(resp.text)
        sys.exit(1)

    pod_id = resp.json().get("id")
    if not pod_id:
        sys.exit("[ERROR] No pod ID returned in the response.")
    print(f"[INFO] Pod created with ID={pod_id}")

    # ------------------------------------------------------------- poll status
    while True:
        time.sleep(20)
        statu = requests.get(f"{API_PODS}/{pod_id}", headers=headers, timeout=30)
        if not statu.ok:
            print("[WARN] GET /pods/{podId} failed – retrying…")
            continue
        status = statu.json().get("status", "UNKNOWN")
        print(f"[INFO] Pod status = {status}")
        if status not in ("Pending", "Running"):
            break

    # -------------------------------------------------------------- fetch logs
    logs = requests.get(f"{API_PODS}/{pod_id}/logs", headers=headers, timeout=30)
    if logs.ok:
        print("------ Pod logs (tail) ------")
        print(logs.text[-3000:])
    else:
        print("[WARN] Could not fetch logs. HTTP", logs.status_code)


if __name__ == "__main__":
    main()
