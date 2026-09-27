from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .presentation import human_bytes, observation_text
from .runtime import Runtime
from .ui_panels import Controls, QuickPanel
from .ui_theme import STYLE as STYLE
from .ui_widgets import FloatingWindow, ResultSummary, TitleBar, button, card, icon, keep_on_screen, label


class MainWindow(QMainWindow):
    def __init__(self, runtime: Runtime):
        super().__init__()
        self.runtime = runtime
        self.state = {}
        self.settings_loaded = False
        self.table_signature = None
        self.history_signature = None
        self.protection_signature = None
        self.optimization_pending = False
        self.notice_message = ""
        self.notice_timer = QTimer(self)
        self.notice_timer.setSingleShot(True)
        self.notice_timer.timeout.connect(self.clear_notice)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Jev-Cache · 内存助手")
        self.setWindowIcon(icon())
        self.resize(940, 680)
        self.setMinimumSize(820, 540)
        chrome = QFrame()
        chrome.setObjectName("chrome")
        root = QVBoxLayout(chrome)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)
        root.addWidget(TitleBar("Jev-Cache / 内存助手", self.close, self.showMinimized))
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        sidebar = QWidget()
        sidebar.setFixedWidth(202)
        rail = QVBoxLayout(sidebar)
        rail.setContentsMargins(16, 20, 16, 12)
        rail.setSpacing(6)
        self.controls = Controls(self, compact=True)
        self.clean, self.auto, self.pause = self.controls.clean, self.controls.auto, self.controls.pause
        rail.addWidget(self.controls)
        rail.addSpacing(14)
        self.nav = []
        for index, text in enumerate(("最近结果", "应用与网页", "处理记录", "助手记忆", "设置")):
            nav = button(text, lambda checked=False, target=index: self.show_page(target), "nav")
            nav.setCheckable(True)
            self.nav.append(nav)
            rail.addWidget(nav)
        rail.addStretch()
        rail.addWidget(label("把内存留给\n接下来要做的事。", "caption"))
        rail.addWidget(button("打开小面板 ↗", self.show_quick, "link"))
        content.addWidget(sidebar)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.addTab(self._overview(), "最近结果")
        self.tabs.addTab(self._objects(), "应用与网页")
        self.tabs.addTab(self._history(), "处理记录")
        self.tabs.addTab(self._memory(), "助手记忆")
        self.tabs.addTab(self._settings(), "设置")
        self.tabs.currentChanged.connect(self._page_changed)
        content.addWidget(self.tabs, 1)
        root.addLayout(content, 1)
        self.notice_bar = label("", "notice", True)
        self.notice_bar.hide()
        root.addWidget(self.notice_bar)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(10, 7, 3, 1)
        self.connection = label("正在连接本地组件…", "caption")
        self.footer = label("手动模式 · 开发预览 0.1", "caption")
        bottom.addWidget(self.connection, 1)
        bottom.addWidget(self.footer)
        bottom.addWidget(QSizeGrip(self))
        root.addLayout(bottom)
        self.setCentralWidget(chrome)
        self.floating = FloatingWindow()
        self.quick = QuickPanel(self)
        self.context = self.quick.context
        self.floating.details_requested.connect(self.toggle_quick)
        self.floating.optimize_requested.connect(self.optimize)
        self.floating.concealed.connect(self.quick.hide)
        self.quick.dismissed.connect(lambda: self.floating.set_expanded(False))
        screen = QApplication.primaryScreen().availableGeometry()
        self.floating.move(screen.right() - 330, screen.bottom() - 124)
        self.floating.show()
        self.tray = QSystemTrayIcon(icon(), self)
        self.tray.setToolTip("Jev-Cache · 内存助手")
        menu = QMenu()
        menu.addAction("打开小面板", self.show_quick)
        menu.addAction("打开详情", self.show_panel)
        menu.addAction("一键清理", self.optimize)
        menu.addAction("显示悬浮窗", self.floating.restore)
        menu.addSeparator()
        menu.addAction("退出助手", lambda: QApplication.instance().exit(0))
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_quick() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray.show()
        QShortcut(QKeySequence("Escape"), self, activated=self.hide)
        runtime.state_changed.connect(self.update_state)
        runtime.notice.connect(self.show_notice)
        runtime.configuration_result.connect(self.connection_result)
        self._page_changed(0)

    @staticmethod
    def _page(title, subtitle):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(12)
        root.addWidget(label(title, "title"))
        root.addWidget(label(subtitle, "muted", True))
        return page, root

    def _overview(self):
        page, root = self._page("给接下来的事，留点空间。", "需要时清理，重要的先保留。")
        self.result = ResultSummary()
        root.addWidget(self.result)
        root.addWidget(button("查看处理记录 →", lambda: self.show_page(2), "link"))
        kept, layout = card()
        layout.addWidget(label("此刻正在保留", "sectionTitle"))
        self.protection_rows = label("正在读取应用与网页状态…", "muted", True)
        layout.addWidget(self.protection_rows)
        layout.addWidget(button("查看应用与网页 →", lambda: self.show_page(1), "link"))
        root.addWidget(kept)
        self.live_status = label("正在了解这台电脑", "caption", True)
        root.addWidget(self.live_status)
        self.setup_hint = button("连接 Jev，开始智能判断 →", lambda: self.show_page(4), "link")
        root.addWidget(self.setup_hint)
        root.addStretch()
        return page

    def _objects(self):
        page, root = self._page("应用与网页", "你认识的名称，你决定的保留项。")
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("查找应用或网页")
        self.search.setAccessibleName("查找应用或网页")
        self.search.textChanged.connect(lambda _: self._update_objects(force=True))
        self.kept_only = QCheckBox("只看保留名单")
        self.kept_only.toggled.connect(lambda _: self._update_objects(force=True))
        row.addWidget(self.search, 1)
        row.addWidget(self.kept_only)
        root.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["应用 / 网页", "当前占用", "状态", "操作"])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 104)
        self.table.setColumnWidth(2, 136)
        self.table.setColumnWidth(3, 180)
        root.addWidget(self.table, 1)
        root.addWidget(label("当前占用不等于可释放量。正常关闭会保留应用自己的保存提示。", "caption", True))
        return page

    def _history(self):
        page, root = self._page("处理记录", "做了什么、测到了什么，分别记录。")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.history_layout = QVBoxLayout(body)
        self.history_layout.setContentsMargins(0, 0, 8, 0)
        self.history_layout.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll)
        return page

    def _memory(self):
        page, root = self._page("助手记住了什么", "习惯留在本机，由你决定是否记住。")
        frame, layout = card()
        layout.addWidget(label("你的保留偏好", "sectionTitle"))
        self.memory_names = label("尚未设置保留项。", wrap=True)
        layout.addWidget(self.memory_names)
        layout.addWidget(button("管理保留名单 →", self.show_kept, "link"))
        root.addWidget(frame)
        frame, layout = card()
        layout.addWidget(label("使用习惯与清理反馈", "sectionTitle"))
        self.memory_status = label("正在读取本地记录", "muted", True)
        layout.addWidget(self.memory_status)
        layout.addWidget(
            label(
                "启用 Jev 后，仅与本轮判断有关的摘要会被发送。关闭习惯记忆后，明确设置的保留项仍然有效。",
                "muted",
                True,
            )
        )
        layout.addWidget(button("调整记忆设置 →", lambda: self.show_page(4), "link"))
        root.addWidget(frame)
        clear = button("清除学习与处理记录", self.clear_memory)
        root.addWidget(clear, 0, Qt.AlignmentFlag.AlignLeft)
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
        self.api_key.setAccessibleName("TypeSafe API Key")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("粘贴 TypeSafe API Key")
        layout.addWidget(self.api_key)
        self.model = QLineEdit("jev-latest")
        self.model.setAccessibleName("Jev 模型名称")
        self.model.setPlaceholderText("模型名称")
        layout.addWidget(self.model)
        self.cloud = QCheckBox("允许自动清理时向 Jev 发送必要摘要与相关记忆")
        self.share_titles = QCheckBox("附加简短网页标题（可选，可能含敏感信息）")
        self.remember = QCheckBox("在本机记住使用习惯和清理反馈")
        for widget in (self.cloud, self.share_titles, self.remember):
            layout.addWidget(widget)
        layout.addWidget(
            label("手动点击“一键清理”会发送本轮必要摘要并开始清理，无需开启自动清理权限。", "caption", True)
        )
        row = QHBoxLayout()
        save = QPushButton("保存设置")
        save.setObjectName("primary")
        save.clicked.connect(self.save_settings)
        self.test = QPushButton("测试连接")
        self.test.clicked.connect(self.test_connection)
        remove = QPushButton("移除密钥")
        remove.clicked.connect(self.remove_key)
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
        self.test_status.setText("设置已提交。可通过“测试连接”检查 Jev 是否可用。")

    def test_connection(self):
        self.test_status.setText("正在连接 Jev…")
        self.test.setEnabled(False)
        self.runtime.submit(
            "test_connection", key=self.api_key.text().strip(), model=self.model.text().strip()
        )

    def remove_key(self):
        self.api_key.clear()
        self.cloud.setChecked(False)
        self.runtime.submit("settings", remove_key=True, cloud=False, auto=False)

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
        if not self.state.get("configured"):
            self.show_page(4)
            self.api_key.setFocus()
            return
        if self.optimization_pending:
            return
        if self.state.get("busy"):
            return
        self.optimization_pending = True
        for control in (self.controls.clean, self.quick.controls.clean, self.floating.clean):
            control.setEnabled(False)
        self.runtime.submit("optimize", context=self.context.text(), allow_summary_once=True)
        self.update_state(self.state)
        QTimer.singleShot(1000, self._release_click)

    def _release_click(self):
        self.optimization_pending = False
        self.update_state(self.state)

    def toggle_pause(self):
        self.runtime.submit("pause", value=not self.state.get("paused", False))

    def show_panel(self):
        self.quick.hide()
        keep_on_screen(self)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def show_page(self, index):
        self.tabs.setCurrentIndex(index)
        self.show_panel()

    def show_kept(self):
        self.kept_only.setChecked(True)
        self.show_page(1)

    def _page_changed(self, index):
        for n, nav in enumerate(self.nav):
            nav.setChecked(n == index)
        if self.state:
            self.update_state(self.state)

    def show_quick(self):
        self.floating.restore()
        self.quick.reveal(self.floating)
        self.floating.set_expanded(True)

    def toggle_quick(self):
        if self.quick.isVisible():
            self.quick.hide()
        else:
            self.show_quick()

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def show_notice(self, message):
        self.notice_message = message
        self.notice_bar.setText(message)
        self.notice_bar.show()
        self.notice_timer.start(8000)
        self.live_status.setText(message)
        self.quick.live_status.setText(message)
        # Ordinary results never interrupt a full-screen game or generate tray spam.

    def clear_notice(self):
        self.notice_message = ""
        self.notice_bar.hide()
        self.update_state(self.state)

    def update_state(self, state):
        if not state:
            return
        self.state = state
        settings = state["settings"]
        self.controls.update_state(state)
        self.quick.controls.update_state(state)
        self.result.update_state(state)
        self.quick.result.update_state(state)
        self.live_status.setText(self.notice_message or state["status"])
        self.quick.live_status.setText(self.notice_message or state["status"])
        setup_needed = not state["configured"] or not state["browser_connected"]
        self.quick.setup.setVisible(setup_needed)
        self.quick.setup.setText(
            "连接 Jev，开始智能判断 →" if not state["configured"] else "连接 Edge 网页 →"
        )
        self.setup_hint.setVisible(setup_needed)
        self.setup_hint.setText(self.quick.setup.text())
        self.floating.clean.setText(self.controls.clean.text())
        self.floating.clean.setToolTip(self.controls.clean.toolTip())
        self.floating.clean.setEnabled(self.controls.clean.isEnabled() and not self.optimization_pending)
        if self.optimization_pending:
            self.controls.clean.setEnabled(False)
            self.quick.controls.clean.setEnabled(False)
        sample = state.get("sample", {})
        floating_status = (
            "已暂停"
            if state["paused"] and not self.optimization_pending
            else "正在处理"
            if state["busy"] or self.optimization_pending
            else "内存偏紧"
            if state.get("memory_pressure")
            else "内存够用"
            if sample
            else "正在观察"
        )
        mode = "自动" if settings["auto"] else "手动"
        self.floating.titlebar.title.setText(
            f"Jev-Cache · {floating_status}"
            if state["paused"] or state["busy"] or self.optimization_pending
            else "Jev-Cache"
        )
        if sample.get("total", 0) > 0:
            total = sample["total"]
            available = max(0, min(sample["available"], total))
            used_percent = (1 - available / total) * 100
            self.floating.info.setText(f"内存占用 {used_percent:.0f}%")
            self.floating.meta.setText(f"可用 {human_bytes(available)} · {mode}")
            details = (
                f"已用 {human_bytes(total - available)} / {human_bytes(total)}\n"
                f"可用 {human_bytes(available)}\n{floating_status} · {mode}模式"
            )
            self.floating.info.setToolTip(details)
            self.floating.meta.setToolTip(details)
        else:
            self.floating.info.setText("内存占用 —")
            self.floating.meta.setText(f"正在读取 · {mode}")
            self.floating.info.setToolTip("")
            self.floating.meta.setToolTip("")
        service = "Jev 已配置" if state["configured"] else "Jev 待连接"
        if state["configured"] and not settings["cloud"]:
            service = "Jev 已配置 · 手动按次使用"
        browser = "Edge 已连接" if state["browser_connected"] else "Edge 待接入"
        self.connection.setText(f"{service} · {browser}")
        self.quick.connection.setText(f"{service} · {browser}")
        self.footer.setText(f"{'自动' if settings['auto'] else '手动'}模式 · 开发预览 0.1")
        self.browser_status.setText(state.get("browser_error") or browser)
        if not self.settings_loaded:
            self.cloud.setChecked(settings["cloud"])
            self.share_titles.setChecked(settings["share_titles"])
            self.remember.setChecked(settings["memory"])
            self.model.setText(settings["model"])
            self.settings_loaded = True
        self.api_key.setPlaceholderText(
            "已加密保存；输入可替换" if state["configured"] else "粘贴 TypeSafe API Key"
        )
        self.memory_status.setText(
            f"已记录 {state['memory_count']} 个对象的使用摘要。"
            if settings["memory"]
            else "习惯记忆已关闭，只使用当前观察和明确偏好。"
        )
        names = list(state["keep_names"].values())
        self.memory_names.setText("、".join(names) if names else "尚未设置保留项。")
        protections = []
        for item in state["items"]:
            if item.stable_key in state["kept"]:
                protections.append(f"{item.name}  ·  你要求保留")
            elif item.active:
                protections.append(f"{item.name}  ·  正在使用")
            if len(protections) == 4:
                break
        self.protection_rows.setText(
            "\n\n".join(protections) if protections else "查看应用与网页，可将重要内容设为始终保留。"
        )
        if self.tabs.currentIndex() == 1:
            self._update_objects()
        if self.tabs.currentIndex() == 2:
            self._update_history()

    def _update_objects(self, force=False):
        if not self.state:
            return
        query = self.search.text().casefold()
        items = [
            i
            for i in self.state["items"]
            if query in i.name.casefold()
            and (not self.kept_only.isChecked() or i.stable_key in self.state["kept"])
        ][:80]
        signature = tuple(
            (
                i.id,
                i.active,
                i.protections,
                i.allowed_action,
                i.auto_eligible,
                i.details,
                (i.memory_bytes or 0) // (8 * 1024 * 1024),
                i.stable_key in self.state["kept"],
            )
            for i in items
        )
        signature = (self.state["busy"], self.state["paused"], query, self.kept_only.isChecked(), signature)
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
                    human_bytes(item.memory_bytes) if item.memory_bytes is not None else "暂无单独数据",
                    status,
                )
            ):
                cell = QTableWidgetItem(text)
                cell.setToolTip(item.details)
                self.table.setItem(row, col, cell)
            controls = QWidget()
            layout = QHBoxLayout(controls)
            layout.setContentsMargins(6, 5, 6, 5)
            keep = QPushButton("取消保留" if kept else "始终保留")
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
            self.table.setRowHeight(row, 54)

    def _update_history(self):
        history = self.state.get("history", [])
        signature = repr(history) + repr(self.state.get("ghosts", {})) + str(self.state["browser_connected"])
        if signature == self.history_signature:
            return
        self.history_signature = signature
        while self.history_layout.count():
            old = self.history_layout.takeAt(0)
            if old.widget():
                old.widget().deleteLater()
        if not history:
            frame, layout = card()
            layout.addWidget(label("还没有处理记录", "sectionTitle"))
            layout.addWidget(label("清理发生后，实际处理的对象和观察到的变化会出现在这里。", "muted", True))
            self.history_layout.addWidget(frame)
        for record in history:
            frame, layout = card()
            date = datetime.fromtimestamp(record["at"]).strftime("%m/%d %H:%M")
            heading = QHBoxLayout()
            heading.addWidget(label(record["name"], "sectionTitle", True), 1)
            heading.addWidget(label(date, "utility"))
            layout.addLayout(heading)
            status = record["status"]
            completed = status == "completed"
            status_text = (
                "已释放网页 · 标签页仍保留"
                if completed and record["kind"] == "tab"
                else "已确认应用退出"
                if completed
                else "正在等待处理结果"
                if status == "requested"
                else "本次未确认完成"
            )
            layout.addWidget(label(status_text, wrap=True))
            if not completed:
                layout.addWidget(label(record.get("message", "尚未收到完成回执。"), "muted", True))
            measurement = record.get("measurement")
            if completed and measurement:
                layout.addWidget(label(observation_text(measurement), "observation", True))
                if measurement.get("valid"):
                    layout.addWidget(label("其他应用的活动也可能影响这个数值。", "caption", True))
            if completed:
                row = QHBoxLayout()
                if record["kind"] == "tab":
                    reopen = button(
                        "重新打开",
                        lambda checked=False, target=record["id"]: self.runtime.submit(
                            "reopen", action_id=target
                        ),
                        "small",
                    )
                    reopen.setToolTip("重新加载原标签页；不保证恢复全部页面状态。")
                    reopen.setEnabled(self.state["browser_connected"])
                    row.addWidget(reopen)
                correction = button(
                    "已记录纠正" if record.get("corrected") else "这次不该清理",
                    lambda checked=False, target=record["id"]: self.runtime.submit(
                        "correct", action_id=target
                    ),
                    "small",
                )
                correction.setEnabled(not record.get("corrected"))
                row.addWidget(correction)
                row.addStretch()
                layout.addLayout(row)
            self.history_layout.addWidget(frame)
        self.history_layout.addStretch()
