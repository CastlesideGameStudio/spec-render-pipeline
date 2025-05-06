#!/usr/bin/env python3
"""
Generate 3×1 orthographic sprite-sheets with PixArt-α XL.

Local  → outputs/<Style>/sheet/<stem>.png  
Remote → castlesidegamestudio-spec-sheets/<YYYYMMDD>/<Style>/sheet/<stem>.png  
A README.txt is uploaded at <YYYYMMDD>/ to prove the prefix is writable.
"""

from __future__ import annotations

# ───────────────────── Determinism before heavy imports ────────────────────
import os as _os
_os.environ.setdefault("TRANSFORMERS_NO_GGML", "1")
_os.environ.setdefault("TRANSFORMERS_NO_TF",  "1")
_os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
_os.environ.setdefault("PYTHONHASHSEED", "0")

# ───────────────────────── Std-lib / third-party ───────────────────────────
import glob, json, os, random, subprocess, sys, time, tempfile, shutil, hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import torch
torch.use_deterministic_algorithms(True, warn_only=False)

from PIL import Image                           # noqa: F401
from diffusers import DiffusionPipeline

# ==== 1) FULL STYLE TABLE (unchanged) ======================================
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
    "Neon_Wireframe":        "glowing neon wireframe, dark background, synth-grid",
}

# ==== 2) helpers ===========================================================
def req(key: str) -> str:
    v = os.getenv(key)
    if not v:
        sys.exit(f"[ERROR] env '{key}' is required")
    return v

def load_prompts(pattern: str) -> List[Tuple[str, str]]:
    prompts: list[Tuple[str, str]] = []
    for path in glob.glob(pattern, recursive=True):
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                if ln.strip():
                    d = json.loads(ln)
                    txt = d.get("text") or d.get("prompt") or ""
                    if txt.strip():
                        prompts.append((Path(path).stem, txt.strip()))
    if not prompts:
        sys.exit(f"[ERROR] no prompts matched {pattern!r}")
    return prompts

def seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

def sha256_png(img: "Image.Image") -> str:
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return hashlib.sha256(buf.getvalue()).hexdigest()

# ---- AWS CLI helpers ------------------------------------------------------
BUCKET   = "castlesidegamestudio-spec-sheets"
S3_EP    = req("LINODE_S3_ENDPOINT")        # e.g. https://us-east-1.linodeobjects.com
DATE_STR = datetime.now(timezone.utc).strftime("%Y%m%d")

# ── NEW : map Linode creds → AWS CLI & print masked preview ───────────────
LINODE_KEY    = os.getenv("LINODE_ACCESS_KEY_ID")
LINODE_SECRET = os.getenv("LINODE_SECRET_ACCESS_KEY")
if not LINODE_KEY or not LINODE_SECRET:
    sys.exit("[ERROR] Linode S3 credentials are missing in the pod env")

os.environ["AWS_ACCESS_KEY_ID"]     = LINODE_KEY
os.environ["AWS_SECRET_ACCESS_KEY"] = LINODE_SECRET

def _mask(s: str) -> str:
    return f"{s[:4]}…{s[-4:]}" if len(s) > 8 else "****"

print(f"[INFO] Using creds  ID={_mask(LINODE_KEY)}  SECRET={_mask(LINODE_SECRET)}")

def ensure_awscli() -> None:
    """Install AWS CLI v1 inside the pod if it's missing."""
    if shutil.which("aws") is None:
        print("[INFO] aws CLI not found – installing …")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "awscli==1.32.0"],
            check=True
        )

def create_remote_prefix() -> None:
    """Upload README.txt to <DATE_STR>/ to verify we can write to the bucket."""
    ensure_awscli()
    readme_text = (
        f"Sprite-sheets uploaded {DATE_STR} by generate_pixart.py\n"
        f"Layout: <Style>/sheet/<file>.png • one image per (prompt×style).\n"
    )
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        tmp.write(readme_text)
        tmp_path = tmp.name
    uri = f"s3://{BUCKET}/{DATE_STR}/README.txt"
    subprocess.run(
        ["aws", "--endpoint-url", S3_EP, "s3", "cp", tmp_path, uri, "--only-show-errors"],
        check=True
    )
    os.remove(tmp_path)
    print(f"[OK] verified remote prefix {DATE_STR}/ (README.txt created)")

def s3_upload(local_path: Path, style: str) -> None:
    ensure_awscli()
    rel_key = f"{DATE_STR}/{style}/sheet/{local_path.name}"
    uri     = f"s3://{BUCKET}/{rel_key}"
    res = subprocess.run(
        ["aws", "--endpoint-url", S3_EP, "s3", "cp", str(local_path), uri, "--only-show-errors"],
        capture_output=True, text=True
    )
    if res.returncode:
        print(f"[WARN] S3 upload failed → {rel_key}\n{res.stderr}", file=sys.stderr)
    else:
        print(f"      -> uploaded {rel_key}")

# ==== 3) main ==============================================================  
def main() -> None:
    t0 = time.perf_counter()

    model_id  = req("MODEL_ID")
    pattern   = req("PROMPT_GLOB")
    base_seed = int(req("SEED"))
    width     = int(os.getenv("WIDTH",  "3072"))
    height    = int(os.getenv("HEIGHT", "1024"))
    ortho     = os.getenv("ORTHO", "true").lower() == "true"
    model_rev = os.getenv("MODEL_REV") or None

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipe = DiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        revision=model_rev,
    ).to(device)

    # --- make sure bucket prefix is writable
    create_remote_prefix()

    out_root = Path("outputs")
    out_root.mkdir(exist_ok=True)

    prompts = load_prompts(pattern)
    total   = len(prompts) * len(STYLES)
    counter = 0

    for stem, subj in prompts:
        for s_idx, (style, style_desc) in enumerate(STYLES.items(), start=1):
            seed = base_seed + s_idx * 1000
            seed_everything(seed)
            gen = torch.Generator(device).manual_seed(seed)

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
                generator           = gen,
            ).images[0]

            save_dir = out_root / style / "sheet"
            save_dir.mkdir(parents=True, exist_ok=True)
            out_path = save_dir / f"{stem}.png"
            image.save(out_path)
            print(f"      -> saved {out_path.relative_to(out_root)}")

            s3_upload(out_path, style)
            counter += 1

    dt = time.perf_counter() - t0
    print(f"[OK] Completed → {counter} sheets ({dt/60:4.1f} min)")

# ==== 4) smoke-test mode ===================================================
if __name__ == "__main__":
    if "--smoke-test" in sys.argv or os.getenv("SMOKE_TEST") == "1":
        os.environ.setdefault("WIDTH",  "96")
        os.environ.setdefault("HEIGHT", "32")
        os.environ.setdefault("SEED",   "42")
        print("[SMOKE] 32×96 deterministic canary …")
        main()
        p = next(Path("outputs").rglob("*.png"))
        print(f"[SMOKE] SHA-256 = {sha256_png(Image.open(p))}")
        sys.exit(0)
    main()
