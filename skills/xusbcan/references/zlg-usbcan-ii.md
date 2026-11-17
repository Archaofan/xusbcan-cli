# Zhou Ligong USBCAN-II

Read this file only when the device is `vendor = "zlg"` and `model = "USBCAN-II"`. Do not apply it to USBCAN-2E-U, PEAK, Vector, socketcan, or any other backend.

## Setup

Same SDK variable as other Zhou Ligong cards in this repo: `ZLG_SDK_DIR` must point at a user-installed directory that contains `zlgcan.dll` and `kerneldlls/`. Never hard-code a disk path. Do not set this variable for non-ZLG backends.

The model shortcut selects interface `zlg`, channel `0` or `1`, and the device type for this card. It does not accept a CAN FD data bitrate.

## Software filter, not hardware filter tables

On this model, `set_frame_filter` / `accept_all_frames` use the in-process python-can filter path. They do not program the card's hardware filter property tables. Clearing filters restores full reception in the process; do not expect a hardware whitelist on this card.

## Periodic send stays software

`periodic_start` uses software `send_periodic`. A normal `send_frame` can run while a soft periodic task is active. That differs from USBCAN-2E-U hardware periodic lockout. Do not copy 2E-U periodic rules onto this model.

## Transmit with no ACK

With no other node to ACK, a normal transmit can block inside the driver for several seconds and then report zero frames sent. Do not retry in a tight loop.

## Close, then open

Closing can return before the driver has fully released the device. Opening again in the same process with no pause may fail. Wait at least half a second, then retry.

## Do not automate these writes

| Avoid | Why |
|-------|-----|
| Custom serial number | Can be stored across power cycles |
| Persistent dynamic config / firmware paths | Same |
| Non-standard custom baud encoding | Easy to leave the channel on an unexpected rate |
| Listen-only init mode | Can make the next open fail until a long cooldown |
| Hardware `filter_*` / `auto_send` property paths | Not used on this model; stick to `set_frame_filter` and soft periodic |

Read-only device info and a normal-mode open/send/receive loop cover almost every debug task.

## Resident script

```python
import can

bus = can.Bus(interface="zlg", channel=0, bitrate=250_000, device_type=4)
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
