#!/usr/bin/env python3
"""
Batch generator for PixArt-α XL 2 (Diffusers).
Reads NDJSON prompts, renders each prompt in
N styles × 3 orthographic views, saves PNGs.
"""
from __future__ import annotations
import glob, json, os, sys, time, random
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

import torch
from diffusers import PixArtAlphaPipeline
from PIL import Image

# ── styles (same keys you used before) ───────────────────────────────────
STYLES: dict[str, str] = {
    "Photorealistic":    "photorealistic, lifelike textures, realistic lighting",
    "Disney":            "Disney animation style, whimsical, vibrant colours",
    "Cartoon":           "cartoon style, bold outlines, flat colours",
    "Watercolor":        "soft watercolor painting, gentle brush strokes",
    "Anime":             "anime style, crisp line art, cel shading",
    "3D_Render":         "cinematic 3D render, physically based shading",
    "Pixel_Art":         "retro pixel-art style, low resolution, 16-bit palette",
    "World_of_Warcraft": "dark-fantasy World-of-Warcraft style, ornate armour",
    "Studio_Ghibli":     "Studio Ghibli, pastel palette, hand-drawn feel",
    "Line_Art":          "clean line-art, high contrast ink drawing",
}
VIEWS = ["front", "side", "back"]

# ── helpers ──────────────────────────────────────────────────────────────
def req(key: str) -> str:
    v = os.getenv(key)
    if not v:
        sys.exit(f"[ERROR] env '{key}' is required")
    return v

def load_prompts(pattern: str) -> List[Tuple[str, str]]:
    items: List[Tuple[str, str]] = []
    for p in glob.glob(pattern, recursive=True):
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                data = json.loads(line)
                txt  = data.get("text") or data.get("prompt", "")
                if txt.strip():
                    items.append((Path(p).stem, txt.strip()))
    if not items:
        sys.exit(f"[ERROR] no prompts matched {pattern!r}")
    return items

def seed_for(base: int, s_idx: int, v_idx: int) -> int:
    return base + s_idx * 100 + v_idx

# ── main ─────────────────────────────────────────────────────────────────
def main() -> None:
    import diffusers, transformers
    print(f"[INFO] diffusers {diffusers.__version__}, transformers {transformers.__version__}")

    model_id  = req("MODEL_ID")
    pattern   = req("PROMPT_GLOB")
    base_seed = int(req("SEED"))

    W = int(os.getenv("WIDTH",  "1024"))
    H = int(os.getenv("HEIGHT", "1024"))
    ortho = os.getenv("ORTHO", "true").lower() == "true"

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pipe   = PixArtAlphaPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16,
    ).to(device)
    pipe.set_progress_bar_config(disable=True)

    out_root = Path("outputs"); out_root.mkdir(exist_ok=True)

    entries = load_prompts(pattern)
    total   = len(entries) * len(STYLES) * len(VIEWS)
    idx_out = 0

    for stem, subj in entries:
        for v_idx, view in enumerate(VIEWS):
            for s_idx, (style_name, style_desc) in enumerate(STYLES.items()):
                seed = seed_for(base_seed, s_idx, v_idx)
                g    = torch.Generator(device=device).manual_seed(seed)

                prompt = (
                    f"{subj}, {style_desc}, "
                    f"orthographic {view} view, "
                    f"{'transparent background' if ortho else 'studio background'}"
                )

                t0 = time.perf_counter()
                img: Image.Image = pipe(prompt=prompt,
                                        height=H, width=W,
                                        generator=g,
                                        num_inference_steps=25,
                                        guidance_scale=6.0).images[0]
                dt = time.perf_counter() - t0
                print(f"[{idx_out+1}/{total}] {style_name:<14} {view:<5} "
                      f"seed={seed}  {dt:4.1f}s")

                save_dir = out_root / style_name / view
                save_dir.mkdir(parents=True, exist_ok=True)
                img_path = save_dir / f"{stem}_{idx_out:04}.png"
                img.save(img_path)

                idx_out += 1

    print(f"[✓] wrote {idx_out} PNGs to {out_root.resolve()}")

if __name__ == "__main__":
    main()
