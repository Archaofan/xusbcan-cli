# Pitfalls

Cross-backend notes only. Model-specific setup and field notes live on the catalog-selected model page—do not open every model file.

## Contracts (always apply)

### CLI is not a resident session

Each `xusbcan send`, `receive`, or `monitor` opens and closes the device. A `while` loop of those commands flaps the hardware. `periodic` stays open only for its `--duration`, then stops and closes.

Hold one process for a long job: MCP `open_device`, or one `can.Bus` / core session.

### Timeout is not a failure

`receive` and `receive_frame` with no traffic return `status=ok` and no frame when the timeout elapses. Branch on `status` and `error.code`. Do not treat that as a crash.

### One filter range, then accept all

`set_frame_filter` replaces reception with one ID range on every backend. `accept_all_frames`, or `set_filters(None)` on the bus, restores full reception. Do not leave a cleared filter in place and expect traffic.

### Do not reuse another card's setup

Driver, environment variables, channel type, and `extra` keys belong to the backend named in the config. Copying one vendor's SDK variable or channel string onto another backend will not open the device. Keep SDK directories separate; do not load two different vendor DLLs in one process. Exact env names and channel rules: [catalog.md](catalog.md) → matching model page only.

### README “verified” is a finite bench label

A model marked verified on hardware in the README still has a finite bench scope. Do not invent error-frame injection, soak guarantees, or in-vehicle authorization from that label. Stay inside the public CLI / MCP commands and the matching model reference.

## Field notes (not guarantees)

The following were **reported by earlier contributors** while developing or benching this project. They may not reproduce, may be unit/driver/environment specific, and are **not** a claim that every backend is defective or that a feature is formally unsupported. Match the current symptom before acting; otherwise ignore.

- On **some** backends, after `periodic_start` / `send_periodic`, a later `send_frame` failed until every periodic task was stopped. Stop the task, then send—but do **not** assume that lockout (or its absence) for a card you have not identified; check that model’s **How this backend behaves** section.
- Mixing another card’s timing numbers (for example “blocks ~N seconds with no ACK”) onto an unmatched vendor wasted time. Identify `vendor` / `model` first via [catalog.md](catalog.md).
