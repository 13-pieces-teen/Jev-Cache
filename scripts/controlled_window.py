"""Disposable integration-test target, never a stand-in for third-party compatibility."""

import argparse
import json
import os
from pathlib import Path

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel

parser = argparse.ArgumentParser()
parser.add_argument("--ready", required=True, type=Path)
args = parser.parse_args()
app = QApplication([])
window = QLabel("Jev-Cache 正常关闭验证窗口\n仅此测试窗口参与验证，无用户文档。")
window.setWindowTitle("Jev-Cache controlled verification target")
window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
window.resize(360, 90)
memory = bytearray(32 * 1024 * 1024)
for offset in range(0, len(memory), 4096):
    memory[offset] = 1
window.show()
args.ready.write_text(
    json.dumps({"pid": os.getpid(), "created": psutil.Process().create_time(), "hwnd": int(window.winId())}),
    encoding="utf-8",
)
QTimer.singleShot(20000, lambda: app.exit(0))
raise SystemExit(app.exec())
