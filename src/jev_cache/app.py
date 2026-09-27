from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from .runtime import Runtime
from .storage import data_directory
from .ui import STYLE, MainWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--quit-after", type=int, default=0)
    parser.add_argument("--start-hidden", action="store_true")
    parser.add_argument("--prepare-edge", action="store_true")
    args = parser.parse_args()
    if args.prepare_edge:
        from .browser_setup import register_edge

        register_edge()
        return 0
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Jev-Cache")
    app.setOrganizationName("JevCache")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)
    folder = data_directory()
    lock = QLockFile(str(folder / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, "Jev-Cache", "助手已在运行，请点击悬浮窗或系统托盘图标。")
        return 0
    from logging.handlers import RotatingFileHandler

    handler = RotatingFileHandler(folder / "app.log", maxBytes=256 * 1024, backupCount=2, encoding="utf-8")
    logging.getLogger("jev_cache").addHandler(handler)
    logging.getLogger("jev_cache").setLevel(logging.WARNING)
    runtime = Runtime()
    window = MainWindow(runtime)
    if not args.start_hidden:
        window.show()
    runtime.start()

    def capture():
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(args.screenshot))
        sample = window.state.get("sample", {})
        (args.screenshot.parent / "smoke-state.json").write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "sample": sample,
                    "item_count": len(window.state.get("items", [])),
                    "provider_configured": window.state.get("configured", False),
                    "fake_data": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    if args.screenshot:
        QTimer.singleShot(6500, capture)
    if args.quit_after:
        QTimer.singleShot(args.quit_after * 1000, lambda: app.exit(0))

    def shutdown():
        runtime.stop()
        runtime.wait(12000)
        window.tray.hide()
        window.floating.close()
        lock.unlock()

    app.aboutToQuit.connect(shutdown)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
