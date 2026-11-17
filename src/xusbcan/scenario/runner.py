"""剧本执行器：send / wait_id / sleep / filter / accept_all / open / close / periodic_*。"""

from __future__ import annotations

import time
from typing import Any

from ..core import (
    accept_all_frames,
    close_session,
    open_session,
    parse_hex,
    periodic_start,
    periodic_stop,
    receive,
    send,
    set_frame_filter,
)
from ..core.session import SessionManager
from ..models.frame import CanFrame
from ..models.result import ErrorCode, Result


def _parse_id(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def _step_send(manager: SessionManager, step: dict) -> dict:
    alias = str(step["device"])
    frame = CanFrame(
        arbitration_id=_parse_id(step["id"]),
        data=parse_hex(str(step.get("data", ""))),
        is_extended=bool(step.get("ext", False)),
    )
    t0 = time.perf_counter()
    result = send(manager, alias, frame)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        "ok": result.status == "ok",
        "elapsed_ms": round(elapsed_ms, 3),
        "result": result.to_dict(),
    }


def _step_wait_id(manager: SessionManager, step: dict) -> dict:
    alias = str(step["device"])
    want = _parse_id(step["id"])
    timeout = float(step.get("timeout", 1.0))
    t0 = time.perf_counter()
    deadline = t0 + timeout
    last: dict | None = None
    while time.perf_counter() < deadline:
        remain = max(0.01, deadline - time.perf_counter())
        result = receive(manager, alias, timeout=min(0.1, remain))
        last = result.to_dict()
        if result.status != "ok":
            return {
                "ok": False,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
                "result": last,
            }
        frame = (result.data or {}).get("frame")
        if frame is not None and int(frame["arbitration_id"]) == want:
            return {
                "ok": True,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
                "frame": frame,
            }
    return {
        "ok": False,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "error": f"wait_id timeout for 0x{want:X}",
        "result": last,
    }


def _step_sleep(step: dict) -> dict:
    seconds = float(step.get("seconds", 0))
    t0 = time.perf_counter()
    if seconds > 0:
        time.sleep(seconds)
    return {"ok": True, "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3)}


def _step_filter(manager: SessionManager, step: dict) -> dict:
    alias = str(step["device"])
    start = _parse_id(step.get("from_id", step.get("start_id")))
    end = _parse_id(step.get("to_id", step.get("end_id", start)))
    t0 = time.perf_counter()
    result = set_frame_filter(manager, alias, start, end, bool(step.get("ext", False)))
    return {
        "ok": result.status == "ok",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "result": result.to_dict(),
    }


def _step_accept_all(manager: SessionManager, step: dict) -> dict:
    alias = str(step["device"])
    t0 = time.perf_counter()
    result = accept_all_frames(manager, alias)
    return {
        "ok": result.status == "ok",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "result": result.to_dict(),
    }


def _step_open(manager: SessionManager, step: dict) -> dict:
    alias = str(step["device"])
    t0 = time.perf_counter()
    result = open_session(manager, alias)
    return {
        "ok": result.status == "ok",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "result": result.to_dict(),
    }


def _step_close(manager: SessionManager, step: dict) -> dict:
    alias = str(step["device"])
    t0 = time.perf_counter()
    result = close_session(manager, alias)
    return {
        "ok": result.status == "ok",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "result": result.to_dict(),
    }


def _step_periodic_start(manager: SessionManager, step: dict) -> dict:
    alias = str(step["device"])
    frame = CanFrame(
        arbitration_id=_parse_id(step["id"]),
        data=parse_hex(str(step.get("data", ""))),
        is_extended=bool(step.get("ext", False)),
    )
    t0 = time.perf_counter()
    result = periodic_start(
        manager,
        alias,
        str(step["name"]),
        frame,
        float(step["period"]),
    )
    return {
        "ok": result.status == "ok",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "result": result.to_dict(),
    }


def _step_periodic_stop(manager: SessionManager, step: dict) -> dict:
    alias = str(step["device"])
    t0 = time.perf_counter()
    result = periodic_stop(manager, alias, str(step["name"]))
    return {
        "ok": result.status == "ok",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "result": result.to_dict(),
    }


_HANDLERS = {
    "send": lambda m, s: _step_send(m, s),
    "wait_id": lambda m, s: _step_wait_id(m, s),
    "sleep": lambda m, s: _step_sleep(s),
    "filter": lambda m, s: _step_filter(m, s),
    "accept_all": lambda m, s: _step_accept_all(m, s),
    "open": lambda m, s: _step_open(m, s),
    "close": lambda m, s: _step_close(m, s),
    "periodic_start": lambda m, s: _step_periodic_start(m, s),
    "periodic_stop": lambda m, s: _step_periodic_stop(m, s),
}


def run_scenario(
    manager: SessionManager,
    steps: list[dict],
    *,
    stop_on_error: bool = True,
) -> Result:
    """按顺序执行步骤。默认遇错停止；``data.steps`` 含每步耗时与结果。"""
    if not steps:
        return Result.err(ErrorCode.INVALID_ARGUMENT, "剧本没有步骤")

    records: list[dict] = []
    failed_at: int | None = None
    for index, step in enumerate(steps):
        action = str(step.get("action", "")).strip()
        handler = _HANDLERS.get(action)
        if handler is None:
            record = {
                "index": index,
                "action": action,
                "ok": False,
                "error": f"未知步骤: {action}",
            }
            records.append(record)
            failed_at = index
            if stop_on_error:
                break
            continue
        try:
            detail = handler(manager, step)
        except Exception as e:  # noqa: BLE001 — 收拢为步骤失败，避免剧本半状态裸抛
            detail = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        record = {"index": index, "action": action, **detail}
        records.append(record)
        if not detail.get("ok", False):
            failed_at = index
            if stop_on_error:
                break

    payload = {"steps": records, "failed_at": failed_at, "count": len(records)}
    if failed_at is not None:
        return Result.err(
            ErrorCode.INTERNAL_ERROR,
            f"剧本在步骤 {failed_at} 失败",
            data=payload,
        )
    return Result.ok(payload)
