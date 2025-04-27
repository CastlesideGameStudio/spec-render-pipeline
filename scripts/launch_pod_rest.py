#!/usr/bin/env python3
"""
Launch a RunPod COMMUNITY pod via REST v2 and stream status.

Required env vars:
  RUNPOD_API_KEY   – bearer token
  PROMPT_GLOB      – NDJSON glob
  IMAGE_TAG        – GHCR tag
  RUNPOD_GPU_TYPE  – e.g. 'NVIDIA GeForce RTX 4090'
"""
import os, sys, glob, time, pathlib, requests, json

API  = "https://rest.runpod.io/v2"
HEAD = {
    "Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}",
    "Content-Type":  "application/json",
    "Accept":        "application/json"
}

def quit(msg, code=1):
    print("[launcher]", msg, flush=True)
    sys.exit(code)

# ─── gather prompts ─────────────────────────────────────────────
prompts = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()
if not prompts:
    quit("No prompts match " + os.environ["PROMPT_GLOB"])

env_block = { "PROMPTS_NDJSON": "\n".join(prompts)[:48000] }

image = (f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
         f"/spec-render:{os.environ['IMAGE_TAG']}")
gpu_type = os.environ["RUNPOD_GPU_TYPE"]

# ─── launch pod ─────────────────────────────────────────────────
payload = {
    "name"      : "spec-render",
    "cloudType" : "COMMUNITY",
    "gpuTypeId" : gpu_type,      # e.g. 'NVIDIA GeForce RTX 4090'
    "gpuCount"  : 1,
    "imageName" : image,
    "volumeInGb": 20,
    "env"       : env_block      # object in REST v2
}
resp = requests.post(f"{API}/pods", headers=HEAD, json=payload)

if not resp.ok:                             # 4xx / 5xx
    quit(f"HTTP {resp.status_code}\n{resp.text[:2000]}")

try:
    pod_id = resp.json()["id"]              # REST v2 returns 'id'
except Exception as e:
    quit("Non-JSON response:\n" + resp.text[:1000])

print("[launcher] Pod ID", pod_id, flush=True)

# ─── poll status until finished ─────────────────────────────────
while True:
    info  = requests.get(f"{API}/pods/{pod_id}", headers=HEAD).json()
    phase = info["phase"]; runtime = info.get("runtime")
    print(f"[launcher] Phase {phase:<9} Runtime {runtime}", flush=True)

    if phase in ("SUCCEEDED", "FAILED"):
        logs = requests.get(f"{API}/pods/{pod_id}/logs",
                            headers=HEAD).text
        print("--- tail of pod logs ---\n", logs[-4000:], flush=True)
        quit("Done", 0 if phase == "SUCCEEDED" else 1)

    time.sleep(20)
