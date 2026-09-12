FROM python:3.12-slim

LABEL io.modelcontextprotocol.server.name="io.github.js713-lab/sonicmatch-mcp"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY data ./data

RUN pip install --no-cache-dir .

ENV SONICMATCH_CACHE_DIR=/data/cache
VOLUME ["/data/cache"]

# HTTP MCP has no auth. Do not publish this port to the public internet.
EXPOSE 8765
ENTRYPOINT ["sonicmatch-mcp"]
CMD ["--http", "--host", "0.0.0.0", "--port", "8765"]
