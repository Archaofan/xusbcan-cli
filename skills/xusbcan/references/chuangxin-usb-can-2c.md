# Chuangxin USB_CAN-2C

Read this file when the device is `vendor = "chuangxin"` and `model = "USB_CAN-2C"`. For `USB_CAN-2A-GD`, use the same backend rules; hardware verification for that model is suspended—do not claim it verified. Do not open this card with a ZLG `vendor` / `model`, and do not set `ZLG_SDK_DIR` for it.

## Setup

`CHUANGXIN_SDK_DIR` points at the user-installed directory that contains Chuangxin's `ControlCAN.dll`. Load that file by absolute path. Never hard-code a disk path in committed files.

Install the Chuangxin USB driver so the host enumerates the adapter. Match DLL bitness to the Python process (64-bit with 64-bit Python).

The model shortcut selects interface `chuangxin`, channels `0` or `1`, and device type `4` for this product family. It does not accept a CAN FD data bitrate.

## What was verified here

On an authorized bench, against a verified Zhou Ligong USBCAN-2E-U on the same classic CAN bus, this repo confirmed through the shared CLI / core path: open/close and reopen, bidirectional frames, software filters, both Chuangxin channels open with the ZLG alias, `monitor`, `periodic`, and `scenario` steps including `burst_send`, `wait_n`, and `repeat`.

Not verified: active error-frame generation, long soak, or in-vehicle networks. One host pass does not guarantee every USB_CAN-2C unit.

## Choosing the model

If the user already said the adapter is Chuangxin USB_CAN-2C (or the config names it), open that alias. If the config only says a vague dual-channel USB-CAN name without a vendor, ask which vendor and model before opening. Do not guess by trying another vendor's entry first.

## Coexistence

- ZLG cards in this project use `ZLG_SDK_DIR` and `zlgcan.dll`. Chuangxin uses `CHUANGXIN_SDK_DIR` and `ControlCAN.dll`. With separate directories, a ZLG 2E and a Chuangxin 2C may be open together in one process.
- Do not load two different `ControlCAN.dll` binaries in the same process. Keep other tools that need their own `ControlCAN.dll` in separate directories or processes.
- Do not point `CHUANGXIN_SDK_DIR` at a ZLG SDK tree, and do not point `ZLG_SDK_DIR` at a Chuangxin ControlCAN tree.

## Filters and periodic send

`set_frame_filter` / `accept_all_frames` and `periodic_start` use the python-can software path on this backend. Prefer distinctive test IDs when another adapter shares the bus.

## Transmit without ACK

Behavior follows the ControlCAN driver. Do not copy another vendor's timeout numbers onto this card.

## Resident script

```python
import can

bus = can.Bus(
    interface="chuangxin",
    channel=0,
    bitrate=250_000,
    device_type=4,
    device_index=0,
)
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

`CHUANGXIN_SDK_DIR` must be set in the process environment before `can.Bus` opens. Match `channel` and `bitrate` to the config.
