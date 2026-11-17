"""无硬件：双别名共享 virtual 通道，验证会话级收发与滤波交叉契约。"""

from __future__ import annotations

import can

from xusbcan.core import (
    SessionManager,
    accept_all_frames,
    close_session,
    open_session,
    receive,
    send,
    set_frame_filter,
)
from xusbcan.models import BitrateConfig, CanFrame, DeviceSpec, Result


def _shared_opener(spec: DeviceSpec):
    # 同一 channel 名 → python-can virtual 回环
    return Result.ok(
        can.Bus(interface="virtual", channel="xusbcan-dual-loop", bitrate=500_000)
    )


def test_dual_alias_loopback_and_soft_filters():
    mgr = SessionManager(opener=_shared_opener)
    mgr.register("a", DeviceSpec("virtual", "virtual", 0, BitrateConfig(500_000)))
    mgr.register("b", DeviceSpec("virtual", "virtual", 1, BitrateConfig(500_000)))
    assert open_session(mgr, "a").status == "ok"
    assert open_session(mgr, "b").status == "ok"

    assert send(mgr, "a", CanFrame(0x321, b"\x01\x02")).status == "ok"
    rx = receive(mgr, "b", timeout=0.5)
    assert rx.status == "ok"
    assert rx.data["frame"]["arbitration_id"] == 0x321
    assert rx.data["frame"]["data"] == "0102"

    assert set_frame_filter(mgr, "b", 0x400, 0x400, False).status == "ok"
    assert send(mgr, "a", CanFrame(0x401, b"\x99")).status == "ok"
    blocked = receive(mgr, "b", timeout=0.2)
    assert blocked.data["frame"] is None
    assert send(mgr, "a", CanFrame(0x400, b"\x40")).status == "ok"
    passed = receive(mgr, "b", timeout=0.5)
    assert passed.data["frame"]["arbitration_id"] == 0x400
    assert accept_all_frames(mgr, "b").status == "ok"

    close_session(mgr, "a")
    close_session(mgr, "b")
