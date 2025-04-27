#!/usr/bin/env python3
"""
RunPod launcher that auto-selects a Community GPU with capacity.

Env vars:
  RUNPOD_API_KEY   – required
  PROMPT_GLOB      – required
  IMAGE_TAG        – required
  RUNPOD_GPU_TYPE  – optional (blank = auto pick)  [or workflow input]

Uses runpod-python 1.x
"""
import os, sys, glob, time, json, pathlib, runpod, traceback

runpod.api_key = os.environ["RUNPOD_API_KEY"]
def log(msg): print("[launcher]", msg, flush=True)

# ─── helper: choose GPU ─────────────────────────────────────────
def pick_gpu(user_choice: str | None) -> str:
    """Return a gpu_type_id slug. If user_choice is falsy, auto-select."""
    gpus = runpod.get_gpus()  # each: id, displayName, memoryInGb, podsAvailable
    # Build capacity table
    log(f"{'GPU':<26} {'VRAM':>6}  Avail")
    for g in gpus:
        log(f"{g['displayName']:<26} {g.get('memoryInGb','?'):>4}GB  {g.get('podsAvailable','?')}")
    log("-" * 46)

    if user_choice:
        # Accept either id (slug) or displayName
        for g in gpus:
            if g["id"] == user_choice or g["displayName"] == user_choice:
                return g["id"]
        sys.exit(f"[launcher] Requested GPU '{user_choice}' not found.")

    # Auto-pick: Community only, >0 podsAvailable, highest VRAM first
    eligible = [g for g in gpus
                if g.get("cloudType") == "COMMUNITY" and g.get("podsAvailable", 0) > 0]
    if not eligible:
        sys.exit("[launcher] No Community GPUs have capacity right now.")

    chosen = sorted(eligible, key=lambda g: g.get("memoryInGb", 0), reverse=True)[0]
    log(f"Auto-selected: {chosen['displayName']} ({chosen['id']})")
    return chosen["id"]

# ─── collect prompts ───────────────────────────────────────────
prompts = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()
if not prompts:
    sys.exit("[launcher] No prompts match " + os.environ["PROMPT_GLOB"])
log(f"Collected {len(prompts)} prompt lines")

# ─── build payload ─────────────────────────────────────────────
env_block = { "PROMPTS_NDJSON": "\n".join(prompts)[:48000] }
image     = (f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
             f"/spec-render:{os.environ['IMAGE_TAG']}")
gpu_slug  = pick_gpu(os.environ.get("RUNPOD_GPU_TYPE"))

payload = {
    "name":         "spec-render",
    "gpu_type_id":  gpu_slug,
    "gpu_count":    1,
    "image_name":   image,
    "cloud_type":   "COMMUNITY",
    "volume_in_gb": 20,
    "env":          env_block,
}
log("create_pod payload:\n" + json.dumps(payload, indent=2))

try:
    pod = runpod.create_pod(**payload)
except Exception as e:
    log("RunPod SDK raised:")
    traceback.print_exc()
    if hasattr(e, "response") and e.response is not None:
        log("--- raw RunPod error JSON ---\n" + e.response.text[:2000])
    sys.exit(1)

log("create_pod response:\n" + json.dumps(pod, indent=2))
pod_id = pod["id"]; log(f"Pod ID {pod_id}")

# ─── poll until finished ───────────────────────────────────────
while True:
    info = runpod.get_pod(pod_id)
    phase = info["phase"]; runtime = info.get("runtime")
    log(f"Phase {phase:<9} Runtime {runtime}")
    if phase in ("SUCCEEDED", "FAILED"):
        tail = runpod.get_pod_logs(pod_id)[-4000:]
        log("--- tail of pod logs ---\n" + tail)
        sys.exit(0 if phase == "SUCCEEDED" else 1)
    time.sleep(20)
