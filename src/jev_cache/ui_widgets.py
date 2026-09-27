from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .presentation import human_bytes, receipt_view
from .windows import fullscreen_other


def label(text, object_name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if object_name:
        widget.setObjectName(object_name)
    widget.setWordWrap(wrap)
    if wrap:
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return widget


def button(text, callback, kind=None):
    widget = QPushButton(text)
    if kind:
        widget.setObjectName(kind)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(callback)
    return widget


def card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    return frame, layout


def icon() -> QIcon:
    result = QIcon()
    for size in (16, 24, 32, 48, 64):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.scale(size / 16, size / 16)
        for n in (4, 7, 10):
            p.fillRect(n, 1, 2, 14, QColor("#777777"))
            p.fillRect(1, n, 14, 2, QColor("#777777"))
        p.fillRect(3, 3, 10, 10, QColor("#202020"))
        p.fillRect(4, 4, 8, 8, QColor("#ffffff"))
        p.fillRect(5, 5, 6, 6, QColor("#326747"))
        p.fillRect(6, 6, 2, 2, QColor("#bed4bd"))
        p.end()
        result.addPixmap(pixmap)
    return result


def keep_on_screen(widget, position=None):
    point = position if position is not None else widget.pos()
    screen = QApplication.screenAt(point + QPoint(widget.width() // 2, 20)) or QApplication.primaryScreen()
    if screen is None:
        return
    bounds = screen.availableGeometry()
    widget.move(
        max(bounds.left(), min(point.x(), bounds.right() + 1 - widget.width())),
        max(bounds.top(), min(point.y(), bounds.bottom() + 1 - widget.height())),
    )


class TitleBar(QWidget):
    """Native system movement with an explicit drag-only title area."""

    moved = Signal()

    def __init__(self, title, close, minimize=None, parent=None):
        super().__init__(parent)
        self.setObjectName("titlebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.drag_origin = None
        self.window_origin = None
        row = QHBoxLayout(self)
        row.setContentsMargins(7, 4, 4, 4)
        row.setSpacing(7)
        chip = QLabel()
        chip.setPixmap(icon().pixmap(16, 16))
        chip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(chip)
        self.title = label(title, "windowTitle")
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.title, 1)
        if minimize:
            control = button("−", minimize, "chromeButton")
            control.setFixedSize(24, 23)
            control.setAccessibleName("最小化")
            control.setToolTip("最小化")
            row.addWidget(control)
        control = button("×", close, "chromeButton")
        control.setFixedSize(24, 23)
        control.setAccessibleName("收起窗口")
        control.setToolTip("收起窗口")
        row.addWidget(control)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.drag_origin = event.globalPosition().toPoint()
        self.window_origin = self.window().pos()
        handle = self.window().windowHandle()
        if handle and handle.startSystemMove():
            self.drag_origin = None
        event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(self.window_origin + event.globalPosition().toPoint() - self.drag_origin)
            self.moved.emit()

    def mouseReleaseEvent(self, event):
        self.drag_origin = None
        keep_on_screen(self.window())
        self.moved.emit()


class MemoryMeter(QWidget):
    """A segmented status bar; segment clipping preserves the actual memory ratio."""

    def __init__(self):
        super().__init__()
        self.used = 0.0
        self.setFixedHeight(18)
        self.setAccessibleName("内存使用情况")

    def set_sample(self, sample):
        total = sample.get("total", 0)
        available = sample.get("available", 0)
        self.used = max(0.0, min(1.0, 1 - available / total)) if total > 0 else 0.0
        description = f"已使用 {human_bytes(total - available)}，可用 {human_bytes(available)}"
        self.setAccessibleDescription(description)
        self.setToolTip(description)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        area = self.rect().adjusted(1, 1, -1, -1)
        p.fillRect(area, QColor("#becfbc"))
        p.fillRect(
            QRect(area.x(), area.y(), round(area.width() * self.used), area.height()), QColor("#555555")
        )
        p.setPen(QColor("#fafaf8"))
        for x in range(area.left() + 12, area.right(), 12):
            p.drawLine(x, area.top(), x, area.bottom())
        p.setPen(QColor("#777777"))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


class ResultSummary(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("receipt")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(9)
        layout.addWidget(label("最近一次", "caption"))
        self.headline = label("还没有处理记录", "resultHeadline", True)
        self.object_text = label("清理完成后，这里会显示实际处理的内容。", "muted", True)
        self.observation = label("", "observation", True)
        self.detail = label("", "caption", True)
        for widget in (self.headline, self.object_text, self.observation, self.detail):
            layout.addWidget(widget)

    def update_state(self, state):
        view = receipt_view(state)
        for widget, text in (
            (self.headline, view.headline),
            (self.object_text, view.object_text),
            (self.observation, view.observation),
            (self.detail, view.detail),
        ):
            widget.setText(text)
            widget.setVisible(bool(text))


class FloatingWindow(QWidget):
    details_requested = Signal()
    optimize_requested = Signal()
    concealed = Signal()

    def __init__(self):
        super().__init__(
            None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setObjectName("floating")
        self.setWindowTitle("Jev-Cache 小助手")
        self.user_hidden = False
        self.expanded = False
        self.setFixedSize(304, 94)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("chrome")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        self.titlebar = TitleBar("Jev-Cache", self.hide_by_user)
        layout.addWidget(self.titlebar)
        row = QHBoxLayout()
        row.setContentsMargins(7, 2, 5, 4)
        summary = QVBoxLayout()
        summary.setSpacing(1)
        self.info = label("内存占用 —", "floatingMetric")
        self.info.setAccessibleName("内存占用比例")
        self.meta = label("正在读取…", "caption")
        self.meta.setAccessibleName("可用内存与清理模式")
        summary.addWidget(self.info)
        summary.addWidget(self.meta)
        row.addLayout(summary, 1)
        self.clean = button("连接 Jev", self.optimize_requested.emit, "small")
        row.addWidget(self.clean)
        self.more = button("▴", self.details_requested.emit, "small")
        self.more.setFixedWidth(28)
        self.more.setAccessibleName("展开 Jev-Cache")
        self.more.setToolTip("展开面板")
        row.addWidget(self.more)
        layout.addLayout(row)
        root.addWidget(frame)
        self.fullscreen_timer = QTimer(self)
        self.fullscreen_timer.timeout.connect(self._fullscreen)
        self.fullscreen_timer.start(2000)
        QApplication.instance().screenRemoved.connect(lambda _: keep_on_screen(self))

    def set_expanded(self, expanded):
        self.expanded = expanded
        self.clean.setVisible(not expanded)
        self.more.setText("▾" if expanded else "▴")
        self.more.setAccessibleName("收起面板" if expanded else "展开 Jev-Cache")

    def hide_by_user(self):
        self.user_hidden = True
        self.hide()
        self.concealed.emit()

    def restore(self):
        self.user_hidden = False
        keep_on_screen(self)
        self.show()

    def _fullscreen(self):
        hide = fullscreen_other()
        if hide:
            if self.isVisible():
                self.hide()
            self.concealed.emit()
        elif not self.user_hidden and not self.isVisible():
            keep_on_screen(self)
            self.show()

    def event(self, event):
        if event.type() == QEvent.Type.ScreenChangeInternal and self.isVisible():
            QTimer.singleShot(0, lambda: keep_on_screen(self))
        return super().event(event)
