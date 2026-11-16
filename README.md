# xusbcan-cli

面向 AI Agent 的 CAN 总线调试工具。

以后端服务形态运行，同时提供标准 **CLI** 与 **MCP（Model Context Protocol）接口**，让 AI Agent 能直接完成 CAN 报文的收发、监听、周期发送等调试操作——无需人工操作上位机软件，即可实现 **Agent 自动化联合调试**。

## 目标与展望

在 AI 时代，让 Agent 能像使用普通工具一样操作 CAN 总线：结构化输出、稳定契约、可被程序化调用。

我们希望 xusbcan-cli 成为 **AI 与车载 / 工业 CAN 总线之间的标准桥梁**，让「用 Agent 自动完成整条总线的联调、诊断、验证」成为常态。

## 特性

- **统一设备抽象**：多家厂商 CAN 卡（周立功 / Vector / PEAK / 创芯 …）通过统一接口接入，Agent 看到的是同一套命令语义
- **CLI 与 MCP 共享核心**：行为一致，结构化 JSON / JSONL 输出，Agent 无需解析人类可读日志
- **轻量**：核心运行时依赖仅 `python-can`

## 安装

```bash
pip install xusbcan-cli        # 仅 CLI + 核心
pip install xusbcan-cli[mcp]   # 追加 MCP 服务器支持
```

## 快速开始

### 1. 安装设备驱动

安装所用 CAN 卡的官方驱动。以周立功 USBCAN-2E-U 为例，从周立功官方渠道获取 SDK（含 `zlgcan.dll`），并设置环境变量指向 SDK 目录：

```bash
# Windows
set ZLG_SDK_DIR=D:\path\to\zlgcan_x64
```

### 2. 编写配置 `xusbcan.toml`

```toml
[[devices]]
name = "ecu"          # 逻辑别名，Agent 通过它引用设备
vendor = "zlg"
model = "USBCAN-2E-U"
channel = 1
nominal = 250000      # 波特率
```

### 3. 使用 CLI

```bash
xusbcan list                                # 列出设备
xusbcan send ecu --id 0x123 --data "01 02 03"   # 发送
xusbcan receive ecu --timeout 1             # 接收一帧
xusbcan monitor ecu --duration 5            # 监听
xusbcan status ecu                          # 状态
```

### 4. 启动 MCP 服务器

```bash
xusbcan-mcp
```

在你的 MCP 客户端（Claude Desktop / Cursor / Claude Code 等）里配置后，Agent 即可通过 `send_frame`、`receive_frame`、`monitor`、`periodic_start` 等工具直接调试 CAN 总线。

## 支持的硬件

当前已验证：**周立功 USBCAN-2E-U**。

项目基于 [python-can](https://python-can.readthedocs.io/)，天然覆盖大量厂商后端（Vector、PEAK、socketcan、slcan、Kvaser …）。新增一种 CAN 卡，通常只需增加一个后端适配或一条设备配置，即可让 Agent 用同一套接口操作它。

### 欢迎适配更多 CAN 卡 🙌

如果你手头有其它型号的 CAN 卡（Vector / PEAK / 创芯 / Kvaser / 国产卡 …），欢迎贡献后端适配或设备配置。让更多硬件能被 AI Agent 直接使用，是这个项目的核心目标之一。

## 参与

- 报告问题、提出需求、提交 PR
- 贡献新的 CAN 卡适配
- 一起把「Agent 自动化联合调试 CAN」这件事做成通用能力

## License

第三方组件的许可条款见 [`third_party/NOTICES`](third_party/NOTICES)。
