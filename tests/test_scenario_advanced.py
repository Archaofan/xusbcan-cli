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
                "duration_s": 2.0,
            },
            {"action": "sleep", "seconds": 0.12},
            {"action": "wait_id", "device": "b", "id": 0x100, "timeout": 0.5},
            {"action": "send", "device": "b", "id": 0x101, "data": "aa"},
            {"action": "wait_id", "device": "a", "id": 0x101, "timeout": 0.5},
            {"action": "periodic_stop", "device": "a", "name": "hb"},
        ],
    )
    assert result.status == "ok"
    assert result.data["cleaned_periodics"] == []
    mgr.close_all()


def test_scenario_periodic_requires_duration_and_cleans_on_fail():
    from xusbcan.core import periodic_list

    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    missing = run_scenario(
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
        ],
    )
    assert missing.status == "error"
    assert "duration" in (missing.data["steps"][0].get("error") or "")

    orphan = run_scenario(
        mgr,
        [
            {
                "action": "periodic_start",
                "device": "a",
                "name": "hb",
                "id": 0x100,
                "data": "01",
                "period": 0.05,
                "duration_s": 30.0,
            },
            {"action": "wait_id", "device": "b", "id": 0x7EE, "timeout": 0.05},
        ],
    )
    assert orphan.status == "error"
    assert orphan.data["cleaned_periodics"]
    assert orphan.data["cleaned_periodics"][0]["stopped"] is True
    assert periodic_list(mgr, "a").data["tasks"] == []
    mgr.close_all()


def test_scenario_burst_and_repeat_budget():
    from xusbcan.scenario.runner import MAX_BURST_COUNT, MAX_REPEAT_COUNT

    mgr = _mgr()
    open_session(mgr, "a")
    burst = run_scenario(
        mgr,
        [
            {
                "action": "burst_send",
                "device": "a",
                "id": 0x10,
                "data": "01",
                "count": MAX_BURST_COUNT + 1,
            },
        ],
    )
    assert burst.status == "error"
    assert "burst_send.count" in (burst.data["steps"][0].get("error") or "")

    repeat = run_scenario(
        mgr,
        [
            {
                "action": "repeat",
                "count": MAX_REPEAT_COUNT + 1,
                "steps": [{"action": "sleep", "seconds": 0}],
            },
        ],
    )
    assert repeat.status == "error"
    assert "repeat.count" in (repeat.data["steps"][0].get("error") or "")
    mgr.close_all()


def test_scenario_sleep_step_cap_and_nonfinite():
    from xusbcan.scenario.runner import MAX_STEP_BLOCK_S

    mgr = _mgr()
    open_session(mgr, "a")
    long_sleep = run_scenario(
        mgr,
        [{"action": "sleep", "seconds": MAX_STEP_BLOCK_S + 1}],
    )
    assert long_sleep.status == "error"
    assert "上限" in (long_sleep.data["steps"][0].get("error") or "")

    bad = run_scenario(
        mgr,
        [{"action": "sleep", "seconds": float("nan")}],
    )
    assert bad.status == "error"
    assert "有限数" in (bad.data["steps"][0].get("error") or "")
    mgr.close_all()


def test_scenario_send_frame_budget():
    from xusbcan.scenario import runner as runner_mod

    mgr = _mgr()
    open_session(mgr, "a")
    old = runner_mod.MAX_SCENARIO_SEND_FRAMES
    runner_mod.MAX_SCENARIO_SEND_FRAMES = 3
    try:
        result = run_scenario(
            mgr,
            [
                {"action": "burst_send", "device": "a", "id": 0x11, "data": "01", "count": 2},
                {"action": "burst_send", "device": "a", "id": 0x12, "data": "02", "count": 2},
            ],
        )
        assert result.status == "error"
        assert "累计发送" in (result.data["steps"][1].get("error") or "")
        assert result.data["budget"]["send_frames"] == 3
    finally:
        runner_mod.MAX_SCENARIO_SEND_FRAMES = old
    mgr.close_all()


def test_scenario_multi_device_periodic_cleanup_on_fail():
    from xusbcan.core import periodic_list

    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    result = run_scenario(
        mgr,
        [
            {
                "action": "periodic_start",
                "device": "a",
                "name": "ha",
                "id": 0x100,
                "data": "01",
                "period": 0.05,
                "duration_s": 30.0,
            },
            {
                "action": "periodic_start",
                "device": "b",
                "name": "hb",
                "id": 0x200,
                "data": "02",
                "period": 0.05,
                "duration_s": 30.0,
            },
            {"action": "wait_id", "device": "a", "id": 0x7EE, "timeout": 0.05},
        ],
    )
    assert result.status == "error"
    stopped = { (c["device"], c["name"]): c["stopped"] for c in result.data["cleaned_periodics"] }
    assert stopped.get(("a", "ha")) is True
    assert stopped.get(("b", "hb")) is True
    assert periodic_list(mgr, "a").data["tasks"] == []
    assert periodic_list(mgr, "b").data["tasks"] == []
    mgr.close_all()


def test_scenario_sleep_respects_short_deadline():
    from xusbcan.scenario import runner as runner_mod

    mgr = _mgr()
    open_session(mgr, "a")
    old_wall = runner_mod.MAX_SCENARIO_WALL_S
    runner_mod.MAX_SCENARIO_WALL_S = 0.15
    try:
        result = run_scenario(
            mgr,
            [{"action": "sleep", "seconds": 1.0}],
        )
        assert result.status == "error"
        err = result.data["steps"][0].get("error") or result.error.message
        assert "总时长" in err
        assert result.data["budget"]["overdue"] is True
    finally:
        runner_mod.MAX_SCENARIO_WALL_S = old_wall
    mgr.close_all()


def test_scenario_cleanup_continues_after_one_stop_failure():
    from xusbcan.core import periodic_list, periodic_start, periodic_stop
    from xusbcan.models import CanFrame
    from xusbcan.scenario.runner import ScenarioRuntime

    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    started_a = periodic_start(
        mgr, "a", "ha", CanFrame(0x100, b"\x01"), 0.05, duration_s=30.0
    )
    started_b = periodic_start(
        mgr, "b", "hb", CanFrame(0x200, b"\x02"), 0.05, duration_s=30.0
    )
    assert started_a.status == "ok"
    assert started_b.status == "ok"
    sa = mgr.get("a")
    assert sa is not None
    pt = sa.pop_periodic("ha")
    assert pt is not None
    real = pt.task

    class _Boom:
        def stop(self) -> None:
            raise RuntimeError("stop a failed")

    pt.task = _Boom()
    sa.add_periodic("ha", pt)
    runtime = ScenarioRuntime()
    runtime.note_periodic("a", "ha")
    runtime.note_periodic("b", "hb")
    cleaned = runtime.cleanup_periodics(mgr)
    by = {(c["device"], c["name"]): c for c in cleaned}
    assert by[("a", "ha")]["stopped"] is False
    assert "error" in by[("a", "ha")]
    assert by[("b", "hb")]["stopped"] is True
    assert periodic_list(mgr, "b").data["tasks"] == []
    assert len(periodic_list(mgr, "a").data["tasks"]) == 1
    assert ("a", "ha") in runtime.owned_periodics
    assert ("b", "hb") not in runtime.owned_periodics
    pt.task = real
    assert periodic_stop(mgr, "a", "ha").status == "ok"
    mgr.close_all()


def test_scenario_cleanup_failure_returns_error():
    """步骤成功但 finally 清理失败时，整体不得 Result.ok。"""
    from xusbcan.core import periodic_list, periodic_stop
    from xusbcan.scenario import runner as runner_mod
    from xusbcan.scenario.runner import run_scenario

    mgr = _mgr()
    open_session(mgr, "a")
    steps = [
        {
            "action": "periodic_start",
            "device": "a",
            "name": "hx",
            "id": "0x102",
            "data": "03",
            "period": 0.05,
            "duration_s": 30.0,
        },
        {"action": "sleep", "seconds": 0.01},
    ]
    original_cleanup = runner_mod.ScenarioRuntime.cleanup_periodics

    def _cleanup_with_boom(self, manager):
        for alias, name in list(self.owned_periodics):
            sess = manager.get(alias)
            if sess is None:
                continue
            task = sess.pop_periodic(name)
            if task is None:
                continue

            class _BoomStop:
                def stop(self) -> None:
                    raise RuntimeError("scenario cleanup boom")

            task.task = _BoomStop()
            sess.add_periodic(name, task)
        return original_cleanup(self, manager)

    runner_mod.ScenarioRuntime.cleanup_periodics = _cleanup_with_boom  # type: ignore
    try:
        out = run_scenario(mgr, steps)
    finally:
        runner_mod.ScenarioRuntime.cleanup_periodics = original_cleanup  # type: ignore

    assert out.status == "error"
    assert out.error is not None
    assert "清理失败" in out.error.message
    assert out.data["cleanup_failed"] is True
    assert out.data["cleaned_periodics"][0]["stopped"] is False
    assert len(periodic_list(mgr, "a").data["tasks"]) >= 1

    for t in list(periodic_list(mgr, "a").data["tasks"]):
        name = t["name"]
        sess = mgr.get("a")
        assert sess is not None
        pt2 = sess.pop_periodic(name)
        if pt2 is None:
            continue

        class _Ok:
            def stop(self) -> None:
                return None

        pt2.task = _Ok()
        sess.add_periodic(name, pt2)
        assert periodic_stop(mgr, "a", name).status == "ok"
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
