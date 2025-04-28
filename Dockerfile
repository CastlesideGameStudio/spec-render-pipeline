# Dockerfile – GPU-based, includes safetensors, plus AWS CLI
FROM python:3.11

LABEL maintainer="Your Name <you@example.com>"

# 1. Install OS-level dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl unzip ca-certificates libgl1 \
 && rm -rf /var/lib/apt/lists/*

# 2. Install AWS CLI v2
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip" \
 && unzip /tmp/awscliv2.zip -d /tmp \
 && /tmp/aws/install \
 && rm -rf /tmp/awscliv2.zip /tmp/aws

# 3. Let pip auto-resolve Torch (CUDA 11.8) + xformers + safetensors
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cu118 \
    torch torchvision xformers safetensors

# 4. Clone ComfyUI
WORKDIR /app
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# 5. Copy your ComfyUI graphs (if you have them in "graphs/" locally)
COPY graphs/ /app/ComfyUI/flows/

# 6. Copy your scripts
COPY scripts/ /app/scripts/

# 7. Copy your checkpoints folder (if you have local .safetensors to bake in)
RUN mkdir -p /app/ComfyUI/models/checkpoints
COPY checkpoints/ /app/ComfyUI/models/checkpoints/

# 8. Copy your entrypoint script and make it executable
COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# 9. Set default CMD
CMD ["/app/entrypoint.sh"]
