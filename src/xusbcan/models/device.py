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

    vendor: str = ""  # 型号登记用的厂商标识；直接写 interface 时可空
    model: str = ""  # 型号登记用的型号；直接写 interface 时可空
    channel: int | str | None = 0  # 整数逻辑通道，或 python-can 后端要求的通道名
    bitrate: BitrateConfig | None = None
    extra: dict = field(default_factory=dict)  # 传给 can.Bus 的后端参数
    interface: str | None = None  # python-can 后端名；设置后不再查型号表
