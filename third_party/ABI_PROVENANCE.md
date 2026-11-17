# ZLG 公开 ABI 绑定来源说明（ABI_PROVENANCE）

本文件说明 `src/xusbcan/adapters/zlg/` 中 ctypes / python-can 后端与周立功公开二次开发接口的关系。  
**本仓库不包含** `zlgcan.dll`、`kerneldlls/`、厂商驱动或 SDK 头文件原文；用户须自行从官方渠道获取 SDK。

## 实现方式

- 语言层：Python `ctypes`（`WinDLL` / `__stdcall`）按公开 ABI 声明结构体字段与导出名。
- 总线层：注册为 python-can 后端 `interface=zlg`，上层 CLI / MCP / scenario 不直接依赖厂商头文件。
- 加载方式：运行时读取环境变量 `ZLG_SDK_DIR`，仅定位用户本机已安装的 `zlgcan.dll`。

## 公开来源（文档级）

| 项 | 说明 |
|----|------|
| 接口手册 | 官方《ZLGCAN 接口函数使用手册》（二次开发资料包内；版本以使用者取得的包为准，开发时对照过 V1.21 调用顺序） |
| 许可文本 | 官方包内 `zlgcan License.txt`；摘录见本目录 `NOTICES`「用户自备 SDK」一节 |
| 设备类型常量 | 如 USBCAN-II=`4`、USBCAN-2E-U=`21`，与公开头文件中的设备类型宏一致（常量级互操作信息） |
| 帧与通道结构 | `can_frame`、发送/接收包装、通道初始化联合体等字段顺序与公开 ABI 对齐；本机曾核对常见尺寸（如 `can_frame=16`、`ZCAN_Transmit_Data=20`、`ZCAN_Receive_Data=24`、`ZCAN_CHANNEL_INIT_CONFIG=32`） |

## 明确未做的事

- **未**将官方 `.h` / `.c` / 示例工程源文件复制进本仓库。
- **未**随仓库或 PyPI 包分发 `zlgcan.dll` 或 `kerneldlls/`。
- **未**声称获得广州致远电子 / 周立功的赞助、背书或官方合作。

## 真机确认（公开口径）

| 型号 | 状态 |
|------|------|
| USBCAN-2E-U | 本仓库公开说明为真机已确认 |
| USBCAN-II | 本仓库公开说明为真机已确认 |

板级日志、本机路径与内部脚本留在本地忽略目录，不进入 git。

## 贡献要求（摘要）

向 `adapters/zlg/` 提交改动时，请说明依据的公开文档或 ABI 观察，并确认未粘贴受限制的 SDK 源文件。项目自有代码按根目录 MIT 发布；厂商 SDK 仍由使用者自行遵守其许可。
