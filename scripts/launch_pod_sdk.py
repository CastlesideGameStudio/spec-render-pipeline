#!/usr/bin/env python3
"""
Launch a COMMUNITY pod via the runpod-python SDK and stream status.

Env vars injected by GitHub Actions:
  RUNPOD_API_KEY   – bearer token  (secret)
  PROMPT_GLOB      – NDJSON glob   (workflow input)
  IMAGE_TAG        – GHCR tag      (workflow input)
  RUNPOD_GPU_TYPE  – e.g. 'NVIDIA GeForce RTX 4090'  (secret or input)
"""
import os, sys, glob, time, pathlib, runpod

runpod.api_key = os.environ["RUNPOD_API_KEY"]

# ─── collect prompts ────────────────────────────────────────────
prompts = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()
if not prompts:
    sys.exit("[launcher] No prompts matched " + os.environ["PROMPT_GLOB"])

env_block = { "PROMPTS_NDJSON": "\n".join(prompts)[:48000] }
image     = (f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
             f"/spec-render:{os.environ['IMAGE_TAG']}")
gpu_type  = os.environ["RUNPOD_GPU_TYPE"]

# ─── create pod (SDK maps to createOnDemandPod) ─────────────────
pod = runpod.create_pod(
    name       = "spec-render",
    gpuTypeId  = gpu_type,
    cloudType  = "COMMUNITY",
    imageName  = image,
    gpuCount   = 1,
    volumeInGb = 20,
    env        = env_block        # can pass dict directly
)
pod_id = pod["id"]
print("[launcher] Pod ID", pod_id, flush=True)

# ─── poll until finished ────────────────────────────────────────
while True:
    info = runpod.get_pod(pod_id)
    phase = info["phase"]; runtime = info.get("runtime")
    print(f"[launcher] Phase {phase:<9} Runtime {runtime}", flush=True)

    if phase in ("SUCCEEDED", "FAILED"):
        logs = runpod.get_pod_logs(pod_id)
        print("--- tail of pod logs ---\n", logs[-4000:], flush=True)
        sys.exit(0 if phase == "SUCCEEDED" else 1)

    time.sleep(20)
