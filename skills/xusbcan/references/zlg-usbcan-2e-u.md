# Zhou Ligong USBCAN-2E-U

Read this file only when the device is `vendor = "zlg"` and `model = "USBCAN-2E-U"`. Do not apply it to USBCAN-II, PEAK, Vector, socketcan, or any other python-can backend.

## Setup

`ZLG_SDK_DIR` points at the user-installed SDK directory that contains `zlgcan.dll` and `kerneldlls/`. Never hard-code a disk path. Do not set this variable for other backends.

The model shortcut selects interface `zlg`, channel `0` or `1`, and the device type for this card. It does not accept a CAN FD data bitrate.

## Receive goes empty after a filter change

Hardware filters are a whitelist:

- Standard and extended frames are separate rules.
- A new rule does not apply on the device until it is acknowledged.
- Clearing the table without restoring a full range receives nothing.
- `set_frame_filter` / `accept_all_frames` program that table. `accept_all_frames` installs a full standard range and a full extended range.

## Transmit blocks for seconds

With no other node to ACK, a normal transmit can block inside the driver for about 3.5 seconds and then report zero frames sent. Do not retry in a tight loop.

## Hardware periodic send

`periodic_start` on this card is hardware-timed. Until every such task is stopped, `send_frame` fails on purpose. One task is one frame. `duration` and a data-rewrite callback are not available on this path.

## Close, then open

Closing returns before the driver has fully released the device. Opening again in the same process with no pause often yields an empty handle. Wait at least half a second, then retry.

## Do not automate these writes

| Avoid | Why |
|-------|-----|
| Custom serial number | Can be stored across power cycles |
| Persistent dynamic config / firmware paths | Same |
| Non-standard custom baud encoding | Easy to leave the channel on an unexpected rate |
| Listen-only init mode | Can make the next open fail until a long cooldown |

Read-only device info and a normal-mode open/send/receive loop cover almost every debug task.

## Resident script

```python
import can

bus = can.Bus(interface="zlg", channel=1, bitrate=250_000)  # match this model's config
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
