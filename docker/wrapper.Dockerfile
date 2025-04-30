# Wrapper image: adds jq and your entrypoint to the Flux template
FROM valyriantech/comfyui-with-flux:latest

# install jq for entrypoint.sh
RUN apt-get update \
 && apt-get install -y --no-install-recommends jq \
 && rm -rf /var/lib/apt/lists/*

# copy and activate the driver script
COPY scripts/entrypoint.sh /workspace/entrypoint.sh
RUN chmod +x /workspace/entrypoint.sh

# run the driver on container start
CMD ["/workspace/entrypoint.sh"]
