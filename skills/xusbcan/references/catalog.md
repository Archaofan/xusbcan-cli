# Model catalog (read this, then at most one model page)

**Do not** open every file under `references/`. After you know `interface` or `vendor` / `model` from `xusbcan.toml` (or the user), open **only** the matching row below. If nothing matches, ask which vendor and model; do not guess by trying another vendor's page.

Shared pages (optional, still not model-specific):

- [examples.md](examples.md) — CLI / MCP / scenario **how to call**
- [pitfalls.md](pitfalls.md) — cross-backend contracts + labeled field notes

Each model page is ordered: **Quick start** → **How this backend behaves** → **Field notes (not guarantees)** → optional resident script. Do not treat Field notes as product specs.

## Routes

| Config match | Open this file | Notes |
|--------------|----------------|--------|
| `vendor=zlg`, `model=USBCAN-2E-U` | [zlg-usbcan-2e-u.md](zlg-usbcan-2e-u.md) | Dual-channel `0`/`1`; do not re-ID from `GetDeviceInf` |
| `vendor=zlg`, `model=USBCAN-II` | [zlg-usbcan-ii.md](zlg-usbcan-ii.md) | Dual-channel `0`/`1` |
| `interface=zlg` and `extra.device_type=21` (or default 2E-U) | [zlg-usbcan-2e-u.md](zlg-usbcan-2e-u.md) | Prefer explicit `model`; same as 2E-U row |
| `interface=zlg` and `extra.device_type=4` | [zlg-usbcan-ii.md](zlg-usbcan-ii.md) | Same as USBCAN-II row |
| `vendor=vector`, `model=VN1640A` | [vector-vn1640a.md](vector-vn1640a.md) | |
| `interface=vector` for a VN1640A | [vector-vn1640a.md](vector-vn1640a.md) | Do not treat unverified Vector models as covered |
| `vendor=vector`, `model=VN1630` | *(no dedicated page)* | Registered only; use python-can `vector` docs; do not apply VN1640A field notes |
| `vendor=chuangxin`, `model=USB_CAN-2C` | [chuangxin-usb-can-2c.md](chuangxin-usb-can-2c.md) | |
| `vendor=chuangxin`, `model=USB_CAN-2A-GD` | [chuangxin-usb-can-2c.md](chuangxin-usb-can-2c.md) | Same backend family; HW check suspended—do not claim verified |
| `interface=chuangxin` | [chuangxin-usb-can-2c.md](chuangxin-usb-can-2c.md) | Requires `CHUANGXIN_SDK_DIR`; channels `0`/`1` |
| `vendor=peak`, `model=PCAN-USB` or `interface=pcan` | *(no dedicated page)* | Registered / python-can `pcan`; follow that backend’s docs |
| Other python-can `interface=…` only | *(no dedicated page)* | Passthrough; driver/`channel`/`extra` per python-can; do not open a ZLG/Chuangxin/Vector model page |

## Adding a card

1. Copy [_template-model.md](_template-model.md) → `references/<vendor>-<model-slug>.md`.
2. Fill **Quick start** first; keep **Field notes** short and labeled as non-guarantees.
3. Add one row to this table.
4. Do **not** append model symptoms to the root Skill `description`.
5. Do **not** paste absolute paths, customer names, or local-only notes.
