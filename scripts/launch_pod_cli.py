#!/usr/bin/env python3
"""
launch_pod_cli.py – start a RunPod A6000 pod, stream status, exit on completion.

Called by GitHub Actions.  Expects env vars:
  RUNPOD_API_KEY  – repo secret
  PROMPT_GLOB     – NDJSON glob from workflow_dispatch
  IMAGE_TAG       – GHCR image tag from workflow_dispatch
"""
import os, sys, glob, json, time, pathlib, requests, textwrap, random

API = "https://api.runpod.io/graphql"          # <- fixed .io endpoint
TEMPLATE_ID = "stable-diffusion-comfyui-a6000" # Community Cloud template
MAX_RUNTIME_MIN = 60                           # hard fail-safe

def log(msg): print("[launcher]", msg, flush=True)

# ───────────────────── helpers ──────────────────────
def gq(query, variables=None, tries=5):
    """GraphQL with exponential-backoff retry on 5xx/429."""
    for attempt in range(tries):
        r = requests.post(API,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": os.environ["RUNPOD_API_KEY"]})
        if r.status_code in (502, 503, 504, 429):
            wait = 2 ** attempt + random.random()
            log(f"RunPod API {r.status_code} – retrying in {wait:.1f}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise RuntimeError(data["errors"])
        return data["data"]
    raise RuntimeError(f"RunPod API still failing after {tries} tries")

def start_pod(image, env):
    q = "mutation($in:PodInput!){ podLaunch(input:$in){ podId } }"
    v = {"in":{
        "templateId": TEMPLATE_ID,
        "cloudType":  "COMMUNITY",
        "imageName":  image,
        "env":        env,
        "containerDiskInGb": 20
    }}
    return gq(q, v)["podLaunch"]["podId"]

def pod_status(pid):
    q = "query($id:ID!){ podDetails(podId:$id){ phase runtime exitCode } }"
    return gq(q, {"id": pid})["podDetails"]

def pod_logs(pid):
    q = "query($id:ID!){ podLogs(podId:$id) }"
    return gq(q, {"id": pid})["podLogs"]

# ───────────────────── main ─────────────────────────
prompts = []
for path in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(path).read_text().splitlines()

if not prompts:
    sys.exit(f"No prompts match glob: {os.environ['PROMPT_GLOB']}")

env_block = {"PROMPTS_NDJSON": "\n".join(prompts)[:48000]}
image_ref = f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}/spec-render:{os.environ['IMAGE_TAG']}"

log(f"Launching pod with image  {image_ref}")
pod_id = start_pod(image_ref, env_block)
log(f"Pod ID  {pod_id}")

start_time = time.time()
while True:
    info = pod_status(pod_id)
    phase = info["phase"]
    runtime = info.get("runtime")
    log(f"Phase {phase:<9}  Runtime {runtime}")

    if phase in ("SUCCEEDED", "FAILED"):
        log("--- tail of pod logs ---")
        log(pod_logs(pod_id)[-4000:])          # last few kB to keep log short
        sys.exit(0 if phase == "SUCCEEDED" else 1)

    if (time.time() - start_time) > MAX_RUNTIME_MIN * 60:
        log(f"Timeout > {MAX_RUNTIME_MIN} min – failing job")
        sys.exit(1)

    time.sleep(20)
