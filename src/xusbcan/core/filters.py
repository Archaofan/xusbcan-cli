"""把一条 ID 范围变成 python-can 的掩码滤波。各后端的 recv 都会套用这组掩码。"""

from __future__ import annotations

_STD_MASK = 0x7FF
_EXT_MASK = 0x1FFFFFFF


def id_masks(start: int, end: int, is_extended: bool) -> list[dict]:
    """闭区间 [start, end] 拆成若干 can_id/can_mask。空范围非法。"""
    limit = _EXT_MASK if is_extended else _STD_MASK
    if start < 0 or end < start or end > limit:
        kind = "扩展帧" if is_extended else "标准帧"
        raise ValueError(f"{kind} ID 范围非法: {start:#x}..{end:#x}")
    filters: list[dict] = []
    cur = start
    while cur <= end:
        size = 1
        span = end - cur + 1
        while size * 2 <= span and cur % (size * 2) == 0:
            size *= 2
        filters.append(
            {
                "can_id": cur,
                "can_mask": (~(size - 1)) & limit,
                "extended": is_extended,
            }
        )
        cur += size
    return filters
