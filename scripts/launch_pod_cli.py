#!/usr/bin/env python3
"""
launch_pod_cli.py
────────────────────────────────────────────────────────────────────
 * Starts a RunPod Community-Cloud GPU pod with your GHCR image
 * Streams phase updates until the pod finishes
 * Exits 0 = SUCCEEDED, 1 = FAILED / timeout / API error

ENV VARS injected by GitHub Actions
───────────────────────────────────
RUNPOD_API_KEY   – required – repo secret
PROMPT_GLOB      – required – NDJSON glob from workflow_dispatch
IMAGE_TAG        – required – ghcr.io tag from workflow_dispatch
RUNPOD_GPU_TYPE  – optional – gpuTypeId string, default NVIDIA_RTX4090
"""
import os, sys, glob, time, json, random, pathlib, requests

# ───────── configurable constants ─────────
API             = "https://api.runpod.io/graphql"
GPU_TYPE_ID     = os.environ.get("RUNPOD_GPU_TYPE", "NVIDIA_RTX4090")
MAX_RUNTIME_MIN = 60                                  # fail-safe

def log(msg: str) -> None:
    print("[launcher]", msg, flush=True)

# ───────── GraphQL helper ─────────
def gq(query: str, variables=None, tries: int = 5):
    payload = {"query": query, "variables": variables or {}}
    headers = {"Authorization": os.environ["RUNPOD_API_KEY"]}

    for attempt in range(tries):
        r = requests.post(API, json=payload, headers=headers)

        if r.status_code in (429, 502, 503, 504):
            wait = 2 ** attempt + random.random()
            log(f"RunPod {r.status_code} – retry {attempt+1}/{tries} in {wait:.1f}s")
            time.sleep(wait)
            continue

        if not r.ok:                                      # 4xx
            log(f"HTTP {r.status_code} response:\n{r.text[:1000]}")
            r.raise_for_status()

        data = r.json()
        if data.get("errors"):
            log("API errors:\n" + json.dumps(data["errors"], indent=2))
            raise RuntimeError("RunPod GraphQL errors")

        return data["data"]

    raise RuntimeError("RunPod API still failing after retries")

# ───────── payload builders ─────────
def start_pod(image: str, env_dict: dict) -> str:
    env_array = [{"key": k, "value": v} for k, v in env_dict.items()]
    pod_input = {
        "name":       "spec-render",
        "cloudType":  "COMMUNITY",
        "gpuTypeId":  GPU_TYPE_ID,
        "gpuCount":   1,
        "imageName":  image,
        "env":        env_array,
        "volumeInGb": 20
    }
    q = "mutation($in: PodInput!){ podLaunch(input:$in){ podId } }"
    return gq(q, {"in": pod_input})["podLaunch"]["podId"]

def pod_status(pid: str) -> dict:
    q = "query($id:ID!){ podDetails(podId:$id){ phase runtime exitCode } }"
    return gq(q, {"id": pid})["podDetails"]

def pod_logs(pid: str) -> str:
    q = "query($id:ID!){ podLogs(podId:$id) }"
    return gq(q, {"id": pid})["podLogs"]

# ───────── gather prompts & launch ─────────
prompts: list[str] = []
for p in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(p).read_text().splitlines()

if not prompts:
    sys.exit("No prompts match " + os.environ["PROMPT_GLOB"])

env_block = {"PROMPTS_NDJSON": "\n".join(prompts)[:48000]}
image_ref = (
    f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
    f"/spec-render:{os.environ['IMAGE_TAG']}"
)

log(f"GPU type  {GPU_TYPE_ID}")
log(f"Launching pod with image {image_ref}")
pod_id = start_pod(image_ref, env_block)
log(f"Pod ID {pod_id}")

start = time.time()
while True:
    info = pod_status(pod_id)
    log(f"Phase {info['phase']:<9}  Runtime {info.get('runtime')}")
    if info["phase"] in ("SUCCEEDED", "FAILED"):
        log("--- tail of pod logs ---")
        log(pod_logs(pod_id)[-4000:])
        sys.exit(0 if info["phase"] == "SUCCEEDED" else 1)

    if time.time() - start > MAX_RUNTIME_MIN * 60:
        log(f"Timeout > {MAX_RUNTIME_MIN} min – failing job")
        sys.exit(1)

    time.sleep(20)
