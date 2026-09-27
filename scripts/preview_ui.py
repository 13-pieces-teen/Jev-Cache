"""Render the real Qt widgets with labeled fixtures, without starting a worker or cleaning anything."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from jev_cache.core import Item  # noqa: E402
from jev_cache.ui import STYLE, MainWindow  # noqa: E402


class PreviewRuntime(QObject):
    state_changed = Signal(object)
    notice = Signal(str)
    configuration_result = Signal(str)

    def __init__(self):
        super().__init__()
        self.commands = []

    def submit(self, kind, **payload):
        self.commands.append((kind, payload))


def fixture():
    return {
        "sample": {"total": 16 * 1024**3, "available": 4.1 * 1024**3, "used_percent": 74.375},
        "items": [
            Item("code", "code", "Code", "app", 200, "1", memory_bytes=480 * 1024**2, active=True),
            Item("qt", "qt", "Qt 文档", "tab", 200, "1", protections=("当前标签",)),
            Item(
                "python",
                "python",
                "Python 文档",
                "tab",
                200,
                "1",
                allowed_action="discard_tab",
                auto_eligible=True,
            ),
        ],
        "status": "界面验证用样例 · 非真实清理",
        "paused": False,
        "busy": False,
        "phase": "idle",
        "memory_pressure": False,
        "configured": True,
        "browser_connected": True,
        "settings": {
            "auto": False,
            "cloud": True,
            "share_titles": False,
            "memory": True,
            "model": "jev-latest",
        },
        "kept": {"code"},
        "keep_names": {"code": "Code"},
        "cooldown": set(),
        "history": [
            {
                "id": "fixture",
                "name": "Python 文档",
                "kind": "tab",
                "status": "completed",
                "at": 1790476920,
                "message": "网页已释放",
                "measurement": {"valid": True, "delta_bytes": 512 * 1024**2},
            }
        ],
        "last_result": None,
        "memory_count": 12,
        "ghosts": {},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/ui-retro"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    # The Windows offscreen platform has no system font discovery. Use the same
    # locally installed typefaces as the native desktop renderer.
    for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "consola.ttf"):
        font = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / name
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    runtime = PreviewRuntime()
    window = MainWindow(runtime)
    window.floating.fullscreen_timer.stop()
    window.tray.hide()
    state = fixture()
    window.update_state(state)
    window.show_panel()
    app.processEvents()
    checks = {}

    def capture(widget, name):
        app.processEvents()
        assert widget.grab().save(str(args.output / f"{name}.png"))

    capture(window, "overview-sample")
    for index, name in (
        (1, "objects-sample"),
        (2, "history-sample"),
        (3, "memory-sample"),
        (4, "settings-sample"),
    ):
        window.show_page(index)
        capture(window, name)
    # Changes in view must not save settings or issue commands.
    assert runtime.commands == []
    checks["render_has_no_side_effects"] = True
    window.hide()
    window.show_quick()
    capture(window.quick, "quick-sample")
    window.quick.hide()
    capture(window.floating, "floating-sample")
    window.update_state(state | {"settings": state["settings"] | {"auto": True}})
    window.show_quick()
    capture(window.quick, "automatic-sample")
    assert window.controls.auto.isChecked() and window.quick.controls.auto.isChecked()
    assert runtime.commands == []
    window.quick.controls.auto.click()
    assert runtime.commands == [("settings", {"auto": False})]
    runtime.commands.clear()
    window.quick.hide()
    window.update_state(state)
    checks["automatic_mode_sync_and_command"] = True

    # Clicks run against a recorder only, never Runtime or the network.
    QTest.mouseClick(window.floating.clean, Qt.MouseButton.LeftButton)
    QTest.mouseClick(window.floating.clean, Qt.MouseButton.LeftButton)
    assert [c[0] for c in runtime.commands] == ["optimize"]
    checks["repeated_click_coalesced"] = True
    window._release_click()
    runtime.commands.clear()
    busy = state | {"busy": True, "phase": "judging"}
    window.update_state(busy)
    assert not window.controls.clean.isEnabled() and not window.quick.controls.clean.isEnabled()
    assert not window.floating.clean.isEnabled()
    window.quick.controls.pause.click()
    assert runtime.commands == [("pause", {"value": True})]
    checks["busy_and_stop_shared_by_windows"] = True
    window.show_quick()
    capture(window.quick, "judging-sample")
    window.quick.hide()
    runtime.commands.clear()
    basic = state | {"configured": False, "browser_connected": False, "history": [], "last_result": None}
    window.update_state(basic)
    window.floating.clean.click()
    assert window.tabs.currentIndex() == 4 and not runtime.commands
    assert not window.quick.controls.auto.isEnabled()
    checks["unconfigured_routes_to_settings"] = True
    window.show_quick()
    capture(window.quick, "basic-mode-sample")
    window.quick.hide()

    window.update_state(state)
    window.show_page(2)
    from PySide6.QtWidgets import QPushButton

    reopen = next(b for b in window.findChildren(QPushButton) if b.text() == "重新打开")
    correct = next(b for b in window.findChildren(QPushButton) if b.text() == "这次不该清理")
    reopen.click()
    correct.click()
    assert runtime.commands[-2:] == [
        ("reopen", {"action_id": "fixture"}),
        ("correct", {"action_id": "fixture"}),
    ]
    checks["reopen_and_correction_are_distinct"] = True
    window.show_kept()
    assert window.table.rowCount() == 1
    checks["keep_filter"] = True
    window.update_state(state | {"history": [], "last_result": None})
    assert window.result.headline.text() == "还没有处理记录"
    checks["clearing_records_removes_old_result"] = True
    window.show_quick()
    QTest.keyClick(window.quick, Qt.Key.Key_Escape)
    app.processEvents()
    assert not window.quick.isVisible() and not window.floating.expanded
    checks["escape_collapses_without_cleaning"] = True
    report = {
        "fixture_data": True,
        "real_cleanup_executed": False,
        "scale": os.environ.get("QT_SCALE_FACTOR", "1"),
        "checks": checks,
    }
    (args.output / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    window.quick.hide()
    window.floating.hide_by_user()
    window.hide()


if __name__ == "__main__":
    main()
