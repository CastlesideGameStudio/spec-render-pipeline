#!/usr/bin/env python3
"""
RunPod GPU-picker (vRAM band preference)
────────────────────────────────────────
• Accepts one env-var knob  MIN_VRAM_GB   (default 24)
• Computes                 MAX_VRAM_GB   = 2 × MIN
• Chooses a COMMUNITY GPU whose vRAM is
      MIN_VRAM_GB ≤ vRAM ≤ MAX_VRAM_GB
  preferring vRAM == MIN  (i.e. *exactly* 24 by default).

Other required env-vars (same as before):
  RUNPOD_API_KEY, PROMPT_GLOB, IMAGE_TAG
"""
from __future__ import annotations
import os, sys, glob, time, json, pathlib, traceback, runpod

# ─── utility ───────────────────────────────────────────────────
def log(msg: str) -> None:
    print("[launcher]", msg, flush=True)

def int_env(name: str, default: int) -> int:
    try:
        txt = os.getenv(name, "").strip()
        return int(txt) if txt else default
    except ValueError:
        return default

# ─── constants ────────────────────────────────────────────────
runpod.api_key = os.environ["RUNPOD_API_KEY"]
MIN_VRAM_GB    = int_env("MIN_VRAM_GB", 24)
MAX_VRAM_GB    = MIN_VRAM_GB * 2

log(f"vRAM window → {MIN_VRAM_GB} – {MAX_VRAM_GB} GB (prefers {MIN_VRAM_GB})")

# ─── pick a GPU ───────────────────────────────────────────────
def pick_gpu() -> str:
    gpus = runpod.get_gpus()             # list[dict]
    log(f"{'GPU':<27} {'vRAM':>5}  cloud")
    for g in gpus:
        log(f"{g['displayName']:<27} {g.get('memoryInGb','?'):>4}G  {g.get('cloudType','?')}")
    log("—" * 55)

    eligible = [
        g for g in gpus
        if g.get("cloudType") == "COMMUNITY"
        and MIN_VRAM_GB <= g.get("memoryInGb", 0) <= MAX_VRAM_GB
    ]
    if not eligible:
        sys.exit("[launcher] No Community GPU in requested vRAM band.")

    # 1️⃣ perfect-fit (exact minimum) wins
    exact = [g for g in eligible if g.get("memoryInGb") == MIN_VRAM_GB]
    chosen = (exact or sorted(eligible, key=lambda g: g.get("memoryInGb")))[0]

    log(f"Chosen → {chosen['displayName']}  {chosen['memoryInGb']} GB")
    return chosen["id"]

# ─── collect prompts ──────────────────────────────────────────
prompts: list[str] = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()

if not prompts:
    sys.exit("[launcher] No prompts match " + os.environ["PROMPT_GLOB"])
log(f"Collected {len(prompts)} prompt lines")

# ─── create-pod payload ───────────────────────────────────────
env_block = {"PROMPTS_NDJSON": "\n".join(prompts)[:48_000]}   # < 50 kB limit
image_ref = (
    f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
    f"/spec-render:{os.environ['IMAGE_TAG']}"
)
payload = {
    "name":         "spec-render",
    "gpu_type_id":  pick_gpu(),
    "gpu_count":    1,
    "image_name":   image_ref,
    "cloud_type":   "COMMUNITY",
    "volume_in_gb": 20,
    "env":          env_block,
}
log("create_pod payload:\n" + json.dumps(payload, indent=2))

# ─── launch pod ───────────────────────────────────────────────
try:
    pod = runpod.create_pod(**payload)
except Exception:
    log("RunPod SDK raised:")
    traceback.print_exc()
    sys.exit(1)

log("create_pod response:\n" + json.dumps(pod, indent=2))
pod_id = pod["id"]; log(f"Pod ID {pod_id}")

# ─── poll until completion ────────────────────────────────────
while True:
    info   = runpod.get_pod(pod_id)
    phase  = info["phase"]
    runtime = info.get("runtime")
    log(f"Phase {phase:<9}  Runtime {runtime}")

    if phase in ("SUCCEEDED", "FAILED"):
        tail = runpod.get_pod_logs(pod_id)[-4000:]
        log("--- tail logs ---\n" + tail)
        sys.exit(0 if phase == "SUCCEEDED" else 1)

    time.sleep(20)
