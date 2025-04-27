#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spins up one On-Demand pod on RunPod via the REST API.
Expects env:
  RUNPOD_API_KEY  – your "Bearer" token
  PROMPT_GLOB     – NDJSON pattern (default "addendums/**/*.ndjson")
  IMAGE_TAG       – container tag (default "latest")
  GPU_TYPE        – e.g. "NVIDIA A40", "NVIDIA RTX A5000", etc.
"""
import os
import sys
import glob
import time
import pathlib
import requests

# Note the "/v1" in the base URL now
BASE_URL   = "https://rest.runpod.io/v1"
API_PODS   = f"{BASE_URL}/pod"       # for POST and GET
API_LOGS   = f"{BASE_URL}/pod/logs"  # for GET logs

def main():
    runpod_api_key = os.getenv("RUNPOD_API_KEY", "")
    if not runpod_api_key:
        sys.exit("[ERROR] RUNPOD_API_KEY missing or empty.")

    prompt_glob = os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")
    image_tag   = os.getenv("IMAGE_TAG", "latest")
    gpu_type    = os.getenv("GPU_TYPE", "NVIDIA A40")

    # 1) Gather NDJSON lines
    all_lines = []
    for path in glob.glob(prompt_glob, recursive=True):
        txt = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
        # skip blank lines
        lines = [ln for ln in txt if ln.strip()]
        all_lines.extend(lines)

    if not all_lines:
        sys.exit(f"[ERROR] No prompts found matching {prompt_glob}.")

    print(f"[INFO] Found {len(all_lines)} total lines from '{prompt_glob}'")

    # Combine lines into a single environment variable
    env_block = {"PROMPTS_NDJSON": "\n".join(all_lines)}

    # Build the container reference
    # e.g. "ghcr.io/owner/repo/spec-render:latest"
    repo_slug  = os.getenv("GITHUB_REPOSITORY", "yourorg/yourrepo").lower()
    image_name = f"ghcr.io/{repo_slug}/spec-render:{image_tag}"

    headers = {
        "Authorization": f"Bearer {runpod_api_key}",
        "Content-Type":  "application/json",
    }

    # 2) Create the pod
    payload = {
        "name":         "spec-render-on-demand",
        "cloud_type":   "SECURE",         # On-Demand
        "gpuTypeId":    gpu_type,
        "gpuCount":     1,
        "volumeInGb":   20,
        "containerDiskInGb": 20,
        "imageName":    image_name,
        "env":          env_block
    }

    print(f"[INFO] Creating Pod with GPU='{gpu_type}' image='{image_name}'")
    r = requests.post(API_PODS, json=payload, headers=headers, timeout=60)
    if not r.ok:
        print("[ERROR] Pod creation failed.")
        print("Status:", r.status_code)
        print("Response:", r.text)
        sys.exit(1)

    pod_data = r.json()  # Should return e.g. {"id": "...", "name": "...", ...}
    pod_id   = pod_data.get("id")
    if not pod_id:
        sys.exit("[ERROR] No pod ID returned in response.")

    print(f"[INFO] Pod created with ID={pod_id}")

    # 3) Poll until not "Running"
    while True:
        time.sleep(20)
        r_stat = requests.get(f"{API_PODS}/{pod_id}", headers=headers, timeout=30)
        if not r_stat.ok:
            print("[WARN] GET /pod/<id> failed, ignoring temporarily")
            continue
        status_data = r_stat.json()  # e.g. {"id":..., "status":"Running", ...}
        status = status_data.get("status")
        print(f"[INFO] Pod status={status}")

        if status not in ("Pending", "Running"):
            print("[INFO] Pod is no longer Running. Breaking out of loop.")
            break

    # Optional: retrieve logs
    # GET /pod/<podId>/logs
    r_logs = requests.get(f"{API_PODS}/{pod_id}/logs", headers=headers, timeout=30)
    if r_logs.ok:
        logs_txt = r_logs.text
        print("------ Pod logs ------")
        print(logs_txt[-3000:])  # print last 3000 chars, if large
    else:
        print("[WARN] Could not fetch logs. Status =", r_logs.status_code)

    sys.exit(0)

if __name__ == "__main__":
    main()
