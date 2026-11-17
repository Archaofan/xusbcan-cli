"""配置加载单元测试：TOML 解析与搜索顺序。"""

from __future__ import annotations

import os
import tempfile

from xusbcan.config.loader import load_config
from xusbcan.models.result import ErrorCode


def _write_toml(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def test_load_config_parses_devices():
    path = _write_toml(
        """
[[devices]]
name = "ecu"
vendor = "zlg"
model = "USBCAN-2E-U"
channel = 1
nominal = 250000
"""
    )
    try:
        r = load_config(path)
        assert r.status == "ok"
        cfg = r.data
        assert len(cfg.devices) == 1
        entry = cfg.devices[0]
        assert entry.name == "ecu"
        assert entry.spec.vendor == "zlg"
        assert entry.spec.channel == 1
        assert entry.spec.bitrate.nominal == 250000
    finally:
        os.unlink(path)


def test_load_config_accepts_python_can_interface():
    path = _write_toml(
        """
[[devices]]
name = "sock"
interface = "socketcan"
channel = "can0"
nominal = 500000
"""
    )
    try:
        r = load_config(path)
        assert r.status == "ok"
        spec = r.data.devices[0].spec
        assert spec.interface == "socketcan"
        assert spec.channel == "can0"
        assert spec.vendor == ""
    finally:
        os.unlink(path)


def test_load_config_reads_fd_timing():
    path = _write_toml(
        """
[[devices]]
name = "fd0"
interface = "vector"
channel = 0
nominal = 500000
data = 2000000
sjw = 2
tseg1 = 6
tseg2 = 3
"""
    )
    try:
        r = load_config(path)
        assert r.status == "ok"
        bitrate = r.data.devices[0].spec.bitrate
        assert bitrate.data == 2_000_000
        assert bitrate.sjw == 2
        assert bitrate.tseg1 == 6
        assert bitrate.tseg2 == 3
    finally:
        os.unlink(path)


def test_load_config_missing_field_is_config_error():
    path = _write_toml('[[devices]]\nname = "ecu"\n')
    try:
        r = load_config(path)
        assert r.status == "error"
        assert r.error.code == ErrorCode.CONFIG_ERROR.value
    finally:
        os.unlink(path)


def test_load_config_not_found():
    r = load_config("/nonexistent/path/xusbcan.toml")
    assert r.status == "error"
    assert r.error.code == ErrorCode.CONFIG_ERROR.value
