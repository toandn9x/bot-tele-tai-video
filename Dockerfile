FROM python:3.12-slim

# FFmpeg để merge video+audio chất lượng cao
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Log hiện ngay lập tức, không bị buffer
ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
