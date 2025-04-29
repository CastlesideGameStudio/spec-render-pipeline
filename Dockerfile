FROM python:3.11

LABEL maintainer="Your Name <you@example.com>"

# 1) System dependencies + AWS CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl unzip ca-certificates libgl1 \
 && rm -rf /var/lib/apt/lists/*

RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip" \
 && unzip /tmp/awscliv2.zip -d /tmp \
 && /tmp/aws/install \
 && rm -rf /tmp/aws*

# 2) Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# 3) Install torch + torchvision + safetensors in one step (no xformers yet)
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cu118 \
    torch torchvision safetensors

# 4) Then install xformers in a separate step
RUN pip install --no-cache-dir xformers

# 5) Clone ComfyUI
WORKDIR /app
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# 6) Copy your ComfyUI graphs
COPY graphs/ /app/ComfyUI/flows/
RUN echo "[DEBUG] Copied $(find /app/ComfyUI/flows -type f -name '*.json' | wc -l) graph(s):" \
 && ls -1 /app/ComfyUI/flows || true

# 7) Copy scripts, checkpoints, etc.
COPY scripts/ /app/scripts/
RUN mkdir -p /app/ComfyUI/models/checkpoints
COPY checkpoints/ /app/ComfyUI/models/checkpoints/
RUN echo "[DEBUG] Copied $(find /app/ComfyUI/models/checkpoints -type f -name '*.safetensors' | wc -l) checkpoint(s):" \
 && ls -1 /app/ComfyUI/models/checkpoints || true

# 8) Make entrypoint executable + set as default CMD
COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh \
 && echo "[DEBUG] Entrypoint copied and made executable:" \
 && ls -l /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
