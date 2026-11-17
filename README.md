# xusbcan-cli

面向 AI Agent 的 CAN 总线调试工具。目标是适配多种 CAN 卡；当前阶段真机确认的型号是周立功 USBCAN-2E-U 与 USBCAN-II。

中文 | [English](README.en.md)

以后端服务形态运行，同时提供标准 **CLI** 与 **MCP（Model Context Protocol）接口**，让 AI Agent 能直接完成 CAN 报文的收发、监听、周期发送等调试操作——无需人工操作上位机软件，即可实现 **Agent 自动化联合调试**。

## 目标与展望

在 AI 时代，让 Agent 能像使用普通工具一样操作 CAN 总线：结构化输出、稳定契约、可被程序化调用。

我们希望 xusbcan-cli 成为 **AI 与车载 / 工业 CAN 总线之间的标准桥梁**，让「用 Agent 自动完成整条总线的联调、诊断、验证」成为常态。第一阶段先把一种型号跑通，后续按型号增加，而不是只服务这一张卡。

## 特性

- **同一套命令，按型号接入**：Agent 使用的 CLI / MCP 命令不随厂商变化。驱动、环境变量和配置里的厂商、型号随卡变化
- **CLI 与 MCP 共享核心**：行为一致，结构化 JSON / JSONL 输出，Agent 无需解析人类可读日志
- **以 python-can 为底座**：借用它已经覆盖的 CAN 生态，本项目在上面提供统一的命令和会话。安装本工具不等于自动打开 python-can 支持的每一张卡

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

先看清手上的卡是哪一家、哪一型号，再按该型号准备驱动和配置。下面的周立功步骤只适用于已确认的 USBCAN-2E-U / USBCAN-II，不能套到其它厂商的卡上。

### 1. 通用前提与通用配置

所有卡共用这些：

- Python 3.11+（64 位）
- 配置文件 `xusbcan.toml`（也可用 `--config` 或环境变量 `XUSBCAN_CONFIG`）
- 每台设备写 `name`（别名）。命令和 MCP 工具都用别名
- `interface` 填 python-can 的后端名，`channel` 按该后端的要求写整数或字符串，`nominal` 是标称波特率
- 该后端还要的参数放在 `extra` 里。驱动仍要按该卡自己的要求安装；没装驱动时打开会失败

```toml
[[devices]]
name = "bus0"
interface = "socketcan"   # python-can 已声明的后端名
channel = "can0"
nominal = 500000
data = 2000000         # 可选，CAN FD 数据段波特率
# sjw / tseg1 / tseg2  # 可选，采样点；也会传给使用 *_abr 名称的后端
```

python-can 声明支持的后端都可以这样写，不需要先在本仓库登记型号。`vendor` / `model` 只用于下面那些需要通道映射或专有参数的型号。写了 `interface` 就按这个后端打开，不再套用型号表。

MCP 默认走 stdio。配置里把传输设为 `http` 时，服务只绑定 `127.0.0.1`。

```bash
xusbcan-mcp
```

### 2. 型号专属：周立功 USBCAN-2E-U / USBCAN-II（当前真机已确认）

这两种型号还需要：

- 周立功 USB 设备驱动（让系统识别设备）
- 周立功二次开发 SDK（提供 `zlgcan.dll` 与同目录的 `kerneldlls/`）
- 环境变量 `ZLG_SDK_DIR` 指向解压后的 SDK 目录

SDK 从周立功官方资料页获取：

> https://manual.zlg.cn/web/#/152?page_id=5332

```bash
# Windows（PowerShell，用户级持久化）
[Environment]::SetEnvironmentVariable("ZLG_SDK_DIR", "D:\path\to\解压后的SDK目录", "User")

# 或临时设置（仅当前终端生效）
set ZLG_SDK_DIR=D:\path\to\解压后的SDK目录
```

```toml
[[devices]]
name = "bus0"
vendor = "zlg"
model = "USBCAN-2E-U"   # 或 "USBCAN-II"
channel = 1             # II 常用 0；按实际接线改
nominal = 250000
```

同一套 CLI / MCP 命令；滤波与周期发送在两种卡上的底层路径不同，Agent Skill 里按型号分文件说明。MCP 客户端注册时，这两种周立功卡都需要带上 `ZLG_SDK_DIR`：

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

### 3. 使用 CLI

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

`periodic` 在本进程内发完指定时长后停止。`scenario` 按 JSON 步骤做发→等→再发等编排（同进程会话）；`--dir` 按文件名排序批跑目录内全部 `*.json`。滤波命令对各后端相同。要跨多次命令保持会话，也可用 MCP。

连接 MCP 后，Agent 用 `send_frame`、`receive_frame`、`monitor`、`periodic_start` 等工具操作同一别名。

## 面向 Agent 的 Skill

本仓库附带可安装的 Agent Skill（`skills/xusbcan`）。它先要求确认型号，再说明通用调用方式；厂商踩坑只写在对应型号下。任意兼容 [Agent Skills](https://agentskills.io) 的客户端都可以安装：

```bash
npx skills add Archaofan/xusbcan-cli --skill xusbcan
```

在项目目录中执行即可装到当前工程；加 `-g` 则装到用户目录。需要指定客户端时加上 `-a`（例如 `claude-code`、`cursor`）。

## 支持范围

| 状态 | 厂商 / 型号 | 说明 |
|------|-------------|------|
| 真机已确认 | 周立功 USBCAN-2E-U | 本仓库提供该型号的后端。需要 `ZLG_SDK_DIR` 与周立功驱动、SDK |
| 真机已确认 | 周立功 USBCAN-II | 同一 `zlg` 后端按型号分发。同样需要 `ZLG_SDK_DIR` 与周立功驱动、SDK |
| 已登记，本仓库未做真机确认 | PEAK PCAN-USB | 打开时交给 python-can 的 `pcan`。需要 PEAK 自己的驱动，不要设置 `ZLG_SDK_DIR` |
| 已登记，本仓库未做真机确认 | Vector VN1630 | 打开时交给 python-can 的 `vector`，通道 `0` 和 `1`。需要 Vector 自己的驱动。CAN FD 写 `data` |

python-can 声明的其它后端（socketcan、slcan、Kvaser 等）在配置里写 `interface` 即可由 CLI / MCP 打开。上表只是带了额外映射的型号，不是一张准入名单。本仓库没有逐张做真机确认；驱动和该后端要求的 `channel`、`extra` 仍要按 python-can 的说明准备。

python-can 没有的卡才需要新后端。新后端若要用户自备 SDK，在文末免责声明追加该厂商。

### 欢迎适配更多 CAN 卡

如果你手头有其它型号（Vector、PEAK、创芯、Kvaser 或其它国产卡），欢迎贡献该型号的登记或后端。请分开写通用配置和该型号的驱动、环境变量，并在真机确认前不要写成「已验证」。

## 参与

- 报告问题、提出需求、提交 PR
- 贡献新的 CAN 卡型号
- 一起把「Agent 自动化联合调试 CAN」做成跨厂商能力

## License

本项目采用 [MIT License](LICENSE)。第三方组件的许可条款见 [`third_party/NOTICES`](third_party/NOTICES)。

## 免责声明

本项目是独立的第三方工具，与下列厂商及其产品没有关联、赞助、背书或利益关系。厂商名称、产品名称均为其各自权利人的商标。驱动与 SDK 的版权归权利人所有，由使用者从官方渠道自行获取。

每支持一家需要使用者自备 SDK 或专有驱动的厂商，在此追加一条。不要把某一家的声明当成覆盖所有厂商。

- **广州致远电子股份有限公司（周立功 / ZLG）**：当前直接对接其公开二次开发接口的型号是 USBCAN-2E-U 与 USBCAN-II。"周立功"、"ZLG"、"zlgcan" 等名称均为其商标。本项目不随附其驱动或 `zlgcan.dll`。
