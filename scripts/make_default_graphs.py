#!/usr/bin/env python3
"""
python scripts/make_default_graphs.py graphs/

make_default_graphs.py

Scans a directory (default Y:\\CastlesideGameStudio\\safetensors) for all *.safetensors
files and generates one ComfyUI JSON workflow per file.

Usage:
  python make_default_graphs.py [output_dir]

If no output_dir is given, defaults to "graphs/".

Each resulting JSON file is named like: graph_<stem_of_safetensors>.json
For example, "Disney_Nouveau.safetensors" becomes "graph_Disney_Nouveau.json".

We embed the style name into node #1 under the key "extra_style_info" so that there's
no extra top-level key (like "metadata") to confuse certain extensions.
"""

import json
import pathlib
import textwrap
import sys

# Location of your *.safetensors files
SAFETENSORS_DIR = r"Y:\CastlesideGameStudio\safetensors"

# Minimal template for a ComfyUI graph:
# The first node has an additional "extra_style_info" so you can see the style.
TEMPLATE = textwrap.dedent("""\
{
  "nodes": [
    {
      "id": 1,
      "type": "CheckpointLoaderSimple",
      "extra_style_info": "%(style)s",
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
  ]
}
""")

def main():
    # Output directory from command-line argument, else "graphs/"
    if len(sys.argv) > 1:
        outdir = pathlib.Path(sys.argv[1])
    else:
        outdir = pathlib.Path("graphs")
    outdir.mkdir(parents=True, exist_ok=True)

    # Path to your safetensors directory
    safedir = pathlib.Path(SAFETENSORS_DIR)

    # Find all *.safetensors
    safetensors_list = sorted(safedir.glob("*.safetensors"))
    if not safetensors_list:
        print(f"[WARNING] No .safetensors found in: {safedir}")
        return

    for safepath in safetensors_list:
        # style is derived from the stem of the file (minus extension)
        style_name = safepath.stem
        # filename only (no directories)
        ckpt_filename = safepath.name

        # Fill in the template
        graph_json_str = TEMPLATE % {
            "style": style_name,
            "ckpt":  ckpt_filename
        }

        # Output path: e.g. "graph_Disney_Nouveau.json"
        outpath = outdir / f"graph_{style_name}.json"
        outpath.write_text(graph_json_str, encoding="utf-8")

        print(f"[INFO] Created {outpath} referencing '{ckpt_filename}' (extra_style_info='{style_name}')")

    print("[INFO] Done! Generated graphs in", outdir)

if __name__ == "__main__":
    main()
