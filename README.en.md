# xusbcan-cli

A multi-vendor CAN bus tool for AI agents.

Runs as a backend service with both a standard **CLI** and an **MCP (Model Context Protocol)** interface, so an agent can send, receive, monitor, and periodically transmit CAN frames without a vendor GUI—**agent-driven joint debugging** on the bench.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/xusbcan-cli.svg)](https://pypi.org/project/xusbcan-cli/)

[中文](README.md) | English

## Vision

Agents should drive a CAN bus like any other tool: structured output, stable contracts, programmatic invocation.

The **goal** is for xusbcan-cli to become a reliable bridge between AI and automotive / industrial CAN, so agent-driven bench bring-up, diagnosis, and verification become more common. Built on [python-can](https://github.com/hardbyte/python-can), this project adds a thin command and session layer. This is still an early release: ship verified vendors and models first, then grow by model. It does not claim full multi-vendor coverage or industry-standard status yet.

## Features

- **One command set**: CLI / MCP names stay the same; drivers, env vars, and config change with the card
- **Shared CLI and MCP core**: structured JSON for agent branching
- **python-can first**: set `interface` for backends already declared; register a model only when you need a channel map or fixed options
- **Installable Agent Skill**: identify the model first; vendor pitfalls live in per-model files

## Install

```bash
pip install xusbcan-cli        # CLI + core
pip install xusbcan-cli[mcp]   # + MCP
```

From source:

```bash
git clone https://github.com/Archaofan/xusbcan-cli.git
cd xusbcan-cli
pip install -e ".[mcp]"
```

## Quick start

1. Identify **vendor and model**; install that card’s driver / SDK  
2. Write `xusbcan.toml` (or set `XUSBCAN_CONFIG`)  
3. Call the CLI / MCP by alias  

### Shared config

```toml
[[devices]]
name = "bus0"
interface = "socketcan"   # any backend python-can already declares
channel = "can0"
nominal = 500000
# data = 2000000          # optional CAN FD data bitrate
```

- Python 3.11+ (64-bit)
- `name` is the alias used by commands and MCP
- With `interface` set, that backend opens; `vendor` / `model` are for registered shortcuts
- MCP defaults to stdio; `http` binds `127.0.0.1` only

### CLI

```bash
xusbcan list
xusbcan send bus0 --id 0x123 --data "01 02 03"
xusbcan receive bus0 --timeout 1
xusbcan monitor bus0 --duration 5
xusbcan status bus0
xusbcan receive bus0 --timeout 1 --from-id 0x100 --to-id 0x1FF
xusbcan periodic bus0 --name hb --id 0x123 --data "01" --period 0.1 --duration 5
xusbcan scenario --file steps.json
xusbcan scenario --dir scenarios/
```

`periodic` stops after `--duration`. `scenario` runs send→wait→send in one process; `--dir` batch-runs JSON files by name. Use MCP when the session must stay open across calls.

### MCP

```bash
xusbcan-mcp
```

Agents use `open_device`, `send_frame`, `receive_frame`, `monitor`, `periodic_start`, and related tools. `periodic_start` **requires** `duration_s` (max 300 seconds). Longer jobs belong in a local resident process with an authorized bench.

Set each adapter’s env vars plus `XUSBCAN_CONFIG` when registering the server (see vendor sections below).

## Adapter setup

Read the section for your vendor. Each vendor uses **its own** driver and environment variables. Name that card’s `vendor` / `model` or `interface` in the config.

### ZLG

For verified **USBCAN-2E-U** and **USBCAN-II**.

Needs:

- ZLG USB driver
- Secondary-development SDK (`zlgcan.dll` and `kerneldlls/` beside it)
- `ZLG_SDK_DIR` pointing at that SDK directory

Docs: https://manual.zlg.cn/web/#/152?page_id=5332

```bash
set ZLG_SDK_DIR=D:\path\to\zlg-sdk-dir
```

```toml
[[devices]]
name = "bus0"
vendor = "zlg"
model = "USBCAN-2E-U"   # or "USBCAN-II"
channel = 1
nominal = 250000
```

Filter and periodic paths differ by model; see the Agent Skill references.

```json
{
  "mcpServers": {
    "xusbcan": {
      "command": "xusbcan-mcp",
      "env": {
        "ZLG_SDK_DIR": "D:\\path\\to\\zlg-sdk-dir",
        "XUSBCAN_CONFIG": "D:\\path\\to\\xusbcan.toml"
      }
    }
  }
}
```

### Vector

For verified **VN1640A** (**VN1630** is registered, not verified here).

Needs:

- Vector driver / XL Driver (licensed from official channels)
- `channel` as the **same global index** python-can / the XL Driver use (no remapping). Hardware Channel *N* is usually index `N - 1`; trust host enumeration

Opens through python-can’s `vector` backend; this repo only registers a model shortcut.

```toml
[[devices]]
name = "vn0"
vendor = "vector"
model = "VN1640A"
channel = 2
nominal = 250000
# data = 2000000    # optional when that channel supports CAN FD
```

You may also set `interface = "vector"` directly.

```json
{
  "mcpServers": {
    "xusbcan": {
      "command": "xusbcan-mcp",
      "env": {
        "XUSBCAN_CONFIG": "D:\\path\\to\\xusbcan.toml"
      }
    }
  }
}
```

### Chuangxin

For verified **USB_CAN-2C** (**USB_CAN-2A-GD** is registered on the same backend family; **hardware verification is suspended**—do not mark it verified).

Needs:

- Chuangxin USB driver
- A matching-bitness `ControlCAN.dll`
- `CHUANGXIN_SDK_DIR` pointing at the directory that contains that DLL (loaded by absolute path)

```bash
set CHUANGXIN_SDK_DIR=D:\path\to\chuangxin-controlcan-dir
```

```toml
[[devices]]
name = "cx0"
vendor = "chuangxin"
model = "USB_CAN-2C"
channel = 0
nominal = 250000
```

Load only one chosen `ControlCAN.dll` in a process. If other software needs its own copy of that file name, use separate directories or processes.

```json
{
  "mcpServers": {
    "xusbcan": {
      "command": "xusbcan-mcp",
      "env": {
        "CHUANGXIN_SDK_DIR": "D:\\path\\to\\chuangxin-controlcan-dir",
        "XUSBCAN_CONFIG": "D:\\path\\to\\xusbcan.toml"
      }
    }
  }
}
```

### Other backends

Backends python-can already declares (socketcan, slcan, Kvaser, `pcan`, …) can use `interface` directly. **PEAK PCAN-USB** is also registered here (channel map) as “registered, not verified in this repo”. Follow that backend’s docs for driver, `channel`, and `extra`.

## Supported hardware

| Vendor | Model | Status | Notes |
|--------|-------|--------|-------|
| ZLG | USBCAN-2E-U | Verified | `zlg` backend; needs `ZLG_SDK_DIR` |
| ZLG | USBCAN-II | Verified | Same backend, dispatched by model |
| Vector | VN1640A | Verified | python-can `vector`; XL global channel index |
| Vector | VN1630 | Registered | python-can `vector` |
| Chuangxin | USB_CAN-2C | Verified | ControlCAN backend; needs `CHUANGXIN_SDK_DIR` |
| Chuangxin | USB_CAN-2A-GD | Registered (HW verification suspended) | Same backend family as 2C; verification on hold |
| PEAK | PCAN-USB | Registered | python-can `pcan` |

This table lists registered or verified models; it is not an allow-list. Other python-can backends open via `interface` as well. A card python-can cannot open needs a new backend; if that backend requires a user-supplied SDK, add the vendor to the disclaimer.

### Hardware verification note

“Verified on hardware” means: on an **authorized bench**, a limited set of public CLI / core paths was exercised for that model (open/reopen, send/receive, filters, multi-open, `monitor` / `periodic`, `scenario`, as applicable at the time).

**This note applies to every model marked verified in this repository.** Verification covers only that bench and scope. It is **not** a warranty of performance, compatibility, or merchantability for any vendor’s product, and it does not imply every unit, piggyback, or host setup was tested. Items typically out of scope include active error-frame generation, long soak, and in-vehicle networks. Details and pitfalls live in the Agent Skill model references.

## Agent skill

```bash
npx skills add Archaofan/xusbcan-cli --skill xusbcan
```

Install in the project directory, or `-g` for user-wide, or `-a` for a client (for example `cursor`). The skill confirms the model first; vendor notes stay under `references/`.

## Contributing

Issues, PRs, and new vendor or model registrations are welcome. Keep shared config separate from that model’s driver and env vars, and do not mark a model verified before it has been run on hardware.

## Safe use

- Use only on an **authorized bench or lab**. Do not let an agent transmit unattended on a vehicle control network or unauthorized production line
- Confirm wiring, bitrate, and IDs before send / periodic; use an explicit duration or a local resident process for long runs
- Keep MCP local; HTTP binds `127.0.0.1` only—do not expose it publicly
- **Application-layer budgets (not hardware fail-safe)**: MCP / scenario periodic transmit requires a duration (max 300s); scenarios also cap wall time, per-step blocking, and cumulative send attempts. A driver or hardware fault may still leave transmission running

## Disclaimer

This project is an independent third-party tool. It has no affiliation, sponsorship, endorsement, or other interest relationship with the vendors below or their products. Vendor and product names are trademarks of their respective owners. Drivers and SDKs remain their owners’ property; users obtain them from official channels.

The MIT license covers **this project’s own code** only, with no warranty. Dependencies such as `python-can` and any user-supplied SDK keep their own terms; see [`third_party/NOTICES`](third_party/NOTICES).

**Hardware verification covers only the bench scope in “Hardware verification note” above. It is not a warranty of performance, compatibility, or merchantability for any verified model.**

When a newly supported vendor requires a user-supplied SDK or proprietary driver, add a trademark / delivery bullet here:

- **Guangzhou ZHIYUAN Electronics Co., Ltd. (ZLG)**: models opened through the public secondary-development API include USBCAN-2E-U and USBCAN-II. "ZLG" and "zlgcan" are trademarks of their owner. This project does not ship the vendor driver or `zlgcan.dll`.
- **Vector Informatik GmbH (Vector)**: models opened through python-can `vector` include VN1640A. "Vector", "VN1640A", and "XL Driver" are trademarks of their owners. This project does not ship Vector drivers, the XL Driver, CANoe/CANalyzer, or other proprietary software.
- **Zhuhai Chuangxin Technology Co., Ltd. (Chuangxin)**: models opened through this project’s ControlCAN (`VCI_*`) wrapper include USB_CAN-2C. "Chuangxin", "USB_CAN-2C", and "CANalyst" are trademarks of their owners. This project does not ship the Chuangxin driver or `ControlCAN.dll`.

## License

[MIT License](LICENSE). See [`third_party/NOTICES`](third_party/NOTICES) and [`third_party/ABI_PROVENANCE.md`](third_party/ABI_PROVENANCE.md).
