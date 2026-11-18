# Glama release (Dockerfile admin)

Listing: https://glama.ai/mcp/servers/Archaofan/xusbcan-cli

A **Glama release is not a GitHub release**. Glama builds a container, starts the
MCP server, and checks `initialize` + `tools/list`. This repo’s `Dockerfile` is
for local smoke and for admins who can point at a repository Dockerfile. The
admin page may instead use a **structured form** that generates the image.

## Preferred: repository Dockerfile

On https://glama.ai/mcp/servers/Archaofan/xusbcan-cli/admin/dockerfile :

1. Sync the GitHub mirror so HEAD includes this `Dockerfile` and `docker/`.
2. If the UI accepts a Dockerfile path, use the repo-root `Dockerfile`.
3. Click **Build** / **Deploy**.
4. On success, **Make Release** → version `0.1.3` → publish.

Local check (when Docker is available):

```bash
docker build -t xusbcan-mcp:glama .
docker run --rm -i xusbcan-mcp:glama
```

The image sets `XUSBCAN_CONFIG=/app/docker/xusbcan.toml` (python-can `virtual`
only). It does **not** talk to real CAN hardware.

## Fallback: Glama generated build form

Glama generates its own Dockerfile (clone into `/app`, wrap with `mcp-proxy`).
Do **not** use `uv pip install --system`: on `debian:trixie-slim` that targets the
distro Python and fails with “externally managed”.

| Field | Value |
| --- | --- |
| Base image | `debian:trixie-slim` |
| Node.js | `24` (mcp-proxy) |
| Python | `3.12` |
| Build steps | see JSON below |
| CMD arguments | see JSON below |
| Environment variables schema | see below (`required` must be `[]`) |
| Placeholder parameters | `{"XUSBCAN_CONFIG":"/app/docker/xusbcan.toml"}` |
| Pinned commit SHA | empty (or current HEAD after Sync) |

Build steps:

```json
[
  "uv venv /opt/venv && uv pip install --python /opt/venv/bin/python \".[mcp]\""
]
```

CMD arguments:

```json
[
  "mcp-proxy",
  "--",
  "/opt/venv/bin/xusbcan-mcp"
]
```

Environment variables JSON schema:

```json
{
  "type": "object",
  "properties": {
    "XUSBCAN_CONFIG": {
      "type": "string",
      "description": "Path to xusbcan.toml. For Glama smoke use /app/docker/xusbcan.toml (virtual only)."
    },
    "ZLG_SDK_DIR": {
      "type": "string",
      "description": "Optional host path to ZLG SDK; not used in Glama sandbox."
    },
    "CHUANGXIN_SDK_DIR": {
      "type": "string",
      "description": "Optional host path to Chuangxin SDK; not used in Glama sandbox."
    }
  },
  "required": []
}
```

## After release

- Discovery score should leave the “No Glama release” blocker.
- Server Coherence / TDQS fill after Glama introspects tools from a successful build.
- After improving MCP tool descriptions/annotations in `src/xusbcan/mcp/tools.py`,
  Sync → Build again (same form values) so Glama re-reads `tools/list`, then check
  Admin → TDQS. No need to bump the Glama release version unless you want a new publish.
- Real CAN use remains a **local** install (`uvx` / pip + vendor SDK), not this image.
