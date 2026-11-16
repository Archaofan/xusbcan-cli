"""领域模型单元测试：数据契约的序列化与互转。"""

from __future__ import annotations

from xusbcan.models import BitrateConfig, CanFrame, DeviceSpec


def test_can_frame_serialization_contract():
    """序列化契约：data 为无空格小写十六进制；channel 不进输出 JSON。"""
    f = CanFrame(arbitration_id=0x123, data=bytes([1, 2, 3]), channel=7, dlc=3)
    d = f.to_dict()
    assert d["arbitration_id"] == 0x123
    assert d["data"] == "010203"
    assert d["dlc"] == 3
    assert "channel" not in d  # 通道不进输出 JSON（§4.5）
    assert d["is_extended"] is False
    assert d["is_fd"] is False


def test_can_frame_empty_data():
    f = CanFrame(arbitration_id=0x1, data=b"")
    assert f.to_dict()["data"] == ""


def test_can_frame_roundtrip_with_can_message():
    f = CanFrame(
        arbitration_id=0x18FF0002,
        data=bytes([0xA5] * 8),
        is_extended=True,
        timestamp=1234.5,
        dlc=8,
    )
    m = f.to_can_message()
    assert m.arbitration_id == 0x18FF0002
    assert m.is_extended_id is True
    assert m.data == bytes([0xA5] * 8)

    f2 = CanFrame.from_can_message(m)
    assert f2 == f


def test_device_spec_defaults():
    spec = DeviceSpec(vendor="zlg", model="USBCAN-2E-U")
    assert spec.channel == 0
    assert spec.bitrate is None
    assert spec.extra == {}


def test_bitrate_config():
    b = BitrateConfig(nominal=500_000, data=2_000_000)
    assert b.nominal == 500_000
    assert b.data == 2_000_000
