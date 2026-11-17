"""wait_id 结果写入变量，供后续步骤引用。"""

from __future__ import annotations

import can

from xusbcan.core import SessionManager, open_session
from xusbcan.models import BitrateConfig, DeviceSpec, Result
from xusbcan.scenario import run_scenario


def test_store_frame_fields_into_vars():
    def opener(spec: DeviceSpec):
        return Result.ok(
            can.Bus(interface="virtual", channel="xusbcan-store", bitrate=500_000)
        )

    mgr = SessionManager(opener=opener)
    mgr.register("a", DeviceSpec("virtual", "virtual", 0, BitrateConfig(500_000)))
    mgr.register("b", DeviceSpec("virtual", "virtual", 1, BitrateConfig(500_000)))
    open_session(mgr, "a")
    open_session(mgr, "b")
    result = run_scenario(
        mgr,
        [
            {"action": "send", "device": "a", "id": 0x321, "data": "01 02"},
            {
                "action": "wait_id",
                "device": "b",
                "id": 0x321,
                "timeout": 0.5,
                "store": {"echo_id": "id", "echo_data": "data"},
            },
            {"action": "send", "device": "b", "id": "${echo_id}", "data": "${echo_data}"},
            {"action": "wait_id", "device": "a", "id": 0x321, "data": "0102", "timeout": 0.5},
        ],
    )
    assert result.status == "ok"
    assert result.data["vars"]["echo_id"] == "0x321"
    assert result.data["vars"]["echo_data"] == "0102"
    mgr.close_all()
