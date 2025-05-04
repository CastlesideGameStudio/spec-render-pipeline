#!/usr/bin/env python3
"""
Deterministic batch generator for **Qwen 3 multimodal**.
…
"""
from __future__ import annotations
import glob, json, os, sys, hashlib, base64, binascii          # + base64
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

import torch
from PIL import Image
from transformers import AutoTokenizer, AutoModelForCausalLM
# (rest of header unchanged)

# ─── 1) CONSTANTS ──────────────────────────────────────────────────────────
STYLES = { … }          # unchanged
VIEWS  = ["front", "side", "back"]

# ─── 2) HELPERS ────────────────────────────────────────────────────────────
def req(key: str) -> str: …                       # unchanged
def load_prompts(pattern: str) -> List[Tuple[str, str]]: …  # unchanged
def seed_for(base: int, style_idx: int, view_idx: int) -> int:  # unchanged

# ─── 3) MAIN ───────────────────────────────────────────────────────────────
def main() -> None:
    model_id    = req("MODEL_ID")
    pattern     = req("PROMPT_GLOB")
    base_seed   = int(req("SEED"))

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

    out_root = Path("outputs"); out_root.mkdir(exist_ok=True)
    entries  = load_prompts(pattern)
    total    = len(entries) * len(STYLES) * len(VIEWS)
    counter  = 0

    for stem, subj in entries:
        for v_idx, view in enumerate(VIEWS):
            for s_idx, (style_name, style_desc) in enumerate(STYLES.items()):

                combo_seed = seed_for(base_seed, s_idx, v_idx)
                torch.manual_seed(combo_seed)
                torch.cuda.manual_seed_all(combo_seed)

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

                # ── Qwen-3 chat call → base-64 PNG ────────────────────────
                with torch.inference_mode():
                    _, img_b64 = model.chat(
                        tokenizer,
                        prompt_txt,
                        images=True,
                        temperature=0.0,   # deterministic
                        top_p=None,
                        top_k=None,
                        seed=combo_seed,
                        output_format="PNG",
                    )

                try:
                    png_bytes = base64.b64decode(img_b64)
                except binascii.Error as e:
                    print(f"[ERROR] Base-64 decode failed for {stem}/{style_name}/{view}: {e}")
                    continue

                img = Image.open(BytesIO(png_bytes))

                save_dir = out_root / style_name / view
                save_dir.mkdir(parents=True, exist_ok=True)
                idx  = entries.index((stem, subj))
                file = save_dir / f"{stem}_{idx:03}.png"
                img.save(file)

                counter += 1
                print(f"[{counter}/{total}] Saved {style_name}/{view}/{file.name}")

    print(f"[✓] All done – {counter} images "
          f"({len(STYLES)} styles × {len(VIEWS)} views).")

if __name__ == "__main__":
    main()
