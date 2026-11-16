# xusbcan-cli

面向 AI Agent 的 CAN 总线调试工具。以后端服务形态运行，同时提供标准 CLI 与 MCP 接口，让 Agent 直接完成 CAN 报文的收发、监听、周期发送等调试操作。

## 特性

- **统一设备抽象**：多家厂商 CAN 卡（周立功 / Vector / PEAK / 创芯 …）差异隔离在底层适配层。
- **CLI 与 MCP 共享同一套 core**：行为一致，结构化 JSON / JSONL 输出。
- **轻量**：核心运行时依赖仅 `python-can`；MCP 依赖走可选 extra。

## 安装

```bash
pip install xusbcan-cli        # 仅 CLI + 核心
pip install xusbcan-cli[mcp]   # 追加 MCP 服务器支持
```

## 快速开始

1. 准备周立功 SDK（`zlgcan.dll` + `kerneldlls/`），设置环境变量 `ZLG_SDK_DIR` 指向 SDK 目录。
2. 编写 `xusbcan.toml`（见示例 `xusbcan.toml`），或设置 `XUSBCAN_CONFIG` 指向它。
3. 使用 CLI：

```bash
xusbcan list
xusbcan send can0 --id 0x123 --data "01 02 03"
xusbcan receive can0 --timeout 1
xusbcan monitor can0 --duration 5
```

4. 启动 MCP 服务器：

```bash
xusbcan mcp serve
```

## 设备接入说明

周立功 USBCAN-2E-U 通过本项目自研的 python-can `zlg` backend 接入（ctypes 封装 `zlgcan.dll`）。厂商 DLL 与驱动**不随本项目分发**，请从周立功官方渠道获取并安装驱动；本项目仅通过 `ZLG_SDK_DIR` 定位 SDK 目录。

> 第三方组件（zlgcan 等）的许可条款见 `third_party/NOTICES`（发布时收录）。

## 文档

- [架构设计与实施方案](docs/architecture.md)
