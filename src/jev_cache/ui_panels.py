from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .presentation import human_bytes, status_text
from .ui_widgets import MemoryMeter, ResultSummary, TitleBar, button, keep_on_screen, label


class Controls(QWidget):
    def __init__(self, owner, compact=False):
        super().__init__()
        self.owner = owner
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.status = label("正在了解这台电脑", "sidebarStatus" if compact else "statusText", True)
        self.available = label("正在读取内存…", "caption" if compact else "muted", True)
        self.meter = MemoryMeter()
        self.legend = label("灰色已用 · 绿色可用", "caption")
        for widget in (self.status, self.available, self.meter, self.legend):
            layout.addWidget(widget)
        self.clean = button("一键清理", owner.optimize, "primary")
        layout.addWidget(self.clean)
        self.auto = QCheckBox("自动清理")
        self.auto.toggled.connect(lambda value: owner.runtime.submit("settings", auto=value))
        layout.addWidget(self.auto)
        self.scope = label("当前自动范围：已验证的 Python / Qt 文档。", "caption", True)
        self.scope.setVisible(False)
        layout.addWidget(self.scope)
        self.pause = button("停止后续清理", owner.toggle_pause, "link")
        self.pause.hide()
        layout.addWidget(self.pause)

    def update_state(self, state):
        self.status.setText(status_text(state))
        sample = state.get("sample", {})
        if sample:
            self.available.setText(
                f"可用 {human_bytes(sample['available'])} / {human_bytes(sample['total'])}"
            )
            self.meter.set_sample(sample)
        busy, paused = state.get("busy", False), state.get("paused", False)
        configured = state.get("configured", False)
        ready = configured and state.get("settings", {}).get("cloud")
        self.clean.setText("一键清理" if configured else "连接 Jev")
        self.clean.setToolTip(
            "打开 Jev 连接设置"
            if not configured
            else "恢复并开始本轮清理；仅发送本轮必要摘要给 Jev"
            if paused
            else "正在处理，请稍候"
            if busy
            else "点击后将本轮必要摘要发送给 Jev，并清理符合条件的对象"
        )
        self.clean.setEnabled(not configured or not busy)
        self.pause.setVisible(busy and not paused)
        self.auto.blockSignals(True)
        self.auto.setChecked(state.get("settings", {}).get("auto", False))
        self.auto.setEnabled(bool(ready))
        self.auto.blockSignals(False)
        self.scope.setVisible(self.auto.isChecked())
        self.auto.setToolTip(
            "内存持续紧张时处理合格对象"
            if ready
            else "在设置中允许自动清理发送必要摘要"
            if configured
            else "先连接 Jev"
        )


class QuickPanel(QWidget):
    dismissed = Signal()

    def __init__(self, owner):
        super().__init__(
            None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.owner = owner
        self.setObjectName("quickPanel")
        self.setWindowTitle("Jev-Cache · 内存助手")
        self.resize(440, 600)
        self.setMinimumWidth(400)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("chrome")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)
        layout.addWidget(TitleBar("Jev-Cache", self.hide))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("panel")
        content = QVBoxLayout(body)
        content.setContentsMargins(16, 16, 16, 12)
        content.setSpacing(12)
        self.controls = Controls(owner)
        content.addWidget(self.controls)
        self.setup = button("完成连接设置 →", lambda: owner.show_page(4), "link")
        content.addWidget(self.setup)
        self.live_status = label("需要时整理，日常少打扰。", "caption", True)
        content.addWidget(self.live_status)
        self.result = ResultSummary()
        content.addWidget(self.result)
        self.history = button("查看处理记录 →", lambda: owner.show_page(2), "link")
        content.addWidget(self.history)
        self.context_toggle = button("＋ 补充这次需求", self.toggle_context, "link")
        content.addWidget(self.context_toggle)
        self.context = QLineEdit()
        self.context.setAccessibleName("补充这次需求")
        self.context.setPlaceholderText("例如：这些资料接下来还会用")
        self.context.setMaxLength(200)
        self.context.hide()
        content.addWidget(self.context)
        row = QHBoxLayout()
        row.addWidget(button("保留名单", owner.show_kept, "link"))
        row.addStretch()
        row.addWidget(button("助手记住了什么", lambda: owner.show_page(3), "link"))
        content.addLayout(row)
        content.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(12, 6, 12, 6)
        self.connection = label("正在连接本地组件…", "caption", True)
        footer.addWidget(self.connection, 1)
        self.settings = button("设置", lambda: owner.show_page(4), "small")
        footer.addWidget(self.settings)
        layout.addLayout(footer)
        root.addWidget(frame)
        QShortcut(QKeySequence("Escape"), self, activated=self.hide)

    def toggle_context(self):
        visible = not self.context.isVisible()
        self.context.setVisible(visible)
        self.context_toggle.setText("− 收起补充需求" if visible else "＋ 补充这次需求")
        if visible:
            self.context.setFocus()

    def reveal(self, anchor):
        bounds = anchor.screen().availableGeometry()
        self.resize(min(440, bounds.width()), min(600, bounds.height() - 24))
        point = QPoint(anchor.x() + anchor.width() - self.width(), anchor.y() - self.height() - 6)
        if point.y() < bounds.top():
            point.setY(anchor.y() + anchor.height() + 6)
        keep_on_screen(self, point)
        self.show()
        self.raise_()
        self.activateWindow()
        self.controls.clean.setFocus(Qt.FocusReason.OtherFocusReason)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.dismissed.emit()

    def event(self, event):
        if event.type() == QEvent.Type.WindowDeactivate:
            QTimer.singleShot(0, self._collapse_if_inactive)
        return super().event(event)

    def _collapse_if_inactive(self):
        active = QApplication.activeWindow()
        if self.isVisible() and active is not self and not (active and self.isAncestorOf(active)):
            self.hide()
