"""剧本执行器：顺序 / 重复 / try 恢复 / 数据断言 / 排空 / 多帧等待。

步骤不含厂商概念；长编排在同进程 SessionManager 上执行。
"""

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


def _norm_hex(value: str | bytes | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.hex()
    return parse_hex(str(value)).hex()


def _frame_matches(frame: dict, step: dict) -> bool:
    want = _parse_id(step["id"])
    if int(frame["arbitration_id"]) != want:
        return False
    if "ext" in step and bool(frame.get("is_extended")) != bool(step["ext"]):
        return False
    expect = _norm_hex(step.get("data"))
    if expect is not None and str(frame.get("data", "")) != expect:
        return False
    return True


def _step_send(manager: SessionManager, step: dict) -> dict:
    alias = str(step["device"])
    frame = CanFrame(
        arbitration_id=_parse_id(step["id"]),
        data=parse_hex(str(step.get("data", ""))),
        is_extended=bool(step.get("ext", False)),
    )
    t0 = time.perf_counter()
    result = send(manager, alias, frame)
    return {
        "ok": result.status == "ok",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
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
        if frame is None:
            continue
        if int(frame["arbitration_id"]) != want:
            continue
        if "ext" in step and bool(frame.get("is_extended")) != bool(step["ext"]):
            continue
        expect = _norm_hex(step.get("data"))
        if expect is not None and str(frame.get("data", "")) != expect:
            return {
                "ok": False,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
                "frame": frame,
                "error": (
                    f"wait_id data mismatch for 0x{want:X}: "
                    f"got {frame.get('data')} expect {expect}"
                ),
            }
        return {
            "ok": True,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
            "frame": frame,
        }
    expect = _norm_hex(step.get("data"))
    extra = f" data={expect}" if expect is not None else ""
    return {
        "ok": False,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "error": f"wait_id timeout for 0x{want:X}{extra}",
        "result": last,
    }


def _step_wait_n(manager: SessionManager, step: dict) -> dict:
    alias = str(step["device"])
    need = int(step.get("count", 1))
    if need < 1:
        return {"ok": False, "error": "wait_n.count 必须 >= 1"}
    timeout = float(step.get("timeout", 1.0))
    t0 = time.perf_counter()
    deadline = t0 + timeout
    got = 0
    frames: list[dict] = []
    while time.perf_counter() < deadline and got < need:
        remain = max(0.01, deadline - time.perf_counter())
        result = receive(manager, alias, timeout=min(0.1, remain))
        if result.status != "ok":
            return {
                "ok": False,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
                "received": got,
                "result": result.to_dict(),
            }
        frame = (result.data or {}).get("frame")
        if frame is not None and _frame_matches(frame, step):
            got += 1
            frames.append(frame)
    ok = got >= need
    return {
        "ok": ok,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "received": got,
        "frames": frames,
        **({} if ok else {"error": f"wait_n got {got}/{need}"}),
    }


def _step_drain(manager: SessionManager, step: dict) -> dict:
    """排空接收队列；有帧则丢弃，无帧则在超时前结束。"""
    alias = str(step["device"])
    seconds = float(step.get("seconds", 0.2))
    t0 = time.perf_counter()
    deadline = t0 + max(0.0, seconds)
    dropped = 0
    while time.perf_counter() < deadline:
        remain = max(0.01, deadline - time.perf_counter())
        result = receive(manager, alias, timeout=min(0.05, remain))
        if result.status != "ok":
            return {
                "ok": False,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
                "dropped": dropped,
                "result": result.to_dict(),
            }
        if (result.data or {}).get("frame") is None:
            break
        dropped += 1
    return {
        "ok": True,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "dropped": dropped,
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


def _step_burst_send(manager: SessionManager, step: dict) -> dict:
    """连续发送多帧，可选帧间间隔；用于压测入口。"""
    alias = str(step["device"])
    count = int(step.get("count", 1))
    interval = float(step.get("interval", 0.0))
    if count < 1:
        return {"ok": False, "error": "burst_send.count 必须 >= 1"}
    base_id = _parse_id(step["id"])
    data = parse_hex(str(step.get("data", "")))
    ext = bool(step.get("ext", False))
    increment = bool(step.get("increment_id", False))
    t0 = time.perf_counter()
    sent = 0
    for i in range(count):
        arb = base_id + i if increment else base_id
        result = send(
            manager,
            alias,
            CanFrame(arbitration_id=arb, data=data, is_extended=ext),
        )
        if result.status != "ok":
            return {
                "ok": False,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
                "sent": sent,
                "result": result.to_dict(),
            }
        sent += 1
        if interval > 0 and i + 1 < count:
            time.sleep(interval)
    return {
        "ok": True,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "sent": sent,
    }


def _run_child_steps(
    manager: SessionManager,
    steps: list[dict],
    *,
    stop_on_error: bool,
) -> tuple[list[dict], int | None]:
    records: list[dict] = []
    failed_at: int | None = None
    for index, step in enumerate(steps):
        detail = _dispatch(manager, step, stop_on_error=stop_on_error)
        record = {"index": index, "action": str(step.get("action", "")), **detail}
        records.append(record)
        if not detail.get("ok", False):
            failed_at = index
            if stop_on_error:
                break
    return records, failed_at


def _step_repeat(manager: SessionManager, step: dict, *, stop_on_error: bool) -> dict:
    count = int(step.get("count", 1))
    child = list(step.get("steps") or [])
    if count < 1 or not child:
        return {"ok": False, "error": "repeat 需要 count>=1 且非空 steps"}
    t0 = time.perf_counter()
    rounds: list[dict] = []
    for i in range(count):
        records, failed_at = _run_child_steps(manager, child, stop_on_error=stop_on_error)
        rounds.append({"round": i, "steps": records, "failed_at": failed_at})
        if failed_at is not None:
            return {
                "ok": False,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
                "rounds": rounds,
                "error": f"repeat 在 round {i} 失败",
            }
    return {
        "ok": True,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "rounds": rounds,
        "count": count,
    }


def _step_try(manager: SessionManager, step: dict, *, stop_on_error: bool) -> dict:
    primary = list(step.get("steps") or [])
    on_fail = list(step.get("on_fail") or [])
    on_ok = list(step.get("on_ok") or [])
    if not primary:
        return {"ok": False, "error": "try 需要非空 steps"}
    t0 = time.perf_counter()
    primary_records, failed_at = _run_child_steps(
        manager, primary, stop_on_error=True
    )
    if failed_at is None:
        ok_records: list[dict] = []
        if on_ok:
            ok_records, ok_fail = _run_child_steps(
                manager, on_ok, stop_on_error=stop_on_error
            )
            if ok_fail is not None:
                return {
                    "ok": False,
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
                    "primary": primary_records,
                    "on_ok": ok_records,
                    "recovered": False,
                    "error": "try.on_ok 失败",
                }
        return {
            "ok": True,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
            "primary": primary_records,
            "on_ok": ok_records,
            "recovered": False,
        }

    if not on_fail:
        return {
            "ok": False,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
            "primary": primary_records,
            "recovered": False,
            "error": "try 主路径失败且无 on_fail",
        }
    fail_records, fail_at = _run_child_steps(
        manager, on_fail, stop_on_error=stop_on_error
    )
    ok = fail_at is None
    return {
        "ok": ok,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        "primary": primary_records,
        "on_fail": fail_records,
        "recovered": ok,
        **({} if ok else {"error": "try.on_fail 仍失败"}),
    }


def _dispatch(manager: SessionManager, step: dict, *, stop_on_error: bool) -> dict:
    action = str(step.get("action", "")).strip()
    try:
        if action == "send":
            return _step_send(manager, step)
        if action == "wait_id":
            return _step_wait_id(manager, step)
        if action == "wait_n":
            return _step_wait_n(manager, step)
        if action == "drain":
            return _step_drain(manager, step)
        if action == "sleep":
            return _step_sleep(step)
        if action == "filter":
            return _step_filter(manager, step)
        if action == "accept_all":
            return _step_accept_all(manager, step)
        if action == "open":
            return _step_open(manager, step)
        if action == "close":
            return _step_close(manager, step)
        if action == "periodic_start":
            return _step_periodic_start(manager, step)
        if action == "periodic_stop":
            return _step_periodic_stop(manager, step)
        if action == "burst_send":
            return _step_burst_send(manager, step)
        if action == "repeat":
            return _step_repeat(manager, step, stop_on_error=stop_on_error)
        if action == "try":
            return _step_try(manager, step, stop_on_error=stop_on_error)
        return {"ok": False, "error": f"未知步骤: {action}"}
    except Exception as e:  # noqa: BLE001 — 收拢为步骤失败
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


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
        detail = _dispatch(manager, step, stop_on_error=stop_on_error)
        record = {"index": index, "action": str(step.get("action", "")), **detail}
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
