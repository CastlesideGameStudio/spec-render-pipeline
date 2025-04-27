#!/usr/bin/env python3
import os, sys, glob, time, json, pathlib, runpod, traceback

runpod.api_key = os.environ["RUNPOD_API_KEY"]
def log(msg): print("[launcher]", msg, flush=True)

# ─── credit check ──────────────────────────────────────────────
acct = runpod.get_account()
log(f"Credits: {acct['creditsRemaining']} — Spend rate: {acct['creditsPerHour']} /h")

# ─── helper: displayName OR slug → slug ───────────────────────
def gpu_slug(user_val: str) -> str:
    log("Fetching GPU catalog …")
    for g in runpod.get_gpus():
        log(f"  {g['displayName']:<24} → {g['id']}")
        if g["displayName"] == user_val or g["id"] == user_val:
            return g["id"]
    sys.exit(f"[launcher] GPU '{user_val}' not found.")

# ─── collect prompts ──────────────────────────────────────────
prompts = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()
if not prompts:
    sys.exit("[launcher] No prompts match " + os.environ["PROMPT_GLOB"])
log(f"Collected {len(prompts)} prompt lines")

env_block = { "PROMPTS_NDJSON": "\n".join(prompts)[:48000] }
image     = (f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
             f"/spec-render:{os.environ['IMAGE_TAG']}")
gpu_slug  = gpu_slug(os.environ["RUNPOD_GPU_TYPE"])

payload = {
    "name":         "spec-render",
    "gpu_type_id":  gpu_slug,
    "gpu_count":    1,
    "image_name":   image,
    "cloud_type":   "COMMUNITY",
    "volume_in_gb": 20,
    "env":          env_block
}
log("create_pod payload:\n" + json.dumps(payload, indent=2))

try:
    pod = runpod.create_pod(**payload)
except Exception as e:
    log("RunPod threw an exception:")
    traceback.print_exc()
    # if SDK wrapped an error, print the raw response if available
    if hasattr(e, "response") and e.response is not None:
        log("Raw response:\n" + e.response.text[:2000])
    sys.exit(1)

log("create_pod response:\n" + json.dumps(pod, indent=2))
pod_id = pod["id"]; log(f"Pod ID {pod_id}")

# ─── poll phase ───────────────────────────────────────────────
while True:
    info = runpod.get_pod(pod_id)
    phase = info["phase"]; runtime = info.get("runtime")
    log(f"Phase {phase:<9} Runtime {runtime}")
    if phase in ("SUCCEEDED", "FAILED"):
        logs = runpod.get_pod_logs(pod_id)
        log("--- tail of pod logs ---\n" + logs[-4000:])
        sys.exit(0 if phase == "SUCCEEDED" else 1)
    time.sleep(20)
