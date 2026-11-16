"""统一设备抽象：把「厂商 + 型号 + 通道 + 波特率」收敛成一个结构化对象。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BitrateConfig:
    """波特率配置。上层只见「标称/数据段 + 可选采样点」，不见厂商 Timing 寄存器。"""

    nominal: int  # 标称波特率（仲裁段），如 500_000
    data: int | None = None  # 数据段波特率（CAN FD 用）
    sjw: int | None = None  # v1 不解释，留在模型里
    tseg1: int | None = None  # v1 不解释
    tseg2: int | None = None  # v1 不解释


@dataclass
class DeviceSpec:
    """设备描述。vendor/model 只是声明式字符串，用于查表选 Profile。"""

    vendor: str  # 厂商标识：zlg / peak / vector / canalyst ...
    model: str  # 型号：USBCAN-2E-U / PCAN-USB / VN1630 ...
    channel: int = 0  # 统一逻辑通道号（映射由 Profile 完成）
    bitrate: BitrateConfig | None = None
    extra: dict = field(default_factory=dict)  # 厂商专有参数逃生舱
