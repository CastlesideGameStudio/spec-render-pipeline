#!/usr/bin/env python3
"""
RunPod launcher for GitHub Actions
──────────────────────────────────
• NEVER “hard-codes” a GPU type.
• Lets you express *minimum* requirements instead:

   MIN_VRAM_GB      – integer (default 24)
   MIN_GPU_COUNT    – integer (default 1)        ← usually leave 1
   MAX_PRICE_PER_HR – float   (USD, optional)    ← skip to ignore price

If *no* Community GPU satisfies every min-constraint + has free pods,
the job exits with code 1 and prints the full catalog.

Env vars required by the workflow:
  RUNPOD_API_KEY   – repo secret
  PROMPT_GLOB      – NDJSON glob (addendums/**/*.ndjson)
  IMAGE_TAG        – ghcr tag (sha or latest)
  MIN_VRAM_GB      – optional, see above
  MIN_GPU_COUNT    – optional
  MAX_PRICE_PER_HR – optional
"""
import os, sys, glob, time, json, pathlib, traceback, runpod

runpod.api_key  = os.environ["RUNPOD_API_KEY"]
MIN_VRAM_GB     = int(os.getenv("MIN_VRAM_GB", 24))
MIN_GPU_COUNT   = int(os.getenv("MIN_GPU_COUNT", 1))
# ----- price ceiling  -------------------------------------------------
MAX_PRICE = float(os.getenv("MAX_PRICE_PER_HR", "15"))      # default $15/hr

def log(msg: str) -> None: print("[launcher]", msg, flush=True)

# ─── GPU chooser ────────────────────────────────────────────────
def pick_gpu() -> str:
    gpus = runpod.get_gpus()               # list[dict]
    log(f"{'GPU':<27} {'VRAM':>5}  Avail  $/hr")
    for g in gpus:
        log(f"{g['displayName']:<27} {g.get('memoryInGb','?'):>4}G "
            f" {g.get('podsAvailable','?'):>5}  {g.get('usdPerHr','?')}")
    log("-" * 60)

    eligible = [
        g for g in gpus
        if g.get("cloudType")     == "COMMUNITY"
        and g.get("podsAvailable", 0)       >= MIN_GPU_COUNT
        and g.get("memoryInGb",    0)       >= MIN_VRAM_GB
        and g.get("usdPerHr",      MAX_PRICE+1) <= MAX_PRICE
    ]
    if not eligible:
        sys.exit("[launcher] No Community GPU meets the minima: "
                 f"{MIN_GPU_COUNT} pod(s) ≥{MIN_VRAM_GB} GB and ≤${MAX_PRICE}/hr")

    # highest VRAM first, then cheapest
    chosen = sorted(
        eligible,
        key=lambda g: (g.get("memoryInGb", 0), -g.get("usdPerHr", 0.0)),
        reverse=True
    )[0]
    log(f"Chosen → {chosen['displayName']}  "
        f"{chosen['memoryInGb']} GB  ${chosen['usdPerHr']}/hr  "
        f"free-pods:{chosen['podsAvailable']}")
    return chosen["id"]

# ─── collect prompts ────────────────────────────────────────────
prompts: list[str] = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()
if not prompts:
    sys.exit("[launcher] No prompts match " + os.environ["PROMPT_GLOB"])
log(f"Collected {len(prompts)} prompt lines")

# ─── build payload ──────────────────────────────────────────────
env_block = { "PROMPTS_NDJSON": "\n".join(prompts)[:48_000] }   # RunPod limit 50 kB
image_ref = (f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
             f"/spec-render:{os.environ['IMAGE_TAG']}")
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

# ─── poll until finished ────────────────────────────────────────
while True:
    info = runpod.get_pod(pod_id)
    phase = info["phase"]; runtime = info.get("runtime")
    log(f"Phase {phase:<9}  Runtime {runtime}")
    if phase in ("SUCCEEDED", "FAILED"):
        log("--- tail logs ---\n" + runpod.get_pod_logs(pod_id)[-4000:])
        sys.exit(0 if phase == "SUCCEEDED" else 1)
    time.sleep(20)
