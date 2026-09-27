import time
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from jev_cache.core import Item
from jev_cache.provider import JevProvider
from jev_cache.runtime import Runtime
from jev_cache.storage import Store
from jev_cache.ui import MainWindow


@pytest.fixture
def ui_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("JEVCACHE_DATA_DIR", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    worker = Runtime()
    worker.store = Store(tmp_path / "state.db")
    worker.provider = JevProvider()
    worker.settings = {
        "auto": False,
        "cloud": False,
        "memory": True,
        "share_titles": False,
        "model": "jev-latest",
    }
    worker.kept, worker.keep_names = set(), {}
    target = Item(
        "fixture-tab",
        "fixture-page",
        "测试文档",
        "tab",
        time.time(),
        "1",
        allowed_action="discard_tab",
        auto_eligible=True,
    )
    worker.items = {target.id: target}
    window = MainWindow(worker)
    window.floating.fullscreen_timer.stop()
    window.tray.hide()
    window.update_state(worker.view(time.time()))
    yield window, worker, target
    window.notice_timer.stop()
    window.quick.hide()
    window.floating.hide_by_user()
    window.hide()
    worker.stop()
    worker.pool.shutdown(wait=True)
    worker.store.close()
    window.deleteLater()
    app.processEvents()


def row_button(window, text):
    return next(
        button for button in window.table.cellWidget(0, 3).findChildren(QPushButton) if button.text() == text
    )


def flush(window, worker):
    worker._commands(time.time())
    window.update_state(worker.view(time.time()))


def test_keep_button_reaches_runtime_storage_and_blocks_release(ui_runtime):
    window, worker, target = ui_runtime
    window.show_page(1)
    row_button(window, "始终保留").click()
    flush(window, worker)
    assert worker.store.get("kept") == [target.stable_key]
    assert not row_button(window, "释放网页").isEnabled()
    row_button(window, "取消保留").click()
    flush(window, worker)
    assert worker.store.get("kept") == []
    assert row_button(window, "释放网页").isEnabled()


def test_capability_changes_refresh_release_control(ui_runtime):
    window, worker, target = ui_runtime
    window.show_page(1)
    assert row_button(window, "释放网页").isEnabled()
    worker.items[target.id] = replace(target, allowed_action="none", auto_eligible=False)
    window.update_state(worker.view(time.time()))
    assert not row_button(window, "释放网页").isEnabled()
    assert window.table.item(0, 2).text() == "状态不足，保留"
    worker.items[target.id] = target
    window.update_state(worker.view(time.time()))
    assert row_button(window, "释放网页").isEnabled()


def test_settings_save_and_remove_key_do_not_leave_sensitive_draft(ui_runtime):
    window, worker, _ = ui_runtime
    window.api_key.setText("synthetic-functional-test-key")
    window.cloud.setChecked(True)
    window.remember.setChecked(False)
    window.save_settings()
    flush(window, worker)
    assert worker.provider.configured and not worker.store.get("memory_enabled")
    assert worker.store.get("cloud") and not window.api_key.text()
    window.api_key.setText("unsaved-replacement-key")
    remove = next(button for button in window.findChildren(QPushButton) if button.text() == "移除密钥")
    remove.click()
    flush(window, worker)
    assert worker.store.get("api_key") == ""
    assert not worker.provider.configured and not worker.settings["cloud"] and not worker.settings["auto"]
    assert not window.api_key.text() and not window.cloud.isChecked()


def test_manual_cleanup_starts_without_opening_panels_or_enabling_automatic_upload(ui_runtime):
    window, worker, _ = ui_runtime
    window.api_key.setText("synthetic-functional-test-key")
    window.cloud.setChecked(False)
    window.save_settings()
    flush(window, worker)
    for control in (window.controls.clean, window.quick.controls.clean, window.floating.clean):
        assert control.text() == "一键清理" and control.isEnabled()
        window.hide()
        window.quick.hide()
        control.click()
        assert not window.isVisible() and not window.quick.isVisible()
        assert worker.commands.get_nowait() == ("optimize", {"context": "", "allow_summary_once": True})
        assert worker.commands.empty()
        assert not worker.store.get("cloud") and not window.cloud.isChecked()
        assert not window.controls.auto.isChecked()
        assert "正在处理" in window.floating.titlebar.title.text()
        assert not control.isEnabled()
        window._release_click()

    window.cloud.setChecked(True)
    window.save_settings()
    flush(window, worker)
    window.floating.clean.click()
    assert worker.commands.get_nowait() == ("optimize", {"context": "", "allow_summary_once": True})
    assert not window.controls.clean.isEnabled() and not window.floating.clean.isEnabled()
    window._release_click()

    window.remove_key()
    flush(window, worker)
    for control in (window.controls.clean, window.quick.controls.clean, window.floating.clean):
        assert control.text() == "连接 Jev"


def test_clear_history_confirmation_preserves_explicit_keep(ui_runtime, monkeypatch):
    window, worker, target = ui_runtime
    worker.kept.add(target.stable_key)
    worker.store.put("kept", [target.stable_key])
    worker.store.remember("fixture-usage", {"count": 1})
    worker.store.receipt(
        "fixture-action",
        {
            "id": "fixture-action",
            "at": time.time(),
            "name": "测试文档",
            "kind": "tab",
            "status": "not_completed",
        },
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    window.clear_memory()
    flush(window, worker)
    assert worker.store.recent() and worker.store.memories()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    window.clear_memory()
    flush(window, worker)
    assert not worker.store.recent() and not worker.store.memories()
    assert worker.store.get("kept") == [target.stable_key]
    assert window.result.headline.text() == "还没有处理记录"
