#!/usr/bin/env python3
"""
launch_pod_on_demand.py – spin up one On-Demand RunPod instance and stream logs.

env ──────────────────────────────────────────────────────────────────────────
  RUNPOD_API_KEY   (required)

  IMAGE_NAME       public tag, e.g. valyriantech/comfyui-with-flux:latest
  IMAGE_DIGEST     sha256… (legacy fallback if IMAGE_NAME absent)
  PROMPT_GLOB      NDJSON pattern        [addendums/**/*.ndjson]
  GPU_TYPE         GPU model             [NVIDIA A40]
  VOLUME_GB        disk size in GB       [120]   ← big enough for Flux copy
  CONTAINER_AUTH_ID registry-auth ID     (optional)
  AWS_*            forwarded unchanged to the container
"""

import glob, os, pathlib, sys, time, requests

API = "https://rest.runpod.io/v1/pods"

# ───────── helpers ──────────────────────────────────────────────────────────
def image_ref() -> str:
    if name := os.getenv("IMAGE_NAME"):
        return name
    if not (digest := os.getenv("IMAGE_DIGEST")):
        sys.exit("[ERROR] IMAGE_NAME or IMAGE_DIGEST must be set.")
    repo = os.getenv("GITHUB_REPOSITORY", "").lower()
    return f"ghcr.io/{repo}@{digest}"

def gather(pattern: str) -> str:
    lines = [ln for p in glob.glob(pattern, recursive=True)
                 for ln in pathlib.Path(p).read_text().splitlines() if ln.strip()]
    if not lines:
        sys.exit(f"[ERROR] No prompts matched '{pattern}'.")
    return "\n".join(lines)

# ───────── main ─────────────────────────────────────────────────────────────
def main() -> None:
    key = os.getenv("RUNPOD_API_KEY") or sys.exit("[ERROR] RUNPOD_API_KEY missing.")
    hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    gpu   = os.getenv("GPU_TYPE",  "NVIDIA A40")
    disk  = int(os.getenv("VOLUME_GB", "120"))
    image = image_ref()
    auth  = os.getenv("CONTAINER_AUTH_ID")

    payload = {
        "name":              "spec-render-on-demand",
        "cloudType":         "SECURE",
        "gpuTypeIds":        [gpu],
        "gpuCount":          1,
        "volumeInGb":        disk,
        "containerDiskInGb": disk,
        "imageName":         image,
        "env": {
            "PROMPTS_NDJSON": gather(os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")),
            "AWS_ACCESS_KEY_ID":     os.getenv("AWS_ACCESS_KEY_ID", ""),
            "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            "AWS_DEFAULT_REGION":    os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        },
        # download & run your entrypoint inside the pod ────────────────
        "command": [
            "/bin/bash","-c",
            "curl -fsSL "
            "https://raw.githubusercontent.com/CastlesideGameStudio/"
            "spec-render-pipeline/main/scripts/entrypoint.sh "
            "-o /tmp/entrypoint.sh && "
            "chmod +x /tmp/entrypoint.sh && "
            "/tmp/entrypoint.sh"
        ],
    }
    if auth:
        payload["containerRegistryAuthId"] = auth

    print(f"[INFO] Creating pod → GPU={gpu}  disk={disk}GB  image={image}")
    pod_id = requests.post(API, json=payload, headers=hdr, timeout=60).json().get("id") \
             or sys.exit("[ERROR] No pod ID returned.")
    print("[INFO] Pod ID:", pod_id)

    last = ""
    while True:
        time.sleep(10)
        log = requests.get(f"{API}/{pod_id}/logs", headers=hdr, timeout=30).text
        if log != last:
            print(log[len(last):], end="", flush=True)
            last = log
        status = requests.get(f"{API}/{pod_id}", headers=hdr, timeout=30).json().get("status")
        if status not in ("Pending", "Running"):
            print(f"\n[INFO] Pod status = {status}")
            break

    print("[INFO] Log stream finished.")

if __name__ == "__main__":
    main()
