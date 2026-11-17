"""剧本变量绑定：set / ${var} 展开 / 文件 vars。"""

from __future__ import annotations

import json
from pathlib import Path

import can

from xusbcan.core import SessionManager, open_session
from xusbcan.models import BitrateConfig, DeviceSpec, Result
from xusbcan.scenario import load_scenario, run_scenario


def _mgr() -> SessionManager:
    def opener(spec: DeviceSpec):
        return Result.ok(
            can.Bus(interface="virtual", channel="xusbcan-scenario-vars", bitrate=500_000)
        )

    mgr = SessionManager(opener=opener)
    mgr.register("a", DeviceSpec("virtual", "virtual", 0, BitrateConfig(500_000)))
    mgr.register("b", DeviceSpec("virtual", "virtual", 1, BitrateConfig(500_000)))
    return mgr


def test_set_and_expand_id_data():
    mgr = _mgr()
    open_session(mgr, "a")
    open_session(mgr, "b")
    result = run_scenario(
        mgr,
        [
            {"action": "set", "name": "rid", "value": "0x321"},
            {"action": "set", "name": "payload", "value": "de ad"},
            {"action": "send", "device": "a", "id": "${rid}", "data": "${payload}"},
            {"action": "wait_id", "device": "b", "id": "${rid}", "data": "dead", "timeout": 0.5},
        ],
    )
    assert result.status == "ok"
    assert result.data["steps"][3]["frame"]["arbitration_id"] == 0x321
    mgr.close_all()


def test_load_scenario_file_vars(tmp_path: Path):
    path = tmp_path / "vars.json"
    path.write_text(
        json.dumps(
            {
                "vars": {"rid": "0x400", "payload": "40"},
                "steps": [
                    {"action": "open", "device": "a"},
                    {"action": "open", "device": "b"},
                    {"action": "send", "device": "a", "id": "${rid}", "data": "${payload}"},
                    {"action": "wait_id", "device": "b", "id": "${rid}", "timeout": 0.5},
                    {"action": "close", "device": "a"},
                    {"action": "close", "device": "b"},
                ],
            }
        ),
        encoding="utf-8",
    )
    steps, variables = load_scenario(path)
    mgr = _mgr()
    result = run_scenario(mgr, steps, variables=variables)
    assert result.status == "ok"
    mgr.close_all()
