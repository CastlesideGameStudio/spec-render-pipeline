#!/usr/bin/env python3
"""
Deterministic batch generator for **Qwen 3 multimodal**.

Required ENV (must be non-empty)
--------------------------------
MODEL_ID       – e.g. "Qwen/Qwen3-32B"
PROMPT_GLOB    – e.g. "addendums/**/*.ndjson"
SEED           – integer; base RNG seed for reproducibility

Optional ENV
------------
WIDTH, HEIGHT  – default 1920 × 1080
ORTHO          – "true"/"false" (default true → orthographic)
"""

from __future__ import annotations
import glob, json, os, sys, hashlib
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

import torch
from PIL import Image
from transformers import AutoTokenizer, AutoModelForCausalLM

# ─── 1) CONSTANTS ──────────────────────────────────────────────────────────
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
VIEWS = ["front", "side", "back"]  # orthographic angles  :contentReference[oaicite:0]{index=0}:contentReference[oaicite:1]{index=1}

# ─── 2) HELPERS ────────────────────────────────────────────────────────────
def req(key: str) -> str:
    v = os.getenv(key)
    if not v:
        sys.exit(f"[ERROR] Required ENV '{key}' is missing or empty.")
    return v

def load_prompts(pattern: str) -> List[Tuple[str, str]]:
    items: List[Tuple[str, str]] = []
    for path in glob.glob(pattern, recursive=True):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip(): continue
                data = json.loads(line)
                txt  = data.get("text") or data.get("prompt", "")
                if txt.strip():
                    items.append((Path(path).stem, txt.strip()))
    if not items:
        sys.exit(f"[ERROR] No prompts matched '{pattern}'.")
    return items

def seed_for(base: int, style_idx: int, view_idx: int) -> int:
    """Derive a deterministic but distinct seed for each (style, view)."""
    return base + style_idx * 100 + view_idx

# ─── 3) MAIN ───────────────────────────────────────────────────────────────
def main() -> None:
    model_id    = req("MODEL_ID")
    pattern     = req("PROMPT_GLOB")
    base_seed   = int(req("SEED"))

    width       = int(os.getenv("WIDTH",  "1920"))
    height      = int(os.getenv("HEIGHT", "1080"))
    ortho       = os.getenv("ORTHO", "true").lower() == "true"

    # extra safety: cuBLAS reproducibility
    if os.getenv("CUBLAS_WORKSPACE_CONFIG") is None:
        print("[WARN] CUBLAS_WORKSPACE_CONFIG not set; results may drift on driver change.")

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

    entries = load_prompts(pattern)
    total   = len(entries) * len(STYLES) * len(VIEWS)
    counter = 0

    for stem, subj in entries:
        for v_idx, view in enumerate(VIEWS):
            for s_idx, (style_name, style_desc) in enumerate(STYLES.items()):

                # deterministic seed per combo
                torch.manual_seed(seed_for(base_seed, s_idx, v_idx))
                torch.cuda.manual_seed_all(seed_for(base_seed, s_idx, v_idx))

                full_prompt = (
                    f"<STYLE={style_name.lower()}> "
                    f"<SUBJECT={subj}> "
                    f"<VIEW={'orthographic' if ortho else 'perspective'} {view}> "
                    f"<LIGHT=soft studio key> <BG=transparent> "
                    f"<RES={width}×{height}>"
                )

                prompt_txt = tokenizer.apply_chat_template(
                    [{"role": "user", "content": full_prompt}],
                    tokenize=False, add_generation_prompt=True, enable_thinking=False
                )
                inputs = tokenizer(prompt_txt, return_tensors="pt").to(model.device)

                with torch.inference_mode():
                    out = model.generate(
                        **inputs,
                        max_new_tokens=1,
                        do_sample=False,   # greedy → deterministic
                        return_dict_in_generate=True,
                        output_images=True,
                    )

                img = Image.open(BytesIO(out.images[0]))

                save_dir = out_root / style_name / view
                save_dir.mkdir(parents=True, exist_ok=True)
                idx = entries.index((stem, subj))
                file = save_dir / f"{stem}_{idx:03}.png"
                img.save(file)

                counter += 1
                print(f"[{counter}/{total}] Saved {style_name}/{view}/{file.name}")

    print(f"[✓] All done – {counter} images ( {len(STYLES)} styles × {len(VIEWS)} views ).")

if __name__ == "__main__":
    main()
