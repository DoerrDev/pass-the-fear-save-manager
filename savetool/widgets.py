"""自绘控件：存档卡片、封面大图、加载遮罩、提示气泡。"""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QGraphicsOpacityEffect, QLabel, QSizePolicy, QStyle, QStyledItemDelegate,
                               QWidget)

from .core import Snapshot, human_size
from .theme import C, draw_placeholder

SNAP_ROLE = Qt.ItemDataRole.UserRole + 1


def friendly_time(dt: datetime) -> str:
    today = datetime.now().date()
    if dt.date() == today:
        return f"今天 {dt:%H:%M}"
    if dt.date() == today - timedelta(days=1):
        return f"昨天 {dt:%H:%M}"
    if dt.year == today.year:
        return f"{dt:%m月%d日 %H:%M}"
    return f"{dt:%Y年%m月%d日 %H:%M}"


class ThumbCache:
    def __init__(self):
        self._full: dict[str, QPixmap | None] = {}
        self._scaled: dict[tuple, QPixmap] = {}

    def full(self, snap: Snapshot) -> QPixmap | None:
        if snap.id not in self._full:
            pm = QPixmap(str(snap.thumb_path)) if snap.thumb_path.is_file() else QPixmap()
            self._full[snap.id] = None if pm.isNull() else pm
        return self._full[snap.id]

    def scaled(self, snap: Snapshot, w: int, h: int, dpr: float) -> QPixmap | None:
        key = (snap.id, w, h, dpr)
        if key not in self._scaled:
            pm = self.full(snap)
            if pm is None:
                return None
            self._scaled[key] = crop_fill(pm, w, h, dpr)
        return self._scaled[key]

    def forget(self, sid: str):
        self._full.pop(sid, None)
        for k in [k for k in self._scaled if k[0] == sid]:
            del self._scaled[k]


def crop_fill(pm: QPixmap, w: int, h: int, dpr: float) -> QPixmap:
    tw, th = max(1, int(w * dpr)), max(1, int(h * dpr))
    s = pm.scaled(tw, th, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    s = s.copy((s.width() - tw) // 2, (s.height() - th) // 2, tw, th)
    s.setDevicePixelRatio(dpr)
    return s


class SnapshotDelegate(QStyledItemDelegate):
    HEIGHT = 92
    TW, TH = 112, 63

    def __init__(self, thumbs: ThumbCache, parent=None):
        super().__init__(parent)
        self.thumbs = thumbs

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.HEIGHT)

    def paint(self, p: QPainter, option, index):
        snap: Snapshot = index.data(SNAP_ROLE)
        if snap is None:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(option.rect).adjusted(10, 4, -10, -4)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

        card = QPainterPath()
        card.addRoundedRect(r, 10, 10)
        p.fillPath(card, QColor(C.card_sel if selected else C.card_hover if hover else C.card))
        if selected:
            p.setPen(QPen(QColor(229, 72, 77, 170), 1.2))
            p.drawPath(card)
            bar = QPainterPath()
            bar.addRoundedRect(QRectF(r.left() + 1, r.top() + 18, 3, r.height() - 36), 1.5, 1.5)
            p.fillPath(bar, QColor(C.accent))

        th = QRectF(r.left() + 12, r.top() + (r.height() - self.TH) / 2, self.TW, self.TH)
        clip = QPainterPath()
        clip.addRoundedRect(th, 7, 7)
        p.save()
        p.setClipPath(clip)
        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        pm = self.thumbs.scaled(snap, self.TW, self.TH, dpr)
        if pm:
            p.drawPixmap(th.topLeft(), pm)
        else:
            draw_placeholder(p, th, small=True)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 16), 1))
        p.drawPath(clip)

        tx = th.right() + 14
        tw = r.right() - 12 - tx

        f = QFont(option.font)
        f.setPointSizeF(10.5)
        f.setBold(True)
        fm = QFontMetrics(f)
        badge_w = 0
        if snap.auto:
            bf = QFont(option.font)
            bf.setPointSizeF(8)
            badge_w = QFontMetrics(bf).horizontalAdvance("自动") + 14
        name = fm.elidedText(snap.name, Qt.TextElideMode.ElideRight, int(tw - badge_w - (6 if badge_w else 0)))
        p.setFont(f)
        p.setPen(QColor(C.text))
        name_rect = QRectF(tx, r.top() + 13, tw, 22)
        p.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        if snap.auto:
            bx = tx + fm.horizontalAdvance(name) + 6
            br = QRectF(bx, name_rect.center().y() - 9, badge_w, 18)
            bp = QPainterPath()
            bp.addRoundedRect(br, 9, 9)
            p.fillPath(bp, QColor(245, 185, 74, 30))
            p.setPen(QColor(C.amber))
            p.setFont(bf)
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, "自动")

        f2 = QFont(option.font)
        f2.setPointSizeF(9)
        p.setFont(f2)
        p.setPen(QColor(C.muted))
        p.drawText(QRectF(tx, r.top() + 38, tw, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   friendly_time(snap.created_dt))
        p.setPen(QColor(C.dim))
        p.drawText(QRectF(tx, r.top() + 57, tw, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{human_size(snap.size)} · {snap.files} 个文件")
        p.restore()


class HeroImage(QWidget):
    """详情页顶部的封面大图（16:9，圆角，底部渐变 + 标题）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self.setMinimumHeight(200)
        self._pix: QPixmap | None = None
        self._title = ""
        self._sub = ""

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return max(200, min(int(w * 9 / 16), 430))

    def sizeHint(self):
        return QSize(640, 360)

    def set_content(self, pix: QPixmap | None, title: str, sub: str):
        self._pix, self._title, self._sub = pix, title, sub
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setClipPath(path)
        if self._pix:
            p.drawPixmap(0, 0, crop_fill(self._pix, self.width(), self.height(), self.devicePixelRatioF()))
        else:
            draw_placeholder(p, r)
        g = QLinearGradient(0, r.height() * 0.45, 0, r.height())
        g.setColorAt(0, QColor(8, 9, 12, 0))
        g.setColorAt(1, QColor(8, 9, 12, 225))
        p.fillRect(r, g)

        pad = 24
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 170))
        p.drawText(QRectF(pad, r.bottom() - pad - 18, r.width() - pad * 2, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._sub)
        f.setPointSizeF(20)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("white"))
        title = QFontMetrics(f).elidedText(self._title, Qt.TextElideMode.ElideRight, int(r.width() - pad * 2))
        p.drawText(QRectF(pad, r.bottom() - pad - 58, r.width() - pad * 2, 38),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        p.drawPath(path)


class BusyOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.hide()
        self._angle = 0
        self._text = ""
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def start(self, text: str):
        self._text = text
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self._timer.start()

    def set_text(self, text: str):
        self._text = text
        self.update()

    def stop(self):
        self._timer.stop()
        self.hide()

    def mousePressEvent(self, e):
        e.accept()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(5, 6, 9, 175))
        cw, ch = 340, 150
        card = QRectF((self.width() - cw) / 2, (self.height() - ch) / 2, cw, ch)
        path = QPainterPath()
        path.addRoundedRect(card, 14, 14)
        p.fillPath(path, QColor(C.card))
        p.setPen(QPen(QColor(C.border), 1))
        p.drawPath(path)
        sr = QRectF(card.center().x() - 18, card.top() + 28, 36, 36)
        p.setPen(QPen(QColor(255, 255, 255, 25), 3.5))
        p.drawEllipse(sr)
        pen = QPen(QColor(C.accent), 3.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(sr, -self._angle * 16, 100 * 16)
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(C.text))
        p.drawText(QRectF(card.left() + 16, sr.bottom() + 16, cw - 32, 40), Qt.AlignmentFlag.AlignCenter, self._text)


class Toast(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.hide()
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_done)
        self._hide_timer = QTimer(self, singleShot=True)
        self._hide_timer.timeout.connect(self._fade_out)

    def show_message(self, text: str, kind: str = "ok", ms: int = 2800):
        self.setProperty("kind", kind)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.raise_()
        self.show()
        self._anim.stop()
        self._anim.setDuration(160)
        self._anim.setStartValue(self._fx.opacity() if self.isVisible() else 0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._hide_timer.start(ms)

    def reposition(self):
        par = self.parentWidget()
        self.move((par.width() - self.width()) // 2, par.height() - self.height() - 28)

    def _fade_out(self):
        self._anim.stop()
        self._anim.setDuration(400)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_anim_done(self):
        if self._fx.opacity() <= 0.01:
            self.hide()
