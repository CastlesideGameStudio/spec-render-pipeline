# Example Dockerfile – replace the stub
# Installs Python 3.11, clones ComfyUI, copies your graphs, etc.

FROM python:3.11-slim AS base
LABEL maintainer="CastlesideGameStudio"

# 1) Install OS-level dependencies (e.g., git, wget)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# 2) Create a workspace directory
WORKDIR /app

# 3) Clone ComfyUI (or you can do a git clone of your own code if you prefer)
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# 4) Copy your local graphs/*.json into the container
#    (assuming your repo has a folder named "graphs" at the root)
COPY graphs/*.json /app/ComfyUI/flows/

# 5) Install Python dependencies (if ComfyUI or your code needs them)
#    Example: pip install some library
RUN pip install --no-cache-dir torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu

# 6) (Optional) Download or copy your checkpoint .safetensors
#    If you store your stable diffusion models in the container, do something like:
# COPY checkpoints/*.safetensors /app/checkpoints/
# or
# RUN wget -O /app/checkpoints/model.safetensors https://...link...
# adjust as needed

# 7) Set an entrypoint or CMD that runs ComfyUI (or your script)
#    Example: run ComfyUI with default settings
WORKDIR /app/ComfyUI
CMD ["python", "main.py", "--dont-open-browser"]

