#!/usr/bin/env python3
"""
Batch-generate images with **Qwen 3 multimodal** (no Diffusers).

Required ENV (injected by GitHub workflow → RunPod)
---------------------------------------------------
MODEL_ID       – Hugging Face model id (e.g. Qwen/Qwen3-32B)
PROMPT_GLOB    – glob pattern for *.ndjson files (e.g. addendums/**/*.ndjson)

Optional ENV
------------
WIDTH          – image width  (default 1920)
HEIGHT         – image height (default 1080)
ORTHO          – "true"/"false" → add “orthographic projection”

The model streams PNG bytes directly.  Images are saved under:
outputs/<Style>/<promptStem>_<idx>.png
"""
from __future__ import annotations

import glob, json, os, sys
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

import torch
from PIL import Image
from transformers import AutoTokenizer, AutoModelForCausalLM

# ─── 1) Style definitions ────────────────────────────────────────────────
STYLES: dict[str, str] = {
    "Photorealistic":    "photorealistic style, high fidelity, realistic lighting, lifelike textures",
    "Disney":            "Disney-style animation, whimsical characters, vibrant colours",
    "Cartoon":           "cartoon style, bold outlines, flat colours, stylised exaggeration",
    "Watercolor":        "watercolour / hand-painted style, soft brush strokes, blended colours",
    "Anime":             "anime style, cel-shaded, crisp line art, expressive characters",
    "3D_Render":         "3D render style, realistic shading, detailed modelling, cinematic lighting",
    "Pixel_Art":         "pixel-art style, low resolution, blocky pixels, retro game aesthetic",
    "World_of_Warcraft": "World of Warcraft-style dark fantasy, stylised realism, ornate armour",
    "Studio_Ghibli":     "Studio Ghibli-style soft pastel palette, whimsical detail, hand-drawn feel",
    "Line_Art":          "line-art / ink sketch, high contrast, black & white, hand-drawn lines",
}

# ─── 2) Helpers ───────────────────────────────────────────────────────────
def required_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        sys.exit(f"[ERROR] Required ENV '{key}' is missing or empty.")
    return val

def load_prompts(pattern: str) -> List[Tuple[str, str]]:
    prompts: List[Tuple[str, str]] = []
    for path in glob.glob(pattern, recursive=True):
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                data = json.loads(line)
                text = data.get("text") or data.get("prompt")
                if text and text.strip():
                    prompts.append((Path(path).stem, text.strip()))
    if not prompts:
        sys.exit(f"[ERROR] No prompts found matching '{pattern}'.")
    return prompts

# ─── 3) Main ──────────────────────────────────────────────────────────────
def main() -> None:
    model_id    = required_env("MODEL_ID")
    prompt_glob = required_env("PROMPT_GLOB")

    width       = int(os.getenv("WIDTH",  "1920"))
    height      = int(os.getenv("HEIGHT", "1080"))
    orthographic= os.getenv("ORTHO", "true").lower() == "true"

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] Loading {model_id} on {device} …")

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model     = AutoModelForCausalLM.from_pretrained(
                   model_id,
                   torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                   device_map="auto",
                   trust_remote_code=True,
               )

    out_root = Path("outputs"); out_root.mkdir(exist_ok=True)

    entries = load_prompts(prompt_glob)
    total   = len(entries) * len(STYLES)
    counter = 0

    for stem, base_prompt in entries:
        for style_name, style_desc in STYLES.items():
            full_prompt = f"{base_prompt}, {style_desc}"
            if orthographic:
                full_prompt += ", orthographic projection"
            full_prompt += f", resolution {width}×{height}"

            prompt_txt = tokenizer.apply_chat_template(
                [{"role": "user", "content": full_prompt}],
                tokenize=False, add_generation_prompt=True, enable_thinking=False
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

            img = Image.open(BytesIO(outputs.images[0]))

            style_dir = out_root / style_name; style_dir.mkdir(parents=True, exist_ok=True)
            idx = entries.index((stem, base_prompt))
            out_path = style_dir / f"{stem}_{idx:03}.png"
            img.save(out_path)

            counter += 1
            print(f"[{counter}/{total}] Saved {style_name}/{out_path.name}")

    print(f"[✓] Completed: generated {counter} images across {len(STYLES)} styles.")

if __name__ == "__main__":
    main()
