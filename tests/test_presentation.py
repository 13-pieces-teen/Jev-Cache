from jev_cache.presentation import observation_text, receipt_view, status_text


def receipt(identity="new", **overrides):
    return {
        "id": identity,
        "at": 200,
        "name": "Python 文档",
        "kind": "tab",
        "status": "completed",
    } | overrides


def test_old_measurement_never_attaches_to_new_action_with_same_name():
    view = receipt_view(
        {
            "history": [receipt()],
            "last_result": {
                "action_id": "old",
                "name": "Python 文档",
                "valid": True,
                "delta_bytes": 512 * 1024**2,
            },
        }
    )
    assert view.headline == "已释放 1 个网页"
    assert "512" not in view.observation
    assert "无法确定" in view.observation


def test_latest_failure_keeps_previous_success_number_out_of_result():
    view = receipt_view(
        {
            "history": [
                receipt("old", at=100, measurement={"valid": True, "delta_bytes": 512 * 1024**2}),
                receipt(status="not_completed", message="尚未确认退出"),
            ],
        }
    )
    assert view.headline == "本次未确认完成"
    assert not view.observation


def test_pending_measurement_shows_completed_action_before_number():
    view = receipt_view(
        {
            "history": [receipt()],
            "last_result": {"action_id": "new", "valid": False, "reason": "measuring"},
        }
    )
    assert view.headline == "已释放 1 个网页"
    assert view.observation == "正在观察内存变化…"


def test_negative_zero_and_invalid_measurements_have_honest_copy():
    assert observation_text({"valid": True, "delta_bytes": -128 * 1024**2}) == "处理后可用内存减少约 128 MB"
    assert "基本没有变化" in observation_text({"valid": True, "delta_bytes": 0})
    assert "无法确定" in observation_text({"valid": False, "delta_bytes": 512 * 1024**2})


def test_phase_and_pressure_have_separate_ui_meaning():
    state = {"sample": {"total": 16 * 1024**3}, "memory_pressure": True}
    assert status_text(state) == "内存有点紧张"
    assert "判断" in status_text(state | {"phase": "judging"})
    assert status_text(state | {"paused": True}) == "清理已暂停"
