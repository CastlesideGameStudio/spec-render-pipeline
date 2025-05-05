#!/usr/bin/env python3
"""
Generate a single 3 × 1 orthographic sprite-sheet (front / side / back)
for every (prompt × style) pair using **PixArt-α XL**.

What experience taught us  ────────────────────────────────────────────────
✓ ALWAYS keep `WIDTH == len(VIEWS) * per-panel-width`   
  – the model will happily smear panels together if the arithmetic is off.

✓ ALWAYS call `seed_everything()` once **per sheet** (inside the outer loop)
  so that style-to-style changes are deterministic yet independent.

✓ ALWAYS pass an explicit `torch_dtype` to `DiffusionPipeline.from_pretrained`
  or you risk loading an fp32 model on a 16-GB H100 and OOM’ing instantly.

✓ DON’T request perspective and orthographic panels in one go – the prompt
  tokens fight each other; pick one (`ORTHO=true|false`) per run.

✓ DON’T forget `variant="fp16"` when you pull PixArt-α 2-1024 – the repo’s
  default blobs are fp16; loading them as fp32 doubles VRAM.

✓ DON’T rely on PIL doing colour-space gymnastics for you – the PNGs come out
  in *sRGB, straight-alpha*.  If you post-process, stay in that space.

ENV (unchanged, validated at runtime):
  MODEL_ID, PROMPT_GLOB, SEED, WIDTH, HEIGHT, ORTHO
"""
from __future__ import annotations
import glob, json, os, random, sys, time
from pathlib import Path
from typing import List, Tuple

import torch
from PIL import Image        # noqa: F401 (import side-effects for DiffusionPipeline)
from diffusers import DiffusionPipeline

# ==== 1) ART STYLES ========================================================
# (Pure data – tweak at will.  Keys must be unique; values are appended to prompts.)
STYLES: dict[str, str] = {
    # realistic / painterly
    "Photorealistic":        "photorealistic style, high fidelity, realistic lighting, lifelike textures",
    "Hyper_Real_4K":         "ultra-detailed hyper-realism, 4K textures, ray-traced reflections",
    "Watercolor":            "water-colour / hand-painted style, soft brush strokes, blended colours",
    "Oil_Painting":          "classic oil-painting style, impasto texture, rich pigments",
    "Impressionist":         "impressionist painting, visible brush strokes, vibrant colour dabs",
    "Line_Art":              "line-art / ink sketch, high contrast, black & white, hand-drawn lines",
    "Charcoal_Sketch":       "charcoal sketch, rough shading, chiaroscuro",
    "Vintage_Comic":         "1960s vintage comic-book style, halftone dots, bold ink",
    "Propaganda_Poster":     "mid-century propaganda poster, screen-printed, limited palette",
    "Stencil_Graffiti":      "Banksy-style stencil graffiti, urban wall texture",
    # media / studio looks
    "Disney":                "Disney animation style, whimsical characters, vibrant colours",
    "Pixar":                 "Pixar style, soft volumetric lighting, expressive characters",
    "DreamWorks":            "DreamWorks animation style, stylised realism, cinematic lighting",
    "Studio_Ghibli":         "Studio Ghibli pastel palette, whimsical detail, hand-drawn feel",
    "World_of_Warcraft":     "World-of-Warcraft dark fantasy, stylised realism, ornate armour",
    "Overwatch":             "Overwatch hero style, colourful PBR materials, semi-realistic",
    "Fortnite":              "Fortnite toon PBR, saturated colours, exaggerated proportions",
    "Diablo":                "Diablo grim gothic fantasy, desaturated palette, moody lighting",
    "Soulslike_Dark":        "Souls-like dark fantasy realism, gritty textures, atmospheric haze",
    "Borderlands":           "Borderlands ink-outlined cel shading, comic-book texture",
    # stylised / 3-D renders
    "3D_Render":             "3D render style, realistic shading, detailed modelling, cinematic lighting",
    "Clay_Stopmotion":       "stop-motion clay model look, fingerprints, studio set lighting",
    "Lego_Bricks":           "Lego brick style, interlocking studs, glossy ABS plastic",
    "Papercraft":            "papercraft diorama, folded paper edges, handcrafted texture",
    "Voxel":                 "voxel-art style, blocky 3-D pixels, orthographic view",
    "Isometric_Pixel":       "isometric pixel-art, 45-degree angle, retro game aesthetic",
    "Lowpoly_Synty":         "low-poly style inspired by Synty Studios, chunky facets, flat shading",
    "Lowpoly_Polytoon":      "stylised low-poly cartoon, smooth gradients, cheerful palette",
    "Flat_Shaded":           "flat-shaded 3-D, no texture, crisp colour regions",
    "Cel_Shaded_3D":         "cel-shaded 3-D, thick outline, flat colours, comic feel",
    # cultural / decorative
    "Anime":                 "anime style, cel-shaded, crisp line art, expressive characters",
    "Manga_Monochrome":      "black-and-white manga inks, screentone shading",
    "Art_Nouveau":           "Art-Nouveau decorative style, flowing lines, floral motifs",
    "Art_Deco":              "Art-Deco geometry, gilded accents, 1920s glamour",
    "Baroque":               "baroque ornamentation, dramatic lighting, rich detail",
    "Steampunk":             "steampunk aesthetic, brass gears, victorian diesel machinery",
    "Cyberpunk":             "cyberpunk neon dystopia, holographic glow, rain-soaked streets",
    "Synthwave":             "1980s synthwave grid, neon magenta & blue, retro-future sunset",
    "Retro_Polygon":         "1990s low-poly PS1 style, affine texture warp, low-resolution",
    "Pixel_Art":             "classic pixel-art, 16-bit colour, limited palette",
    # painterly abstractions
    "Watercolour_Splatter":  "loose watercolour splatters, bleeding edges, vibrant hues",
    "Ink_Wash":              "East-Asian sumi-e ink wash, minimal brushwork",
    "Pointillism":           "pointillism dots, optical colour mixing, Seurat inspired",
    "Cubism":                "cubist abstraction, fractured geometry, multiple perspectives",
    "Surrealist":            "surrealist painting, dream-like, impossible juxtapositions",
    "Fauvism":               "fauvist wild brush strokes, non-naturalistic colours",
    # hard-surface realism
    "PBR_Realism":           "AAA PBR realism, physically-based materials, ray-traced lighting",
    "Hard_Surface_Mech":     "hard-surface mech design, clean bevels, sci-fi decals",
    "Dieselpunk":            "dieselpunk machinery, worn metal, oil stains",
    "Industrial_Noir":       "industrial noir, high-contrast lighting, rain-slick metal",
    "Military_Techpack":     "military technical illustration, exploded views, spec labels",
    "Blueprint":             "blueprint drawing, white lines on cyan background, technical style",
    # misc fun
    "Sticker_Bomb":          "die-cut sticker style, bold outlines, drop shadow, white border",
    "Holographic":           "holographic foil, iridescent rainbow sheen, lens flares",
    "Candy_Gloss":           "candy-gloss toy look, translucent plastic, subsurface glow",
    "Metallic_Painted":      "metallic auto-paint, color-shift flakes, studio reflections",
    "Neon_Wireframe":        "glowing neon wireframe, dark background, synth-grid"
}

VIEWS = ["front", "side", "back"]        # ALWAYS left → right
VIEW_GRID_W = len(VIEWS)                 # = 3
VIEW_GRID_H = 1

# ==== 2) HELPERS ===========================================================
def req(key: str) -> str:
    """Fetch required ENV var or exit with an explicit error."""
    val = os.getenv(key)
    if not val:
        sys.exit(f"[ERROR] env '{key}' is required")
    return val

def load_prompts(pattern: str) -> List[Tuple[str, str]]:
    """Load NDJSON prompt files; return list[(stem, prompt_txt)]."""
    out: list[Tuple[str, str]] = []
    for path in glob.glob(pattern, recursive=True):
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                if not ln.strip():
                    continue
                data = json.loads(ln)
                txt = data.get("text") or data.get("prompt") or ""
                if txt.strip():
                    out.append((Path(path).stem, txt.strip()))
    if not out:
        sys.exit(f"[ERROR] no prompts matched {pattern!r}")
    return out

def seed_everything(seed: int) -> None:
    """Deterministic RNG across Py + Torch + CUDA."""
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

# ==== 3) MAIN ==============================================================
def main() -> None:
    t0 = time.perf_counter()

    model_id  = req("MODEL_ID")
    pattern   = req("PROMPT_GLOB")
    base_seed = int(req("SEED"))
    width     = int(os.getenv("WIDTH",  "3072"))   # 3 × 1024
    height    = int(os.getenv("HEIGHT", "1024"))
    ortho     = os.getenv("ORTHO", "true").lower() == "true"

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipe = DiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        variant="fp16",                      # see lesson on fp16 blobs
    ).to(device)

    out_root = Path("outputs")
    out_root.mkdir(exist_ok=True)

    prompts = load_prompts(pattern)
    total   = len(prompts) * len(STYLES)
    counter = 0

    for stem, subj in prompts:
        for s_idx, (style, style_desc) in enumerate(STYLES.items(), start=1):
            seed = base_seed + s_idx * 1000         # deterministic per style
            seed_everything(seed)

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
            ).images[0]

            save_dir = out_root / style / "sheet"
            save_dir.mkdir(parents=True, exist_ok=True)
            out_path = save_dir / f"{stem}.png"
            image.save(out_path)

            counter += 1
            print(f"      -> saved {out_path.relative_to(out_root)}")

    dt = time.perf_counter() - t0
    print(f"[OK] Completed -> {counter} sheets ({dt/60:4.1f} min total)")

if __name__ == "__main__":
    main()
