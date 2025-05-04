#!/usr/bin/env python3
"""
Batch-generate images with **Qwen 3 multimodal** (no Diffusers).
Each prompt line in the NDJSON files will be rendered across all styles
listed in *STYLES*.

Expected ENV (injected by GitHub workflow → RunPod):

MODEL_ID       – HF model id (default: Qwen/Qwen3-32B)
PROMPT_GLOB    – pattern such as addendums/**/*.ndjson
WIDTH / HEIGHT – image resolution in pixels (default 1920×1080)
ORTHO          – true / false → append "orthographic projection"

The script streams PNG images directly emitted by the model and saves them
under outputs/<Style>/<promptStem>_<idx>.png.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

import torch
from PIL import Image
from transformers import AutoTokenizer, AutoModelForCausalLM

# ─── 1) Style definitions ──────────────────────────────────────────────────
STYLES: dict[str, str] = {
    "Photorealistic":      "photorealistic style, high fidelity, realistic lighting, lifelike textures",
    "Disney":              "Disney-style animation, whimsical characters, vibrant colours",
    "Cartoon":             "cartoon style, bold outlines, flat colours, stylised exaggeration",
    "Watercolor":          "watercolour / hand-painted style, soft brush strokes, blended colours",
    "Anime":               "anime style, cel-shaded, crisp line art, expressive characters",
    "3D_Render":           "3D render style, realistic shading, detailed modelling, cinematic lighting",
    "Pixel_Art":           "pixel-art style, low resolution, blocky pixels, retro game aesthetic",
    "World_of_Warcraft":   "World of Warcraft-style dark fantasy, stylised realism, ornate armour",
    "Studio_Ghibli":       "Studio Ghibli-style soft pastel palette, whimsical detail, hand-drawn feel",
    "Line_Art":            "line-art / ink sketch, high contrast, black & white, hand-drawn lines",
}

# ─── 2) Utilities ──────────────────────────────────────────────────────────

def load_prompts(pattern: str) -> List[Tuple[str, str]]:
    """Return list of (stem, text) for each line in every *.ndjson file."""
    prompts: List[Tuple[str, str]] = []
    for path in glob.glob(pattern, recursive=True):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                text = data.get("text") or data.get("prompt")
                if text and text.strip():
                    prompts.append((Path(path).stem, text.strip()))
    if not prompts:
        sys.exit(f"[ERROR] No prompts found matching '{pattern}'.")
    return prompts


# ─── 3) Main generation loop ───────────────────────────────────────────────

def main() -> None:
    # Config via ENV
    model_id = os.getenv("MODEL_ID", "Qwen/Qwen3-32B")
    prompt_glob = os.getenv("PROMPT_GLOB", "addendums/**/*.ndjson")
    width = int(os.getenv("WIDTH", "1920"))
    height = int(os.getenv("HEIGHT", "1080"))
    orthographic = os.getenv("ORTHO", "true").lower() == "true"

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] Loading {model_id} on {device} …")

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map="auto",
        trust_remote_code=True,
    )

    out_root = Path("outputs")
    out_root.mkdir(exist_ok=True)

    entries = load_prompts(prompt_glob)
    total = len(entries) * len(STYLES)
    counter = 0

    for stem, base_prompt in entries:
        for style_name, style_desc in STYLES.items():
            full_prompt = f"{base_prompt}, {style_desc}"
            if orthographic:
                full_prompt += ", orthographic projection"
            # Resolution hint (natural language – Qwen 3 respects it)
            full_prompt += f", resolution {width}×{height}"

            messages = [{"role": "user", "content": full_prompt}]
            prompt_txt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,  # saves VRAM
            )
            inputs = tokenizer(prompt_txt, return_tensors="pt").to(model.device)

            with torch.inference_mode():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=1,
                    do_sample=False,
                    return_dict_in_generate=True,
                    output_images=True,
                )

            png_bytes: bytes = outputs.images[0]
            img = Image.open(BytesIO(png_bytes))

            style_dir = out_root / style_name
            style_dir.mkdir(parents=True, exist_ok=True)
            idx = entries.index((stem, base_prompt))
            out_path = style_dir / f"{stem}_{idx:03}.png"
            img.save(out_path)

            counter += 1
            print(f"[{counter}/{total}] Saved {style_name}/{out_path.name}")

    print(f"[✓] Completed: generated {counter} images across {len(STYLES)} styles.")


if __name__ == "__main__":
    main()
