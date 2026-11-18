# Zhou Ligong USBCAN-II

Read this file **only** when the device is `vendor = "zlg"` and `model = "USBCAN-II"`. Do not apply it to USBCAN-2E-U, PEAK, Vector, socketcan, or any other backend.

## Quick start

1. Set `ZLG_SDK_DIR` to the user-installed SDK directory that contains `zlgcan.dll` and `kerneldlls/`. Never hard-code a disk path. Do not set this variable for non-ZLG backends.
2. This card has **two** CAN ports. Confirm which physical port is cabled, then set `channel` (`0` or `1`). Silk-screen `CAN1` / `CAN2` map to `channel` `0` / `1`. The `0` in the snippet is a placeholder.
3. Config alias:

```toml
[[devices]]
name = "bus0"
vendor = "zlg"
model = "USBCAN-II"
channel = 0
nominal = 500000
```

The model shortcut selects interface `zlg` and this card’s device type. Classic CAN only in the usual path (no CAN FD data bitrate via this shortcut).

4. One-shot: `xusbcan send bus0 --id 0x123 --data "01 02"` then `xusbcan receive bus0 --timeout 1`. Session / scenario / MCP shapes: [examples.md](examples.md).

## How this backend behaves in xusbcan

- **Model identity** comes from the label / config `model`. Do not re-judge the card from opaque SDK device-info strings alone.
- **Channel** is the physical port index (`0` or `1`). Match it to the cable before treating open/send failures as filter or ACK issues.
- `set_frame_filter` / `accept_all_frames` use the **in-process** python-can filter path. They do **not** program this card’s hardware filter property tables. Clearing filters restores full reception in the process.
- `periodic_start` uses software `send_periodic`. A normal `send_frame` can run while a soft periodic task is active—do **not** copy USBCAN-2E-U hardware-periodic lockout rules onto this model.
- Prefer normal-mode open / send / receive. Do not automate writing custom serial numbers, persistent dynamic config, non-standard baud encoding, listen-only init, or hardware `filter_*` / `auto_send` property paths through agent scripts; stick to `set_frame_filter` and soft periodic.

## Field notes (not guarantees)

Items below were **reported by earlier contributors on a specific bench**. They may not reproduce on your unit, SDK/driver build, or bus wiring. They are **not** a formal “unsupported features” list and **not** proof that every USBCAN-II is defective. Use them only when the current symptom matches; otherwise ignore and debug from CLI/MCP `error.code` and Zhou Ligong docs.

Before using these notes: confirm `channel` matches the wired port.

- With no other node to ACK, a normal transmit sometimes blocked inside the driver for several seconds and then reported zero frames sent. Tight retry loops made it worse.
- Closing returned before the driver fully released the device; opening again in the same process with no pause sometimes failed. Waiting on the order of half a second before reopen helped on that bench.
- Listen-only or unusual init modes were associated with later open failures until a long cooldown—avoid unless you are deliberately testing that mode.

## Resident script

```python
import can

bus = can.Bus(interface="zlg", channel=0, bitrate=500_000, device_type=4)
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

Match `channel` / `bitrate` / `device_type` to the config. `ZLG_SDK_DIR` must already be set in the process environment.
