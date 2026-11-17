# xusbcan-cli

面向 AI Agent 的 CAN 总线调试工具。

中文 | [English](README.en.md)

> **免责声明**：本项目与广州致远电子股份有限公司（周立功/ZLG）及其产品**没有任何关联、赞助、背书或利益关系**。"周立功"、"ZLG"、"zlgcan" 等名称均为其各自权利人的商标。本项目是独立的第三方工具，仅通过公开的二次开发接口对接其硬件；驱动与 SDK 版权归其权利人所有，由用户从官方渠道获取。

以后端服务形态运行，同时提供标准 **CLI** 与 **MCP（Model Context Protocol）接口**，让 AI Agent 能直接完成 CAN 报文的收发、监听、周期发送等调试操作——无需人工操作上位机软件，即可实现 **Agent 自动化联合调试**。

## 目标与展望

在 AI 时代，让 Agent 能像使用普通工具一样操作 CAN 总线：结构化输出、稳定契约、可被程序化调用。

我们希望 xusbcan-cli 成为 **AI 与车载 / 工业 CAN 总线之间的标准桥梁**，让「用 Agent 自动完成整条总线的联调、诊断、验证」成为常态。

## 特性

- **统一设备抽象**：多家厂商 CAN 卡（周立功 / Vector / PEAK / 创芯 …）通过统一接口接入，Agent 看到的是同一套命令语义
- **CLI 与 MCP 共享核心**：行为一致，结构化 JSON / JSONL 输出，Agent 无需解析人类可读日志
- **轻量**：核心运行时依赖仅 `python-can`

## 安装

### 从 PyPI 安装（推荐）

```bash
pip install xusbcan-cli        # 仅 CLI + 核心
pip install xusbcan-cli[mcp]   # 追加 MCP 服务器支持
```

### 从源码安装

```bash
git clone https://github.com/Archaofan/xusbcan-cli.git
cd xusbcan-cli
pip install -e .          # 仅 CLI + 核心
pip install -e ".[mcp]"   # 追加 MCP 服务器支持
```

## 快速开始

### 1. 准备环境

**运行前提**：
- Python 3.11+（64 位）
- 一张周立功 USBCAN-2E-U 卡
- 周立功 USB 设备驱动（让系统识别设备）
- 周立功二次开发 SDK 资料包（提供 `zlgcan.dll`）

**获取 SDK**：从周立功官方资料页下载二次开发 SDK 资料包：

> https://manual.zlg.cn/web/#/152?page_id=5332

下载后**解压即符合要求**——官方资料包解压出的 SDK 目录已包含运行所需的 `zlgcan.dll` 与 `kerneldlls/`（内核 DLL），无需额外整理。

**配置环境变量**：将解压后的 SDK 目录路径设为环境变量 `ZLG_SDK_DIR`：

```bash
# Windows（PowerShell，用户级持久化）
[Environment]::SetEnvironmentVariable("ZLG_SDK_DIR", "D:\path\to\解压后的SDK目录", "User")

# 或临时设置（仅当前终端生效）
set ZLG_SDK_DIR=D:\path\to\解压后的SDK目录
```

指向的目录结构应为：

```
<ZLG_SDK_DIR>/
├── zlgcan.dll      # 核心库（必需）
└── kerneldlls/     # 内核 DLL 目录（必需，与 zlgcan.dll 同目录）
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

在你的 MCP 客户端（Claude Desktop / Cursor / Claude Code 等）里注册它。配置示例：

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

连接后，Agent 即可通过 `send_frame`、`receive_frame`、`monitor`、`periodic_start` 等工具直接调试 CAN 总线。

## 面向 Agent 的 Skill

本仓库附带可安装的 Agent Skill（`skills/xusbcan`），说明如何调用 CLI / MCP、如何写可独立运行的收发脚本，以及常见失败时该怎么处理。任意兼容 [Agent Skills](https://agentskills.io) 的客户端都可以安装，不限于某一种编辑器：

```bash
npx skills add Archaofan/xusbcan-cli --skill xusbcan
```

在项目目录中执行即可装到当前工程；加 `-g` 则装到用户目录。需要指定客户端时加上 `-a`（例如 `claude-code`、`cursor`）。

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

本项目采用 [MIT License](LICENSE)。第三方组件的许可条款见 [`third_party/NOTICES`](third_party/NOTICES)。
