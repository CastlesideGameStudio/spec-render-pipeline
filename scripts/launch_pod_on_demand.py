#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spins up one On-Demand pod on RunPod,
using a single GPU type. Expects env:
  RUNPOD_API_KEY (required)
  PROMPT_GLOB    (default 'addendums/**/*.ndjson')
  IMAGE_TAG      (default 'latest')
  GPU_TYPE       (default 'NVIDIA A40') – must match a GPU in 'runpod.get_gpus()'
"""
import os, sys, glob, time, pathlib, requests

API_URL = "https://api.runpod.ai/graphql"
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY", "")

if not RUNPOD_API_KEY:
    sys.exit("[ERROR] RUNPOD_API_KEY not set.")

PROMPT_GLOB = os.environ.get("PROMPT_GLOB", "addendums/**/*.ndjson")
IMAGE_TAG   = os.environ.get("IMAGE_TAG", "latest")
GPU_TYPE    = os.environ.get("GPU_TYPE", "NVIDIA A40")

# This is your GHCR image, for example:
#   ghcr.io/owner/repo/spec-render:latest
REPO_SLUG    = os.environ["GITHUB_REPOSITORY"].lower()  # e.g. "myorg/myrepo"
IMAGE_NAME   = f"ghcr.io/{REPO_SLUG}/spec-render:{IMAGE_TAG}"

def gq(query, variables=None):
    resp = requests.post(
        API_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": RUNPOD_API_KEY},
        timeout=25
    )
    resp.raise_for_status()
    j = resp.json()
    if "errors" in j:
        raise RuntimeError(j["errors"])
    return j["data"]

def start_pod(image_name, env, gpu_type_id):
    query = """mutation($input: PodInput!) {
      podLaunch(input: $input) {
        podId
      }
    }"""
    pod_input = {
        "name": "spec-render-on-demand",
        "cloudType": "SECURE",        # <= On-Demand
        "gpuTypeId": gpu_type_id,     # e.g. "NVIDIA A40"
        "gpuCount": 1,
        "volumeInGb": 20,
        "containerDiskInGb": 20,
        "imageName": image_name,
        "env": env,
    }
    variables = {"input": pod_input}
    data = gq(query, variables)
    return data["podLaunch"]["podId"]

def get_pod_status(pod_id):
    query = """query($podId: ID!) {
      podDetails(podId: $podId) {
        name
        phase
        runtime
        exitCode
      }
    }"""
    data = gq(query, {"podId": pod_id})
    return data["podDetails"]

def get_pod_logs(pod_id):
    query = """query($podId: ID!){
      podLogs(podId: $podId)
    }"""
    data = gq(query, {"podId": pod_id})
    return data["podLogs"]

# ─────────────────────────────────────────────────────────────
# 1) Gather all lines from NDJSON
all_prompts = []
for path in glob.glob(PROMPT_GLOB, recursive=True):
    txt = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    # skip blank lines
    lines = [ln for ln in txt if ln.strip()]
    all_prompts.extend(lines)

if not all_prompts:
    sys.exit(f"[ERROR] No prompts found under '{PROMPT_GLOB}'.")

print(f"[INFO] Found {len(all_prompts)} total prompt lines matching '{PROMPT_GLOB}'")

# Merge them into a single environment variable. 
#   If extremely large, you might exceed the ~48-64KB limit. 
#   For now, just do a naive join.
env_block = {"PROMPTS_NDJSON": "\n".join(all_prompts)}

# ─────────────────────────────────────────────────────────────
# 2) Start the Pod
pod_id = None
try:
    print(f"[INFO] Attempting to launch On-Demand pod with GPU='{GPU_TYPE}'")
    pod_id = start_pod(IMAGE_NAME, env_block, GPU_TYPE)
    print("[INFO] Pod ID =", pod_id)
except Exception as e:
    print("[ERROR] Pod launch failed:", e)
    sys.exit(1)

# ─────────────────────────────────────────────────────────────
# 3) Poll until done
while True:
    time.sleep(20)
    info = get_pod_status(pod_id)
    print(f"[INFO] Pod phase={info['phase']} runtime={info.get('runtime')} sec")

    if info["phase"] in ["SUCCEEDED", "FAILED"]:
        print("[INFO] Pod completed with exitCode=", info.get("exitCode"))
        logs = get_pod_logs(pod_id)
        print("---- Tail of logs ----\n" + logs[-2000:])
        if info["phase"] == "FAILED":
            sys.exit(1)
        else:
            sys.exit(0)
