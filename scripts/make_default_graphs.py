# scripts/make_default_graphs.py
import json, pathlib, textwrap, sys

TEMPLATE = textwrap.dedent("""\
{
  "nodes": [
    { "id": 1, "type": "CheckpointLoaderSimple", "output": "MODEL",
      "inputs": { "ckpt_name": "%(ckpt)s" } },
    { "id": 2, "type": "CLIPTextEncode", "output": "CONDITIONING",
      "inputs": { "text": "PLACEHOLDER_PROMPT" } },
    { "id": 3, "type": "KSampler", "output": "LATENT",
      "inputs": { "model": 1, "cond": 2, "steps": 20, "cfg": 7 } },
    { "id": 4, "type": "VAEDecode", "output": "IMAGE",
      "inputs": { "samples": 3 } },
    { "id": 5, "type": "SaveImage", "inputs": { "images": 4 } }
  ],
  "style": "%(style)s"
}
""")

CKPTS = {
  "flat3t":  "sdxl_turbo.safetensors",
  "lowpoly": "lowpoly.safetensors",
  "albion":  "albion_lora.safetensors",
  "handpt":  "handpainted.safetensors",
  "real":    "realistic_photo_v2.safetensors",
  "anime":   "anime_castlevania.safetensors",
}

outdir = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "graphs")
outdir.mkdir(parents=True, exist_ok=True)

for style, ckpt in CKPTS.items():
    (outdir / f"graph_{style}.json").write_text(
        TEMPLATE % {"style": style, "ckpt": ckpt}
    )

print("Wrote graphs to", outdir)
