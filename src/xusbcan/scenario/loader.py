"""从 JSON 文件加载剧本步骤与初始变量。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_scenario(path: str | Path) -> tuple[list[dict], dict[str, Any]]:
    """读取剧本文件，返回 ``(steps, vars)``。

    支持：
    - 纯 steps 数组
    - ``{"vars": {...}, "steps": [...]}``
    """
    text = Path(path).read_text(encoding="utf-8")
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload, {}
    if isinstance(payload, dict) and isinstance(payload.get("steps"), list):
        variables = dict(payload.get("vars") or {})
        return list(payload["steps"]), variables
    raise ValueError("剧本需为 steps 数组或含 steps 的对象")
