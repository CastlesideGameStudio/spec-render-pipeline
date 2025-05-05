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
    # ── core / generic ————————————————————————————————————————
    "Photorealistic":     "photorealistic style, high fidelity, realistic lighting, lifelike textures",
    "Disney":             "Disney-style animation, whimsical characters, vibrant colours",
    "Cartoon":            "cartoon style, bold outlines, flat colours, stylised exaggeration",
    "Watercolor":         "watercolour / hand-painted style, soft brush strokes, blended colours",
    "Anime":              "anime style, cel-shaded, crisp line art, expressive characters",
    "3D_Render":          "3D render style, realistic shading, detailed modelling, cinematic lighting",
    "Pixel_Art":          "pixel-art style, low resolution, blocky pixels, retro game aesthetic",
    "Line_Art":           "line-art / ink sketch, high contrast, black & white, hand-drawn lines",

    # ── existing MMO / fantasy set ——————————————————————————
    "World_of_Warcraft":  "World-of-Warcraft dark fantasy, stylised realism, ornate armour",
    "Studio_Ghibli":      "Studio-Ghibli soft pastel palette, whimsical detail, hand-drawn feel",
    "Blizzard_Cinematic": "Blizzard Entertainment cinematic style, exaggerated proportions, hyper-clean PBR texturing, heroic posing",
    "Riot_Illustrative":  "League-of-Legends splash-art style, painterly gradients, high-contrast rim light, saturated palette",
    "Dark_Souls":         "FromSoftware grimdark realism, muted colours, heavy weathering, gothic atmosphere",
    "Elder_Scrolls":      "Elder-Scrolls high-fantasy realism, Nordic motifs, subdued earth tones, hand-painted textures",
    "Lineage":            "Lineage MMO style, sleek armour plating, jewel accents, East-Asian high fantasy",
    "Final_Fantasy_XIV":  "FFXIV art style, clean anime-influenced faces, ornate costume design, vibrant effect glows",
    "Guild_Wars_Concept": "Guild-Wars concept art, painterly brushwork, impressionistic backdrops, desaturated mid-tones",
    "Torchlight":         "Torchlight stylised low-poly, chunky silhouettes, bold colour blocking, playful proportions",
    "Forsaken_Dusk":      "high-contrast dusk lighting, purple-blue ambience, ethereal particle effects, mystical aura",
    "Steampunk_MMORPG":   "Victorian steampunk fantasy, brass machinery, leather straps, smoky industrial haze",
    "Cel_Shaded_Combat":  "cel-shaded toon rendering, thick contour lines, vibrant flat shadows, anime motion streaks",
    "Isometric_ARPG":     "isometric ARPG hand-painted textures, exaggerated foreshortening, loot sparkle highlights",

    # ── NEW additions (18) ————————————————————————————————————
    "Diablo_Immortal":    "Diablo-Immortal high-resolution gothic horror, crimson palette, demonic iconography, smouldering embers",
    "Path_of_Exile":      "Path-of-Exile dark baroque fantasy, gritty surfaces, occult glyphs, muted browns and golds",
    "Arcane_Series":      "Arcane (Netflix) painted 3D style, semi-realistic facial micro-detail, graffiti splatter accents",
    "Overwatch_SciFi":    "Overwatch stylised sci-fi, hard-surface armour, saturated highlights, dynamic posing",
    "RuneScape_HD":       "RuneScape modern HD style, bright colours, simplified shapes, whimsical medieval tech",
    "Monster_Hunter":     "Monster-Hunter World realistic creature design, ornate bone armour, lush ecosystems",
    "Dragon_Age":         "Dragon-Age dark heroic fantasy, weathered metals, embroidered fabrics, dramatic chiaroscuro",
    "Warhammer_Grimdark": "Warhammer grimdark, heavy plate, gothic cathedral motifs, oil-paint texture",
    "Mythic_China":       "mythic ancient-China fantasy, flowing silk robes, jade inlays, ink-wash background",
    "Norse_Saga":         "Norse saga illustration, runic carvings, cold misty palette, rugged textures",
    "Atlantean_BioTech":  "Atlantean biotech fantasy, crystalline coral armour, luminous teal highlights, aquatic ambience",
    "Celestial_Paladin":  "celestial paladin aesthetic, radiant gold filigree, angelic wings, holy light bloom",
    "Shadow_Punk":        "shadow-punk aesthetic, black-purple palette, neon edge lights, ethereal smoke trails",
    "Lowpoly_Mobile":     "low-poly mobile-game style, flat shading, minimal textures, vibrant gradients",
    "Voxel_RPG":          "voxel-based RPG art, cubic forms, chunk-outlined edges, retro-lighting",
    "Handpainted_MMO":    "hand-painted MMO textures, visible brush strokes, stylised shapes, saturated fantasy colours",
    "Stylized_PBR":       "stylised PBR workflow, exaggerated normals, crisp cavity maps, colourful albedo",
    "Retro_PS1":          "retro PS1 low-poly look, affine-texture wobble, dithering, 256-colour palette",
    "Comic_Book_Halftone": "comic-book halftone shading, bold inking, screen-tone dots, vintage CMYK offset",
    "Ink_Wash_SumiE":     "Japanese sumi-e ink wash, minimal brushwork, dynamic negative space, rice-paper texture",

    # (total entries = 40)
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
