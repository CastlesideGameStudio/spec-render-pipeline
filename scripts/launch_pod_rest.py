#!/usr/bin/env python3
"""Launch RunPod pod via REST v2 and stream status."""
import os, sys, glob, time, pathlib, requests, json

API = "https://rest.runpod.io/v2"
HEAD = {
    "Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}",
    "Content-Type":  "application/json"
}

# ─── gather prompts ─────────────────────────────────────────────
prompts = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()
if not prompts:
    sys.exit("No prompts matched " + os.environ["PROMPT_GLOB"])

env_block = { "PROMPTS_NDJSON": "\n".join(prompts)[:48000] }
image = (f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
         f"/spec-render:{os.environ['IMAGE_TAG']}")
gpu_type = os.environ["RUNPOD_GPU_TYPE"]

# ─── launch pod ─────────────────────────────────────────────────
payload = {
    "name":       "spec-render",
    "cloudType":  "COMMUNITY",
    "gpuTypeId":  gpu_type,
    "gpuCount":   1,
    "imageName":  image,
    "volumeInGb": 20,
    "env":        env_block
}

r = requests.post(f"{API}/pod/launch", headers=HEAD, json=payload)
if r.status_code != 200:
    print("[launcher] HTTP", r.status_code, "response:\n", r.text)
    r.raise_for_status()

pod_id = r.json()["podId"]
print("[launcher] Pod ID", pod_id, flush=True)

# ─── poll until done ───────────────────────────────────────────
while True:
    info = requests.get(f"{API}/pod/{pod_id}", headers=HEAD).json()
    phase = info["phase"]; runtime = info.get("runtime")
    print("[launcher] Phase", phase, "Runtime", runtime, flush=True)
    if phase in ("SUCCEEDED", "FAILED"):
        logs = requests.get(f"{API}/pod/{pod_id}/logs", headers=HEAD).text
        print("--- tail of pod logs ---\n", logs[-4000:], flush=True)
        sys.exit(0 if phase == "SUCCEEDED" else 1)
    time.sleep(20)
