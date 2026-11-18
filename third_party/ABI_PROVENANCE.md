# 适配层来源与边界说明（ABI_PROVENANCE）

本文件说明本仓库如何对接各厂商 CAN 接口，以及**自有封装**与**用户自备驱动 / SDK** 的边界。  
**本仓库不包含**厂商 DLL、驱动安装包或 SDK 头文件原文；用户须自行从官方渠道获取。

适配分三类，不要混为一谈：

| 类型 | 代表 | 本仓库做什么 |
|------|------|----------------|
| A. 自研 ctypes + 自有 python-can 后端 | 周立功 `zlg`、创芯 `chuangxin` | 按公开 ABI 写绑定，并注册 `can.interface` 入口 |
| B. 仅型号快捷方式 | Vector、PEAK 等 | **不**写厂商 ABI；打开时调用 python-can 已有后端 |
| C. 配置直写 `interface` | socketcan、slcan、Kvaser… | 无型号文件也可打开；本仓库不增加厂商封装 |

---

## 1. 周立功（类型 A）— `adapters/zlg/`

### 实现方式

- 语言层：Python `ctypes`（`WinDLL` / `__stdcall`）按公开 ABI 声明结构体与导出名。
- 总线层：注册为 python-can 后端 `interface=zlg`（见 `pyproject.toml` 的 `can.interface` 入口）。
- 加载：环境变量 `ZLG_SDK_DIR`，定位用户本机的 `zlgcan.dll`。

### 公开来源（文档级）

| 项 | 说明 |
|----|------|
| 接口手册 | 官方《ZLGCAN 接口函数使用手册》（二次开发资料包内；开发时对照过 V1.21 调用顺序，版本以使用者取得的包为准） |
| 许可文本 | 官方包内 `zlgcan License.txt`；摘录见 `NOTICES` |
| 设备类型常量 | 如 USBCAN-II=`4`、USBCAN-2E-U=`21` |
| 结构布局 | 与公开 ABI 对齐；本机曾核对常见尺寸（如 `can_frame=16`、`ZCAN_Transmit_Data=20`、`ZCAN_Receive_Data=24`、`ZCAN_CHANNEL_INIT_CONFIG=32`） |

### 明确未做的事

- **未**复制官方 `.h` / `.c` / 示例工程进仓库。
- **未**分发 `zlgcan.dll` 或 `kerneldlls/`。
- **未**声称厂商赞助、背书或官方合作。

### 公开「真机已确认」型号（以 README 为准）

USBCAN-2E-U、USBCAN-II。

---

## 2. 创芯（类型 A）— `adapters/chuangxin/`

### 实现方式

- 语言层：自研 `ctypes` 绑定用户自备的 `ControlCAN.dll`（`VCI_*` 风格接口）。
- 总线层：注册为 python-can 后端 `interface=chuangxin`。
- 加载：环境变量 `CHUANGXIN_SDK_DIR`，**按绝对路径**加载 DLL，避免与其它同名 `ControlCAN.dll` 混淆。
- 滤波与周期发送：走 python-can 软件路径（不写创芯硬件滤波 / 硬件定时表）。
- 能力：经典 CAN；配置 CAN FD 时打开失败（有意不支持）。

### 公开来源（文档级）

| 项 | 说明 |
|----|------|
| 接口形态 | 创芯二次开发资料中的 ControlCAN / `VCI_*` 约定（以使用者取得的 SDK 包为准） |
| 设备类型 | `VCI_USBCAN2 = 4`（USB_CAN-2C 等与公开头文件常见取值一致） |
| 波特率时序 | 常见标称波特率 → `(Timing0, Timing1)` 表，与同类 ControlCAN 8 MHz 时序表一致 |
| 结构体 | 如 `VCI_CAN_OBJ`、`VCI_INIT_CONFIG`、`VCI_BOARD_INFO` 等字段布局按公开 ABI 自研 ctypes 定义 |

### 明确未做的事

- **未**复制创芯 SDK 头文件或示例工程进仓库。
- **未**分发 `ControlCAN.dll` 或创芯驱动。
- **未**声称创芯赞助、背书或官方合作。
- 与周立功目录分开：`CHUANGXIN_SDK_DIR` 与 `ZLG_SDK_DIR` 勿混用同一进程内的不同同名 DLL。

### 公开状态（以 README 为准）

- USB_CAN-2C：真机已确认。
- USB_CAN-2A-GD：同后端族已登记；真机验证挂起，勿标为已确认。

---

## 3. Vector（类型 B）— `adapters/vector/`

### 本仓库实际做了什么

- **没有**自研 Vector / XL Driver 的 ctypes 或 DLL 封装。
- **没有**注册独立的 `can.interface` 厂商后端；打开时调用 **python-can 已有的 `vector` 后端**。
- 本目录只有 `profiles.py` 型号快捷方式，例如 VN1640A：
  - 声明通道数量与是否允许配置 CAN FD 数据段；
  - 固定 `app_name=None`，按 XL **全局通道索引**打开（不做逻辑通道重映射）；
  - `channel` 原样交给 python-can。
- 公开文档与 Skill：安装驱动、通道索引含义、与其它后端共用 CLI / MCP / scenario 时的注意点。
- 「真机已确认」指：在授权台架上，经本仓库 **统一 CLI / 核心路径**（与 MCP 同源）做过有限验证；底层收发仍由 python-can + 本机 Vector 驱动完成。

### 明确未做的事

- **未**实现第二套 Vector API。
- **未**分发 Vector 驱动、XL Driver、CANoe/CANalyzer 等。
- **未**声称 Vector 官方合作或背书。
- 登记但未真机确认的型号（如 VN1630）不得写成已验证。

### 与「直接写 interface=vector」的关系

配置里写 `interface = "vector"` 且自行传 python-can 文档中的参数，也可打开，**不必**经过本仓库的 `vendor` / `model` 行。型号快捷方式只是减少重复配置、固定已验证过的打开习惯（如 `app_name=None`）。

---

## 4. PEAK 等其它「仅登记」型号（类型 B）

如 `adapters/peak/profiles.py`：把逻辑通道映射为 python-can `pcan` 所需的通道名字符串。同样**无**本仓库自研 PEAK ABI。真机状态以 README 为准（当前多为「已登记，未在本仓库真机确认」）。

---

## 贡献要求（摘要）

- 向类型 A 目录提交改动：说明依据的公开文档或 ABI 观察，确认未粘贴受限制的 SDK 源文件。
- 向类型 B 目录提交改动：只增加或修正 Profile / 文档；不要引入未说明来源的厂商头文件拷贝。
- 类型 C：无需为本仓库新增厂商目录；文档中说明 `interface` 即可打开，勿伪造「本仓库已封装该厂商 ABI」。
- **去耦合**：不得在 `core` / `cli` / `mcp` 引入厂商分支；新型号不得要求改会话层 API 才能打开。
- **Skill**：新增或修订型号页时走 `skills/xusbcan/references/_template-model.md` + `catalog.md` 一行；Field notes 标注「前人现场、未必可复现」；禁止把各型号症状写入根 `SKILL.md` 的 `description`。
- 项目自有代码按根目录 MIT 发布；厂商驱动与 SDK 由使用者自行遵守其许可（见 `NOTICES`）。提交前脱敏：无 DLL、无本机绝对路径、无客户/ECU 名（见根目录 `CLAUDE.md`）。
