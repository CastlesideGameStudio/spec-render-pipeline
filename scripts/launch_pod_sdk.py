#!/usr/bin/env python3
"""
Verbose RunPod launcher for GitHub Actions.
  • prints GPU list + slug mapping
  • dumps JSON payload sent to create_pod
  • prints full responses for create, status, and final logs
Env vars (same as before):
  RUNPOD_API_KEY, PROMPT_GLOB, IMAGE_TAG, RUNPOD_GPU_TYPE
"""
import os, sys, glob, time, json, pathlib, runpod

runpod.api_key = os.environ["RUNPOD_API_KEY"]

def log(msg): print("[launcher]", msg, flush=True)

# ─── helper: map displayName → slug ────────────────────────────
def gpu_slug(display_name: str) -> str:
    log("Fetching GPU catalog …")
    gpu_table = runpod.get_gpus()          # [{id,displayName,…}, …]
    for g in gpu_table:
        log(f"  {g['displayName']:<25} → {g['id']}")
        if g["displayName"] == display_name:
            return g["id"]
    sys.exit(f"[launcher] GPU '{display_name}' not found.")

# ─── gather prompts ───────────────────────────────────────────
prompts = []
for path in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(path).read_text().splitlines()
if not prompts:
    sys.exit("[launcher] No prompts match " + os.environ["PROMPT_GLOB"])
log(f"Collected {len(prompts)} prompt lines")

env_block = { "PROMPTS_NDJSON": "\n".join(prompts)[:48000] }
image     = (f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
             f"/spec-render:{os.environ['IMAGE_TAG']}")
gpu_slug  = gpu_slug(os.environ["RUNPOD_GPU_TYPE"])

# ─── create pod ───────────────────────────────────────────────
payload = {
    "name"         : "spec-render",
    "gpu_type_id"  : gpu_slug,
    "gpu_count"    : 1,
    "image_name"   : image,
    "cloud_type"   : "COMMUNITY",
    "volume_in_gb" : 20,
    "env"          : env_block
}
log("create_pod payload:\n" + json.dumps(payload, indent=2))
pod = runpod.create_pod(**payload)
log("create_pod response:\n" + json.dumps(pod, indent=2))

pod_id = pod["id"]
log(f"Pod ID {pod_id}")

# ─── poll until finished ──────────────────────────────────────
while True:
    info = runpod.get_pod(pod_id)
    log("status response:\n" + json.dumps(info, indent=2))
    phase  = info["phase"]; runtime = info.get("runtime")
    log(f"Phase {phase:<9}  Runtime {runtime}")
    if phase in ("SUCCEEDED", "FAILED"):
        logs = runpod.get_pod_logs(pod_id)
        log("--- full pod logs (truncated to 4kB) ---\n" + logs[-4000:])
        sys.exit(0 if phase == "SUCCEEDED" else 1)
    time.sleep(20)
