# Examples

Replace `bus0` with the alias in `xusbcan.toml`. Match that file's channel and bitrate. Do not embed a real SDK directory.

A device is either `interface = "<python-can backend>"` plus that backend's channel, or a `vendor` / `model` shortcut. The ZLG blocks below are only for USBCAN-2E-U. Do not set `ZLG_SDK_DIR` or `interface = "zlg"` for other backends.

```toml
[[devices]]
name = "bus0"
interface = "socketcan"
channel = "can0"
nominal = 500000
```

## CLI (one shot)

```bash
xusbcan list
xusbcan send bus0 --id 0x123 --data "01 02 03"
xusbcan receive bus0 --timeout 1
xusbcan monitor bus0 --duration 2 --max-frames 50
xusbcan status bus0
```

Extended frame: add `--ext`. Each command prints one JSON object and exits.

## MCP tools

Register `xusbcan-mcp` in the MCP client. Set `XUSBCAN_CONFIG` in that server's environment (paths belong in the user's local config, not in this skill). Add `ZLG_SDK_DIR` only when the configured model is USBCAN-2E-U.

Typical order for a session:

1. `list_devices`
2. `open_device` with the alias
3. `send_frame` / `receive_frame` / `monitor`
4. `periodic_start` with `period_s` in seconds, then `periodic_stop`. On USBCAN-2E-U this is hardware-timed: `send_frame` fails until every periodic task is stopped. Other registered backends do not use that lockout
5. On USBCAN-2E-U: `set_frame_filter` to keep one ID range, then `accept_all_frames` before `close_device` if the bus should receive everything again. Do not send those filter rules to a PEAK or Vector device
6. `close_device`

HTTP MCP, when enabled in config, listens on `127.0.0.1` only. Do not point it at a public address.

`receive_frame` with no traffic returns `status=ok` and a null frame when `timeout` elapses.

`monitor` is bounded (`duration_s` at most 30 seconds). It is not a streaming log.

## python-can (resident, verified model)

USBCAN-2E-U only. For a registered PEAK or Vector device, use `interface="pcan"` or `interface="vector"` and that model's channel. A direct `can.Bus` call does not consult the xusbcan model table; the CLI still will.

```python
import can

bus = can.Bus(interface="zlg", channel=0, bitrate=500_000)
bus.send(can.Message(arbitration_id=0x123, data=[0x01, 0x02], is_extended_id=False))
msg = bus.recv(timeout=1.0)
bus.shutdown()
```

## Offline script skeleton

```python
import signal
import can

stop = False


def _stop(*_):
    global stop
    stop = True


signal.signal(signal.SIGINT, _stop)

bus = can.Bus(interface="zlg", channel=0, bitrate=500_000)  # USBCAN-2E-U
task = bus.send_periodic(
    can.Message(arbitration_id=0x123, data=[0x01], is_extended_id=False),
    period=0.1,
)
try:
    while not stop:
        msg = bus.recv(timeout=0.2)
finally:
    task.stop()
    bus.shutdown()
```

Run it with the environment already set. The process does not need an agent after it starts.
