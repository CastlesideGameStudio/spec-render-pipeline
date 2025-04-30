FROM python:3.11

LABEL maintainer="Your Name <you@example.com>"

# ───────────────────── system packages + AWS CLI ────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl unzip ca-certificates libgl1 jq && \
    rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip" && \
    unzip /tmp/awscliv2.zip -d /tmp && \
    /tmp/aws/install && \
    rm -rf /tmp/aws*

# ───────────────────── Python packages ──────────────────────────────────────
# 1) keep pip fresh + always-needed libs
RUN pip install --no-cache-dir --upgrade pip pyyaml einops

# 2) heavy PyTorch stack (CUDA 11.8) + xformers
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cu118 \
    torch torchvision safetensors xformers

# 3) torchaudio CPU build (avoids libcudart.so.12 requirement)
RUN pip install --no-cache-dir torchaudio==2.2.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# ───────────────────── ComfyUI ──────────────────────────────────────────────
WORKDIR /app
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI
RUN pip install --no-cache-dir -r /app/ComfyUI/requirements.txt

# ───────────────────── graphs & checkpoints ─────────────────────────────────
COPY graphs/ /app/ComfyUI/flows/
RUN echo "[DEBUG] Copied $(find /app/ComfyUI/flows -type f -name '*.json' | wc -l) graph(s):" && \
    ls -1 /app/ComfyUI/flows || true

RUN mkdir -p /app/ComfyUI/models/checkpoints
COPY checkpoints/ /tmp/ckpt-staging/
RUN find /tmp/ckpt-staging -type f -name '*.safetensors' \
        -exec cp {} /app/ComfyUI/models/checkpoints/ \; && \
    echo "[DEBUG] Copied $(ls -1 /app/ComfyUI/models/checkpoints | wc -l) checkpoint(s):" && \
    ls -1 /app/ComfyUI/models/checkpoints || true && \
    rm -rf /tmp/ckpt-staging

# ───────────────────── entrypoint ───────────────────────────────────────────
COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && \
    echo "[DEBUG] Entrypoint copied and made executable:" && \
    ls -l /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
