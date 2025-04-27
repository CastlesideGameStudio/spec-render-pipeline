#!/usr/bin/env python3
"""
RunPod launcher for GitHub Actions
──────────────────────────────────
• Chooses a Community GPU that satisfies *minimum* constraints
  instead of hard-coding a specific type.
• Prints:
    – the min-constraint values in effect
    – the full Community-GPU catalog (VRAM, price, free pods)
    – the GPU it finally selects
    – the create-pod payload and full RunPod responses
    – live phase updates and the tail of pod logs

Environment variables
─────────────────────
(required)  RUNPOD_API_KEY      – repo secret
(required)  PROMPT_GLOB         – NDJSON glob (e.g. addendums/**/*.ndjson)
(required)  IMAGE_TAG           – GHCR tag (commit SHA or 'latest')
(optional)  MIN_VRAM_GB         – default 24
(optional)  MIN_GPU_COUNT       – default 1
(optional)  MAX_PRICE_PER_HR    – default 15.0 (USD)
"""
from __future__ import annotations
import os, sys, glob, time, json, pathlib, traceback, runpod

# ── helpers ──────────────────────────────────────────────────────
def log(msg: str) -> None:
    print("[launcher]", msg, flush=True)

def _as_int(s: str | None, default: int) -> int:
    try:
        return int(s) if s not in (None, "", "null") else default
    except ValueError:
        return default

def _as_float(s: str | None, default: float) -> float:
    try:
        return float(s) if s not in (None, "", "null") else default
    except ValueError:
        return default

# ── user-tunable minima (robust parsing) ─────────────────────────
MIN_VRAM_GB     = _as_int  (os.getenv("MIN_VRAM_GB"),        24)
MIN_GPU_COUNT   = _as_int  (os.getenv("MIN_GPU_COUNT"),       1)
MAX_PRICE       = _as_float(os.getenv("MAX_PRICE_PER_HR"),  15.0)

runpod.api_key = os.environ["RUNPOD_API_KEY"]

# ── echo the constraints up front ───────────────────────────────
log(
    f"Min-constraints →  vRAM ≥ {MIN_VRAM_GB} GB,  "
    f"GPUs ≥ {MIN_GPU_COUNT},  price ≤ ${MAX_PRICE}/hr"
)

# ── GPU chooser ─────────────────────────────────────────────────
def pick_gpu() -> str:
    gpus = runpod.get_gpus()      # list[dict]
    log(f"{'GPU':<27} {'VRAMGB':>6}  Avail  $/hr")
    for g in gpus:
        log(f"{g['displayName']:<27} {g.get('memoryInGb','?'):>6}  "
            f"{g.get('podsAvailable','?'):>5}  {g.get('usdPerHr','?')}")
    log("—" * 60)

    eligible = [
        g for g in gpus
        if g.get("cloudType")           == "COMMUNITY"
        and g.get("podsAvailable", 0)   >= MIN_GPU_COUNT
        and g.get("memoryInGb",   0)    >= MIN_VRAM_GB
        and g.get("usdPerHr",     MAX_PRICE + 1) <= MAX_PRICE
    ]
    if not eligible:
        sys.exit(
            "[launcher] No Community GPU meets the minima: "
            f"{MIN_GPU_COUNT} pod(s) • ≥{MIN_VRAM_GB} GB • ≤${MAX_PRICE}/hr"
        )

    # Prefer more VRAM, then lower cost
    chosen = sorted(
        eligible,
        key=lambda g: (g.get("memoryInGb", 0), -g.get("usdPerHr", 0.0)),
        reverse=True
    )[0]

    log(
        f"Chosen → {chosen['displayName']}  {chosen['memoryInGb']} GB  "
        f"${chosen['usdPerHr']}/hr  free-pods:{chosen['podsAvailable']}"
    )
    return chosen["id"]

# ── gather prompts ──────────────────────────────────────────────
prompts: list[str] = []
for path in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(path).read_text().splitlines()

if not prompts:
    sys.exit("[launcher] No prompts match " + os.environ["PROMPT_GLOB"])

log(f"Collected {len(prompts)} prompt lines")

# ── build create-pod payload ────────────────────────────────────
env_block = {"PROMPTS_NDJSON": "\n".join(prompts)[:48_000]}   # API limit ~50 kB
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

# ── launch pod ──────────────────────────────────────────────────
try:
    pod = runpod.create_pod(**payload)
except Exception as e:
    log("RunPod SDK raised:")
    traceback.print_exc()
    if hasattr(e, "response") and e.response is not None:
        log("--- raw RunPod error JSON ---\n" + e.response.text[:2000])
    sys.exit(1)

log("create_pod response:\n" + json.dumps(pod, indent=2))
pod_id = pod["id"]
log(f"Pod ID {pod_id}")

# ── poll until finished ─────────────────────────────────────────
while True:
    info   = runpod.get_pod(pod_id)
    phase  = info["phase"]
    runtime = info.get("runtime")
    log(f"Phase {phase:<9}  Runtime {runtime}")

    if phase in ("SUCCEEDED", "FAILED"):
        logs_tail = runpod.get_pod_logs(pod_id)[-4000:]
        log("--- tail of pod logs ---\n" + logs_tail)
        sys.exit(0 if phase == "SUCCEEDED" else 1)

    time.sleep(20)
