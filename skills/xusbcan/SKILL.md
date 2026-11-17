---
name: xusbcan
description: Use when an agent must send, receive, monitor, or periodically transmit CAN frames with xusbcan-cli, xusbcan-mcp, or a python-can interface named in xusbcan config, including a long-running script. Also when the physical adapter or python-can interface name is still unknown, or when a Zhou Ligong USBCAN-2E-U shows empty receive after a filter change, transmit that blocks with no ACK, hardware periodic send that conflicts with normal transmit, or a device that will not reopen right after close.
license: MIT
compatibility: Python 3.11+. Drivers and SDK depend on the adapter model. The verified ZLG USBCAN-2E-U needs ZLG_SDK_DIR. Other registered models do not use that variable.
metadata:
  author: xusbcan-cli
  version: "1.1"
---

# xusbcan

## Overview

Identify the adapter before opening it. Then use the public CLI, MCP tools, or one resident process. Shared commands do not change with the vendor. Drivers, environment variables, and the config entry do.

Set `interface` to a backend python-can already declares (`socketcan`, `pcan`, `kvaser`, `slcan`, …). That opens through the CLI and MCP with that backend's own `channel` and `extra`. No model row is required. `vendor` / `model` are only shortcuts that add a channel map or fixed options: USBCAN-2E-U (verified on hardware), PCAN-USB, and VN1630. If `interface` is set, those shortcuts are not applied.

A card python-can does not declare needs a backend in this repo. Installing the driver is still required; a known interface name does not mean the hardware was verified here.

Do not invent vendor calls, and do not put machine-local paths or private notes into files that will be committed.

## When to use

- One-shot send, receive, monitor, or status
- A session that stays open (periodic transmit, repeated receive)
- An offline script that must keep running after the agent exits
- The card is any python-can backend, or the config has not named `interface` yet
- On a USBCAN-2E-U: receive suddenly empty, transmit hangs, hardware periodic send blocks normal send, or reopen fails immediately after close

When not to use: changing product firmware, writing a new vendor backend, or editing ignored local design notes.

## Before calling the hardware

1. Read `interface`, or `vendor` / `model`, from `xusbcan.toml`. An `interface` value must be a python-can backend name. Do not reuse another card's driver steps.
2. Shared setup: alias, channel, bitrate, and `XUSBCAN_CONFIG` or `./xusbcan.toml`. Confirm with `xusbcan list`.
3. Model-specific setup only after the card is known.
   - USBCAN-2E-U without `interface`: `ZLG_SDK_DIR` points at the user-installed SDK directory (never hard-code a disk path).
   - Any other backend: that vendor's own driver and the `channel` / `extra` python-can documents. Do not set `ZLG_SDK_DIR` unless the backend is `zlg`.

## Which interface

| Need | Use |
|------|-----|
| One command, then exit | CLI: `list` `send` `receive` `monitor` `status` |
| Agent tools, session, periodic | MCP: `open_device`, `send_frame`, `receive_frame`, `monitor`, `periodic_start` / `periodic_stop` / `periodic_list`, `set_frame_filter`, `accept_all_frames`, `close_device` |
| Hours-long send/receive with no agent | One Python process holding `can.Bus` or a core session |

`set_frame_filter` replaces one ID range on every backend. Hardware acceptance is used when the backend has it (USBCAN-2E-U). Other backends use python-can ID masks, including inside `receive` / `monitor`. `accept_all_frames` restores full reception. Do not treat an empty hardware table as accept-all.

`periodic_start` is hardware-timed on USBCAN-2E-U and blocks `send_frame` until every task stops. Other backends use python-can periodic send and can still send. CLI `periodic` runs one task for `--duration` seconds, then stops.

CLI and one-shot MCP calls open and close the device each time. Do not loop them for a long job.

Stdout of the CLI is one JSON object. Branch on `status` and `error.code`. A receive timeout is success with no frame, not a crash.

Details and copy-paste templates: [references/examples.md](references/examples.md). Failures for the verified ZLG model: [references/pitfalls.md](references/pitfalls.md).

## Long-running script

The snippet below is the verified USBCAN-2E-U case (`interface="zlg"`). A registered PEAK or Vector device uses `pcan` or `vector` instead, with that model's channel and bitrate. Do not pass `interface="zlg"` for those cards.

```python
import can

bus = can.Bus(interface="zlg", channel=1, bitrate=250_000)  # USBCAN-2E-U; match its config
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

## Safety

On the verified ZLG adapter, do not set a custom serial number, a non-standard baud encoding, a persistent device config, or listen-only mode from an automated script. Those can survive power cycle or leave that device unable to open. Do not copy those writes onto another vendor. See [references/pitfalls.md](references/pitfalls.md).

## Privacy

Public skills and commits may name `ZLG_SDK_DIR` and neutral IDs such as `0x123`. They must not contain absolute paths, customer or ECU names, or text copied from local-only notes. Before any `git add` / `commit` in this repo, run the full desensitization checklist in `CLAUDE.md`.

## Maintenance

Update this skill when CLI or MCP names change, when a model is registered or verified, or when a pitfall is safe to publish. Put new vendor steps under that model. Keep board-specific notes out of the repository. When a vendor SDK is wrapped, add that vendor to the README disclaimer.
