# Vendor ModelName

**Maintainer template only**—agents must not load this file for a live session. Copy it when adding a card, then fill and register a row in [catalog.md](catalog.md).

Read the filled model page **only** when the config (or user) names that exact card. Do not apply one model page to other vendors or models.

## Quick start

1. Env / driver: …
2. Minimal `xusbcan.toml` alias: …

```toml
[[devices]]
name = "bus0"
vendor = "…"
model = "…"
channel = 0
nominal = 500000
```

3. One-shot: `xusbcan send bus0 --id 0x123 --data "01 02"` (see [examples.md](examples.md) for MCP / scenario).
4. Channel / bitrate / `extra` rules for **this** card only. Multi-port cards: document port→`channel` mapping in Quick start / How this backend behaves; treat snippet `channel` as a placeholder. If vendor device-info APIs can misreport model or channel count, state that under How this backend behaves (do not rely on Field notes alone).

## How this backend behaves in xusbcan

Facts about **this repo’s** adapter path (filter path, periodic path, FD support). Prefer these over copying another model page.

## Field notes (not guarantees)

Items below were **reported by earlier contributors on a specific bench**. They may not reproduce on your unit, driver version, or bus. They are **not** a formal unsupported-feature list and **not** proof that every card of this model is defective. Match the current symptom before acting; if it does not match, ignore the note and debug from CLI/MCP `error.code` and the vendor’s own docs.

- …

## Resident script

```python
import can
# match interface / channel / bitrate / extra to this model's config
```
