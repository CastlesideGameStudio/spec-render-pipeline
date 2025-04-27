#!/usr/bin/env python3
"""
Launch a RunPod Community-Cloud pod via REST v1 and stream status.
Required env vars (Github Actions passes them):
  RUNPOD_API_KEY   Bearer token (repo secret)
  PROMPT_GLOB      *.ndjson glob
  IMAGE_TAG        ghcr tag
  RUNPOD_GPU_TYPE  e.g. 'NVIDIA GeForce RTX 4090'
"""
import os, sys, glob, time, pathlib, json, requests

API   = "https://rest.runpod.io"
HEAD  = {"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}",
         "Content-Type":  "application/json"}

# ─── join prompts ──────────────────────────────
prompts = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()
if not prompts:
    sys.exit("No prompts matched " + os.environ["PROMPT_GLOB"])
env_block = { "PROMPTS_NDJSON": "\n".join(prompts)[:48000] }

# ─── launch pod ────────────────────────────────
image = f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}/spec-render:{os.environ['IMAGE_TAG']}"
payload = {
    "name":       "spec-render",
    "cloudType":  "COMMUNITY",
    "gpuTypeId":  os.environ["RUNPOD_GPU_TYPE"],   # 'NVIDIA GeForce RTX 4090'
    "gpuCount":   1,
    "imageName":  image,
    "volumeInGb": 20,
    "dockerArgs": "",
    "env":        env_block
}
pod = requests.post(f"{API}/pod/launch", headers=HEAD, json=payload).json()
pod_id = pod["podId"]
print("[launcher] Pod ID", pod_id, flush=True)

# ─── poll until done ───────────────────────────
while True:
    info = requests.get(f"{API}/pod/{pod_id}", headers=HEAD).json()
    phase = info["phase"]; runtime = info.get("runtime")
    print("[launcher] Phase", phase, "Runtime", runtime, flush=True)
    if phase in ("SUCCEEDED", "FAILED"):
        logs = requests.get(f"{API}/pod/{pod_id}/logs", headers=HEAD).text
        print("--- tail of pod logs ---\n", logs[-4000:], flush=True)
        sys.exit(0 if phase == "SUCCEEDED" else 1)
    time.sleep(20)
