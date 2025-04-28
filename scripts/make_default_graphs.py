#!/usr/bin/env python3
"""
make_default_graphs.py

Generates one ComfyUI JSON workflow per style, referencing the .safetensors
file for each style's checkpoint.

Usage:
  python make_default_graphs.py [output_dir]

If no output_dir is given, defaults to "graphs/".

Example styles:
  • BloodMagic   -> "Blood_Magic_-_Grimoire-000011.safetensors"
  • Disney       -> "Disney_Nouveau.safetensors"
  • MagicalLines -> "iLLMythM4gicalL1nes.safetensors"
  • SemiReal     -> "Semi-real pretty fantasy - IL.safetensors"
"""

import json
import pathlib
import textwrap
import sys

# Minimal template for a ComfyUI graph with a CheckpointLoaderSimple node
TEMPLATE = textwrap.dedent("""\
{
  "nodes": [
    {
      "id": 1,
      "type": "CheckpointLoaderSimple",
      "output": "MODEL",
      "inputs": {
        "ckpt_name": "%(ckpt)s"
      }
    },
    {
      "id": 2,
      "type": "CLIPTextEncode",
      "output": "CONDITIONING",
      "inputs": {
        "text": "PLACEHOLDER_PROMPT"
      }
    },
    {
      "id": 3,
      "type": "KSampler",
      "output": "LATENT",
      "inputs": {
        "model": 1,
        "cond": 2,
        "steps": 20,
        "cfg": 7
      }
    },
    {
      "id": 4,
      "type": "VAEDecode",
      "output": "IMAGE",
      "inputs": {
        "samples": 3
      }
    },
    {
      "id": 5,
      "type": "SaveImage",
      "inputs": {
        "images": 4
      }
    }
  ],
  "style": "%(style)s"
}
""")

# Map each style to the .safetensors checkpoint filename.
CKPTS = {
    "BloodMagic":   "Blood_Magic_-_Grimoire-000011.safetensors",
    "Disney":       "Disney_Nouveau.safetensors",
    "MagicalLines": "iLLMythM4gicalL1nes.safetensors",
    "SemiReal":     "Semi-real pretty fantasy - IL.safetensors",
}

def main():
    # Determine output directory from command-line arg or default to 'graphs'
    if len(sys.argv) > 1:
        outdir = pathlib.Path(sys.argv[1])
    else:
        outdir = pathlib.Path("graphs")

    # Make sure the output directory exists
    outdir.mkdir(parents=True, exist_ok=True)

    # Create a ComfyUI workflow file for each style
    for style, ckpt_filename in CKPTS.items():
        graph_json = TEMPLATE % {"style": style, "ckpt": ckpt_filename}
        outpath = outdir / f"graph_{style}.json"
        outpath.write_text(graph_json, encoding="utf-8")
        print(f"[INFO] Wrote {outpath} using checkpoint '{ckpt_filename}'")

    print("[INFO] Done! Generated graphs in", outdir)

if __name__ == "__main__":
    main()
