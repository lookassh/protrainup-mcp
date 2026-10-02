# protrainup-mcp as an HTTP (streamable-http) MCP sidecar.
# The endpoint is unauthenticated - run it on a private docker network
# (see compose.yml) or behind an authenticating reverse proxy.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# install dependencies first for better layer caching
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PROTRAINUP_MCP_TRANSPORT=http \
    PROTRAINUP_MCP_HOST=0.0.0.0 \
    PROTRAINUP_MCP_PORT=8000 \
    UV_NO_SYNC=1

EXPOSE 8000

# drop root for the runtime
USER 65534:65534

ENTRYPOINT ["uv", "run", "--no-dev", "protrainup-mcp"]
