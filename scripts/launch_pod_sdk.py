#!/usr/bin/env python3
"""
RunPod launcher for GitHub Actions
──────────────────────────────────
ENV (supplied by the workflow):
  RUNPOD_API_KEY    – required
  PROMPT_GLOB       – required
  IMAGE_TAG         – required
  MIN_VRAM_GB       – optional, default 24
  MAX_PRICE_PER_HR  – optional, blank = ignore
"""
import os, sys, glob, time, json, pathlib, traceback, runpod
runpod.api_key = os.environ["RUNPOD_API_KEY"]

MIN_VRAM_GB = int(os.getenv("MIN_VRAM_GB", 24))
MAX_VRAM_GB = MIN_VRAM_GB * 2
MAX_PRICE   = os.getenv("MAX_PRICE_PER_HR")
MAX_PRICE   = float(MAX_PRICE) if MAX_PRICE else None

def log(msg): print("[launcher]", msg, flush=True)

# ─── gather prompts ────────────────────────────────────────────
prompts = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()
if not prompts:
    sys.exit("[launcher] No prompts match " + os.environ["PROMPT_GLOB"])
log(f"Collected {len(prompts)} prompt lines")

env_block = {"PROMPTS_NDJSON": "\n".join(prompts)[:48_000]}
image_ref = (f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
             f"/spec-render:{os.environ['IMAGE_TAG']}")

# ─── GPU catalogue ─────────────────────────────────────────────
all_gpus = runpod.get_gpus()          # [{id,displayName,memoryInGb,…},…]
log(f"vRAM window → {MIN_VRAM_GB} – {MAX_VRAM_GB} GB (prefers {MIN_VRAM_GB})")
log(f"{'GPU':<28} {'vRAM':>5}  $/hr")

def meets_window(g):
    vr = g.get("memoryInGb", 0)
    if not (MIN_VRAM_GB <= vr <= MAX_VRAM_GB):
        return False
    if MAX_PRICE and g.get("usdPerHr") and g["usdPerHr"] > MAX_PRICE:
        return False
    return True

candidates = []
for g in all_gpus:
    log(f"{g['displayName']:<28} {g.get('memoryInGb','?'):>4}G  {g.get('usdPerHr','?')}")
    if meets_window(g):
        candidates.append(g)

if not candidates:
    sys.exit("[launcher] No GPU in requested vRAM / price band")

# prefer vRAM closest to MIN_VRAM_GB then cheaper
candidates.sort(key=lambda g: (abs(g["memoryInGb"] - MIN_VRAM_GB),
                               g.get("usdPerHr", 0)))

tried = []
for g in candidates:
    log("—" * 60)
    log(f"Trying → {g['displayName']}  {g['memoryInGb']} GB "
        f"@ ${g.get('usdPerHr','?')}/hr")
    payload = {
        "name"        : "spec-render",
        "gpu_type_id" : g["id"],
        "gpu_count"   : 1,
        "image_name"  : image_ref,
        "cloud_type"  : "COMMUNITY",
        "volume_in_gb": 20,
        "env"         : env_block,
    }
    log("create_pod payload:\n" + json.dumps(payload, indent=2))
    try:
        pod = runpod.create_pod(**payload)
        log("create_pod response:\n" + json.dumps(pod, indent=2))
        pod_id = pod["id"]; log(f"Pod ID {pod_id}")
        break                                   # ⬅ success, leave the loop
    except Exception as e:
        log("create_pod FAILED – will try next GPU")
        traceback.print_exc()
        tried.append(g["displayName"])
else:
    sys.exit("[launcher] All eligible GPUs failed to launch: "
             + ", ".join(tried))

# ─── tail until done ───────────────────────────────────────────
while True:
    info = runpod.get_pod(pod_id)
    log(f"Phase {info['phase']:<9}  Runtime {info.get('runtime')}")
    if info["phase"] in ("SUCCEEDED", "FAILED"):
        log("--- tail pod logs ---\n" + runpod.get_pod_logs(pod_id)[-4000:])
        sys.exit(0 if info["phase"] == "SUCCEEDED" else 1)
    time.sleep(20)
