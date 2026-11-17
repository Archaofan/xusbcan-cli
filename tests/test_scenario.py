"""毫秒级剧本：发→等→再发（virtual 双别名回环）。"""

from __future__ import annotations

import json
import os
import tempfile

import can

from xusbcan.cli.app import main
from xusbcan.core import SessionManager, open_session
from xusbcan.models import BitrateConfig, DeviceSpec, Result
from xusbcan.scenario import run_scenario


def _mgr() -> SessionManager:
    def opener(spec: DeviceSpec):
        return Result.ok(
            can.Bus(interface="virtual", channel="xusbcan-scenario", bitrate=500_000)
        )

    mgr = SessionManager(opener=opener)
    mgr.register("a", DeviceSpec("virtual", "virtual", 0, BitrateConfig(500_000)))
    mgr.register("b", DeviceSpec("virtual", "virtual", 1, BitrateConfig(500_000)))
    return mgr


def test_send_wait_send_roundtrip():
    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    result = run_scenario(
        mgr,
        [
            {"action": "send", "device": "a", "id": 0x321, "data": "01 02"},
            {"action": "wait_id", "device": "b", "id": 0x321, "timeout": 0.5},
            {"action": "send", "device": "b", "id": 0x322, "data": "aa"},
            {"action": "wait_id", "device": "a", "id": 0x322, "timeout": 0.5},
        ],
    )
    assert result.status == "ok"
    steps = result.data["steps"]
    assert len(steps) == 4
    assert steps[1]["frame"]["arbitration_id"] == 0x321
    assert steps[1]["elapsed_ms"] >= 0
    assert steps[3]["frame"]["arbitration_id"] == 0x322
    mgr.close_all()


def test_wait_id_timeout_fails_step():
    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    result = run_scenario(
        mgr,
        [
            {"action": "wait_id", "device": "b", "id": 0x7FF, "timeout": 0.05},
        ],
    )
    assert result.status == "error"
    assert result.data["failed_at"] == 0
    assert result.data["steps"][0]["ok"] is False
    mgr.close_all()


def test_filter_then_wait():
    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    result = run_scenario(
        mgr,
        [
            {"action": "filter", "device": "b", "from_id": 0x400, "to_id": 0x400},
            {"action": "send", "device": "a", "id": 0x401, "data": "99"},
            {"action": "sleep", "seconds": 0.05},
            {"action": "send", "device": "a", "id": 0x400, "data": "40"},
            {"action": "wait_id", "device": "b", "id": 0x400, "timeout": 0.5},
            {"action": "accept_all", "device": "b"},
        ],
    )
    assert result.status == "ok"
    assert result.data["steps"][4]["frame"]["data"] == "40"
    mgr.close_all()


def test_cli_scenario_file_on_virtual():
    cfg = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False, encoding="utf-8")
    cfg.write(
        """
[[devices]]
name = "a"
interface = "virtual"
channel = "cli-scenario"
nominal = 500000

[[devices]]
name = "b"
interface = "virtual"
channel = "cli-scenario"
nominal = 500000
"""
    )
    cfg.close()
    script = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(
        {
            "steps": [
                {"action": "open", "device": "a"},
                {"action": "open", "device": "b"},
                {"action": "send", "device": "a", "id": "0x111", "data": "01"},
                {"action": "wait_id", "device": "b", "id": "0x111", "timeout": 0.5},
                {"action": "close", "device": "a"},
                {"action": "close", "device": "b"},
            ]
        },
        script,
    )
    script.close()
    try:
        code = main(["--config", cfg.name, "scenario", "--file", script.name])
    finally:
        os.unlink(cfg.name)
        os.unlink(script.name)
    assert code == 0
