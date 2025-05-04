#!/usr/bin/env python3
"""
python scripts/make_default_graphs.py [output_dir]

Scans a directory (default Y:\\CastlesideGameStudio\\safetensors) for all *.safetensors
files and generates one ComfyUI JSON workflow per file.

Outputs a JSON whose top-level structure is:
{
  "prompt": [
    {
      "id": 1,
      "class_type": "CheckpointLoaderSimple",
      ...
    },
    ...
  ]
}

No extra metadata keys, no additional top-level fields, etc.
"""

import json
import pathlib
import textwrap
import sys

# Location of your *.safetensors files
SAFETENSORS_DIR = r"Y:\CastlesideGameStudio\safetensors"

# Minimal template for a ComfyUI graph: 
# We'll produce a top-level 'prompt' array of node dicts.
# All nodes use "class_type" rather than "type".
# We do not store a "style" or "metadata" key, to avoid 
# confusion with certain custom extensions.
NODE_TEMPLATE = [
    {
        "id": 1,
        "class_type": "CheckpointLoaderSimple",
        "output": "MODEL",
        "inputs": {
            "ckpt_name": None  # we'll fill in
        }
    },
    {
        "id": 2,
        "class_type": "CLIPTextEncode",
        "output": "CONDITIONING",
        "inputs": {
            "text": "PLACEHOLDER_PROMPT"
        }
    },
    {
        "id": 3,
        "class_type": "KSampler",
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
        "class_type": "VAEDecode",
        "output": "IMAGE",
        "inputs": {
            "samples": 3
        }
    },
    {
        "id": 5,
        "class_type": "SaveImage",
        "inputs": {
            "images": 4
        }
    }
]

def main():
    if len(sys.argv) > 1:
        outdir = pathlib.Path(sys.argv[1])
    else:
        outdir = pathlib.Path("graphs")
    outdir.mkdir(parents=True, exist_ok=True)

    safedir = pathlib.Path(SAFETENSORS_DIR)

    safetensors_list = sorted(safedir.glob("*.safetensors"))
    if not safetensors_list:
        print(f"[WARNING] No .safetensors files found in: {safedir}")
        return

    for safepath in safetensors_list:
        style_name = safepath.stem
        ckpt_filename = safepath.name

        # Deep copy the template so each file gets its own structure
        node_list = json.loads(json.dumps(NODE_TEMPLATE))

        # Insert the correct ckpt_name
        node_list[0]["inputs"]["ckpt_name"] = ckpt_filename

        # We'll produce a single JSON: 
        # { "prompt": [ {class_type:..} , ... ] }
        graph_data = {
            "prompt": node_list
        }

        outpath = outdir / f"graph_{style_name}.json"
        with outpath.open("w", encoding="utf-8") as f:
            json.dump(graph_data, f, indent=2)

        print(f"[INFO] Created {outpath} referencing '{ckpt_filename}'")

    print("[INFO] Done! Generated graphs in", outdir)

if __name__ == "__main__":
    main()
