FROM python:3.12-slim-bookworm

# FFmpeg (merge video+audio) + Cloudflare WARP (proxy lách chặn IP datacenter của YouTube)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl gnupg ca-certificates \
    && curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ bookworm main" > /etc/apt/sources.list.d/cloudflare-client.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends cloudflare-warp \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# Log hiện ngay lập tức, không bị buffer
ENV PYTHONUNBUFFERED=1

CMD ["./entrypoint.sh"]
