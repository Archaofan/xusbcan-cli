"""CLI：argparse 命令定义，薄封装 core。

一次性命令：list / send / receive / monitor / status（每次调用自己 open → 操作 → close）。
stdout 只放一个 JSON 对象（Result）；日志/诊断走 stderr。
"""

from __future__ import annotations

import argparse
import json
import sys

from ..config.loader import load_config
from ..core import (
    SessionManager,
    list_devices,
    monitor,
    parse_hex,
    receive,
    send,
    status,
)
from ..models.frame import CanFrame
from ..models.result import ErrorCode, Result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xusbcan", description="面向 AI Agent 的 CAN 总线调试工具"
    )
    parser.add_argument(
        "--config", help="配置文件路径（默认按 XUSBCAN_CONFIG / ./xusbcan.toml 搜索）"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出设备（只读配置与会话表）")

    p = sub.add_parser("send", help="发送一帧 CAN 报文")
    p.add_argument("alias", help="设备逻辑别名")
    p.add_argument("--id", required=True, help="报文 ID（支持 0x 前缀）")
    p.add_argument("--data", default="", help='十六进制数据，如 "01 02 03"')
    p.add_argument("--ext", action="store_true", help="扩展帧")
    p.add_argument("--fd", action="store_true", help="CAN FD（2E 卡不支持）")

    p = sub.add_parser("receive", help="接收一帧（带超时）")
    p.add_argument("alias", help="设备逻辑别名")
    p.add_argument("--timeout", type=float, default=1.0, help="超时（秒，默认 1）")

    p = sub.add_parser("monitor", help="有界监听")
    p.add_argument("alias", help="设备逻辑别名")
    p.add_argument("--duration", type=float, default=1.0, help="时长（秒，上限 30）")
    p.add_argument("--max-frames", type=int, default=500, help="最大帧数")

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
        return receive(mgr, args.alias, args.timeout)
    if cmd == "monitor":
        return monitor(mgr, args.alias, args.duration, args.max_frames)
    if cmd == "status":
        return status(mgr, args.alias)
    return Result.err(ErrorCode.INVALID_ARGUMENT, f"未知命令: {cmd}")


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
