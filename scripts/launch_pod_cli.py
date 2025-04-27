#!/usr/bin/env python3
"""
launch_pod_cli.py – launch a raw A6000 Community pod with your GHCR image,
stream status, exit with pod result.  Called by GitHub Actions.

Needs env vars:
  RUNPOD_API_KEY  – repo secret
  PROMPT_GLOB     – NDJSON glob from workflow_dispatch
  IMAGE_TAG       – GHCR image tag (SHA or 'latest')
"""
import os, sys, glob, time, json, random, pathlib, requests

API = "https://api.runpod.io/graphql"
MAX_RUNTIME_MIN = 60

def log(msg): print("[launcher]", msg, flush=True)

# ───────── GraphQL helper with retries + verbose errors ───────────
def gq(query, variables=None, tries=5):
    payload = {"query": query, "variables": variables or {}}
    headers = {"Authorization": os.environ["RUNPOD_API_KEY"]}

    for attempt in range(tries):
        r = requests.post(API, json=payload, headers=headers)

        if r.status_code in (429, 502, 503, 504):
            wait = 2 ** attempt + random.random()
            log(f"RunPod {r.status_code} – retry {attempt+1}/{tries} in {wait:.1f}s")
            time.sleep(wait)
            continue

        if not r.ok:
            log(f"HTTP {r.status_code} response:\n{r.text[:1000]}")
            r.raise_for_status()

        data = r.json()
        if "errors" in data and data["errors"]:
            log("API errors:\n" + json.dumps(data["errors"], indent=2))
            raise RuntimeError("RunPod GraphQL returned errors")

        return data["data"]

    raise RuntimeError(f"RunPod API still failing after {tries} retries")

# ───────── payload builders ───────────────────────────────────────
 def start_pod(image, env_dict):
     env_array = [{"key": k, "value": v} for k, v in env_dict.items()]
     q = "mutation($in:PodInput!){ podLaunch(input:$in){ podId } }"
     v = {"in": {
         "name":       "spec-render",
         "cloudType":  "COMMUNITY",
         "gpuTypeId":  "NVIDIA_A6000",
         "gpuCount":   1,
         "imageName":  image,
         "env":        env_array,
-        "containerDiskInGb": 20,   # ← delete this line
         "volumeInGb": 20
     }}
     return gq(q, v)["podLaunch"]["podId"]

def pod_status(pid):
    q = "query($id:ID!){ podDetails(podId:$id){ phase runtime exitCode } }"
    return gq(q, {"id": pid})["podDetails"]

def pod_logs(pid):
    q = "query($id:ID!){ podLogs(podId:$id) }"
    return gq(q, {"id": pid})["podLogs"]

# ───────── gather prompts & launch ────────────────────────────────
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
        log(pod_logs(pod_id)[-4000:])
        sys.exit(0 if phase == "SUCCEEDED" else 1)

    if time.time() - start > MAX_RUNTIME_MIN * 60:
        log(f"Timeout > {MAX_RUNTIME_MIN} min – failing job")
        sys.exit(1)

    time.sleep(20)
