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

If the admin UI only shows build steps + CMD (no free-form Dockerfile):

| Field | Value |
| --- | --- |
| Build steps | `pip install --no-cache-dir ".[mcp]"` |
| CMD arguments | `xusbcan-mcp` (one argument), or `python` + `-m` + `xusbcan.mcp.server` |
| Environment variables schema | see below |
| Placeholder parameters | `{}` |
| Pinned commit SHA | empty (use latest after Sync) |

Environment variables JSON schema (single-line in the form if required):

```json
{"type":"object","properties":{"XUSBCAN_CONFIG":{"type":"string","description":"Path to xusbcan.toml"}},"required":[]}
```

If the form cannot set `XUSBCAN_CONFIG`, the cloned repo’s root `xusbcan.toml` is
enough for `tools/list` (devices register; open needs host drivers for real
models). Prefer setting:

`XUSBCAN_CONFIG=/app/docker/xusbcan.toml`

so sandbox probes that call `open` still use `virtual`.

## After release

- Discovery score should leave the “No Glama release” blocker.
- Server Coherence / TDQS may fill after Glama introspects tools.
- Real CAN use remains a **local** install (`uvx` / pip + vendor SDK), not this image.
