"""ID 范围到 python-can 掩码，以及 CLI 限时周期发送。"""

from __future__ import annotations

import os
import tempfile

from xusbcan.cli.app import main
from xusbcan.core.filters import id_masks


def test_id_masks_cover_aligned_block_and_single_id():
    block = id_masks(0x100, 0x1FF, False)
    assert block == [{"can_id": 0x100, "can_mask": 0x700, "extended": False}]
    one = id_masks(0x123, 0x123, False)
    assert one[0]["can_mask"] == 0x7FF
    assert id_masks(0, 0x7FF, False)[0]["can_mask"] == 0


def test_cli_periodic_on_virtual_bus():
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False, encoding="utf-8")
    handle.write(
        """
[[devices]]
name = "bus0"
interface = "virtual"
channel = "cli-virt"
nominal = 500000
"""
    )
    handle.close()
    try:
        code = main(
            [
                "--config",
                handle.name,
                "periodic",
                "bus0",
                "--name",
                "hb",
                "--id",
                "0x123",
                "--data",
                "01",
                "--period",
                "0.05",
                "--duration",
                "0.05",
            ]
        )
    finally:
        os.unlink(handle.name)
    assert code == 0
