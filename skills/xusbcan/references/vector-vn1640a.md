# Vector VN1640A

Read this file only when the device is `vendor = "vector"` and `model = "VN1640A"`, or when `interface = "vector"` is intentionally used for this card. Do not apply it to ZLG, PEAK, socketcan, or other backends. Do not treat a registered but unverified Vector model (for example VN1630) as covered by this page.

## Setup

Install the Vector driver / XL Driver from Vector. Do **not** set `ZLG_SDK_DIR` for this card.

The model shortcut opens python-can's `vector` backend. Channel numbers are the **same global indices** python-can and the XL Driver use. There is no logical remapping in xusbcan. Hardware Channel *N* is usually index `N - 1`; confirm with the host enumeration before sending.

The shortcut sets `app_name` to `None` so the bus opens by that global index. If you set `interface = "vector"` yourself, pass the same kind of arguments python-can documents (including how you select the application name or global index). Prefer the `vendor` / `model` shortcut when the config already names VN1640A.

Do not hard-code absolute paths, serial numbers, or board wiring into committed files.

## What was verified here

On an authorized bench, against a verified Zhou Ligong USBCAN-2E-U on the same classic CAN bus, this repo confirmed through the shared CLI / core path (the same commands MCP exposes):

- Open, close, and reopen
- Bidirectional data frames
- Soft ID-range filters via `set_frame_filter` / `accept_all_frames`
- Multiple Vector channels open together with the ZLG alias
- `monitor`, `periodic`, and `scenario` steps including `burst_send`, `wait_n`, and `repeat`

Not verified: active error-frame generation, long soak, in-vehicle networks, CAN FD on every piggyback, or channels that are not wired for CAN.

Verification on one host does not guarantee every VN1640A unit, piggyback mix, or Vector software license.

## Channel choice

Pick the index that matches the physical CAN port on the bus. LIN, IO, or unused ports are not interchangeable with CAN. If open fails with an invalid channel mask, the index is wrong for CAN, or the Vector application binding does not match how you open the port.

## Filters and other traffic

`set_frame_filter` uses python-can masks on this backend. Other nodes on the bus may still produce frames outside a standard-ID whitelist (for example extended frames). Prefer distinctive test IDs when another adapter shares the bus. Restoring full reception needs `accept_all_frames`.

## Transmit without ACK

With no acknowledging node, transmit behavior follows the Vector / python-can path. Do not assume the Zhou Ligong “blocks ~3.5 s” note applies here. Identify the configured model before copying another card’s timing.

## Resident script

```python
import can

bus = can.Bus(interface="vector", channel=2, bitrate=250_000, app_name=None)
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

Match `channel` and `bitrate` to the config. Stop the periodic task before shutdown.
