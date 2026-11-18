# Zhou Ligong USBCAN-2E-U

Read this file **only** when the device is `vendor = "zlg"` and `model = "USBCAN-2E-U"`. Do not apply it to USBCAN-II, PEAK, Vector, socketcan, or any other backend.

## Quick start

1. Set `ZLG_SDK_DIR` to the user-installed SDK directory that contains `zlgcan.dll` and `kerneldlls/`. Never hard-code a disk path. Do not set this variable for other backends.
2. Config alias:

```toml
[[devices]]
name = "bus0"
vendor = "zlg"
model = "USBCAN-2E-U"
channel = 0
nominal = 500000
```

Channels are `0` or `1`. The model shortcut selects interface `zlg` and this card’s device type. Classic CAN only in the usual path (no CAN FD data bitrate via this shortcut).

3. One-shot: `xusbcan send bus0 --id 0x123 --data "01 02"` then `xusbcan receive bus0 --timeout 1`. Session / scenario / MCP shapes: [examples.md](examples.md).

## How this backend behaves in xusbcan

- `set_frame_filter` / `accept_all_frames` program the card’s **hardware** filter table (whitelist). Standard and extended ranges are separate; `accept_all_frames` installs a full standard range and a full extended range.
- `periodic_start` on this card uses a **hardware-timed** path. Until every such task is stopped, a normal `send_frame` is rejected on purpose. One task is one frame; `duration` rewrite callbacks are not available on that hardware path.
- Prefer normal-mode open / send / receive. Do not automate writing custom serial numbers, persistent dynamic config, non-standard baud encoding, or listen-only init through agent scripts—those can leave the device hard to reopen.

## Field notes (not guarantees)

Items below were **reported by earlier contributors on a specific bench**. They may not reproduce on your unit, SDK/driver build, or bus wiring. They are **not** a formal “unsupported features” list and **not** proof that every USBCAN-2E-U is defective. Use them only when the current symptom matches; otherwise ignore and debug from CLI/MCP `error.code` and Zhou Ligong docs.

- After changing filters, reception looked empty until the rule was acknowledged and a full range restored—clearing the table without restoring a full range received nothing.
- With no other node to ACK, a normal transmit sometimes blocked inside the driver for roughly a few seconds and then reported zero frames sent. Tight retry loops made it worse.
- Closing returned before the driver fully released the device; opening again in the same process with no pause sometimes yielded an empty handle. Waiting on the order of half a second before reopen helped on that bench.
- Listen-only or unusual init modes were associated with later open failures until a long cooldown—avoid unless you are deliberately testing that mode.

## Resident script

```python
import can

bus = can.Bus(interface="zlg", channel=0, bitrate=500_000)  # match config
task = bus.send_periodic(
    can.Message(arbitration_id=0x123, data=[0x01, 0x02], is_extended_id=False),
    period=0.1,
)
try:
    while True:
        msg = bus.recv(timeout=0.5)
        if msg is not None:
            pass
finally:
    task.stop()
    bus.shutdown()
```

Match `channel` / `bitrate` to the config. `ZLG_SDK_DIR` must already be set in the process environment.
