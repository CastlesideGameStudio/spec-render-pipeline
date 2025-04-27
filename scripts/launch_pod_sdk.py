#!/usr/bin/env python3
"""
Launch a Community pod via the runpod-python SDK and stream status.
Env vars: RUNPOD_API_KEY, PROMPT_GLOB, IMAGE_TAG, RUNPOD_GPU_TYPE
"""
import os, sys, glob, time, pathlib, runpod

runpod.api_key = os.environ["RUNPOD_API_KEY"]

# ─── collect prompts ───────────────────────────────────────────
prompts = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()
if not prompts:
    sys.exit("[launcher] No prompts match " + os.environ["PROMPT_GLOB"])

env_block = { "PROMPTS_NDJSON": "\n".join(prompts)[:48000] }
image     = (f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
             f"/spec-render:{os.environ['IMAGE_TAG']}")
gpu_type  = os.environ["RUNPOD_GPU_TYPE"]

# ─── create pod (note snake-case params) ───────────────────────
pod = runpod.create_pod(
    name         = "spec-render",
    gpu_type_id  = gpu_type,
    gpu_count    = 1,
    image_name   = image,
    cloud_type   = "COMMUNITY",
    volume_in_gb = 20,
    env          = env_block          # dict is fine
)
pod_id = pod["id"]
print("[launcher] Pod ID", pod_id, flush=True)

# ─── poll until finished ───────────────────────────────────────
while True:
    info = runpod.get_pod(pod_id)
    phase = info["phase"]; runtime = info.get("runtime")
    print(f"[launcher] Phase {phase:<9} Runtime {runtime}", flush=True)

    if phase in ("SUCCEEDED", "FAILED"):
        logs = runpod.get_pod_logs(pod_id)
        print("--- tail of pod logs ---\n", logs[-4000:], flush=True)
        sys.exit(0 if phase == "SUCCEEDED" else 1)

    time.sleep(20)
