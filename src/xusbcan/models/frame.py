"""统一帧模型：跨层传递的报文数据契约，是对 python-can Message 的投影。"""

from __future__ import annotations

from dataclasses import dataclass

import can


@dataclass
class CanFrame:
    arbitration_id: int
    data: bytes
    is_extended: bool = False
    is_fd: bool = False
    is_remote: bool = False
    bitrate_switch: bool = False
    error_state_indicator: bool = False
    timestamp: float | None = None
    channel: int = 0
    dlc: int | None = None

    @classmethod
    def from_can_message(cls, m: can.Message) -> "CanFrame":
        return cls(
            arbitration_id=m.arbitration_id,
            data=m.data,
            is_extended=m.is_extended_id,
            is_fd=m.is_fd,
            is_remote=m.is_remote_frame,
            bitrate_switch=m.bitrate_switch,
            error_state_indicator=m.error_state_indicator,
            timestamp=m.timestamp,
            channel=m.channel if m.channel is not None else 0,
            dlc=m.dlc,
        )

    def to_can_message(self) -> can.Message:
        return can.Message(
            arbitration_id=self.arbitration_id,
            data=self.data,
            is_extended_id=self.is_extended,
            is_fd=self.is_fd,
            is_remote_frame=self.is_remote,
            bitrate_switch=self.bitrate_switch,
            error_state_indicator=self.error_state_indicator,
            timestamp=self.timestamp,
            channel=self.channel,
            dlc=self.dlc,
        )

    def to_dict(self) -> dict:
        """序列化契约（§4.2）：data 为无空格小写十六进制；channel 不进输出 JSON。"""
        d: dict = {
            "arbitration_id": self.arbitration_id,
            "data": self.data.hex(),
            "is_extended": self.is_extended,
            "is_fd": self.is_fd,
            "is_remote": self.is_remote,
            "bitrate_switch": self.bitrate_switch,
            "error_state_indicator": self.error_state_indicator,
        }
        if self.timestamp is not None:
            d["timestamp"] = self.timestamp
        if self.dlc is not None:
            d["dlc"] = self.dlc
        # 注意：channel 不进入输出 JSON，通道以会话和 list/status 为准。
        return d
