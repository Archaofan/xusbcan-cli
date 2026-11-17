# Examples

Replace `bus0` with the alias in `xusbcan.toml`. Match that file's `interface` or `vendor` / `model`, channel, and bitrate. Do not embed a real SDK directory.

```toml
[[devices]]
name = "bus0"
interface = "socketcan"
channel = "can0"
nominal = 500000
```

`interface` is any backend python-can declares. A `vendor` / `model` shortcut is optional and is skipped when `interface` is set. Model-specific setup, such as a vendor SDK directory, belongs in that model's reference and is used only when the config names that model.

## CLI (one shot)

```bash
xusbcan list
xusbcan send bus0 --id 0x123 --data "01 02 03"
xusbcan receive bus0 --timeout 1
xusbcan receive bus0 --timeout 1 --from-id 0x100 --to-id 0x1FF
xusbcan monitor bus0 --duration 2 --max-frames 50
xusbcan periodic bus0 --name hb --id 0x123 --data "01" --period 0.1 --duration 5
xusbcan status bus0
xusbcan scenario --file steps.json
xusbcan scenario --dir scenarios/
```

Extended frame: add `--ext`. Each command prints one JSON object and exits. `periodic` holds the device only for `--duration`.

`scenario` / MCP `run_scenario` run millisecond steps in one process. `--dir` runs every `*.json` in that folder in name order and returns one aggregate Result:
`open` `send` `wait_id` `wait_n` `drain` `burst_send` `filter` `accept_all` `sleep` `repeat` `try` `set` `periodic_*` `close`.
File-level `vars` and `${name}` placeholders are expanded before each step.
`wait_id` / `wait_n` may set `"store": {"var": "id|data|dlc|ext"}` to capture fields into vars.

Example:

```json
{
  "steps": [
    {"action": "open", "device": "bus0"},
    {"action": "send", "device": "bus0", "id": "0x321", "data": "01 02"},
    {"action": "wait_id", "device": "bus0", "id": "0x321", "timeout": 1.0},
    {"action": "close", "device": "bus0"}
  ]
}
```

## MCP tools

Register `xusbcan-mcp` in the MCP client. Set `XUSBCAN_CONFIG` in that server's environment. Paths belong in the user's local config, not in this skill. Add a vendor SDK variable only when that model's reference says so.

Typical order for a session:

1. `list_devices`
2. `open_device` with the alias
3. `send_frame` / `receive_frame` / `monitor`
4. `periodic_start` with `period_s` in seconds, then `periodic_stop`
5. `set_frame_filter` to keep one ID range, then `accept_all_frames` before `close_device` if the bus should receive everything again
6. `close_device`

HTTP MCP, when enabled in config, listens on `127.0.0.1` only. Do not point it at a public address.

`receive_frame` with no traffic returns `status=ok` and a null frame when `timeout` elapses.

`monitor` is bounded (`duration_s` at most 30 seconds). It is not a streaming log.

## python-can (resident)

`interface` and `channel` come from the config. This shape is not tied to one vendor.

```python
import can

bus = can.Bus(interface="socketcan", channel="can0", bitrate=500_000)
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

bus = can.Bus(interface="socketcan", channel="can0", bitrate=500_000)
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
