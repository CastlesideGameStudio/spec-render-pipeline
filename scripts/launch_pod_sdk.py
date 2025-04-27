#!/usr/bin/env python3
"""
RunPod launcher – pick a Community GPU by vRAM only (no availability field
required).  Min/max are expressed as environment variables:

  MIN_VRAM_GB      default 24   ← required vRAM
  MAX_PRICE_PER_HR default none ← ignore if blank

Other required env vars come from the GitHub Actions workflow:
  RUNPOD_API_KEY, PROMPT_GLOB, IMAGE_TAG
"""
import os, sys, glob, time, json, pathlib, traceback, runpod
runpod.api_key = os.environ["RUNPOD_API_KEY"]

# ────────── user limits ──────────
MIN_VRAM_GB = int(os.getenv("MIN_VRAM_GB", 24))
MAX_VRAM_GB = MIN_VRAM_GB * 2                  # “at most 2× the min”
MAX_PRICE   = os.getenv("MAX_PRICE_PER_HR")    # blank → ignore price
MAX_PRICE   = float(MAX_PRICE) if MAX_PRICE else None

def log(msg): print("[launcher]", msg, flush=True)
log(f"vRAM window → {MIN_VRAM_GB} – {MAX_VRAM_GB} GB (prefers {MIN_VRAM_GB})")

# ────────── prompt bundle ─────────
prompts = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()
if not prompts:
    sys.exit("[launcher] No prompts match " + os.environ["PROMPT_GLOB"])
log(f"Collected {len(prompts)} prompt lines")

env_block = {"PROMPTS_NDJSON": "\n".join(prompts)[:48_000]}
image_ref = (f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
             f"/spec-render:{os.environ['IMAGE_TAG']}")

# ────────── GPU catalogue ─────────
gpus = runpod.get_gpus()   # list of dicts
log(f"{'GPU':<28} {'vRAM':>5}  $/hr")
for g in gpus:
    log(f"{g['displayName']:<28} "
        f"{g.get('memoryInGb','?'):>4}G  {g.get('usdPerHr','?')}")

log("—" * 60)

def eligible(g):
    vram = g.get("memoryInGb", 0)
    if not (MIN_VRAM_GB <= vram <= MAX_VRAM_GB):
        return False
    if MAX_PRICE is not None and g.get("usdPerHr") and g["usdPerHr"] > MAX_PRICE:
        return False
    # if RunPod ever omits price, treat as “OK”
    return True

candidates = [g for g in gpus if eligible(g)]
if not candidates:
    sys.exit("[launcher] No GPU satisfies the vRAM (and optional price) limits.")

# pick the card closest to MIN_VRAM_GB, then cheaper price if tie
best = sorted(candidates,
              key=lambda g: (abs(g["memoryInGb"] - MIN_VRAM_GB),
                             g.get("usdPerHr", 0)))[0]

log(f"Chosen → {best['displayName']}  {best['memoryInGb']} GB  "
    f"${best.get('usdPerHr','?')}/hr")

# ────────── launch pod ────────────
payload = {
    "name"        : "spec-render",
    "gpu_type_id" : best["id"],
    "gpu_count"   : 1,
    "image_name"  : image_ref,
    "cloud_type"  : "COMMUNITY",
    "volume_in_gb": 20,
    "env"         : env_block,
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

# ────────── tail until done ───────
while True:
    info = runpod.get_pod(pod_id)
    log(f"Phase {info['phase']:<9}  Runtime {info.get('runtime')}")
    if info["phase"] in ("SUCCEEDED", "FAILED"):
        log("--- tail pod logs ---\n" + runpod.get_pod_logs(pod_id)[-4000:])
        sys.exit(0 if info["phase"] == "SUCCEEDED" else 1)
    time.sleep(20)
