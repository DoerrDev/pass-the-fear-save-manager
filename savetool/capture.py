"""抓取游戏画面作为存档封面。"""
from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage

from . import core, win32


def _is_blank(img: QImage) -> bool:
    small = img.scaled(24, 14, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
    peak = 0
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            peak = max(peak, c.red(), c.green(), c.blue())
    return peak < 14


def _to_image(raw) -> QImage | None:
    if not raw:
        return None
    data, w, h = raw
    img = QImage(data, w, h, w * 4, QImage.Format.Format_RGB32).copy()
    return None if _is_blank(img) else img


def grab_game_image() -> QImage | None:
    """可在后台线程调用（只用 Win32 GDI，不依赖 Qt 的屏幕接口）。"""
    hwnd = core.main_game_window()
    if not hwnd or win32.user32.IsIconic(hwnd):
        return None
    img = _to_image(win32.print_window(hwnd))
    # 独占全屏时 PrintWindow 可能拿到黑图，游戏在前台就直接从屏幕截取
    if img is None and win32.user32.GetForegroundWindow() == hwnd:
        img = _to_image(win32.screen_grab(hwnd))
    return img


def to_thumb_bytes(img: QImage, width: int = 960) -> bytes:
    if img.width() > width:
        img = img.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "JPG", 88)
    return bytes(ba.data())


def grab_game_thumbnail() -> bytes | None:
    img = grab_game_image()
    return to_thumb_bytes(img) if img else None
