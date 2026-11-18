"""MCP 工具定义：薄封装 core，只做「参数解析 → 调 core → 序列化 Result」。"""

from __future__ import annotations

import json
from typing import Annotated

from .. import core
from ..models.frame import CanFrame
from ..models.result import ErrorCode, Result
from ..scenario import run_scenario as execute_scenario

# mcp / pydantic 仅为 optional（.[mcp]）。注解用 dict，避免无 mcp 时
# import tools 失败（CI 的 .[dev] 不含 mcp）。有 pydantic 时 Field 写入 schema。
try:
    from pydantic import Field
except ImportError:  # pragma: no cover

    def Field(*, description: str, **_kwargs):  # type: ignore[misc]
        return description


# MCP ToolAnnotations-compatible dicts (readOnlyHint / … camelCase keys).
_RO = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
_RW_BUS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}
_RW_IDEM_BUS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}
_RW_SESSION = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


def _json(result: Result) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False)


def register_tools(mcp, manager: core.SessionManager) -> None:
    """把 core 命令注册为 MCP 工具。工具签名是统一语义，不含厂商概念。"""

    @mcp.tool(annotations=_RO)
    def list_devices() -> str:
        """List configured device aliases and whether each session is open.

        Read-only inventory of the loaded config (name, channel, capabilities,
        open state). Does not open hardware. Use open_device before send/receive;
        use get_status for one alias's live session details.
        Returns JSON Result with the device list in data.
        """
        return _json(core.list_devices(manager))

    @mcp.tool(annotations=_RW_BUS)
    def send_frame(
        device: Annotated[
            str, Field(description="Device alias from config / list_devices")
        ],
        arbitration_id: Annotated[
            int, Field(description="CAN arbitration ID (integer, not hex string)")
        ],
        data: Annotated[
            str,
            Field(
                description='Hex payload, e.g. "01 02 03" or "010203" (classic CAN max 8 bytes)'
            ),
        ],
        is_extended: Annotated[
            bool, Field(description="True for 29-bit extended ID; default false (11-bit)")
        ] = False,
    ) -> str:
        """Transmit one CAN frame on an open session.

        Requires open_device first. Puts a single frame on the bus; for repeating
        the same frame use periodic_start, for multi-step scripts use run_scenario.
        Fails while a hardware periodic task owns the TX path — call periodic_stop
        first. Returns JSON Result (error.code on failure).
        """
        try:
            frame = CanFrame(
                arbitration_id=arbitration_id,
                data=core.parse_hex(data),
                is_extended=is_extended,
            )
        except ValueError as e:
            return _json(Result.err(ErrorCode.INVALID_ARGUMENT, str(e)))
        return _json(core.send(manager, device, frame))

    @mcp.tool(annotations=_RW_BUS)
    def receive_frame(
        device: Annotated[
            str, Field(description="Device alias from config / list_devices")
        ],
        timeout: Annotated[
            float, Field(description="Seconds to wait for one frame; default 1.0")
        ] = 1.0,
    ) -> str:
        """Receive the next CAN frame from an open session (consumes one frame).

        Requires open_device. Waits up to timeout seconds; on timeout returns
        status=ok with frame=null (not an error). Prefer monitor to capture many
        frames over a wall-clock window; prefer wait_id inside run_scenario when
        matching a specific ID. Returns JSON Result.
        """
        return _json(core.receive(manager, device, timeout))

    @mcp.tool(annotations=_RW_BUS)
    def monitor(
        device: Annotated[
            str, Field(description="Device alias from config / list_devices")
        ],
        duration_s: Annotated[
            float, Field(description="Capture window in seconds; capped at 30")
        ] = 1.0,
        max_frames: Annotated[
            int, Field(description="Stop early after this many frames; default 500")
        ] = 500,
    ) -> str:
        """Time-bounded capture of CAN frames into one response.

        Requires open_device. Collects up to max_frames for up to duration_s
        (hard cap 30s), then returns. Use receive_frame for a single next frame;
        use run_scenario wait_* steps for ID-matched waits. Returns JSON Result
        with data.frames[], count, and truncated.
        """
        return _json(core.monitor(manager, device, duration_s, max_frames))

    @mcp.tool(annotations=_RO)
    def get_status(
        device: Annotated[
            str, Field(description="Device alias from config / list_devices")
        ],
    ) -> str:
        """Read session state for one alias (open/closed, features, receive owner).

        Read-only; does not open or close the device. Use list_devices to see all
        aliases at once. Returns JSON Result with state/features/receive_owner.
        """
        return _json(core.status(manager, device))

    @mcp.tool(annotations=_RW_IDEM_BUS)
    def open_device(
        device: Annotated[
            str, Field(description="Device alias from config / list_devices")
        ],
    ) -> str:
        """Open (or reuse) a CAN session for the alias and keep it in-process.

        Needed before send_frame, receive_frame, monitor, filters, or periodic_*.
        Idempotent while already open (returns reused=true). Pair with close_device
        when finished. Hardware/SDK must be available on the host for real adapters;
        virtual configs work without USB. Returns JSON Result.
        """
        return _json(core.open_session(manager, device))

    @mcp.tool(annotations=_RW_IDEM_BUS)
    def close_device(
        device: Annotated[
            str, Field(description="Device alias from config / list_devices")
        ],
    ) -> str:
        """Close the session for an alias and release bus resources.

        Stops ownership of the adapter channel for this process. Does not remove
        the alias from config — call open_device again to resume. Prefer this over
        abandoning an open session. Returns JSON Result.
        """
        return _json(core.close_session(manager, device))

    @mcp.tool(annotations=_RW_BUS)
    def periodic_start(
        device: Annotated[
            str, Field(description="Device alias from config / list_devices")
        ],
        name: Annotated[
            str, Field(description="Task name used later with periodic_stop / periodic_list")
        ],
        arbitration_id: Annotated[
            int, Field(description="CAN arbitration ID (integer, not hex string)")
        ],
        data: Annotated[
            str, Field(description='Payload as hex bytes, e.g. "01 02 03"')
        ],
        period_s: Annotated[
            float, Field(description="Interval between frames in seconds (> 0)")
        ],
        duration_s: Annotated[
            float,
            Field(
                description="Required run time in seconds before auto-stop; hard cap 300"
            ),
        ],
        is_extended: Annotated[
            bool, Field(description="True for 29-bit extended ID; default false")
        ] = False,
    ) -> str:
        """Start a named, time-bounded periodic TX task on an open session.

        duration_s is required (max 300s); the task auto-stops, or stop early with
        periodic_stop. Adapters with hardware periodic TX use it; while that path
        is active, send_frame may fail until periodic_stop. For one-shot TX use
        send_frame; for scripted sequences use run_scenario. Longer bench jobs
        belong in a local long-running process, not unbounded MCP TX.
        Returns JSON Result.
        """
        try:
            frame = CanFrame(
                arbitration_id=arbitration_id,
                data=core.parse_hex(data),
                is_extended=is_extended,
            )
        except ValueError as e:
            return _json(Result.err(ErrorCode.INVALID_ARGUMENT, str(e)))
        return _json(
            core.periodic_start(
                manager, device, name, frame, period_s, duration_s=duration_s
            )
        )

    @mcp.tool(annotations=_RW_SESSION)
    def periodic_stop(
        device: Annotated[
            str, Field(description="Device alias from config / list_devices")
        ],
        name: Annotated[
            str, Field(description="Exact task name previously passed to periodic_start")
        ],
    ) -> str:
        """Stop and remove one periodic TX task by name.

        Use after periodic_start when you need to free the TX path for send_frame
        or end early before duration_s. periodic_list shows active names. Returns
        JSON Result.
        """
        return _json(core.periodic_stop(manager, device, name))

    @mcp.tool(annotations=_RO)
    def periodic_list(
        device: Annotated[
            str, Field(description="Device alias from config / list_devices")
        ],
    ) -> str:
        """List active periodic TX tasks for one open session.

        Read-only. Use periodic_start / periodic_stop to change tasks. Returns
        JSON Result with the task list.
        """
        return _json(core.periodic_list(manager, device))

    @mcp.tool(annotations=_RW_IDEM_BUS)
    def set_frame_filter(
        device: Annotated[
            str, Field(description="Device alias from config / list_devices")
        ],
        start_id: Annotated[
            int, Field(description="Inclusive start of accepted arbitration ID range")
        ],
        end_id: Annotated[
            int, Field(description="Inclusive end of accepted arbitration ID range")
        ],
        is_extended: Annotated[
            bool,
            Field(description="Match extended (29-bit) IDs when true; default false"),
        ] = False,
    ) -> str:
        """Replace the session RX filter with one inclusive ID range.

        Requires open_device. Replaces any previous filter (not additive). To accept
        all IDs again, call accept_all_frames — do not assume clearing filters
        another way. Affects receive_frame / monitor / scenario waits. Returns
        JSON Result.
        """
        return _json(core.set_frame_filter(manager, device, start_id, end_id, is_extended))

    @mcp.tool(annotations=_RW_IDEM_BUS)
    def accept_all_frames(
        device: Annotated[
            str, Field(description="Device alias from config / list_devices")
        ],
    ) -> str:
        """Clear the RX filter so the session accepts all CAN IDs again.

        Requires open_device. Use after set_frame_filter when you need full traffic;
        opposite of set_frame_filter. Returns JSON Result.
        """
        return _json(core.accept_all_frames(manager, device))

    @mcp.tool(annotations=_RW_BUS)
    def run_scenario(
        steps_json: Annotated[
            str,
            Field(
                description=(
                    "JSON string: a steps array, or an object with steps plus optional vars. "
                    "Actions include open/send/wait_id/wait_n/drain/filter/accept_all/sleep/"
                    "repeat/try/burst_send/periodic_start/periodic_stop/close."
                )
            ),
        ],
    ) -> str:
        """Run a millisecond-timed multi-step CAN script in one call.

        Prefer this for sequenced open→send→wait→close flows; use the single-shot
        tools (send_frame, monitor, …) for one operation. periodic_start steps must
        include duration_s (max 300). On finish, scenario-owned periodic tasks are
        cleaned up. Returns JSON Result with per-step timing; invalid JSON yields
        INVALID_ARGUMENT.
        """
        try:
            payload = json.loads(steps_json)
        except json.JSONDecodeError as e:
            return _json(Result.err(ErrorCode.INVALID_ARGUMENT, f"steps_json 无效: {e}"))
        if isinstance(payload, list):
            steps = payload
            variables: dict = {}
        elif isinstance(payload, dict) and isinstance(payload.get("steps"), list):
            steps = payload["steps"]
            variables = dict(payload.get("vars") or {})
        else:
            return _json(
                Result.err(ErrorCode.INVALID_ARGUMENT, "需要 steps 数组或含 steps 的对象")
            )
        return _json(execute_scenario(manager, steps, variables=variables))
