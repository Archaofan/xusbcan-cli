---
name: xusbcan
description: Use when an agent must send, receive, monitor, or periodically transmit CAN frames with xusbcan-cli, xusbcan-mcp, or a python-can interface named in xusbcan config, including a long-running script. Also when the adapter model is still unknown. When the configured model is Zhou Ligong USBCAN-2E-U, also when receive goes empty after a filter change, transmit blocks with no ACK, hardware periodic send conflicts with normal transmit, or the device will not reopen right after close.
license: MIT
compatibility: Python 3.11+. Drivers depend on the backend named in the config. Read a model reference only when that model is the one configured.
metadata:
  author: xusbcan-cli
  version: "1.3"
---

# xusbcan

## Overview

Identify the adapter from `xusbcan.toml` before opening it. Then use the public CLI, MCP tools, or one resident process. Command names do not change with the vendor. The driver, channel, and `extra` keys do.

Set `interface` to a backend python-can already declares (`socketcan`, `pcan`, `kvaser`, `slcan`, `vector`, …). That opens through the CLI and MCP. No model row is required. `vendor` / `model` are optional shortcuts that add a channel map or fixed options. If `interface` is set, those shortcuts are not applied.

A card python-can does not declare needs a backend under `adapters/<vendor>/`. Installing the driver is still required. A known interface name does not mean the hardware was verified here.

Do not invent vendor calls, and do not put machine-local paths or private notes into files that will be committed.

## When to use

- One-shot send, receive, monitor, or status
- A session that stays open (periodic transmit, repeated receive)
- An offline script that must keep running after the agent exits
- The config names any python-can backend, or the backend is not chosen yet

When not to use: changing product firmware, or editing ignored local design notes.

## Before calling the hardware

1. Read `interface`, or `vendor` / `model`, from `xusbcan.toml`. Do not reuse another card's driver steps.
2. Shared setup: alias, channel, bitrate, and `XUSBCAN_CONFIG` or `./xusbcan.toml`. Confirm with `xusbcan list`.
3. Open a model reference only after the name matches. For `vendor = "zlg"` and `model = "USBCAN-2E-U"`, or `interface = "zlg"`, read [references/zlg-usbcan-2e-u.md](references/zlg-usbcan-2e-u.md). Do not open that file for any other card.

## Which interface

| Need | Use |
|------|-----|
| One command, then exit | CLI: `list` `send` `receive` `monitor` `status` `periodic` |
| Millisecond send→wait→send script | CLI: `scenario --file`, or `xusbcan.scenario.run_scenario` |
| Agent tools, session, periodic, scenario | MCP: `open_device`, `send_frame`, `receive_frame`, `monitor`, `periodic_start` / `periodic_stop` / `periodic_list`, `set_frame_filter`, `accept_all_frames`, `run_scenario`, `close_device` |
| Hours-long send/receive with no agent | One Python process holding `can.Bus` or a core session |

`receive` and `monitor` take `--from-id` and `--to-id` for one range. `set_frame_filter` does the same on an open session. `accept_all_frames` restores full reception. `periodic` runs until `--duration` elapses. MCP `periodic_start` keeps the task until `periodic_stop`.

CLI and one-shot MCP calls open and close the device each time. Do not loop them for a long job.

Stdout of the CLI is one JSON object. Branch on `status` and `error.code`. A receive timeout is success with no frame, not a crash.

Templates: [references/examples.md](references/examples.md). Shared failures: [references/pitfalls.md](references/pitfalls.md).

## Long-running script

Use the `interface` and `channel` from the config. The snippet uses socketcan only as a shape. Replace both when the config names a different backend.

```python
import can

bus = can.Bus(interface="socketcan", channel="can0", bitrate=500_000)
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

Stop the periodic task before shutdown.

## Privacy

Public skills and commits may name an environment variable the backend documents, and neutral IDs such as `0x123`. They must not contain absolute paths, customer or ECU names, or text copied from local-only notes. Before any `git add` / `commit` in this repo, run the full desensitization checklist in `CLAUDE.md`.

## Maintenance

Update this skill when CLI or MCP names change. Put a new card's driver steps and pitfalls in `references/<model>.md`, and link that file only from the step that checks the model name. Keep board-specific notes out of the repository. When a vendor SDK is wrapped, add that vendor to the README disclaimer.
