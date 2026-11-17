# xusbcan-cli

An AI-agent-oriented CAN bus tool. It is meant to cover many adapters. Models verified on hardware in this stage include the ZLG USBCAN-2E-U and USBCAN-II, the Vector VN1640A (python-can `vector`), and Chuangxin USB_CAN-2C (ControlCAN).

[中文](README.md) | English

Runs as a backend service with both a standard **CLI** and an **MCP (Model Context Protocol) interface**, so an agent can send, receive, monitor, and periodically transmit CAN frames without a vendor GUI.

## Vision

Agents should drive a CAN bus like any other tool: structured output, stable contracts, programmatic invocation.

The **goal** is for xusbcan-cli to become a reliable bridge between AI and automotive / industrial CAN on the bench. This is still an early release: ship the verified models first, then grow by model. It does not claim full multi-vendor coverage or industry-standard status yet.

## Features

- **One command set, per-model setup**: CLI and MCP commands stay the same. Drivers, environment variables, and the configured vendor and model change with the card
- **CLI and MCP share one core**: consistent behavior, structured JSON / JSONL output
- **Built on python-can**: the project uses that ecosystem and adds a thin command and session layer. Installing this package does not turn on every interface python-can ships

## Install

### From PyPI (recommended)

```bash
pip install xusbcan-cli        # CLI + core only
pip install xusbcan-cli[mcp]   # + MCP server support
```

### From source

```bash
git clone https://github.com/Archaofan/xusbcan-cli.git
cd xusbcan-cli
pip install -e .          # CLI + core only
pip install -e ".[mcp]"   # + MCP server support
```

## Quick Start

Identify the vendor and model first, then follow that model's driver and config. ZLG, Vector, and Chuangxin each have their own steps and environment variables—do not mix them.

### 1. Shared prerequisites and config

Every card uses:

- Python 3.11+ (64-bit)
- `xusbcan.toml` (or `--config`, or `XUSBCAN_CONFIG`)
- A `name` (alias). Commands and MCP tools take that alias
- `interface`: a python-can backend name. `channel`: an integer or string, as that backend requires. `nominal`: bitrate
- Further backend arguments go in `extra`. The vendor driver still has to be installed; opening fails when it is missing

```toml
[[devices]]
name = "bus0"
interface = "socketcan"   # a backend python-can already declares
channel = "can0"
nominal = 500000
```

Any backend python-can declares can be written this way. No per-model registration in this repo is required. `vendor` / `model` exist for the rows below that need a channel map or extra options. When `interface` is set, that backend is opened and the model table is not applied.

The MCP default transport is stdio. `http` binds `127.0.0.1` only.

```bash
xusbcan-mcp
```

### 2. Model-specific: ZLG USBCAN-2E-U / USBCAN-II (verified on hardware)

Both models also need:

- The ZLG USB driver
- The ZLG secondary-development SDK (`zlgcan.dll` and `kerneldlls/` beside it)
- `ZLG_SDK_DIR` pointing at that extracted directory

Download the SDK from the vendor's documentation page:

> https://manual.zlg.cn/web/#/152?page_id=5332

```bash
# Windows (PowerShell, user-level, persistent)
[Environment]::SetEnvironmentVariable("ZLG_SDK_DIR", "D:\path\to\extracted-sdk-dir", "User")

# or temporary (current terminal only)
set ZLG_SDK_DIR=D:\path\to\extracted-sdk-dir
```

```toml
[[devices]]
name = "bus0"
vendor = "zlg"
model = "USBCAN-2E-U"   # or "USBCAN-II"
channel = 1             # II often uses 0; match your wiring
nominal = 250000
```

CLI and MCP commands are the same; filter and periodic paths differ by model (see the Agent Skill per-model files). Both ZLG models need `ZLG_SDK_DIR` in the MCP client config:

```json
{
  "mcpServers": {
    "xusbcan": {
      "command": "xusbcan-mcp",
      "env": {
        "ZLG_SDK_DIR": "D:\\path\\to\\zlgcan_x64",
        "XUSBCAN_CONFIG": "D:\\path\\to\\xusbcan.toml"
      }
    }
  }
}
```

### 3. Model-specific: Vector VN1640A (verified on hardware)

This model does **not** use the ZLG SDK and must **not** set `ZLG_SDK_DIR`. Opening goes to python-can's declared `vector` backend; this repo only registers a model shortcut and does not ship a custom Vector driver stack.

Also required:

- A locally installed Vector driver / XL Driver (obtained and licensed from Vector)
- `channel` must be the **same global channel index** python-can / the XL Driver use (no logical remapping). Hardware Channel *N* is usually index `N - 1`; trust the host enumeration
- Optional: set `interface = "vector"` directly, or `vendor = "vector"` / `model = "VN1640A"` (the shortcut supplies defaults needed to open by global index)

```toml
[[devices]]
name = "vn_ch3"
vendor = "vector"
model = "VN1640A"
channel = 2          # example: hardware Channel 3 → index 2; match your wiring
nominal = 250000
# data = 2000000    # optional when that channel supports CAN FD
```

The same CLI / MCP commands apply by alias. The Agent Skill opens the VN1640A reference only after the configured model matches.

**Hardware verification scope (summary):** on an authorized bench, against a verified ZLG USBCAN-2E-U on the same classic CAN bus: open/close and reopen, bidirectional frames, filters, multi-channel and dual-adapter open, `monitor` / `periodic`, and `scenario` (including `burst_send` / `wait_n` / `repeat`). Not covered: active error-frame generation, long soak runs, in-vehicle networks, or channels that are not wired. Passing these checks does not guarantee every VN1640A unit, piggyback mix, or Vector software license.

When registering MCP for Vector, omit `ZLG_SDK_DIR`. Point at a correct `XUSBCAN_CONFIG` and keep the Vector driver available on the host:

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

### 4. Model-specific: Chuangxin USB_CAN-2C (verified on hardware)

This model uses the Chuangxin **ControlCAN** library (`VCI_*`). Do **not** set `ZLG_SDK_DIR`, and do **not** open it with a ZLG model name.

Also required:

- The Chuangxin USB driver
- A matching-bitness Chuangxin `ControlCAN.dll`
- `CHUANGXIN_SDK_DIR` pointing at the directory that contains that DLL (this tool loads it by absolute path)

```bash
# current terminal only (do not set a machine-wide variable unless you choose to)
set CHUANGXIN_SDK_DIR=D:\path\to\chuangxin-controlcan-dir
```

```toml
[[devices]]
name = "cx0"
vendor = "chuangxin"
model = "USB_CAN-2C"
channel = 0             # first CAN channel; second is 1
nominal = 250000
```

The same CLI / MCP commands apply. `USB_CAN-2A-GD` is registered on the same ControlCAN backend and device-type family as 2C; confirm on your hardware before treating it as verified.

**Hardware verification scope (summary):** on an authorized bench, against a verified ZLG USBCAN-2E-U on the same classic CAN bus: open/close and reopen, bidirectional frames, filters, dual-channel and dual-adapter open, `monitor` / `periodic`, and `scenario` (including `burst_send` / `wait_n` / `repeat`). Not covered: active error-frame generation, long soak, or in-vehicle networks. Passing these checks does not guarantee every USB_CAN-2C unit or host setup.

**Coexistence notes:**

- In this tool, ZLG uses `ZLG_SDK_DIR` (`zlgcan.dll`) and Chuangxin uses `CHUANGXIN_SDK_DIR` (`ControlCAN.dll`). With separate directories, a verified ZLG 2E and Chuangxin 2C **can be open in the same process**.
- Do **not** load two different binaries that share the file name `ControlCAN.dll` in one process (the OS usually keeps a single module name). If other software also depends on its own `ControlCAN.dll`, keep directories or processes separate.
- Config must name `chuangxin` / `USB_CAN-2C` (or another registered model in that family). Do not use a ZLG `USBCAN-II` entry to open a Chuangxin card.

When registering MCP for Chuangxin, set `CHUANGXIN_SDK_DIR` (and `XUSBCAN_CONFIG`). Omit `ZLG_SDK_DIR` unless the same process also opens a ZLG card:

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

### 5. Use the CLI

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

`periodic` transmits for `--duration` seconds in this process, then stops. `scenario` runs millisecond send→wait→send steps in one process; `--dir` runs every `*.json` in that folder in name order. Filter commands are the same for every backend. Use MCP when the session must stay open across calls.

After the MCP server is connected, the agent uses `send_frame`, `receive_frame`, `monitor`, `periodic_start`, and the other tools on the same alias. MCP `periodic_start` **requires** `duration_s` (max 300 seconds) and stops when it elapses; for longer transmit jobs use a local resident process with an explicitly authorized bench setup.

## Agent skill

This repo ships an installable Agent Skill (`skills/xusbcan`). It asks for the model first, then documents the shared commands. Vendor pitfalls stay under that vendor. Any client that supports [Agent Skills](https://agentskills.io) can install it:

```bash
npx skills add Archaofan/xusbcan-cli --skill xusbcan
```

Run that in the project to install locally, or add `-g` for a user-wide install. Pass `-a` to target a client (for example `claude-code` or `cursor`).

## Supported hardware

| Status | Vendor / model | Notes |
|--------|----------------|-------|
| Verified on hardware | ZLG USBCAN-2E-U | Backend in this repo. Needs `ZLG_SDK_DIR` plus the vendor driver and SDK |
| Verified on hardware | ZLG USBCAN-II | Same `zlg` backend, dispatched by model. Needs `ZLG_SDK_DIR` plus the vendor driver and SDK |
| Verified on hardware | Vector VN1640A | Opens python-can's `vector`; channel index matches the XL global index (no remapping). Needs the Vector driver. Agents call it through the CLI / MCP. Set `data` for CAN FD |
| Verified on hardware | Chuangxin USB_CAN-2C | ControlCAN backend in this repo. Needs `CHUANGXIN_SDK_DIR` plus the vendor driver and DLL. Agents call it through the CLI / MCP |
| Registered, not verified here | Chuangxin USB_CAN-2A-GD | Same ControlCAN backend and device-type family as 2C; confirm on hardware |
| Registered, not verified here | Vector VN1630 | Opens python-can's `vector`, channels `0` and `1`. Needs the Vector driver. Set `data` for CAN FD |
| Registered, not verified here | PEAK PCAN-USB | Opens python-can's `pcan`. Needs the PEAK driver, not `ZLG_SDK_DIR` |

Other python-can backends (socketcan, slcan, Kvaser, and the rest) open through the CLI and MCP when `interface` names them. The table above is only the models that need an extra mapping, not an allow-list. This repo has not verified each card on hardware. Install that card's driver, and set `channel` and `extra` the way python-can documents them.

A card python-can cannot open needs a new backend. If that backend requires the user to supply an SDK, add the vendor to the disclaimer.

### Help support more adapters

Contributions for other models (Vector, PEAK, CANalyst, Kvaser, and others) are welcome. Keep shared config separate from that model's driver and environment variables, and do not mark a model verified before it has been run on hardware.

## Contributing

- Report issues, request features, submit PRs
- Add another CAN adapter model
- Make agent-driven CAN debugging work across vendors

## License

This project is licensed under the [MIT License](LICENSE). See [`third_party/NOTICES`](third_party/NOTICES) for third-party component licenses and [`third_party/ABI_PROVENANCE.md`](third_party/ABI_PROVENANCE.md) for how the ZLG public ABI binding was derived.

## Safe use

- Use only on an **authorized bench or lab** bus. Do not let an agent transmit unattended on a vehicle control network or an unauthorized production line.
- Both the CLI and MCP can send and periodically transmit. Confirm wiring, bitrate, and IDs first. For long runs, set an explicit duration or use a local resident process, and accept the operational risk yourself.
- Keep MCP on the local machine. When HTTP is enabled, it binds to `127.0.0.1` only; do not expose it publicly.
- **Application-layer budgets (not hardware fail-safe)**: MCP/scenario periodic transmit requires a duration (max 300s). Scenarios also cap wall time (~300s), per-step blocking (~60s), and cumulative `send`/`burst_send` attempts (~10000). Frames from periodic tasks are **not** counted in that 10000; they are bounded by `duration_s` instead. A driver or hardware fault may still leave transmission running.

## Disclaimer

This project is an independent third-party tool. It has no affiliation, sponsorship, endorsement, or other interest relationship with the vendors below or their products. Vendor and product names are trademarks of their respective owners. Drivers and SDKs remain the property of those owners; users obtain them from official channels.

The MIT license covers **this project's own code** only, with no warranty. Dependencies such as `python-can` and any user-supplied SDK keep their own terms; see [`third_party/NOTICES`](third_party/NOTICES). Do not treat the whole install tree as MIT.

When a newly supported vendor requires the user to supply an SDK or proprietary driver, add a bullet here. One vendor's notice does not cover the others.

- **Guangzhou ZHIYUAN Electronics Co., Ltd. (ZLG)**: the models this project calls through the public secondary-development API are the USBCAN-2E-U and USBCAN-II. "ZLG" and "zlgcan" are trademarks of their owner. This project does not ship the vendor driver or `zlgcan.dll`.
- **Vector Informatik GmbH (Vector)**: models such as the VN1640A open through python-can's `vector` backend. This project does not implement or ship Vector drivers, the XL Driver, CANoe/CANalyzer, or other Vector proprietary software. "Vector", "VN1640A", and "XL Driver" are trademarks of their owners. Users must obtain a lawful license for the driver and runtime. Hardware verification here covers only the bench scope described above and is not a warranty of Vector product performance, compatibility, or merchantability.
- **Zhuhai Chuangxin Technology Co., Ltd. (Chuangxin)**: models such as the USB_CAN-2C open through this project's thin ControlCAN (`VCI_*`) wrapper. "Chuangxin", "USB_CAN-2C", and "CANalyst" are trademarks of their owners. This project does not ship the Chuangxin driver or `ControlCAN.dll`; users obtain them from official channels and point `CHUANGXIN_SDK_DIR` at the DLL directory. Hardware verification covers only the bench scope above and is not a warranty of performance or merchantability.
