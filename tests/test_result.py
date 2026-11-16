"""Result 契约单元测试：错误码枚举化、超时成功态、schema_version。"""

from __future__ import annotations

from xusbcan.models import ErrorCode, Result


def test_error_code_serializes_to_plain_string():
    """ErrorCode 必须序列化为纯值 "SEND_FAILED"，而非 "ErrorCode.SEND_FAILED"。"""
    r = Result.err(ErrorCode.SEND_FAILED, "无 ACK", data={"sent": 0, "failed_index": 0})
    assert r.error.code == "SEND_FAILED"
    assert r.error.code != "ErrorCode.SEND_FAILED"


def test_result_ok_shape():
    r = Result.ok({"sent": 1})
    d = r.to_dict()
    assert d["status"] == "ok"
    assert d["data"] == {"sent": 1}
    assert d["error"] is None
    assert d["meta"]["schema_version"] == "1.0"
    assert "timestamp" in d["meta"]


def test_result_err_shape():
    r = Result.err(ErrorCode.DEVICE_NOT_FOUND, "未找到设备", context={"vendor": "zlg"})
    d = r.to_dict()
    assert d["status"] == "error"
    assert d["error"]["code"] == "DEVICE_NOT_FOUND"
    assert d["error"]["context"] == {"vendor": "zlg"}


def test_receive_timeout_is_success():
    """接收超时是成功态，不是错误（§4.5）。"""
    r = Result.ok({"frame": None, "reason": "timeout"})
    assert r.status == "ok"
    assert r.data["frame"] is None
    assert r.data["reason"] == "timeout"


def test_partial_send_keeps_progress():
    """多帧发送失败保留已发送进度（§4.5）。"""
    r = Result.err(
        ErrorCode.SEND_FAILED,
        "发送失败",
        data={"sent": 1, "failed_index": 1},
    )
    assert r.status == "error"
    assert r.data == {"sent": 1, "failed_index": 1}
