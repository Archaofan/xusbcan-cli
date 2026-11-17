# Pitfalls

These notes apply to every adapter opened by xusbcan. Do not add machine paths, serial numbers, or customer frame maps.

A model-specific file is not part of this page. Open it only when the config `vendor` / `model` (or `interface`) is exactly that card.

## CLI is not a resident session

Each `xusbcan send`, `receive`, or `monitor` opens and closes the device. A `while` loop of those commands flaps the hardware. `periodic` stays open only for its `--duration`, then stops and closes.

Hold one process for a long job: MCP `open_device`, or one `can.Bus` / core session.

## Timeout is not a failure

`receive` and `receive_frame` with no traffic return `status=ok` and no frame when the timeout elapses. Branch on `status` and `error.code`. Do not treat that as a crash.

## One filter range, then accept all

`set_frame_filter` replaces reception with one ID range on every backend. `accept_all_frames`, or `set_filters(None)` on the bus, restores full reception. Do not leave a cleared filter in place and expect traffic.

## Periodic send may block a normal send

`periodic_start` uses `send_periodic`. On some backends a later `send_frame` fails until every periodic task is stopped. Stop the task, then send. Do not assume that lockout, or its absence, for a card you have not identified.

## Do not reuse another card's setup

Driver, environment variables, channel type, and `extra` keys belong to the backend named in the config. Copying one vendor's SDK variable or channel string onto another backend will not open the device.

Examples: `ZLG_SDK_DIR` is only for Zhou Ligong backends; `CHUANGXIN_SDK_DIR` is only for Chuangxin ControlCAN; Vector VN1640A needs the Vector driver and the XL global channel index. Keep SDK directories separate. Do not load two different `ControlCAN.dll` files in one process.

## Verified does not mean every feature

A model marked verified on hardware in the README still has a finite bench scope. Do not invent error-frame injection, soak guarantees, or in-vehicle authorization from that label. Stay inside the public CLI / MCP commands and the matching model reference.
