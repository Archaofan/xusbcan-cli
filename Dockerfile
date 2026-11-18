# Minimal MCP image for Glama build tests / local smoke.
# Starts stdio MCP with python-can virtual buses only — not a substitute for
# host installs with vendor SDKs and real USB-CAN hardware.

FROM python:3.12-slim-bookworm

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY docker ./docker

RUN pip install --no-cache-dir ".[mcp]"

ENV XUSBCAN_CONFIG=/app/docker/xusbcan.toml

# Glama may wrap this with mcp-proxy; keep stdio as the default transport.
CMD ["xusbcan-mcp"]
