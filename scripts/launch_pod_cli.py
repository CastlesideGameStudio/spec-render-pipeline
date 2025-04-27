#!/usr/bin/env python3
"""
launch_pod_cli.py – start a RunPod A6000 pod, stream status, exit on completion.

Called by GitHub Actions. Expects env vars:
  RUNPOD_API_KEY  – repo secret
  PROMPT_GLOB     – NDJSON glob from workflow_dispatch
  IMAGE_TAG       – GHCR image tag from workflow_dispatch
"""
import os, sys, glob, time, json, random, pathlib, requests

API = "https://api.runpod.io/graphql"          # correct endpoint
TEMPLATE_ID = "stable-diffusion-comfyui-a6000" # Community Cloud template
MAX_RUNTIME_MIN = 60                           # hard fail-safe

def log(msg): print("[launcher]", msg, flush=True)

# ───────────────────── helpers ──────────────────────
def gq(query, variables=None, tries=5):
    """GraphQL call with retry and verbose error echo."""
    payload = {"query": query, "variables": variables or {}}
    headers = {"Authorization": os.environ["RUNPOD_API_KEY"]}

    for attempt in range(tries):
        r = requests.post(API, json=payload, headers=headers)

        # Retry on transient gateway / rate-limit errors
        if r.status_code in (429, 502, 503, 504):
            wait = 2 ** attempt + random.random()
            log(f"RunPod {r.status_code} – retry #{attempt+1} in {wait:.1f}s")
            time.sleep(wait)
            continue

        if not r.ok:                   # Any other HTTP error
            log(f"HTTP {r.status_code} response:")
            log(r.text.strip()[:1000]) # print up to 1 KB
            r.raise_for_status()

        data = r.json()
        if "errors" in data and data["errors"]:
            # GraphQL-level error – print and bail
            log("API errors:\n" + json.dumps(data["errors"], indent=2))
            raise RuntimeError("RunPod GraphQL returned errors")

        return data["data"]

    raise RuntimeError(f"RunPod API still failing after {tries} retries")

def start_pod(image, env):
    q = "mutation($in:PodInput!){ podLaunch(input:$in){ podId } }"
    v = {"in": {
        "templateId": TEMPLATE_ID,
        "cloudType":  "COMMUNITY",
        "imageName":  image,           # remove this line if your template forbids overrides
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
image_ref  = f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}/spec-render:{os.environ['IMAGE_TAG']}"

log(f"Launching pod with image {image_ref}")
pod_id = start_pod(image_ref, env_block)
log(f"Pod ID {pod_id}")

start = time.time()
while True:
    info   = pod_status(pod_id)
    phase  = info["phase"]
    runsec = info.get("runtime")
    log(f"Phase {phase:<9}  Runtime {runsec}")

    if phase in ("SUCCEEDED", "FAILED"):
        log("--- tail of pod logs ---")
        log(pod_logs(pod_id)[-4000:])        # last few KB
        sys.exit(0 if phase == "SUCCEEDED" else 1)

    if time.time() - start > MAX_RUNTIME_MIN * 60:
        log(f"Timeout > {MAX_RUNTIME_MIN} min – failing job")
        sys.exit(1)

    time.sleep(20)
