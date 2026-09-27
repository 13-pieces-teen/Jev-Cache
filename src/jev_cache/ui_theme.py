"""The small, tactile desktop vocabulary shared by all Jev-Cache windows."""

COLORS = {
    "surface": "#d6d6d6",
    "paper": "#fafaf8",
    "ink": "#202020",
    "muted": "#555555",
    "shadow": "#777777",
    "highlight": "#ffffff",
    "success": "#326747",
    "warning": "#895509",
    "focus": "#1d45a1",
}

STYLE = """
QWidget {
    color: #202020; font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 14px;
}
QMainWindow, QWidget#panel, QWidget#quickPanel, QWidget#floating { background: #d6d6d6; }
QFrame#chrome {
    background: #d6d6d6; border: 2px solid;
    border-top-color: #ffffff; border-left-color: #ffffff;
    border-bottom-color: #202020; border-right-color: #202020;
}
QFrame#card, QFrame#receipt {
    background: #fafaf8; border: 1px solid;
    border-top-color: #777777; border-left-color: #777777;
    border-bottom-color: #ffffff; border-right-color: #ffffff;
}
QFrame#card QLabel, QFrame#receipt QLabel { background: transparent; border: none; }
QWidget#titlebar { background: #202020; }
QLabel#windowTitle {
    color: #ffffff; font-family: 'Segoe UI'; font-size: 14px; font-weight: 600;
}
QLabel#title { font-size: 22px; font-weight: 600; }
QLabel#sectionTitle { font-size: 17px; font-weight: 600; }
QLabel#resultHeadline { font-size: 20px; font-weight: 600; }
QLabel#muted, QLabel#caption { color: #555555; }
QLabel#caption { font-size: 12px; }
QLabel#observation { font-size: 14px; font-weight: 600; }
QLabel#utility { font-family: 'Consolas', 'Microsoft YaHei UI'; font-size: 12px; color: #555555; }
QLabel#notice { background: #eee9d7; color: #604b1b; padding: 8px; }
QLabel#statusText { font-size: 20px; font-weight: 600; }
QLabel#sidebarStatus { font-size: 17px; font-weight: 600; }
QLabel#floatingMetric { font-size: 14px; font-weight: 600; }
QPushButton {
    background: #d6d6d6; padding: 7px 12px; border: 2px solid;
    border-top-color: #ffffff; border-left-color: #ffffff;
    border-bottom-color: #777777; border-right-color: #777777;
}
QPushButton:hover { background: #e3e3e3; }
QPushButton:pressed, QPushButton:checked {
    background: #c6c6c6; border-top-color: #777777; border-left-color: #777777;
    border-bottom-color: #ffffff; border-right-color: #ffffff;
    padding-top: 8px; padding-left: 13px; padding-bottom: 6px; padding-right: 11px;
}
QPushButton:focus { outline: none; border-color: #1d45a1; }
QPushButton:disabled { color: #777777; background: #d6d6d6; }
QPushButton#primary { font-size: 16px; font-weight: 600; padding: 10px 12px; }
QPushButton#small { padding: 5px 8px; font-size: 12px; }
QPushButton#chromeButton { padding: 0; color: #202020; font-family: 'Segoe UI'; font-size: 17px; }
QPushButton#link { border: 1px solid transparent; background: transparent; padding: 4px 0; text-align: left; }
QPushButton#link:hover { color: #1d45a1; text-decoration: underline; }
QPushButton#link:focus { border: 1px dotted #1d45a1; }
QPushButton#link:disabled { color: #777777; }
QPushButton#nav { border: 1px solid transparent; background: transparent; text-align: left; padding: 9px 10px; }
QPushButton#nav:hover { background: #e7e7e7; }
QPushButton#nav:checked { border: 1px solid #777777; background: #fafaf8; font-weight: 600; }
QPushButton#nav:focus { border: 1px dotted #1d45a1; }
QLineEdit {
    background: #fafaf8; padding: 8px; border: 1px solid;
    border-top-color: #777777; border-left-color: #777777;
    border-right-color: #ffffff; border-bottom-color: #ffffff;
    selection-background-color: #202020; selection-color: white;
}
QLineEdit:focus { border: 1px solid #1d45a1; }
QCheckBox { spacing: 8px; padding: 3px 0; }
QCheckBox::indicator { width: 17px; height: 17px; }
QCheckBox:disabled { color: #777777; }
QTabWidget::pane { border: none; background: transparent; }
QTableWidget { background: #fafaf8; border: 1px solid #777777; gridline-color: #d6d6d6; }
QHeaderView::section { background: #e4e4e4; border: none; border-bottom: 1px solid #777777; padding: 8px; }
QTableWidget::item { padding: 6px; border-bottom: 1px solid #e0e0e0; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #d6d6d6; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #999999; min-height: 30px; border: 2px solid #d6d6d6; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #e4e4e4; }
QMenu { background: #d6d6d6; border: 1px solid #777777; padding: 3px; }
QMenu::item { padding: 7px 24px; }
QMenu::item:selected { background: #202020; color: #ffffff; }
QToolTip { background: #fffde7; color: #202020; border: 1px solid #202020; padding: 5px; }
"""
