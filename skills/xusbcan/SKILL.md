---
name: xusbcan
description: Use when an agent must send, receive, monitor, or periodically transmit CAN frames with xusbcan-cli, xusbcan-mcp, or python-can interface zlg, including a long-running script that runs without an agent. Also when receive goes empty after a filter change, transmit blocks with no ACK, hardware periodic send conflicts with normal transmit, or the device will not reopen right after close.
license: MIT
compatibility: Python 3.11+. The zlg backend needs a user-supplied vendor SDK via the ZLG_SDK_DIR environment variable.
metadata:
  author: xusbcan-cli
  version: "1.0"
---

# xusbcan

## Overview

Drive the bus through the public CLI, MCP tools, or `python-can` (`interface="zlg"`). Keep one process open for a long session. Do not invent vendor calls, and do not put machine-local paths or private notes into files that will be committed.

## When to use

- One-shot send, receive, monitor, or status
- A session that stays open (periodic transmit, repeated receive)
- An offline script that must keep running after the agent exits
- Receive suddenly empty, transmit hangs, or reopen fails immediately after close

When not to use: changing product firmware, writing a new vendor backend, or editing ignored local design notes.

## Before calling the hardware

1. `ZLG_SDK_DIR` points at the SDK directory the user installed (never hard-code a disk path).
2. `xusbcan.toml` (or `XUSBCAN_CONFIG`) names the device alias, channel, and bitrate.
3. Confirm with `xusbcan list` before the first send.

## Which interface

| Need | Use |
|------|-----|
| One command, then exit | CLI: `list` `send` `receive` `monitor` `status` |
| Agent tools, session, software periodic | MCP: `open_device`, `send_frame`, `receive_frame`, `monitor`, `periodic_start` / `periodic_stop` / `periodic_list`, `close_device` |
| Hours-long send/receive with no agent | One Python process holding `can.Bus` or a core session |

CLI and one-shot MCP calls open and close the device each time. Do not loop them for a long job.

Stdout of the CLI is one JSON object. Branch on `status` and `error.code`. A receive timeout is success with no frame, not a crash.

Details and copy-paste templates: [references/examples.md](references/examples.md). Failures: [references/pitfalls.md](references/pitfalls.md).

## Long-running script

```python
import can

bus = can.Bus(interface="zlg", channel=1, bitrate=250_000)  # match xusbcan.toml
task = bus.send_periodic(
    can.Message(arbitration_id=0x123, data=[0x01, 0x02], is_extended_id=False),
    period=0.1,
)
try:
    while True:
        msg = bus.recv(timeout=0.5)
        if msg is not None:
            pass  # handle msg
finally:
    task.stop()
    bus.shutdown()
```

Use the channel and bitrate from the project config. Stop the periodic task before shutdown.

## Safety

Do not set a custom serial number, a non-standard baud encoding, a persistent device config, or listen-only mode from an automated script. Those can survive power cycle or leave the device unable to open. See [references/pitfalls.md](references/pitfalls.md).

## Privacy

Public skills and commits may name `ZLG_SDK_DIR` and neutral IDs such as `0x123`. They must not contain absolute paths, customer or ECU names, or text copied from local-only notes. Before any `git add` / `commit` in this repo, run the full desensitization checklist in `CLAUDE.md`.

## Maintenance

Update this skill when CLI or MCP names change, or when a pitfall is safe to publish. Keep board-specific notes out of the repository.
