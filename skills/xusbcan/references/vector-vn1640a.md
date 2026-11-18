# Vector VN1640A

Read this file **only** when the device is `vendor = "vector"` and `model = "VN1640A"`, or when `interface = "vector"` is intentionally used for this card. Do not apply it to ZLG, PEAK, socketcan, or other backends. Do not treat a registered but unverified Vector model (for example VN1630) as covered by this page.

## Quick start

1. Install the Vector driver / XL Driver from Vector. Do **not** set `ZLG_SDK_DIR` or `CHUANGXIN_SDK_DIR` for this card.
2. Config alias (channel is the XL / python-can **global** index—no remapping in xusbcan):

```toml
[[devices]]
name = "vn0"
vendor = "vector"
model = "VN1640A"
channel = 0
nominal = 500000
```

Hardware Channel *N* is usually index `N - 1`; confirm with host enumeration before sending. Prefer the `vendor` / `model` shortcut when the config already names VN1640A. If you set `interface = "vector"` yourself, pass the same kind of arguments python-can documents (including application name or global index).

3. One-shot: `xusbcan send vn0 --id 0x123 --data "01 02"` then `xusbcan receive vn0 --timeout 1`. Session / scenario / MCP shapes: [examples.md](examples.md).

Do not hard-code absolute paths, serial numbers, or board wiring into committed files.

## How this backend behaves in xusbcan

- This card uses python-can’s stock `vector` backend end-to-end. xusbcan does **not** ship a separate Vector/XL ctypes layer. The model shortcut only supplies profile defaults (channel count, `app_name=None`) and then calls `can.Bus(interface="vector", ...)`.
- `set_frame_filter` / `accept_all_frames` use python-can software masks on this backend.
- `periodic_start` uses software `send_periodic`.
- Channel indices are the same global indices python-can and the XL Driver use. LIN, IO, or unused ports are not interchangeable with CAN.

## Field notes (not guarantees)

Items below were **reported by earlier contributors on a specific authorized classic-CAN bench**. They may not reproduce on your unit, piggyback mix, Vector license, or wiring. They are **not** a formal “unsupported features” list and **not** proof that every VN1640A behaves the same. Use them only when the current symptom matches.

- On that bench, open/close/reopen, bidirectional data frames, soft ID-range filters, multiple Vector channels in one process alongside a second adapter, plus `monitor` / `periodic` / `scenario` steps (`burst_send`, `wait_n`, `repeat`) worked through this project’s shared CLI / core path.
- Not exercised there: active error-frame generation, long soak, in-vehicle networks, CAN FD on every piggyback, or channels that were not wired for CAN.
- Open failing with an invalid channel mask usually meant the index was wrong for CAN, or the Vector application binding did not match how the port was opened—confirm enumeration first.
- Other nodes may still produce frames outside a standard-ID whitelist (for example extended frames). Prefer distinctive test IDs when another adapter shares the bus; restore full reception with `accept_all_frames`.
- Transmit-without-ACK timing follows the Vector / python-can path. Do **not** copy Zhou Ligong “blocks ~N seconds” numbers onto this card.

## Resident script

```python
import can

bus = can.Bus(interface="vector", channel=0, bitrate=500_000, app_name=None)
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

Match `channel` and `bitrate` to the config. Stop the periodic task before shutdown.
