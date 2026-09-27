from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .runtime import Runtime
from .windows import fullscreen_other

STYLE = """
QWidget { color: #203d34; font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; }
QMainWindow, QWidget#panel { background: #f2f4ed; }
QFrame#card { background: #fcfdf8; border: 1px solid #e0e6db; border-radius: 18px; }
QLabel#eyebrow { color: #6f8177; font-size: 11px; letter-spacing: 2px; }
QLabel#title { font-size: 27px; font-weight: 650; }
QLabel#number { font-size: 48px; font-weight: 650; }
QLabel#muted { color: #718077; }
QPushButton { background: #e7eddf; border: none; border-radius: 9px; padding: 10px 15px; }
QPushButton:hover { background: #d9e4cd; }
QPushButton:disabled { color: #9aa59a; background: #ebeee7; }
QPushButton#primary { background: #214d3d; color: #f4f8e9; font-size: 16px; font-weight: 600; padding: 14px 22px; }
QPushButton#primary:hover { background: #30634e; }
QPushButton#small { padding: 6px 11px; font-size: 12px; }
QLineEdit { background: #fffef9; border: 1px solid #d6dfcf; border-radius: 8px; padding: 10px; }
QLineEdit:focus { border-color: #74976a; }
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab { background: transparent; color: #708175; padding: 12px 20px; margin-right: 5px; }
QTabBar::tab:selected { color: #244c3d; border-bottom: 3px solid #244c3d; font-weight: 600; }
QTableWidget { background: #fcfdf8; border: 1px solid #e0e6db; border-radius: 12px; gridline-color: #edf0e9; }
QHeaderView::section { background: #eaf0e2; border: none; padding: 11px; color: #5e7164; }
QTableWidget::item { padding: 9px; border-bottom: 1px solid #edf0e9; }
QProgressBar { background: #e7ecdf; border: none; border-radius: 4px; max-height: 7px; }
QProgressBar::chunk { background: #80a973; border-radius: 4px; }
QCheckBox { spacing: 9px; padding: 7px 0; }
QCheckBox::indicator { width: 17px; height: 17px; }
QScrollArea { border: none; background: transparent; }
"""


def human_bytes(number: int | float, signed=False) -> str:
    prefix = "+" if signed and number > 0 else "−" if number < 0 else ""
    value = abs(number)
    if value >= 1024**3:
        return f"{prefix}{value / 1024**3:.1f} GB"
    return f"{prefix}{value / 1024**2:.0f} MB"


def icon() -> QIcon:
    image = QPixmap(64, 64)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#244d3c"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 18, 18)
    painter.setPen(QColor("#d9efaa"))
    painter.setFont(QFont("Segoe UI", 27, QFont.Weight.DemiBold))
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, "J")
    painter.end()
    return QIcon(image)


def label(text, object_name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if object_name:
        widget.setObjectName(object_name)
    widget.setWordWrap(wrap)
    return widget


def card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(24, 22, 24, 22)
    layout.setSpacing(12)
    return frame, layout


class FloatingWindow(QWidget):
    details_requested = Signal()
    optimize_requested = Signal()

    def __init__(self):
        super().__init__(
            None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Jev-Cache 小助手")
        self.resize(292, 82)
        self.drag_start = None
        self.original = None
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        panel = QFrame()
        panel.setObjectName("floating")
        panel.setStyleSheet(
            "QFrame#floating{background:#244d3c;border-radius:18px;} QLabel{color:#e9f5da;}"
            "QPushButton{background:#d9efaa;color:#244d3c;padding:9px 10px;}"
        )
        row = QHBoxLayout(panel)
        row.setContentsMargins(15, 12, 12, 12)
        stack = QVBoxLayout()
        self.name = label("Jev-Cache")
        self.info = label("正在观察…")
        self.info.setStyleSheet("font-size:11px;color:#bbd1be")
        self.name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.info.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        stack.addWidget(self.name)
        stack.addWidget(self.info)
        row.addLayout(stack, 1)
        self.clean = QPushButton("整理")
        self.clean.clicked.connect(self.optimize_requested)
        more = QPushButton("⋯")
        more.clicked.connect(self.details_requested)
        row.addWidget(self.clean)
        row.addWidget(more)
        root.addWidget(panel)
        self.fullscreen_timer = QTimer(self)
        self.fullscreen_timer.timeout.connect(self._fullscreen)
        self.fullscreen_timer.start(2000)

    def _fullscreen(self):
        hide = fullscreen_other()
        if hide and self.isVisible():
            self.hide()
        elif not hide and not self.isVisible():
            self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = event.globalPosition().toPoint()
            self.original = self.pos()

    def mouseMoveEvent(self, event):
        if self.drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(self.original + event.globalPosition().toPoint() - self.drag_start)

    def mouseReleaseEvent(self, event):
        self.drag_start = None
        screen = self.screen().availableGeometry()
        self.move(
            max(screen.left(), min(self.x(), screen.right() - self.width())),
            max(screen.top(), min(self.y(), screen.bottom() - self.height())),
        )


class MainWindow(QMainWindow):
    def __init__(self, runtime: Runtime):
        super().__init__()
        self.runtime = runtime
        self.state = {}
        self.settings_loaded = False
        self.table_signature = None
        self.history_signature = None
        self.setWindowTitle("Jev-Cache · 把内存留给接下来要做的事")
        self.setWindowIcon(icon())
        self.resize(980, 750)
        self.setMinimumSize(820, 660)
        panel = QWidget()
        panel.setObjectName("panel")
        root = QVBoxLayout(panel)
        root.setContentsMargins(30, 25, 30, 18)
        root.setSpacing(18)
        header = QHBoxLayout()
        brand = QVBoxLayout()
        brand.addWidget(label("J E V – C A C H E", "eyebrow"))
        brand.addWidget(label("给接下来的事，留点空间。", "title"))
        header.addLayout(brand, 1)
        self.pause = QPushButton("暂停整理")
        self.pause.clicked.connect(lambda: runtime.submit("pause", value=not self.state.get("paused", False)))
        header.addWidget(self.pause)
        root.addLayout(header)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._overview(), "概览")
        self.tabs.addTab(self._objects(), "正在占用")
        self.tabs.addTab(self._history(), "处理记录")
        self.tabs.addTab(self._memory(), "记忆")
        self.tabs.addTab(self._settings(), "设置")
        self.tabs.currentChanged.connect(lambda _: self.update_state(self.state))
        root.addWidget(self.tabs, 1)
        self.footer = label("本地观察 · 手动模式 · 开发预览 0.1", "muted")
        root.addWidget(self.footer)
        self.setCentralWidget(panel)
        self.floating = FloatingWindow()
        self.floating.details_requested.connect(self.show_panel)
        self.floating.optimize_requested.connect(self.optimize)
        geometry = QApplication.primaryScreen().availableGeometry()
        self.floating.move(geometry.right() - 318, geometry.bottom() - 112)
        self.floating.show()
        self.tray = QSystemTrayIcon(icon(), self)
        self.tray.setToolTip("Jev-Cache")
        menu = QMenu()
        menu.addAction("打开 Jev-Cache", self.show_panel)
        menu.addAction("整理一下", self.optimize)
        menu.addSeparator()
        menu.addAction("退出助手", lambda: QApplication.instance().exit(0))
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_panel() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray.show()
        runtime.state_changed.connect(self.update_state)
        runtime.notice.connect(self.show_notice)
        runtime.configuration_result.connect(self.connection_result)

    def _overview(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 18, 0, 0)
        root.setSpacing(14)
        top, layout = card()
        row = QHBoxLayout()
        metric = QVBoxLayout()
        metric.addWidget(label("现在可用的内存", "muted"))
        self.available = label("—", "number")
        metric.addWidget(self.available)
        self.total = label("正在读取本机状态", "muted")
        metric.addWidget(self.total)
        row.addLayout(metric, 1)
        actions = QVBoxLayout()
        self.clean = QPushButton("整理一下  ↗")
        self.clean.setObjectName("primary")
        self.clean.clicked.connect(self.optimize)
        actions.addWidget(self.clean)
        self.auto = QCheckBox("自动照顾内存")
        self.auto.toggled.connect(lambda checked: self.runtime.submit("settings", auto=checked))
        actions.addWidget(self.auto)
        row.addLayout(actions)
        layout.addLayout(row)
        self.pressure = QProgressBar()
        self.pressure.setTextVisible(False)
        layout.addWidget(self.pressure)
        self.live_status = label("正在了解你的使用情况", "muted", True)
        layout.addWidget(self.live_status)
        root.addWidget(top)
        context, line = card()
        line.addWidget(label("这会儿，你主要在做什么？（可选）"))
        self.context = QLineEdit()
        self.context.setPlaceholderText("例如：正在写文档，Python 资料接下来还要用")
        self.context.setMaxLength(200)
        line.addWidget(self.context)
        root.addWidget(context)
        result, result_layout = card()
        self.result_title = label("整理效果", "muted")
        self.result_number = label("还没有处理记录")
        self.result_number.setStyleSheet("font-size:23px;font-weight:600")
        self.result_detail = label("处理完成后，这里会显示实际动作和测得的变化。", "muted", True)
        result_layout.addWidget(self.result_title)
        result_layout.addWidget(self.result_number)
        result_layout.addWidget(self.result_detail)
        root.addWidget(result)
        self.connection = label("正在连接本地组件…", "muted", True)
        root.addWidget(self.connection)
        root.addStretch(1)
        return page

    def _objects(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 18, 0, 0)
        root.addWidget(label("重要的先保留，其余交给你决定。"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("查找应用或网页")
        self.search.textChanged.connect(lambda _: self._update_objects(force=True))
        root.addWidget(self.search)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["应用 / 网页", "当前占用", "状态", "操作"])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 112)
        self.table.setColumnWidth(2, 177)
        self.table.setColumnWidth(3, 220)
        root.addWidget(self.table, 1)
        root.addWidget(
            label(
                "当前占用包含可能共享的内存，不代表可释放量。正常关闭会保留应用自己的保存提示。",
                "muted",
                True,
            )
        )
        return page

    def _history(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 18, 0, 0)
        root.addWidget(label("每一次处理，都有记录。"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.history_layout = QVBoxLayout(body)
        self.history_layout.setContentsMargins(0, 0, 8, 0)
        scroll.setWidget(body)
        root.addWidget(scroll)
        return page

    def _memory(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 18, 0, 0)
        frame, layout = card()
        layout.addWidget(label("助手记住了什么", "title"))
        self.memory_status = label("正在读取本地记录", "muted", True)
        self.memory_names = label("尚未设置保留项。", wrap=True)
        layout.addWidget(self.memory_status)
        layout.addWidget(self.memory_names)
        layout.addWidget(
            label(
                "使用摘要和清理后的回访保存在这台电脑上。只有与你本次判断有关的摘要，才会在启用 Jev 后发送。",
                "muted",
                True,
            )
        )
        clear = QPushButton("清除学习与处理记录")
        clear.clicked.connect(self.clear_memory)
        layout.addWidget(clear)
        root.addWidget(frame)
        root.addStretch()
        return page

    def _settings(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 18, 8, 0)
        frame, layout = card()
        layout.addWidget(label("连接 Jev", "title"))
        layout.addWidget(
            label(
                "当前为个人开发版，API Key 使用 Windows 当前用户加密保存。普通用户分发前将改为产品网关。",
                "muted",
                True,
            )
        )
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("粘贴 TypeSafe API Key")
        layout.addWidget(self.api_key)
        self.model = QLineEdit("jev-latest")
        self.model.setPlaceholderText("模型名称")
        layout.addWidget(self.model)
        self.cloud = QCheckBox("允许向 Jev 发送本轮候选的最小状态摘要与相关记忆")
        self.share_titles = QCheckBox("附加简短网页标题，帮助理解用途（可选，仍可能包含敏感信息）")
        self.remember = QCheckBox("在本机记住使用习惯和清理反馈")
        for widget in (self.cloud, self.share_titles, self.remember):
            layout.addWidget(widget)
        row = QHBoxLayout()
        save = QPushButton("保存设置")
        save.setObjectName("primary")
        save.clicked.connect(self.save_settings)
        self.test = QPushButton("测试连接")
        self.test.clicked.connect(self.test_connection)
        remove = QPushButton("移除密钥")
        remove.clicked.connect(
            lambda: self.runtime.submit("settings", remove_key=True, cloud=False, auto=False)
        )
        row.addWidget(save)
        row.addWidget(self.test)
        row.addWidget(remove)
        layout.addLayout(row)
        self.test_status = label("连接测试只发送固定测试文本，不发送电脑信息。", "muted", True)
        layout.addWidget(self.test_status)
        root.addWidget(frame)
        browser, bl = card()
        bl.addWidget(label("连接 Edge 网页", "title"))
        self.browser_status = label("尚未连接扩展", "muted", True)
        bl.addWidget(self.browser_status)
        bl.addWidget(
            label(
                "浏览器扩展独立安装。当前自动候选限定为 Python / Qt 只读文档；其他网页保持原样。",
                "muted",
                True,
            )
        )
        instructions = QPushButton("查看安装步骤")
        instructions.clicked.connect(self.browser_instructions)
        prepare = QPushButton("准备 Edge 接入并复制扩展目录")
        prepare.clicked.connect(self.prepare_edge)
        bl.addWidget(prepare)
        bl.addWidget(instructions)
        root.addWidget(browser)
        root.addStretch()
        scroll.setWidget(page)
        return scroll

    def save_settings(self):
        model = self.model.text().strip() or "jev-latest"
        self.runtime.submit(
            "settings",
            key=self.api_key.text().strip(),
            model=model,
            cloud=self.cloud.isChecked(),
            share_titles=self.share_titles.isChecked(),
            memory=self.remember.isChecked(),
        )
        self.api_key.clear()

    def test_connection(self):
        self.test_status.setText("正在连接 Jev…")
        self.test.setEnabled(False)
        self.runtime.submit(
            "test_connection", key=self.api_key.text().strip(), model=self.model.text().strip()
        )

    def connection_result(self, message):
        self.test_status.setText(message)
        self.test.setEnabled(True)

    def clear_memory(self):
        # A destructive user-data operation has a concrete, local confirmation.
        answer = QMessageBox.question(
            self, "清除记录", "删除本机学习记录和处理历史？明确设置的保留项将保留。"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.runtime.submit("forget")

    def browser_instructions(self):
        import sys

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        root = (
            Path(sys.executable).parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[2]
        )
        readme = root / "EDGE-SETUP.md"
        if readme.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(readme)))
        else:
            QMessageBox.information(
                self,
                "Edge 接入",
                "请查看项目中的 EDGE-SETUP.md：注册桥接器后，在 Edge 扩展页加载 extensions/edge。",
            )

    def prepare_edge(self):
        from .browser_setup import register_edge

        try:
            extension = register_edge()
            QApplication.clipboard().setText(str(extension))
            self.browser_status.setText("本机桥接已准备，扩展目录已复制。请在 Edge 扩展页加载该目录。")
            QMessageBox.information(
                self,
                "连接 Edge",
                "桥接已注册到当前 Windows 用户。\n\n"
                "打开 edge://extensions，开启开发人员模式，点击“加载解压缩的扩展”，粘贴已复制的目录。\n\n"
                "完成后，助手会自动显示连接状态。",
            )
        except (OSError, ValueError, KeyError):
            self.browser_status.setText("暂时未能准备桥接，请使用完整打包目录并查看安装步骤。")

    def optimize(self):
        self.runtime.submit("optimize", context=self.context.text())

    def show_panel(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def show_notice(self, message):
        self.live_status.setText(message)
        if not self.isVisible():
            self.tray.showMessage("Jev-Cache", message, QSystemTrayIcon.MessageIcon.Information, 4000)

    def update_state(self, state):
        if not state:
            return
        self.state = state
        sample = state.get("sample", {})
        if sample:
            self.available.setText(human_bytes(sample["available"]))
            self.total.setText(f"共 {human_bytes(sample['total'])} · 数据来自这台电脑")
            self.pressure.setValue(round(sample["used_percent"]))
            self.floating.info.setText(f"可用 {human_bytes(sample['available'])}")
        self.live_status.setText(state["status"])
        self.clean.setEnabled(not state["busy"] and not state["paused"])
        self.floating.clean.setEnabled(self.clean.isEnabled())
        self.pause.setText("继续整理" if state["paused"] else "暂停整理")
        settings = state["settings"]
        self.auto.blockSignals(True)
        self.auto.setChecked(settings["auto"])
        self.auto.setEnabled(state["configured"] and settings["cloud"])
        self.auto.setToolTip(
            "先在设置中连接 Jev 并开启摘要判断" if not self.auto.isEnabled() else "持续内存压力时处理合格对象"
        )
        self.auto.blockSignals(False)
        service = "Jev 已配置" if state["configured"] else "Jev 待配置 · 基础模式"
        if state["configured"] and not settings["cloud"]:
            service += " · 摘要上传未开启"
        browser = "Edge 已连接" if state["browser_connected"] else "Edge 待接入"
        self.connection.setText(f"{service}    /    {browser}")
        self.footer.setText(f"本地观察 · {'自动' if settings['auto'] else '手动'}模式 · 开发预览 0.1")
        self.browser_status.setText(browser)
        if not self.settings_loaded:
            self.cloud.setChecked(settings["cloud"])
            self.share_titles.setChecked(settings["share_titles"])
            self.remember.setChecked(settings["memory"])
            self.model.setText(settings["model"])
            self.settings_loaded = True
        self.api_key.setPlaceholderText(
            "已加密保存；输入可替换" if state["configured"] else "粘贴 TypeSafe API Key"
        )
        result = state["last_result"]
        if result:
            self.result_title.setText("处理后观察到的可用内存变化")
            if result.get("valid"):
                self.result_number.setText(human_bytes(result["delta_bytes"], signed=True))
                self.result_detail.setText("来自固定时间窗的本机观测；同时运行的其他应用也可能影响这个数值。")
            else:
                self.result_number.setText(
                    "已完成处理，正在观察"
                    if result.get("reason") == "measuring"
                    else "本次暂无法确定内存变化"
                )
                self.result_detail.setText(
                    f"{result.get('name', '')} · 动作与数值分别记录，不用估计值填充结果。"
                )
        elif not state["history"]:
            self.result_number.setText("还没有处理记录")
            self.result_detail.setText("处理完成后，这里会显示实际动作和测得的变化。")
        self.memory_status.setText(
            f"当前有 {state['memory_count']} 个对象的使用摘要。"
            if settings["memory"]
            else "习惯记忆已关闭，只使用当前观察和明确偏好。"
        )
        names = list(state["keep_names"].values())
        self.memory_names.setText("你要求保留：\n" + "、".join(names) if names else "尚未设置保留项。")
        if self.tabs.currentIndex() == 1:
            self._update_objects()
        if self.tabs.currentIndex() == 2:
            self._update_history()

    def _update_objects(self, force=False):
        if not self.state:
            return
        query = self.search.text().casefold()
        items = [i for i in self.state["items"] if query in i.name.casefold()][:80]
        signature = tuple(
            (
                i.id,
                i.active,
                i.protections,
                (i.memory_bytes or 0) // (8 * 1024 * 1024),
                i.stable_key in self.state["kept"],
            )
            for i in items
        )
        signature = (self.state["busy"], self.state["paused"], signature)
        if not force and signature == self.table_signature:
            return
        self.table_signature = signature
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            kept = item.stable_key in self.state["kept"]
            status = (
                "你要求保留"
                if kept
                else "、".join(item.protections)
                if item.protections
                else (
                    "可单独请求关闭"
                    if item.allowed_action == "request_exit"
                    else "支持网页释放"
                    if item.auto_eligible
                    else "状态不足，保留"
                )
            )
            for col, text in enumerate(
                (
                    item.name,
                    human_bytes(item.memory_bytes) if item.memory_bytes is not None else "不逐页估算",
                    status,
                )
            ):
                cell = QTableWidgetItem(text)
                cell.setToolTip(item.details)
                self.table.setItem(row, col, cell)
            controls = QWidget()
            layout = QHBoxLayout(controls)
            layout.setContentsMargins(6, 5, 6, 5)
            keep = QPushButton("取消保留" if kept else "保留")
            keep.setObjectName("small")
            keep.clicked.connect(lambda _=False, target=item.id: self.runtime.submit("keep", item_id=target))
            layout.addWidget(keep)
            close = QPushButton("正常关闭" if item.kind == "app" else "释放网页")
            close.setObjectName("small")
            close.setEnabled(
                not kept
                and not item.protections
                and not item.active
                and item.allowed_action != "none"
                and not self.state["busy"]
                and not self.state["paused"]
            )
            close.clicked.connect(
                lambda _=False, target=item.id: self.runtime.submit("close_item", item_id=target)
            )
            layout.addWidget(close)
            self.table.setCellWidget(row, 3, controls)
            self.table.setRowHeight(row, 52)

    def _update_history(self):
        history = self.state.get("history", [])
        signature = repr(history) + repr(self.state.get("ghosts", {}))
        if signature == self.history_signature:
            return
        self.history_signature = signature
        while self.history_layout.count():
            old = self.history_layout.takeAt(0)
            if old.widget():
                old.widget().deleteLater()
        if not history:
            self.history_layout.addWidget(label("还没有处理记录。真实完成的动作会出现在这里。", "muted"))
        for record in history:
            frame, layout = card()
            date = datetime.fromtimestamp(record["at"]).strftime("%m-%d %H:%M")
            layout.addWidget(label(f"{record['name']}    ·    {date}"))
            layout.addWidget(label(record.get("message", "已发起正常处理"), "muted", True))
            measurement = record.get("measurement", {})
            if measurement.get("valid"):
                layout.addWidget(
                    label("处理后观察到 " + human_bytes(measurement["delta_bytes"], signed=True))
                )
            row = QHBoxLayout()
            if record["status"] == "completed":
                if record["kind"] == "tab":
                    reopen = QPushButton("重新打开原标签")
                    reopen.clicked.connect(
                        lambda _=False, target=record["id"]: self.runtime.submit("reopen", action_id=target)
                    )
                    row.addWidget(reopen)
                correction = QPushButton("已记录纠正" if record.get("corrected") else "这次不该清理")
                correction.setEnabled(not record.get("corrected"))
                correction.clicked.connect(
                    lambda _=False, target=record["id"]: self.runtime.submit("correct", action_id=target)
                )
                row.addWidget(correction)
                layout.addLayout(row)
            self.history_layout.addWidget(frame)
        self.history_layout.addStretch()
