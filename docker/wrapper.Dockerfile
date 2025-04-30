# docker/wrapper.Dockerfile
FROM valyriantech/comfyui-with-flux:latest      # community template (11 GB)

# add jq for entrypoint.sh
RUN apt-get update                             \
 && apt-get install -y --no-install-recommends jq \
 && rm -rf /var/lib/apt/lists/*

# copy and activate your driver script
COPY scripts/entrypoint.sh /workspace/entrypoint.sh
RUN chmod +x /workspace/entrypoint.sh

# start the driver when the container launches
CMD ["/workspace/entrypoint.sh"]
