#!/usr/bin/env python3
"""
Deterministic batch generator for **Qwen 3 multimodal**

Required ENV ───────────────────────────────────────────────────────────────
MODEL_ID       – e.g. "Qwen/Qwen3-32B"
PROMPT_GLOB    – e.g. "addendums/**/*.ndjson"
SEED           – integer; base RNG seed for reproducibility

Optional ENV ───────────────────────────────────────────────────────────────
WIDTH, HEIGHT  – default 1920 × 1080
ORTHO          – "true"/"false" (default true → orthographic)
"""
from __future__ import annotations

import base64, binascii, glob, json, os, sys
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
    "World_of_Warcraft": "World of Warcraft–style dark fantasy, stylised realism, ornate armour",
    "Studio_Ghibli":     "Studio Ghibli–style soft pastel palette, whimsical detail, hand-drawn feel",
    "Line_Art":          "line-art / ink sketch, high contrast, black & white, hand-drawn lines",
}
VIEWS = ["front", "side", "back"]   # orthographic angles

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
                if not line.strip():
                    continue
                data = json.loads(line)
                txt = data.get("text") or data.get("prompt", "")
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
    import base64, binascii, transformers
    print(f"[INFO] transformers-py version = {transformers.__version__}")

    model_id  = req("MODEL_ID")
    pattern   = req("PROMPT_GLOB")
    base_seed = int(req("SEED"))

    width  = int(os.getenv("WIDTH",  "1920"))
    height = int(os.getenv("HEIGHT", "1080"))
    ortho  = os.getenv("ORTHO", "true").lower() == "true"

    if os.getenv("CUBLAS_WORKSPACE_CONFIG") is None:
        print("[WARN] CUBLAS_WORKSPACE_CONFIG not set; results may drift.")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] Loading {model_id} on {device} …")

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model     = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map="auto",
        trust_remote_code=True,
    )

    # ── detect image interface flags (first success sticks) ──────────────
    HAS_CHAT   = hasattr(model, "chat")
    HAS_IMAGES = False          # set True once generate(images=True) succeeds
    MODE_USED  = None           # human-readable description (printed once)

    out_root = Path("outputs"); out_root.mkdir(exist_ok=True)
    entries  = load_prompts(pattern)
    total    = len(entries) * len(STYLES) * len(VIEWS)
    counter  = 0

    for stem, subj in entries:
        for v_idx, view in enumerate(VIEWS):
            for s_idx, style_name in enumerate(STYLES):

                combo_seed = seed_for(base_seed, s_idx, v_idx)
                torch.manual_seed(combo_seed)
                torch.cuda.manual_seed_all(combo_seed)

                prompt_txt = tokenizer.apply_chat_template(
                    [{"role": "user",
                      "content":
                      f"<STYLE={style_name.lower()}> "
                      f"<SUBJECT={subj}> "
                      f"<VIEW={'orthographic' if ortho else 'perspective'} {view}> "
                      f"<LIGHT=soft studio key> <BG=transparent> "
                      f"<RES={width}×{height}>"}],
                    tokenize=False, add_generation_prompt=True, enable_thinking=False,
                )

                png_bytes: bytes | None = None

                # ── (1) legacy chat() API ────────────────────────────────
                if HAS_CHAT:
                    try:
                        with torch.inference_mode():
                            _, b64_png = model.chat(
                                tokenizer, prompt_txt,
                                images=True, output_format="PNG",
                                temperature=0.6,  # chat() is always sampled
                                top_p=None, top_k=None, seed=combo_seed,
                            )
                        png_bytes = base64.b64decode(b64_png)
                        if MODE_USED is None:
                            MODE_USED = "chat()"
                            print(f"[INFO] Image mode detected → {MODE_USED}")
                    except Exception as e:
                        HAS_CHAT = False
                        print(f"[INFO] chat() unavailable → fallback ({e})")

                # ── (2) generate(images=True) API ────────────────────────
                if png_bytes is None and not HAS_CHAT:
                    tokens = tokenizer(prompt_txt, return_tensors="pt").to(model.device)
                    try:
                        with torch.inference_mode():
                            png_list: list[bytes] = model.generate(
                                **tokens,
                                images=True,
                                max_new_tokens=1,
                                do_sample=False,      # greedy
                                top_p=None, top_k=None,
                            )
                        png_bytes = png_list[0]
                        HAS_IMAGES = True
                        if MODE_USED is None:
                            MODE_USED = "generate(images=True)"
                            print(f"[INFO] Image mode detected → {MODE_USED}")
                    except (TypeError, ValueError):
                        HAS_IMAGES = False   # flag so we never try again

                # ── (3) image as base-64 inside text  (current build) ────
                if png_bytes is None and not HAS_CHAT and not HAS_IMAGES:
                    tokens = tokenizer(prompt_txt, return_tensors="pt").to(model.device)
                    with torch.inference_mode():
                        out_ids = model.generate(
                            **tokens,
                            max_new_tokens=256,
                            do_sample=False,      # greedy
                            top_p=None, top_k=None,
                        )
                    reply = tokenizer.decode(out_ids[0], skip_special_tokens=True)
                    if "data:image/png;base64," in reply:
                        b64 = reply.split("data:image/png;base64,", 1)[1].split()[0]
                        try:
                            png_bytes = base64.b64decode(b64)
                            if MODE_USED is None:
                                MODE_USED = "PNG base-64 in text"
                                print(f"[INFO] Image mode detected → {MODE_USED}")
                        except binascii.Error:
                            print(f"[WARN] b64 decode failed for {stem}/{style_name}/{view}")
                            continue
                    else:
                        print(f"[WARN] No image in reply for {stem}/{style_name}/{view}")
                        continue

                # ── save PNG ─────────────────────────────────────────────
                img = Image.open(BytesIO(png_bytes))
                save_dir = out_root / style_name / view
                save_dir.mkdir(parents=True, exist_ok=True)
                idx  = entries.index((stem, subj))
                file = save_dir / f"{stem}_{idx:03}.png"
                img.save(file)

                counter += 1
                print(f"[{counter}/{total}] Saved {style_name}/{view}/{file.name}")

    print(f"[✓] Completed → {counter} images "
          f"({len(STYLES)} styles × {len(VIEWS)} views) using [{MODE_USED}].")


if __name__ == "__main__":
    main()
