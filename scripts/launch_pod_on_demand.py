#!/usr/bin/env python3
"""
Create an On-Demand RunPod (COMMUNITY) pod and stream logs.

env
  RUNPOD_API_KEY   (required)
  IMAGE_NAME       valyriantech/comfyui-with-flux:latest
  GPU_TYPE         NVIDIA A40 (default)
  VOLUME_GB        120 (default; plenty for Flux copy)
  PROMPT_GLOB      addendums/**/*.ndjson (default)
  AWS_*            forwarded to container
"""

import glob, os, pathlib, sys, time, requests, json

API = "https://rest.runpod.io/v1/pods"


def image_tag() -> str:
    if (name := os.getenv("IMAGE_NAME")): return name
    sys.exit("[ERROR] IMAGE_NAME must be set (use the Flux tag).")


def prompts(glob_pat: str) -> str:
    lines = [ln for p in glob.glob(glob_pat, recursive=True)
                 for ln in pathlib.Path(p).read_text().splitlines() if ln.strip()]
    if not lines:
        sys.exit(f"[ERROR] No prompts matched '{glob_pat}'.")
    return "\n".join(lines)


def main() -> None:
    key = os.getenv("RUNPOD_API_KEY") or sys.exit("[ERROR] RUNPOD_API_KEY missing.")
    hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    gpu   = os.getenv("GPU_TYPE", "NVIDIA A40")
    disk  = int(os.getenv("VOLUME_GB", "120"))
    image = image_tag()

    payload = {
        "name": "spec-render-batch",
        "cloudType": "COMMUNITY",         # ← community template
        "gpuTypeIds": [gpu],
        "gpuCount": 1,
        "volumeInGb": disk,
        "containerDiskInGb": disk,
        "imageName": image,
        "env": {
            "PROMPTS_NDJSON": prompts(os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")),
            "AWS_ACCESS_KEY_ID":     os.getenv("AWS_ACCESS_KEY_ID", ""),
            "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            "AWS_DEFAULT_REGION":    os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        },
        "startCommand": (
            "/bin/bash -c "
            "curl -fsSL "
            "https://raw.githubusercontent.com/CastlesideGameStudio/"
            "spec-render-pipeline/main/scripts/entrypoint.sh "
            "-o /tmp/entrypoint.sh && "
            "chmod +x /tmp/entrypoint.sh && /tmp/entrypoint.sh"
        ),
    }

    print("[INFO] Requesting pod …")
    r = requests.post(API, json=payload, headers=hdr, timeout=60)
    if not r.ok:
        sys.exit(f"[ERROR] create failed HTTP {r.status_code}\n{r.text}")

    body = r.json()
    if "id" not in body:
        sys.exit(f"[ERROR] create failed\n{json.dumps(body, indent=2)}")
    pod_id = body["id"]
    print("[INFO] Pod ID:", pod_id)

    last = ""
    while True:
        time.sleep(10)
        logs = requests.get(f"{API}/{pod_id}/logs", headers=hdr, timeout=30).text
        if logs != last:
            print(logs[len(last):], end="", flush=True)
            last = logs
        status = requests.get(f"{API}/{pod_id}", headers=hdr, timeout=30).json().get("status")
        if status not in ("Pending", "Running"):
            print(f"\n[INFO] Pod status = {status}")
            break

    print("[INFO] Done streaming logs.")


if __name__ == "__main__":
    main()
