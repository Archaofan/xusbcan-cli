"""CLI：argparse 命令定义，薄封装 core。

一次性命令：list / send / receive / monitor / status / periodic；
scenario 按 JSON 步骤在同一进程编排（可含 open/close），适合毫秒级发→等→再发。
stdout 只放一个 JSON 对象（Result）；日志/诊断走 stderr。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

from ..config.loader import load_config
from ..core import (
    SessionManager,
    close_session,
    list_devices,
    monitor,
    open_session,
    parse_hex,
    periodic_start,
    periodic_stop,
    receive,
    send,
    status,
)
from ..models.frame import CanFrame
from ..models.result import ErrorCode, Result
from ..scenario import load_scenario, run_scenario


def _add_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from-id", default=None, help="接收滤波起始 ID（与 --to-id 成对）")
    parser.add_argument("--to-id", default=None, help="接收滤波结束 ID（含）")
    parser.add_argument("--ext", action="store_true", help="滤波按扩展帧")


def _filter_bounds(args: argparse.Namespace) -> tuple[int | None, int | None, Result | None]:
    if args.from_id is None and args.to_id is None:
        return None, None, None
    if args.from_id is None or args.to_id is None:
        return None, None, Result.err(
            ErrorCode.INVALID_ARGUMENT, "滤波需要同时给出 --from-id 和 --to-id"
        )
    try:
        return int(args.from_id, 0), int(args.to_id, 0), None
    except ValueError as e:
        return None, None, Result.err(ErrorCode.INVALID_ARGUMENT, str(e))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xusbcan", description="面向 AI Agent 的 CAN 总线调试工具"
    )
    parser.add_argument(
        "--config", help="配置文件路径（默认按 XUSBCAN_CONFIG / ./xusbcan.toml 搜索）"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出设备（只读配置与会话表）")

    p = sub.add_parser("scenario", help="执行毫秒级报文剧本（JSON 步骤文件或目录）")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="单个剧本 JSON 路径（含 steps 数组）")
    src.add_argument("--dir", help="目录内按文件名排序批跑全部 *.json")

    p = sub.add_parser("send", help="发送一帧 CAN 报文")
    p.add_argument("alias", help="设备逻辑别名")
    p.add_argument("--id", required=True, help="报文 ID（支持 0x 前缀）")
    p.add_argument("--data", default="", help='十六进制数据，如 "01 02 03"')
    p.add_argument("--ext", action="store_true", help="扩展帧")
    p.add_argument("--fd", action="store_true", help="CAN FD（2E 卡不支持）")

    p = sub.add_parser("receive", help="接收一帧（带超时）")
    p.add_argument("alias", help="设备逻辑别名")
    p.add_argument("--timeout", type=float, default=1.0, help="超时（秒，默认 1）")
    _add_filter_args(p)

    p = sub.add_parser("monitor", help="有界监听")
    p.add_argument("alias", help="设备逻辑别名")
    p.add_argument("--duration", type=float, default=1.0, help="时长（秒，上限 30）")
    p.add_argument("--max-frames", type=int, default=500, help="最大帧数")
    _add_filter_args(p)

    p = sub.add_parser("periodic", help="在本进程内周期发送指定时长后停止")
    p.add_argument("alias", help="设备逻辑别名")
    p.add_argument("--name", required=True, help="任务名")
    p.add_argument("--id", required=True, help="报文 ID（支持 0x 前缀）")
    p.add_argument("--data", default="", help='十六进制数据，如 "01 02 03"')
    p.add_argument("--ext", action="store_true", help="扩展帧")
    p.add_argument("--period", type=float, required=True, help="周期（秒）")
    p.add_argument("--duration", type=float, required=True, help="持续发送的秒数，结束后停止并关闭")

    p = sub.add_parser("status", help="查询会话/设备状态")
    p.add_argument("alias", help="设备逻辑别名")

    return parser


def dispatch(args: argparse.Namespace) -> Result:
    cfg_result = load_config(args.config)
    if cfg_result.status == "error":
        return cfg_result
    cfg = cfg_result.data

    mgr = SessionManager()
    for entry in cfg.devices:
        mgr.register(entry.name, entry.spec)

    cmd = args.command
    if cmd == "list":
        return list_devices(mgr)
    if cmd == "send":
        try:
            arb_id = int(args.id, 0)
            data = parse_hex(args.data)
        except ValueError as e:
            return Result.err(ErrorCode.INVALID_ARGUMENT, str(e))
        frame = CanFrame(
            arbitration_id=arb_id,
            data=data,
            is_extended=args.ext,
            is_fd=args.fd,
        )
        return send(mgr, args.alias, frame)
    if cmd == "receive":
        start, end, err = _filter_bounds(args)
        if err is not None:
            return err
        return receive(mgr, args.alias, args.timeout, start, end, args.ext)
    if cmd == "monitor":
        start, end, err = _filter_bounds(args)
        if err is not None:
            return err
        return monitor(mgr, args.alias, args.duration, args.max_frames, start, end, args.ext)
    if cmd == "periodic":
        return _periodic_for(mgr, args)
    if cmd == "status":
        return status(mgr, args.alias)
    if cmd == "scenario":
        if args.file:
            return _scenario_for(mgr, args.file)
        return _scenario_dir_for(mgr, args.dir)
    return Result.err(ErrorCode.INVALID_ARGUMENT, f"未知命令: {cmd}")


def _scenario_for(mgr: SessionManager, path: str) -> Result:
    try:
        steps, variables = load_scenario(path)
    except OSError as e:
        return Result.err(ErrorCode.CONFIG_ERROR, f"无法读取剧本: {e}")
    except (json.JSONDecodeError, ValueError) as e:
        return Result.err(ErrorCode.INVALID_ARGUMENT, f"剧本无效: {e}")
    try:
        return run_scenario(mgr, steps, variables=variables)
    finally:
        mgr.close_all()


def _scenario_dir_for(mgr: SessionManager, dir_path: str) -> Result:
    root = Path(dir_path)
    if not root.is_dir():
        return Result.err(ErrorCode.CONFIG_ERROR, f"剧本目录不存在: {dir_path}")
    files = sorted(root.glob("*.json"))
    if not files:
        return Result.err(ErrorCode.INVALID_ARGUMENT, f"目录内无 *.json: {dir_path}")
    reports: list[dict] = []
    all_ok = True
    try:
        for path in files:
            try:
                steps, variables = load_scenario(str(path))
                one = run_scenario(mgr, steps, variables=variables)
            except OSError as e:
                one = Result.err(ErrorCode.CONFIG_ERROR, f"无法读取剧本: {e}")
            except (json.JSONDecodeError, ValueError) as e:
                one = Result.err(ErrorCode.INVALID_ARGUMENT, f"剧本无效: {e}")
            reports.append({"file": path.name, "result": one.to_dict()})
            if one.status != "ok":
                all_ok = False
            mgr.close_all()
            time.sleep(0.05)
    finally:
        mgr.close_all()
    data = {"dir": str(root), "count": len(reports), "ok": all_ok, "runs": reports}
    if all_ok:
        return Result.ok(data)
    return Result.err(
        ErrorCode.INTERNAL_ERROR,
        "目录批跑存在失败剧本",
        data=data,
    )



def _periodic_for(mgr: SessionManager, args: argparse.Namespace) -> Result:
    if (
        not math.isfinite(args.duration)
        or not math.isfinite(args.period)
        or args.duration <= 0
        or args.period <= 0
    ):
        return Result.err(
            ErrorCode.INVALID_ARGUMENT, "period 和 duration 必须为正有限数"
        )
    try:
        frame = CanFrame(
            arbitration_id=int(args.id, 0),
            data=parse_hex(args.data),
            is_extended=args.ext,
        )
    except ValueError as e:
        return Result.err(ErrorCode.INVALID_ARGUMENT, str(e))
    opened = open_session(mgr, args.alias)
    if opened.status == "error":
        return opened
    try:
        started = periodic_start(mgr, args.alias, args.name, frame, args.period)
        if started.status != "ok":
            return started
        time.sleep(args.duration)
        stopped = periodic_stop(mgr, args.alias, args.name)
        if stopped.status != "ok":
            return stopped
        data = dict(started.data or {})
        data["duration_s"] = args.duration
        return Result.ok(data)
    finally:
        close_session(mgr, args.alias)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    result = dispatch(args)
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
