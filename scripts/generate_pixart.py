#!/usr/bin/env python3
"""
Generate 3×1 orthographic sprite-sheets with PixArt-α XL.

Local  → outputs/<RUN_ID>/<Style>/sheet/<stem>.png
Remote → castlesidegamestudio-spec-sheets/<YYYYMMDD>/sprites_<RUN_ID>.zip
A README.txt is uploaded at <YYYYMMDD>/ to prove the prefix is writable.
"""

from __future__ import annotations
# ───────────────────── Determinism before heavy imports ────────────────────
import os as _os
_os.environ.setdefault("TRANSFORMERS_NO_GGML", "1")
_os.environ.setdefault("TRANSFORMERS_NO_TF",  "1")
_os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
_os.environ.setdefault("PYTHONHASHSEED", "0")

# ───────────────────────── Std-lib / third-party ───────────────────────────
import glob, json, os, random, subprocess, sys, time, tempfile, shutil, hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import torch
torch.use_deterministic_algorithms(True, warn_only=False)

from PIL import Image                          # noqa: F401
from diffusers import DiffusionPipeline

# ==== 0) Run identifiers ===================================================
UTC_NOW  = datetime.now(timezone.utc)
DATE_STR = UTC_NOW.strftime("%Y%m%d")              # for bucket prefix
RUN_ID   = UTC_NOW.strftime("%Y%m%d_%H%M%S")       # unique per invocation

# ==== 1) FULL STYLE TABLE (unchanged) ======================================
STYLES: dict[str, str] = {  # … full table unchanged …
    "Photorealistic": "photorealistic style, high fidelity, realistic lighting, lifelike textures",
    #     ↓  (table content omitted for brevity; keep exactly as before)
    "Neon_Wireframe": "glowing neon wireframe, dark background, synth-grid",
}

# ==== 2) helpers ===========================================================
def req(key: str) -> str:
    v = os.getenv(key)
    if not v:
        sys.exit(f"[ERROR] env '{key}' is required")
    return v

def load_prompts(pattern: str) -> List[Tuple[str, str]]:
    prompts: list[Tuple[str, str]] = []
    for path in glob.glob(pattern, recursive=True):
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                if ln.strip():
                    d = json.loads(ln)
                    txt = d.get("text") or d.get("prompt") or ""
                    if txt.strip():
                        prompts.append((Path(path).stem, txt.strip()))
    if not prompts:
        sys.exit(f"[ERROR] no prompts matched {pattern!r}")
    return prompts

def seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

def sha256_png(img: "Image.Image") -> str:
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return hashlib.sha256(buf.getvalue()).hexdigest()

# ---- AWS CLI helpers ------------------------------------------------------
BUCKET   = "castlesidegamestudio-spec-sheets"
S3_EP    = req("LINODE_S3_ENDPOINT")        # e.g. https://us-east-1.linodeobjects.com

# credential mapping + masked print (unchanged from last patch)
LINODE_KEY    = os.getenv("LINODE_ACCESS_KEY_ID")
LINODE_SECRET = os.getenv("LINODE_SECRET_ACCESS_KEY")
if not LINODE_KEY or not LINODE_SECRET:
    sys.exit("[ERROR] Linode S3 credentials are missing in the pod env")
os.environ["AWS_ACCESS_KEY_ID"]     = LINODE_KEY
os.environ["AWS_SECRET_ACCESS_KEY"] = LINODE_SECRET
def _mask(s: str) -> str: return f"{s[:4]}…{s[-4:]}" if len(s) > 8 else "****"
print(f"[INFO] Using creds  ID={_mask(LINODE_KEY)}  SECRET={_mask(LINODE_SECRET)}")

def ensure_awscli() -> None:
    if shutil.which("aws") is None:
        print("[INFO] aws CLI not found – installing …")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "awscli==1.32.0"],
            check=True
        )

def create_remote_prefix() -> None:
    ensure_awscli()
    readme_text = (
        f"Sprite-sheets uploaded {DATE_STR} run {RUN_ID}\n"
        f"Archive: sprites_{RUN_ID}.zip → unpacks to <Style>/sheet/*.png\n"
    )
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        tmp.write(readme_text); tmp_path = tmp.name
    uri = f"s3://{BUCKET}/{DATE_STR}/README.txt"
    subprocess.run(["aws","--endpoint-url",S3_EP,"s3","cp",tmp_path,uri,"--only-show-errors"],check=True)
    os.remove(tmp_path)
    print(f"[OK] verified remote prefix {DATE_STR}/ (README.txt)")

def upload_zip(zip_path: Path) -> None:
    ensure_awscli()
    uri = f"s3://{BUCKET}/{DATE_STR}/sprites_{RUN_ID}.zip"
    subprocess.run(
        ["aws","--endpoint-url",S3_EP,"s3","cp",str(zip_path),uri,"--only-show-errors"],
        check=True
    )
    print(f"[OK] uploaded archive → {uri}")

# ==== 3) main ==============================================================  
def main() -> None:
    t0 = time.perf_counter()

    model_id  = req("MODEL_ID")
    pattern   = req("PROMPT_GLOB")
    base_seed = int(req("SEED"))
    width     = int(os.getenv("WIDTH",  "3072"))
    height    = int(os.getenv("HEIGHT", "1024"))
    ortho     = os.getenv("ORTHO", "true").lower() == "true"
    model_rev = os.getenv("MODEL_REV") or None

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipe = DiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        revision=model_rev,
    ).to(device)

    create_remote_prefix()                         # verify bucket early

    out_root = Path("outputs") / RUN_ID            # ← timestamped sub-folder
    out_root.mkdir(parents=True, exist_ok=True)

    prompts = load_prompts(pattern)
    total   = len(prompts) * len(STYLES)
    counter = 0

    for stem, subj in prompts:
        for s_idx, (style, style_desc) in enumerate(STYLES.items(), start=1):
            seed = base_seed + s_idx * 1000
            seed_everything(seed)
            gen = torch.Generator(device).manual_seed(seed)

            prompt = (
                f"{style_desc}. "
                f"A 3-panel orthographic sheet showing the {subj} "
                f"from the front, side and back – left to right. "
                f"{'Orthographic projection.' if ortho else 'Perspective view.'} "
                f"Each panel centred, no overlap, transparent background."
            )

            print(f"[{counter+1:>4}/{total}] {style:<18}  seed={seed}")
            image = pipe(prompt=prompt,height=height,width=width,
                         num_inference_steps=25,guidance_scale=5.0,generator=gen).images[0]

            save_dir = out_root / style / "sheet"
            save_dir.mkdir(parents=True, exist_ok=True)
            out_path = save_dir / f"{stem}.png"
            image.save(out_path)
            print(f"      -> saved {out_path.relative_to(out_root.parent)}")
            counter += 1

    # ---- zip the run folder and upload once
    archive_path = shutil.make_archive(f"sprites_{RUN_ID}", "zip", out_root)
    upload_zip(Path(archive_path))

    dt = time.perf_counter() - t0
    print(f"[OK] Completed → {counter} sheets ({dt/60:4.1f} min)")

# ==== 4) smoke-test mode ===================================================
if __name__ == "__main__":
    if "--smoke-test" in sys.argv or os.getenv("SMOKE_TEST") == "1":
        os.environ.setdefault("WIDTH","96");  os.environ.setdefault("HEIGHT","32")
        os.environ.setdefault("SEED","42")
        print("[SMOKE] 32×96 deterministic canary …")
        main()
        p = next(Path("outputs").rglob("*.png"))
        print(f"[SMOKE] SHA-256 = {sha256_png(Image.open(p))}")
        sys.exit(0)
    main()
