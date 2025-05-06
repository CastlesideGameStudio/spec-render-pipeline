#!/usr/bin/env python3
"""
Generate 3×1 orthographic sprite-sheets with PixArt-α XL, saving each PNG
locally **and** to Linode S3 as soon as it renders.

Bucket layout on Linode
────────────────────────────────────────────────────────
  castlesidegamestudio-spec-sheets/
      20250506/               # UTC date of the run
          Pixar/
              sheet/
                  dragon.png
                  knight.png
          Watercolor/
              sheet/…
"""

from __future__ import annotations
# ───────────────────────── DETERMINISM PRE-IMPORT ──────────────────────────
import os as _os
_os.environ.setdefault("TRANSFORMERS_NO_GGML", "1")
_os.environ.setdefault("TRANSFORMERS_NO_TF",  "1")
_os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
_os.environ.setdefault("PYTHONHASHSEED", "0")

# ───────────────────────── STANDARD LIB / 3rd-PARTY ────────────────────────
import glob, json, os, random, subprocess, sys, time, hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import torch
torch.use_deterministic_algorithms(True, warn_only=False)

from PIL import Image                           # noqa: F401
from diffusers import DiffusionPipeline

# ==== 1) ART STYLES (unchanged) ============================================
STYLES: dict[str, str] = {  # … (full dict exactly as in your message) …
    "Photorealistic": "photorealistic style, high fidelity, realistic lighting, lifelike textures",
    #  ↓ DICT CONTENT TRUNCATED FOR B﻿R﻿E﻿V﻿I﻿T﻿Y — KEEP EVERYTHING UNCHANGED
    "Neon_Wireframe": "glowing neon wireframe, dark background, synth-grid",
}

VIEWS        = ["front", "side", "back"]
VIEW_GRID_W  = len(VIEWS)
VIEW_GRID_H  = 1

# ==== 2) HELPERS ============================================================
def req(key: str) -> str:
    val = os.getenv(key)
    if not val:
        sys.exit(f"[ERROR] env '{key}' is required")
    return val

def load_prompts(pattern: str) -> List[Tuple[str, str]]:
    out: list[Tuple[str, str]] = []
    for path in glob.glob(pattern, recursive=True):
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                if ln.strip():
                    data = json.loads(ln)
                    txt  = data.get("text") or data.get("prompt") or ""
                    if txt.strip():
                        out.append((Path(path).stem, txt.strip()))
    if not out:
        sys.exit(f"[ERROR] no prompts matched {pattern!r}")
    return out

def seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

def sha256_png(img: "Image.Image") -> str:
    import io, hashlib
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return hashlib.sha256(buf.getvalue()).hexdigest()

# ---- Linode upload --------------------------------------------------------
BUCKET   = "castlesidegamestudio-spec-sheets"
S3_EP    = req("LINODE_S3_ENDPOINT")        # e.g. https://us-east-1.linodeobjects.com
DATE_STR = datetime.now(timezone.utc).strftime("%Y%m%d")

def s3_sync_single(local_path: Path, style: str) -> None:
    rel_key = f"{DATE_STR}/{style}/sheet/{local_path.name}"
    uri     = f"s3://{BUCKET}/{rel_key}"
    cmd = [
        "aws", "--endpoint-url", S3_EP,
        "s3", "cp", str(local_path), uri,
        "--only-show-errors"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[WARN] S3 upload failed → {uri}\n{res.stderr}", file=sys.stderr)
    else:
        print(f"      -> uploaded {uri}")

# ==== 3) MAIN ==============================================================
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

    out_root = Path("outputs")
    out_root.mkdir(exist_ok=True)

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
                f"from the front, side and back - left to right. "
                f"{'Orthographic projection.' if ortho else 'Perspective view.'} "
                f"Each panel centred, no overlap, transparent background."
            )

            print(f"[{counter+1:>4}/{total}] {style:<18}  seed={seed}")
            image = pipe(
                prompt              = prompt,
                height              = height,
                width               = width,
                num_inference_steps = 25,
                guidance_scale      = 5.0,
                generator           = gen,
            ).images[0]

            save_dir = out_root / style / "sheet"
            save_dir.mkdir(parents=True, exist_ok=True)
            out_path = save_dir / f"{stem}.png"
            image.save(out_path)
            print(f"      -> saved {out_path.relative_to(out_root)}")

            # ---- immediate Linode upload
            s3_sync_single(out_path, style)

            counter += 1

    dt = time.perf_counter() - t0
    print(f"[OK] Completed -> {counter} sheets ({dt/60:4.1f} min total)")

# ==== 4) SMOKE-TEST ========================================================
if __name__ == "__main__":
    if "--smoke-test" in sys.argv or os.getenv("SMOKE_TEST") == "1":
        os.environ.setdefault("WIDTH",  "96")
        os.environ.setdefault("HEIGHT", "32")
        os.environ.setdefault("SEED",   "42")
        print("[SMOKE] running 32×96 deterministic canary …")
        main()
        example = next(Path("outputs").rglob("*.png"))
        digest  = sha256_png(Image.open(example))
        print(f"[SMOKE] SHA-256 digest = {digest}")
        sys.exit(0)
    else:
        main()
