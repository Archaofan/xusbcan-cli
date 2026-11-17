"""复杂剧本：repeat / try / drain / data 断言 / 周期并行 / MCP run_scenario。"""

from __future__ import annotations

import json

import can

from xusbcan.core import SessionManager, open_session
from xusbcan.mcp.tools import register_tools
from xusbcan.models import BitrateConfig, DeviceSpec, Result
from xusbcan.scenario import run_scenario


def _mgr() -> SessionManager:
    def opener(spec: DeviceSpec):
        return Result.ok(
            can.Bus(interface="virtual", channel="xusbcan-scenario-adv", bitrate=500_000)
        )

    mgr = SessionManager(opener=opener)
    mgr.register("a", DeviceSpec("virtual", "virtual", 0, BitrateConfig(500_000)))
    mgr.register("b", DeviceSpec("virtual", "virtual", 1, BitrateConfig(500_000)))
    return mgr


class _Host:
    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, fn=None, **_kwargs):
        def deco(f):
            self.tools[f.__name__] = f
            return f

        return deco if fn is None else deco(fn)


def test_repeat_burst_and_wait_n():
    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    result = run_scenario(
        mgr,
        [
            {
                "action": "repeat",
                "count": 5,
                "steps": [
                    {"action": "send", "device": "a", "id": 0x200, "data": "01"},
                ],
            },
            {"action": "wait_n", "device": "b", "id": 0x200, "count": 5, "timeout": 1.0},
        ],
    )
    assert result.status == "ok"
    wait = result.data["steps"][1]
    assert wait["ok"] is True
    assert wait["received"] == 5
    mgr.close_all()


def test_wait_id_data_mismatch_fails():
    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    result = run_scenario(
        mgr,
        [
            {"action": "send", "device": "a", "id": 0x210, "data": "11 22"},
            {
                "action": "wait_id",
                "device": "b",
                "id": 0x210,
                "data": "aa bb",
                "timeout": 0.5,
            },
        ],
    )
    assert result.status == "error"
    assert result.data["failed_at"] == 1
    mgr.close_all()


def test_try_on_fail_recovers():
    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    result = run_scenario(
        mgr,
        [
            {
                "action": "try",
                "steps": [
                    {"action": "wait_id", "device": "b", "id": 0x7FE, "timeout": 0.05},
                ],
                "on_fail": [
                    {"action": "send", "device": "a", "id": 0x220, "data": "55"},
                    {"action": "wait_id", "device": "b", "id": 0x220, "timeout": 0.5},
                ],
            },
        ],
    )
    assert result.status == "ok"
    assert result.data["steps"][0]["recovered"] is True
    mgr.close_all()


def test_drain_then_unique_frame():
    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    result = run_scenario(
        mgr,
        [
            {"action": "send", "device": "a", "id": 0x230, "data": "01"},
            {"action": "send", "device": "a", "id": 0x231, "data": "02"},
            {"action": "drain", "device": "b", "seconds": 0.2},
            {"action": "send", "device": "a", "id": 0x232, "data": "03"},
            {"action": "wait_id", "device": "b", "id": 0x232, "data": "03", "timeout": 0.5},
        ],
    )
    assert result.status == "ok"
    assert result.data["steps"][4]["frame"]["data"] == "03"
    mgr.close_all()


def test_periodic_parallel_with_request_response():
    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    result = run_scenario(
        mgr,
        [
            {
                "action": "periodic_start",
                "device": "a",
                "name": "hb",
                "id": 0x100,
                "data": "01",
                "period": 0.05,
            },
            {"action": "sleep", "seconds": 0.12},
            {"action": "wait_id", "device": "b", "id": 0x100, "timeout": 0.5},
            {"action": "send", "device": "b", "id": 0x101, "data": "aa"},
            {"action": "wait_id", "device": "a", "id": 0x101, "timeout": 0.5},
            {"action": "periodic_stop", "device": "a", "name": "hb"},
        ],
    )
    assert result.status == "ok"
    mgr.close_all()


def test_mcp_run_scenario_tool():
    mgr = _mgr()
    host = _Host()
    register_tools(host, mgr)
    assert "run_scenario" in host.tools
    payload = {
        "steps": [
            {"action": "open", "device": "a"},
            {"action": "open", "device": "b"},
            {"action": "send", "device": "a", "id": 0x300, "data": "0f"},
            {"action": "wait_id", "device": "b", "id": 0x300, "timeout": 0.5},
            {"action": "close", "device": "a"},
            {"action": "close", "device": "b"},
        ]
    }
    raw = host.tools["run_scenario"](json.dumps(payload))
    result = json.loads(raw)
    assert result["status"] == "ok"
    assert result["data"]["failed_at"] is None
