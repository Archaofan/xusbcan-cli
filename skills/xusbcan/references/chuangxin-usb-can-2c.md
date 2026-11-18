# Chuangxin USB_CAN-2C

Read this file when the device is `vendor = "chuangxin"` and `model = "USB_CAN-2C"`. For `USB_CAN-2A-GD`, use the same backend rules; hardware verification for that model is suspended—do not claim it verified. Do not open this card with a ZLG `vendor` / `model`, and do not set `ZLG_SDK_DIR` for it.

## Quick start

1. Install the Chuangxin USB driver so the host enumerates the adapter. Set `CHUANGXIN_SDK_DIR` to the user-installed directory that contains Chuangxin’s `ControlCAN.dll`. Load that DLL by absolute path via the env var—never hard-code a disk path in committed files. Match DLL bitness to the Python process (64-bit with 64-bit Python).
2. Config alias:

```toml
[[devices]]
name = "cx0"
vendor = "chuangxin"
model = "USB_CAN-2C"
channel = 0
nominal = 500000
```

Channels are `0` or `1`. The model shortcut selects interface `chuangxin` and device type `4` for this product family. Classic CAN only in the usual path (no CAN FD data bitrate via this shortcut).

3. One-shot: `xusbcan send cx0 --id 0x123 --data "01 02"` then `xusbcan receive cx0 --timeout 1`. Session / scenario / MCP shapes: [examples.md](examples.md).

If the user already named USB_CAN-2C (or the config does), open that alias. If the config only says a vague dual-channel USB-CAN name without a vendor, ask which vendor and model before opening—do not guess by trying another vendor’s entry first.

## How this backend behaves in xusbcan

- `set_frame_filter` / `accept_all_frames` and `periodic_start` use the python-can **software** path on this backend.
- Keep SDK trees separate: ZLG uses `ZLG_SDK_DIR` + `zlgcan.dll`; Chuangxin uses `CHUANGXIN_SDK_DIR` + `ControlCAN.dll`. Do not point either env var at the other vendor’s tree. Do not load two different `ControlCAN.dll` binaries in the same process.

## Field notes (not guarantees)

Items below were **reported by earlier contributors on a specific authorized classic-CAN bench**. They may not reproduce on your unit, DLL build, or wiring. They are **not** a formal “unsupported features” list and **not** proof that every USB_CAN-2C is defective. Use them only when the current symptom matches.

- On that bench, open/close/reopen, bidirectional frames, software filters, both Chuangxin channels open in one process alongside a second adapter, plus `monitor` / `periodic` / `scenario` steps (`burst_send`, `wait_n`, `repeat`) worked through this project’s shared CLI / core path.
- Not exercised there: active error-frame generation, long soak, or in-vehicle networks.
- With separate SDK directories, a ZLG card and a Chuangxin 2C could be open together in one process on that host—still keep other tools that need their own `ControlCAN.dll` in separate directories or processes.
- Prefer distinctive test IDs when another adapter shares the bus.
- Transmit-without-ACK behavior follows the ControlCAN driver. Do **not** copy another vendor’s timeout numbers onto this card.

## Resident script

```python
import can

bus = can.Bus(
    interface="chuangxin",
    channel=0,
    bitrate=500_000,
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
            pass
finally:
    task.stop()
    bus.shutdown()
```

`CHUANGXIN_SDK_DIR` must be set in the process environment before `can.Bus` opens. Match `channel` and `bitrate` to the config.
