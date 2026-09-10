FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg yt-dlp \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY data ./data

RUN pip install --no-cache-dir .

ENV SONICMATCH_CACHE_DIR=/data/cache
VOLUME ["/data/cache"]

EXPOSE 8765
ENTRYPOINT ["sonicmatch-mcp"]
CMD ["--http", "--host", "0.0.0.0", "--port", "8765"]
