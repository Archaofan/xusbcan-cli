# xusbcan-cli

An AI-Agent-oriented CAN bus debugging tool.

[中文](README.md) | English

> **Disclaimer**: This project has no affiliation, sponsorship, endorsement, or other interest relationship with Guangzhou ZHIYUAN Electronics Co., Ltd. (ZLG) or its products. "ZLG", "zlgcan" and related names are trademarks of their respective owners. This project is an independent third-party tool that interfaces with the hardware through publicly documented APIs; drivers and SDK remain the property of their respective owners, and users obtain them from official channels.

Runs as a backend service with both a standard **CLI** and an **MCP (Model Context Protocol) interface**, letting AI agents directly send / receive / monitor / periodically transmit CAN frames — no manual GUI tooling required. It enables **agent-driven automated joint debugging**.

## Vision

In the AI era, agents should be able to drive a CAN bus like any other tool: structured output, stable contracts, programmatic invocation.

We aim to make xusbcan-cli the **standard bridge between AI and automotive / industrial CAN buses**, turning "agent-automated bus bring-up, diagnostics and validation" into the norm.

## Features

- **Unified device abstraction**: CAN adapters from multiple vendors (ZLG / Vector / PEAK / CANalyst …) behind one interface, one command semantics for agents
- **CLI and MCP share one core**: consistent behavior, structured JSON / JSONL output — no parsing of human-readable logs
- **Lightweight**: core runtime dependency is just `python-can`

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

### 1. Prepare the environment

**Prerequisites**:
- Python 3.11+ (64-bit)
- A ZLG USBCAN-2E-U adapter
- The ZLG USB device driver (so the OS can detect the device)
- The ZLG secondary-development SDK package (provides `zlgcan.dll`)

**Get the SDK**: download the SDK package from the official ZLG documentation page:

> https://manual.zlg.cn/web/#/152?page_id=5332

**Extract and you're done** — the extracted SDK directory already contains the required `zlgcan.dll` and `kerneldlls/` (kernel DLLs). No extra arrangement needed.

**Set the environment variable**: point `ZLG_SDK_DIR` at the extracted SDK directory:

```bash
# Windows (PowerShell, user-level, persistent)
[Environment]::SetEnvironmentVariable("ZLG_SDK_DIR", "D:\path\to\extracted-sdk-dir", "User")

# or temporary (current terminal only)
set ZLG_SDK_DIR=D:\path\to\extracted-sdk-dir
```

The directory should look like:

```
<ZLG_SDK_DIR>/
├── zlgcan.dll      # core library (required)
└── kerneldlls/     # kernel DLL directory (required, same dir as zlgcan.dll)
```

### 2. Write `xusbcan.toml`

```toml
[[devices]]
name = "ecu"          # logical alias agents use to reference the device
vendor = "zlg"
model = "USBCAN-2E-U"
channel = 1
nominal = 250000      # bitrate
```

### 3. Use the CLI

```bash
xusbcan list
xusbcan send ecu --id 0x123 --data "01 02 03"
xusbcan receive ecu --timeout 1
xusbcan monitor ecu --duration 5
xusbcan status ecu
```

### 4. Run the MCP server

```bash
xusbcan-mcp
```

Then register it in your MCP client. Example config (Claude Desktop / Cursor / Claude Code):

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

Once connected, agents can use tools such as `send_frame`, `receive_frame`, `monitor`, `periodic_start` to debug the bus directly.

## Supported hardware

Verified so far: **ZLG USBCAN-2E-U**.

Built on [python-can](https://python-can.readthedocs.io/), which already covers many vendor backends (Vector, PEAK, socketcan, slcan, Kvaser …). Adding a new adapter usually takes just a backend or a device config — and agents keep the same interface.

### Help us support more adapters 🙌

If you have other CAN adapters (Vector / PEAK / CANalyst / Kvaser / domestic …), contributions of backends or device configs are very welcome. Getting more hardware usable by AI agents is a core goal of this project.

## Contributing

- Report issues, request features, submit PRs
- Contribute adapters for new CAN cards
- Let's make "agent-automated CAN joint debugging" a general capability

## License

See [`third_party/NOTICES`](third_party/NOTICES) for third-party component licenses.
