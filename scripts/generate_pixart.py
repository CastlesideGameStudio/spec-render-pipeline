#!/usr/bin/env python3
"""
Generate one 3 × 1 orthographic sprite-sheet (front | side | back)
for every  ( prompt  ×  style )  pair using PixArt-α-XL.

ENV (all inherited from the GitHub workflow):

  MODEL_ID       – Hugging Face ID, e.g. PixArt-alpha/PixArt-XL-2-1024-MS
  PROMPT_GLOB    – NDJSON prompt paths, glob-style
  SEED           – base RNG seed (integer, deterministic)
  WIDTH          – sheet width   (default 3072 → 3 × 1024)
  HEIGHT         – sheet height  (default 1024)
  ORTHO          – "true"/"false" → orthographic vs perspective

Outputs land in  outputs/<Style>/sheet/<prompt-stem>.png
"""
from __future__ import annotations

import glob, json, os, random, sys, time
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

import torch
from PIL import Image
from diffusers import DiffusionPipeline

# ─── 1 ▸ style catalogue ────────────────────────────────────────────────
STYLES: dict[str, str] = {
    "Photorealistic":    "photorealistic style, high fidelity, realistic lighting, lifelike textures",
    "Disney":            "Disney-style animation, whimsical characters, vibrant colours",
    "Cartoon":           "cartoon style, bold outlines, flat colours, stylised exaggeration",
    "Watercolor":        "water-colour / hand-painted style, soft brush strokes, blended colours",
    "Anime":             "anime style, cel-shaded, crisp line art, expressive characters",
    "3D_Render":         "3-D render style, realistic shading, detailed modelling, cinematic lighting",
    "Pixel_Art":         "pixel-art style, low resolution, blocky pixels, retro game aesthetic",
    "World_of_Warcraft": "World-of-Warcraft dark fantasy, stylised realism, ornate armour",
    "Studio_Ghibli":     "Studio-Ghibli soft pastel palette, whimsical detail, hand-drawn feel",
    "Line_Art":          "line-art / ink sketch, high contrast, black & white, hand-drawn lines",
}

VIEWS              = ["front", "side", "back"]   # always L → R
VIEW_GRID_W, VIEW_GRID_H = 3, 1                  # fixed for now

# ─── 2 ▸ utility helpers ────────────────────────────────────────────────
def req_env(key: str) -> str:
    v = os.getenv(key)
    if not v:
        sys.exit(f"[ERROR] env '{key}' is required")
    return v

def load_prompts(pattern: str) -> List[Tuple[str, str]]:
    out: list[Tuple[str, str]] = []
    for path in glob.glob(pattern, recursive=True):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                data = json.loads(line)
                txt  = data.get("text") or data.get("prompt") or ""
                if txt.strip():
                    out.append((Path(path).stem, txt.strip()))
    if not out:
        sys.exit(f"[ERROR] no prompts matched {pattern!r}")
    return out

def seed_everything(seed: int) -> torch.Generator:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    return torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu").manual_seed(seed)

# ─── 3 ▸ main routine ───────────────────────────────────────────────────
def main() -> None:
    t0          = time.perf_counter()
    model_id    = req_env("MODEL_ID")
    pattern     = req_env("PROMPT_GLOB")
    base_seed   = int(req_env("SEED"))

    width       = int(os.getenv("WIDTH",  "3072"))   # 3 × 1024
    height      = int(os.getenv("HEIGHT", "1024"))
    ortho       = os.getenv("ORTHO", "true").lower() == "true"

    device      = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] Loading {model_id} on {device} …")
    pipe = DiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype = torch.float16 if device == "cuda" else torch.float32,
        variant     = "fp16"
    ).to(device)
    pipe.set_progress_bar_config(disable=True)

    out_root = Path("outputs"); out_root.mkdir(exist_ok=True)
    prompt_list = load_prompts(pattern)
    total   = len(prompt_list) * len(STYLES)

    counter = 0
    for prompt_stem, subject in prompt_list:
        for s_idx, (style_name, style_desc) in enumerate(STYLES.items()):
            seed = base_seed + (s_idx + 1) * 1000
            g    = seed_everything(seed)

            # — composite text prompt ————————————————————————————
            prompt = (
                f"{style_desc}. "
                f"A 3-panel orthographic sheet showing the {subject} "
                f"from the front, side and back, left-to-right. "
                f"{'Orthographic projection.' if ortho else 'Perspective view.'} "
                f"Each panel centred, no overlap, transparent background."
            )

            print(f"[{counter+1}/{total}] {style_name:<14}  seed={seed}")
            image = pipe(
                prompt               = prompt,
                height               = height,
                width                = width,
                num_inference_steps  = 25,
                guidance_scale       = 5.0,
                generator            = g,
            ).images[0]

            save_dir = out_root / style_name / "sheet"
            save_dir.mkdir(parents=True, exist_ok=True)
            out_path = save_dir / f"{prompt_stem}.png"
            image.save(out_path)

            counter += 1
            print(f"      → saved {out_path.relative_to(out_root)}")

    dt = time.perf_counter() - t0
    print(f"[✓] Completed  {counter} sheets  ({dt/60:4.1f} min total)")

if __name__ == "__main__":
    main()
