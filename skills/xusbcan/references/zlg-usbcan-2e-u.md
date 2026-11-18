# Zhou Ligong USBCAN-2E-U

Read this file **only** when the device is `vendor = "zlg"` and `model = "USBCAN-2E-U"`. Do not apply it to USBCAN-II, PEAK, Vector, socketcan, or any other backend.

## Quick start

1. Set `ZLG_SDK_DIR` to the user-installed SDK directory that contains `zlgcan.dll` and `kerneldlls/`. Never hard-code a disk path. Do not set this variable for other backends.
2. This card has **two** CAN ports. Confirm which physical port is cabled, then set `channel` to that index (`0` or `1`). Silk-screen `CAN1` / `CAN2` map to `channel` `0` / `1`. If the wired port is unknown, ask—do not open on an assumed `0`.
3. Config alias (set `channel` to the wired port; the `0` below is only a placeholder):

```toml
[[devices]]
name = "bus0"
vendor = "zlg"
model = "USBCAN-2E-U"
channel = 0
nominal = 500000
```

The model shortcut selects interface `zlg` and `device_type = 21`. Classic CAN only in the usual path (no CAN FD data bitrate via this shortcut).

4. One-shot: `xusbcan send bus0 --id 0x123 --data "01 02"` then `xusbcan receive bus0 --timeout 1`. Session / scenario / MCP shapes: [examples.md](examples.md).

## How this backend behaves in xusbcan

- **Model identity** comes from the product label / purchase name / config `model` (`USBCAN-2E-U`, `device_type = 21`). `ZCAN_GetDeviceInf` fields such as `hwType` and `can_Num` are **not** authoritative here: they may report strings like `USBCAN-E` or `can_Num = 1` on a real 2E-U. Do **not** switch `device_type`, treat the card as single-channel, or open a CAN FD path because of those fields.
- **Channel** is the physical port index (`0` or `1`). Opening the wrong index for the cable produces InitCAN / empty-handle / transmit-zero-frame symptoms that look like filter or ACK problems. Match `channel` to the wired port before debugging further; after a bad open, a USB unplug/replug may be needed before reopen.
- `set_frame_filter` / `accept_all_frames` program the card’s **hardware** filter table (whitelist). Standard and extended ranges are separate; `accept_all_frames` installs a full standard range and a full extended range.
- `periodic_start` on this card uses a **hardware-timed** path. Until every such task is stopped, a normal `send_frame` is rejected on purpose. One task is one frame; `duration` rewrite callbacks are not available on that hardware path.
- Prefer normal-mode open / send / receive. Do not automate writing custom serial numbers, persistent dynamic config, non-standard baud encoding, or listen-only init through agent scripts—those can leave the device hard to reopen.

## Field notes (not guarantees)

Items below were **reported by earlier contributors on a specific bench**. They may not reproduce on your unit, SDK/driver build, or bus wiring. They are **not** a formal “unsupported features” list and **not** proof that every USBCAN-2E-U is defective. Use them only when the current symptom matches; otherwise ignore and debug from CLI/MCP `error.code` and Zhou Ligong docs.

Before using these notes: confirm `channel` matches the wired port (and reopen / USB re-plug if a prior open failed). Wrong channel and sticky open state share symptoms with the bullets below.

- After changing filters, reception looked empty until the rule was acknowledged and a full range restored—clearing the table without restoring a full range received nothing.
- With no other node to ACK, a normal transmit sometimes blocked inside the driver for roughly a few seconds and then reported zero frames sent. Tight retry loops made it worse.
- Closing returned before the driver fully released the device; opening again in the same process with no pause sometimes yielded an empty handle. Waiting on the order of half a second before reopen helped on that bench.
- Listen-only or unusual init modes were associated with later open failures until a long cooldown—avoid unless you are deliberately testing that mode.

## Resident script

```python
import can

# Set channel to the wired port (0 or 1), matching xusbcan.toml
bus = can.Bus(interface="zlg", channel=0, bitrate=500_000)
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
