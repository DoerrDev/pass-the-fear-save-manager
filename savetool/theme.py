"""配色、样式表与绘制工具。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPalette,
                           QPixmap, QRadialGradient)
from PySide6.QtWidgets import QApplication


class C:
    bg = "#0d0f13"
    panel = "#111419"
    card = "#161a21"
    card_hover = "#1c212a"
    card_sel = "#241a1e"
    border = "#222731"
    text = "#e8eaf0"
    muted = "#838a9b"
    dim = "#5c6272"
    accent = "#e5484d"
    accent2 = "#b8323a"
    green = "#3dd68c"
    amber = "#f5b94a"


ASSETS = (Path(__file__).resolve().parent / "assets").as_posix()
ICON_FONTS = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]


class G:
    """Segoe Fluent 图标码位"""
    save = "\uE74E"
    play = "\uE768"
    rename = "\uE8AC"
    delete = "\uE74D"
    folder = "\uE838"
    settings = "\uE713"
    search = "\uE721"
    add = "\uE710"
    history = "\uE81C"
    warning = "\uE7BA"
    info = "\uE946"
    game = "\uE7FC"
    camera = "\uE722"


def icon_font(px: int) -> QFont:
    f = QFont()
    f.setFamilies(ICON_FONTS)
    f.setPixelSize(px)
    return f


def glyph_icon(glyph: str, color: str = C.text, size: int = 18) -> QIcon:
    icon = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.GlobalColor.transparent)
        pm.setDevicePixelRatio(scale)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(icon_font(int(size * 0.8)))
        p.setPen(QColor(color))
        p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, glyph)
        p.end()
        icon.addPixmap(pm)
    return icon


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, s, s)
        g.setColorAt(0, QColor("#f0585d"))
        g.setColorAt(1, QColor("#6e161c"))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)
        p.fillPath(path, g)
        p.setFont(icon_font(int(s * 0.56)))
        p.setPen(QColor("white"))
        p.drawText(QRectF(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, G.save)
        p.end()
        icon.addPixmap(pm)
    return icon


def draw_placeholder(p: QPainter, rect: QRectF, small: bool = False) -> None:
    """没有截图时的封面：暗红雾气 + 字标。"""
    p.save()
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0, QColor("#2b1014"))
    g.setColorAt(1, QColor("#0f1116"))
    p.fillRect(rect, g)
    rg = QRadialGradient(QPointF(rect.left() + rect.width() * 0.75, rect.top() + rect.height() * 0.2),
                         rect.width() * 0.6)
    rg.setColorAt(0, QColor(229, 72, 77, 70))
    rg.setColorAt(1, QColor(229, 72, 77, 0))
    p.fillRect(rect, rg)
    f = QFont("Segoe UI")
    f.setBold(True)
    f.setPixelSize(max(8, int(rect.height() * (0.16 if small else 0.11))))
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 130)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 60 if small else 45))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "PASS THE FEAR")
    p.restore()


def apply_palette(app: QApplication) -> None:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(C.bg))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(C.text))
    pal.setColor(QPalette.ColorRole.Base, QColor(C.card))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(C.panel))
    pal.setColor(QPalette.ColorRole.Text, QColor(C.text))
    pal.setColor(QPalette.ColorRole.Button, QColor(C.card))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(C.text))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(C.accent))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(C.card))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(C.text))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(C.dim))
    app.setPalette(pal)


STYLESHEET = f"""
* {{ font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 10pt; color: {C.text}; }}
QMainWindow, #Central, QDialog {{ background: {C.bg}; }}
QToolTip {{ background: {C.card}; color: {C.text}; border: 1px solid {C.border}; padding: 5px 8px; border-radius: 6px; }}

#Header {{ background: {C.panel}; border-bottom: 1px solid {C.border}; }}
#AppTitle {{ font-family: "Segoe UI"; font-size: 13pt; font-weight: 800; letter-spacing: 3px; }}
#AppSub {{ color: {C.muted}; font-size: 9pt; }}
#Pill {{ border-radius: 13px; padding: 0 14px; font-size: 9pt; font-weight: 600; }}
#Pill[state="on"] {{ background: rgba(61,214,140,0.10); color: {C.green}; border: 1px solid rgba(61,214,140,0.35); }}
#Pill[state="off"] {{ background: rgba(131,138,155,0.08); color: {C.muted}; border: 1px solid {C.border}; }}

#Side {{ background: {C.panel}; border-right: 1px solid {C.border}; }}
#SideTitle {{ font-size: 11pt; font-weight: 700; }}
#Count {{ color: {C.muted}; font-size: 9pt; }}
#Hint {{ color: {C.dim}; font-size: 8.5pt; }}

QLineEdit, QPlainTextEdit, QSpinBox, QKeySequenceEdit {{
    background: {C.card}; border: 1px solid {C.border}; border-radius: 8px; padding: 7px 10px;
    selection-background-color: {C.accent};
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border-color: {C.accent}; }}
QLineEdit:disabled {{ color: {C.dim}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

QPushButton {{
    background: {C.card_hover}; border: 1px solid #2a303c; border-radius: 8px; padding: 8px 16px;
}}
QPushButton:hover {{ background: #252b36; border-color: #363d4b; }}
QPushButton:pressed {{ background: #181c24; }}
QPushButton:disabled {{ color: {C.dim}; background: {C.card}; border-color: {C.border}; }}
QPushButton[kind="primary"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ef5358, stop:1 {C.accent2});
    border: 1px solid rgba(255,255,255,0.06); color: white; font-weight: 700;
}}
QPushButton[kind="primary"]:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f76a6e, stop:1 #cc3b43); }}
QPushButton[kind="primary"]:pressed {{ background: {C.accent2}; }}
QPushButton[kind="primary"]:disabled {{ background: #3a2327; color: #8d6a6e; }}
QPushButton[kind="big"] {{ padding: 13px 16px; font-size: 11pt; border-radius: 10px; }}
QPushButton[kind="danger"] {{ background: transparent; color: #ff7377; border: 1px solid rgba(229,72,77,0.40); }}
QPushButton[kind="danger"]:hover {{ background: rgba(229,72,77,0.12); }}
QPushButton[kind="ghost"] {{ background: transparent; border: 1px solid transparent; color: #b4bac8; }}
QPushButton[kind="ghost"]:hover {{ background: {C.card_hover}; border-color: {C.border}; }}
QPushButton[kind="chip"] {{
    background: {C.card}; border: 1px solid {C.border}; border-radius: 13px; padding: 4px 12px; font-size: 9pt; color: #c4c9d4;
}}
QPushButton[kind="chip"]:hover {{ border-color: {C.accent}; color: white; }}

QListWidget {{ background: transparent; border: none; outline: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2a303c; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3a4252; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid #3a4150; background: {C.card}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {C.accent}; }}
QCheckBox::indicator:checked {{ border: none; image: url({ASSETS}/check.svg); }}
QRadioButton::indicator:checked {{ border: none; image: url({ASSETS}/radio.svg); }}
QCheckBox::indicator:disabled {{ border-color: {C.border}; background: {C.panel}; }}

#DetailTitle {{ font-size: 19pt; font-weight: 800; }}
#Badge {{ background: rgba(245,185,74,0.12); color: {C.amber}; border: 1px solid rgba(245,185,74,0.35);
          border-radius: 10px; padding: 2px 10px; font-size: 8.5pt; font-weight: 600; }}
#Tile {{ background: {C.card}; border: 1px solid {C.border}; border-radius: 10px; }}
#TileLabel {{ color: {C.muted}; font-size: 8.5pt; }}
#TileValue {{ font-size: 11pt; font-weight: 700; }}
#SectionLabel {{ color: {C.muted}; font-size: 9pt; font-weight: 600; }}

#Banner {{ border-radius: 8px; padding: 9px 12px; font-size: 9pt; }}
#Banner[kind="warn"] {{ background: rgba(245,185,74,0.08); color: {C.amber}; border: 1px solid rgba(245,185,74,0.30); }}
#Banner[kind="info"] {{ background: rgba(120,150,255,0.07); color: #a9b8ff; border: 1px solid rgba(120,150,255,0.25); }}
#Banner[kind="error"] {{ background: rgba(229,72,77,0.08); color: #ff8a8d; border: 1px solid rgba(229,72,77,0.35); }}

#DialogTitle {{ font-size: 14pt; font-weight: 800; }}
#DialogText {{ color: #c3c8d3; }}
#Muted {{ color: {C.muted}; }}
#EmptyTitle {{ font-size: 15pt; font-weight: 700; }}

#Toast {{ background: #1b2029; border: 1px solid #2c3340; border-radius: 10px; padding: 10px 18px; font-weight: 600; }}
#Toast[kind="ok"] {{ border-color: rgba(61,214,140,0.55); }}
#Toast[kind="warn"] {{ border-color: rgba(245,185,74,0.55); }}
#Toast[kind="error"] {{ border-color: rgba(229,72,77,0.65); }}

QMenu {{ background: {C.card}; border: 1px solid {C.border}; border-radius: 8px; padding: 5px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {C.card_hover}; }}
QMenu::separator {{ height: 1px; background: {C.border}; margin: 4px 6px; }}
QMessageBox, QInputDialog {{ background: {C.bg}; }}
"""
