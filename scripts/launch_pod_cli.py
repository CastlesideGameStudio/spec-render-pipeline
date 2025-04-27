#!/usr/bin/env python3
"""
launch_pod_cli.py – start a RunPod A6000 pod, stream status, exit on completion
Called by GitHub Actions.  Expects:
  RUNPOD_API_KEY  – secret
  PROMPT_GLOB     – NDJSON glob (workflow_dispatch input)
  IMAGE_TAG       – GHCR image tag (workflow_dispatch input)
"""
import os, sys, glob, json, time, pathlib, requests

API = "https://api.runpod.ai/graphql"
TEMPLATE_ID = "stable-diffusion-comfyui-a6000"  # community cloud

def gq(query, variables=None):
    r = requests.post(API,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": os.environ["RUNPOD_API_KEY"]})
    r.raise_for_status()
    j = r.json()
    if "errors" in j:
        raise RuntimeError(j["errors"])
    return j["data"]

def start_pod(image, env):
    q = """mutation($in: PodInput!){ podLaunch(input:$in){ podId }}"""
    v = {"in":{
        "templateId": TEMPLATE_ID,
        "cloudType":  "COMMUNITY",
        "imageName":  image,
        "env":        env,
        "containerDiskInGb": 20
    }}
    return gq(q, v)["podLaunch"]["podId"]

def pod_status(pid):
    q = "query($id:ID!){ podDetails(podId:$id){ phase runtime exitCode }}"
    return gq(q, {"id": pid})["podDetails"]

# ───── gather prompts and launch ─────────────────────────────────
prompts = []
for path in glob.glob(os.environ["PROMPT_GLOB"], recursive=True):
    prompts += pathlib.Path(path).read_text().splitlines()
env = {"PROMPTS_NDJSON": "\n".join(prompts)[:48000]}

image = f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}/spec-render:{os.environ['IMAGE_TAG']}"
print("Launching pod with image", image)
pod_id = start_pod(image, env)
print("Pod ID:", pod_id)

while True:
    info = pod_status(pod_id)
    print("Phase:", info["phase"], " Runtime:", info.get("runtime"))
    if info["phase"] in ("SUCCEEDED", "FAILED"):
        sys.exit(0 if info["phase"] == "SUCCEEDED" else 1)
    time.sleep(20)
