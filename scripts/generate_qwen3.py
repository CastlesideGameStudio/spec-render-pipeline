#!/usr/bin/env python3
import os
import json
import glob
from pathlib import Path

import torch
from diffusers import DiffusionPipeline

# ──── 1) Style definitions from Qwen 3 overview ─────────────────────────────
STYLES = {
    "Photorealistic":      "photorealistic style, high fidelity, realistic lighting, lifelike textures",
    "Disney":              "Disney-style animation style, whimsical characters, vibrant colors",
    "Cartoon":             "cartoon style, bold outlines, flat colors, stylized exaggeration",
    "Watercolor":          "watercolor / hand-painted style, soft brush strokes, blended colors",
    "Anime":               "anime style, cel-shaded, crisp line art, expressive characters",
    "3D_Render":           "3D render style, realistic shading, detailed modeling, cinematic lighting",
    "Pixel_Art":           "pixel art style, low resolution, blocky pixels, retro game aesthetic",
    "World_of_Warcraft":   "World of Warcraft-style dark fantasy style, stylized realism, ornate armor",
    "Studio_Ghibli":       "Studio Ghibli-style soft pastel palette, whimsical detail, hand-drawn feel",
    "Line_Art":            "line art / ink sketch style, high contrast, black and white, hand-drawn lines"
}

# ──── 2) Load all prompts from NDJSON files ─────────────────────────────────
def load_prompts(glob_pattern):
    prompts = []
    for path in glob.glob(glob_pattern, recursive=True):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                text = data.get("text") or data.get("prompt") or ""
                if text.strip():
                    prompts.append((Path(path).stem, text.strip()))
    return prompts

# ──── 3) Main generation loop ───────────────────────────────────────────────
def main():
    # Config via ENV
    model_id   = os.getenv("MODEL_ID", "modelscope/qwen-image-7b")
    prompt_glob= os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")
    width      = int(os.getenv("WIDTH", 1920))
    height     = int(os.getenv("HEIGHT",1080))
    orthographic = os.getenv("ORTHO","true").lower() == "true"

    print(f"[INFO] Loading Qwen-3 pipeline '{model_id}' at {width}×{height}, ortho={orthographic}")
    pipe = DiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16,
        trust_remote_code=True
    ).to("cuda")

    out_base = Path("outputs")
    out_base.mkdir(exist_ok=True)

    # Gather all (file, prompt) pairs
    entries = load_prompts(prompt_glob)
    total = len(entries) * len(STYLES)
    count = 0

    for file_stem, prompt in entries:
        for style_name, style_desc in STYLES.items():
            full_prompt = f"{prompt}, {style_desc}"
            if orthographic:
                full_prompt += ", orthographic projection"

            img = pipe(
                full_prompt,
                width=width,
                height=height,
                num_inference_steps=20,
                guidance_scale=7
            ).images[0]

            # Save: outputs/<style>/<file>_<index>.png
            style_dir = out_base / style_name
            style_dir.mkdir(parents=True, exist_ok=True)

            idx = entries.index((file_stem, prompt))
            filename = f"{file_stem}_{idx:03}.png"
            out_path = style_dir / filename
            img.save(out_path)

            count += 1
            print(f"[{count}/{total}] Saved {style_name}/{filename}")

    print(f"[✓] Done: generated {count} images across {len(STYLES)} styles.")

if __name__ == "__main__":
    main()
