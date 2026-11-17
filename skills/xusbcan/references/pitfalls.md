# Pitfalls

Public behavior only. Do not add machine paths, serial numbers, or customer frame maps.

## Receive goes empty after a filter change

On the verified classic USB-CAN adapter, filters are a whitelist:

- `filter_mode` selects standard frames (`0`) or extended frames (`1`). It is not a generic "range mode".
- IDs are hex strings with a `0x` prefix.
- A new rule does not apply on the device until it is acknowledged.
- Clearing the table also needs that acknowledge. An empty table means **receive nothing**, not receive everything.
- To accept traffic again, install an explicit full standard range and a full extended range, then acknowledge once.

The product does not expose filter setup on the CLI. Do not experiment with filters unless the user asked, and always restore accept-all before you finish.

## Transmit blocks for seconds

With no other node to ACK, a normal transmit can block inside the driver for about 3.5 seconds and then report zero frames sent. Do not retry in a tight loop. Prefer a bus that already has a peer when you need a quick pass/fail.

## Hardware periodic send vs normal send

If hardware timed transmit is enabled on a channel, a following normal transmit can fail immediately until that timed list is cleared. Software periodic send (`send_periodic` / MCP `periodic_start`) does not have this lockout. Do not mix the two on the same channel.

## Close, then open

Closing the device returns before the driver has fully released it. Opening again in the same process with no pause often yields an empty handle. Wait at least half a second, then retry.

## "Online" is not the generic success code

The online check uses its own codes: online is `2`, offline is `3`. Do not treat `1` (generic success of other calls) as "device online".

## Do not automate these writes

| Avoid | Why |
|-------|-----|
| Custom serial number | Can be stored across power cycles |
| Persistent dynamic config / firmware paths | Same |
| Non-standard custom baud encoding | Easy to leave the channel on an unexpected rate |
| Listen-only init mode | On this adapter it can make the next open fail until a long cooldown |

Read-only device info and a normal-mode open/send/receive loop are enough for almost every debug task.

## CLI is not a resident session

Each `xusbcan send` or `receive` is a fresh open and close. A `while` loop of CLI calls will flap the device and race the close delay above. Hold one `can.Bus` instead.
