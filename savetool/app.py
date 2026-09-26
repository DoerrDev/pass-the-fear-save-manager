"""主窗口。"""
from __future__ import annotations

import ctypes
import os
import sys
import time
import traceback
import winsound
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu, QPlainTextEdit, QPushButton,
                               QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget, QCheckBox, QDialog)

from . import __version__, capture, core
from .config import APP_DIR, Settings
from .core import SaveError, SaveStore, Snapshot, human_size
from .dialogs import LoadDialog, SaveDialog, SettingsDialog, alert, ask_text, banner, button, confirm
from .hotkey import GlobalHotkey
from .theme import C, G, STYLESHEET, app_icon, apply_palette, glyph_icon, icon_font
from .widgets import SNAP_ROLE, BusyOverlay, HeroImage, SnapshotDelegate, ThumbCache, Toast, friendly_time
from .win32 import set_dark_titlebar


class Worker(QThread):
    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.succeeded.emit(self.fn(self.progress.emit))
        except SaveError as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001 - 展示给用户
            self.failed.emit(f"{type(e).__name__}: {e}")


class Tile(QFrame):
    def __init__(self, label: str):
        super().__init__()
        self.setObjectName("Tile")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 11)
        v.setSpacing(2)
        l = QLabel(label)
        l.setObjectName("TileLabel")
        self.value = QLabel("—")
        self.value.setObjectName("TileValue")
        v.addWidget(l)
        v.addWidget(self.value)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        if not self.settings.game_exe:
            exe = core.find_game_exe()
            if exe:
                self.settings.game_exe = str(exe)
        self.store = SaveStore(self.settings.backup_root)
        self.thumbs = ThumbCache()
        self.current: Snapshot | None = None
        self._worker: Worker | None = None
        self._hotkey: GlobalHotkey | None = None
        self._running: bool | None = None

        self.setWindowTitle("Pass the Fear 存档管理器")
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(920, 600)
        self._build()
        self._build_tray()

        self._note_timer = QTimer(self, singleShot=True, interval=600)
        self._note_timer.timeout.connect(self._save_note)
        self._status_timer = QTimer(self, interval=1500)
        self._status_timer.timeout.connect(self._poll_game)
        self._status_timer.start()

        self._poll_game()
        self.reload()
        self._apply_hotkey()

    # ------------------------------------------------------------ 构建界面

    def icon_white(self, glyph: str):
        return glyph_icon(glyph, "#ffffff", 16)

    def _build(self):
        central = QWidget(objectName="Central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_side())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_empty())
        self.stack.addWidget(self._build_detail())
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self.overlay = BusyOverlay(central)
        self.toast = Toast(central)

        QShortcut(QKeySequence("Ctrl+S"), self, self.on_save)
        QShortcut(QKeySequence("F2"), self, self.on_rename)
        QShortcut(QKeySequence("Delete"), self.list, self.on_delete)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.search.setFocus())

    def _build_header(self) -> QWidget:
        header = QFrame(objectName="Header")
        header.setFixedHeight(64)
        h = QHBoxLayout(header)
        h.setContentsMargins(20, 0, 16, 0)
        h.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(QSize(34, 34)))
        h.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        t = QLabel("PASS THE FEAR", objectName="AppTitle")
        s = QLabel("存档管理器 · 保存 / 回档 / 一键重启", objectName="AppSub")
        titles.addStretch(1)
        titles.addWidget(t)
        titles.addWidget(s)
        titles.addStretch(1)
        h.addLayout(titles)
        h.addStretch(1)
        self.pill = QLabel(objectName="Pill")
        self.pill.setFixedHeight(26)
        h.addWidget(self.pill, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addSpacing(6)
        b_launch = button("启动游戏", "ghost", glyph_icon(G.game, "#b4bac8", 16))
        b_launch.clicked.connect(self.on_launch)
        self.b_launch = b_launch
        b_dir = button("游戏存档目录", "ghost", glyph_icon(G.folder, "#b4bac8", 16))
        b_dir.clicked.connect(lambda: self._open_dir(Path(self.settings.save_dir)))
        b_set = button("", "ghost", glyph_icon(G.settings, "#b4bac8", 18))
        b_set.setToolTip("设置")
        b_set.clicked.connect(self.on_settings)
        for b in (b_launch, b_dir, b_set):
            h.addWidget(b)
        return header

    def _build_side(self) -> QWidget:
        side = QFrame(objectName="Side")
        side.setFixedWidth(390)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 16, 0, 16)
        v.setSpacing(10)

        top = QHBoxLayout()
        top.setContentsMargins(20, 0, 20, 0)
        top.addWidget(QLabel("我的存档", objectName="SideTitle"))
        top.addStretch(1)
        self.count = QLabel(objectName="Count")
        top.addWidget(self.count)
        v.addLayout(top)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索存档名称或备注")
        self.search.addAction(glyph_icon(G.search, C.dim, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: self.reload())
        sw = QHBoxLayout()
        sw.setContentsMargins(20, 0, 20, 0)
        sw.addWidget(self.search)
        v.addLayout(sw)

        self.show_auto = QCheckBox("显示自动备份")
        self.show_auto.setChecked(True)
        self.show_auto.toggled.connect(lambda: self.reload())
        aw = QHBoxLayout()
        aw.setContentsMargins(22, 0, 20, 0)
        aw.addWidget(self.show_auto)
        aw.addStretch(1)
        v.addLayout(aw)

        self.list = QListWidget()
        self.list.setItemDelegate(SnapshotDelegate(self.thumbs, self.list))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.verticalScrollBar().setSingleStep(24)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.currentItemChanged.connect(self._on_current_changed)
        self.list.itemDoubleClicked.connect(lambda _it: self.on_load())
        v.addWidget(self.list, 1)

        self.b_save = button("  保存当前进度", "primary", self.icon_white(G.save))
        self.b_save.setProperty("kind", "primary")
        self.b_save.setMinimumHeight(48)
        self.b_save.setStyleSheet("font-size: 11pt; border-radius: 10px;")
        self.b_save.clicked.connect(self.on_save)
        bw = QVBoxLayout()
        bw.setContentsMargins(20, 4, 20, 0)
        bw.setSpacing(6)
        bw.addWidget(self.b_save)
        self.hint = QLabel(objectName="Hint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bw.addWidget(self.hint)
        v.addLayout(bw)
        return side

    def _build_empty(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addStretch(2)
        ic = QLabel(G.history)
        ic.setFont(icon_font(64))
        ic.setStyleSheet(f"color: {C.dim};")
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(ic)
        v.addSpacing(10)
        self.empty_title = QLabel("还没有存档", objectName="EmptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.empty_title)
        self.empty_sub = QLabel("进入游戏打到想保留的位置，点击左下角「保存当前进度」\n"
                                "或在游戏中按快捷键快速存档。", objectName="Muted")
        self.empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.empty_sub)
        v.addStretch(3)
        return w

    def _build_detail(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(16)
        self.hero = HeroImage()
        v.addWidget(self.hero)

        tiles = QGridLayout()
        tiles.setSpacing(10)
        self.t_time = Tile("保存时间")
        self.t_size = Tile("存档大小")
        self.t_files = Tile("文件数")
        self.t_state = Tile("保存时游戏状态")
        for i, t in enumerate((self.t_time, self.t_size, self.t_files, self.t_state)):
            tiles.addWidget(t, 0, i)
        v.addLayout(tiles)

        nl = QHBoxLayout()
        nl.addWidget(QLabel("备注", objectName="SectionLabel"))
        nl.addStretch(1)
        self.note_state = QLabel(objectName="Hint")
        nl.addWidget(self.note_state)
        v.addLayout(nl)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("写点什么：队伍配置、谁当房主、为什么存这个档……（自动保存）")
        self.note.setMinimumHeight(70)
        self.note.textChanged.connect(self._on_note_changed)
        v.addWidget(self.note, 1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.b_load = button("  加载存档并重启游戏", "primary", self.icon_white(G.play))
        self.b_load.setMinimumHeight(46)
        self.b_load.setMinimumWidth(240)
        self.b_load.setStyleSheet("font-size: 11pt; border-radius: 10px;")
        self.b_load.clicked.connect(self.on_load)
        b_ren = button("重命名", "", glyph_icon(G.rename, C.text, 16))
        b_ren.clicked.connect(self.on_rename)
        b_open = button("打开文件夹", "", glyph_icon(G.folder, C.text, 16))
        b_open.clicked.connect(lambda: self.current and self._open_dir(self.current.root))
        b_del = button("删除", "danger", glyph_icon(G.delete, "#ff7377", 16))
        b_del.clicked.connect(self.on_delete)
        for b in (b_ren, b_open, b_del):
            b.setMinimumHeight(46)
        actions.addWidget(self.b_load)
        actions.addStretch(1)
        actions.addWidget(b_ren)
        actions.addWidget(b_open)
        actions.addWidget(b_del)
        v.addLayout(actions)
        return w

    def _build_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Pass the Fear 存档管理器")
        menu = QMenu()
        menu.addAction("显示主窗口", self._show_window)
        menu.addAction("快速存档", self.on_quick_save)
        menu.addSeparator()
        menu.addAction("退出", QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._show_window() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    # ------------------------------------------------------------ 列表与详情

    def reload(self, select_id: str | None = None):
        keep = select_id or (self.current.id if self.current else None)
        try:
            snaps = self.store.list()
        except OSError as e:
            snaps = []
            self.toast.show_message(f"读取存档库失败：{e}", "error")
        q = self.search.text().strip().lower()
        shown = [s for s in snaps
                 if (self.show_auto.isChecked() or not s.auto)
                 and (not q or q in s.name.lower() or q in s.note.lower())]
        self.list.blockSignals(True)
        self.list.clear()
        target = None
        for s in shown:
            it = QListWidgetItem()
            it.setData(SNAP_ROLE, s)
            self.list.addItem(it)
            if s.id == keep:
                target = it
        self.list.blockSignals(False)
        manual = sum(1 for s in snaps if not s.auto)
        self.count.setText(f"{manual} 个存档" + (f" · {len(snaps) - manual} 个自动备份" if len(snaps) > manual else ""))
        if target is None and self.list.count():
            target = self.list.item(0)
        if target:
            self.list.setCurrentItem(target)
            self._show(target.data(SNAP_ROLE))
        else:
            self._show(None)
            if snaps:
                self.empty_title.setText("没有匹配的存档")
                self.empty_sub.setText("换个关键词试试。")
            else:
                self.empty_title.setText("还没有存档")
                self.empty_sub.setText("进入游戏打到想保留的位置，点击左下角「保存当前进度」\n"
                                       "或在游戏中按快捷键快速存档。")

    def _on_current_changed(self, cur: QListWidgetItem | None, _prev):
        self._flush_note()
        self._show(cur.data(SNAP_ROLE) if cur else None)

    def _show(self, snap: Snapshot | None):
        self.current = snap
        if snap is None:
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)
        sub = snap.created_dt.strftime("%Y年%m月%d日 %H:%M:%S") + ("  ·  自动备份" if snap.auto else "")
        self.hero.set_content(self.thumbs.full(snap), snap.name, sub)
        self.t_time.value.setText(friendly_time(snap.created_dt))
        self.t_size.value.setText(human_size(snap.size))
        self.t_files.value.setText(str(snap.files))
        self.t_state.value.setText("游戏运行中" if snap.game_running else "游戏已关闭")
        self.note.blockSignals(True)
        self.note.setPlainText(snap.note)
        self.note.blockSignals(False)
        self.note_state.setText("")

    def _on_note_changed(self):
        self.note_state.setText("正在编辑…")
        self._note_timer.start()

    def _save_note(self):
        if not self.current:
            return
        try:
            self.store.set_note(self.current, self.note.toPlainText())
            self.note_state.setText("已保存")
        except OSError as e:
            self.note_state.setText(f"保存失败：{e}")

    def _flush_note(self):
        if self._note_timer.isActive():
            self._note_timer.stop()
            self._save_note()

    def _context_menu(self, pos):
        it = self.list.itemAt(pos)
        if not it:
            return
        self.list.setCurrentItem(it)
        m = QMenu(self)
        m.addAction(glyph_icon(G.play, C.text, 16), "加载存档", self.on_load)
        m.addAction(glyph_icon(G.rename, C.text, 16), "重命名", self.on_rename)
        m.addAction(glyph_icon(G.folder, C.text, 16), "打开文件夹", lambda: self._open_dir(self.current.root))
        m.addSeparator()
        m.addAction(glyph_icon(G.delete, "#ff7377", 16), "删除", self.on_delete)
        m.exec(self.list.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------ 状态

    def _poll_game(self):
        running = core.is_game_running()
        if running == self._running:
            return
        self._running = running
        self.pill.setText("●  游戏运行中" if running else "○  游戏未运行")
        self.pill.setProperty("state", "on" if running else "off")
        self.pill.style().unpolish(self.pill)
        self.pill.style().polish(self.pill)
        self.b_launch.setEnabled(not running)
        self.b_load.setText("  加载存档并重启游戏" if running else "  加载存档并启动游戏")

    def _apply_hotkey(self):
        if self._hotkey:
            self._hotkey.stop()
            self._hotkey = None
        if self.settings.hotkey_enabled:
            self._hotkey = GlobalHotkey(self.settings.hotkey, self)
            self._hotkey.triggered.connect(self.on_quick_save)
            self._hotkey.failed.connect(lambda msg: self.toast.show_message(msg, "warn", 4500))
            self._hotkey.start()
            self.hint.setText(f"Ctrl+S 保存 · 游戏中按 {self.settings.hotkey} 快速存档")
        else:
            self.hint.setText("Ctrl+S 保存 · 双击存档可加载")

    # ------------------------------------------------------------ 后台任务

    def _run(self, text: str, fn, on_done, on_fail=None):
        if self._busy():
            self.toast.show_message("还有操作在进行中，请稍候", "warn")
            return
        self.overlay.start(text)
        w = Worker(fn, self)
        w.progress.connect(self.overlay.set_text)

        def done(result):
            self.overlay.stop()
            on_done(result)

        def fail(msg):
            self.overlay.stop()
            self.reload()
            (on_fail or (lambda m: alert(self, "操作失败", m)))(msg)

        w.succeeded.connect(done)
        w.failed.connect(fail)
        w.finished.connect(lambda: self._on_worker_finished(w))
        self._worker = w
        w.start()

    def _on_worker_finished(self, w: Worker):
        # 先断开引用再销毁，否则下次检查 isRunning() 会访问已删除的 C++ 对象
        if self._worker is w:
            self._worker = None
        w.deleteLater()

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    # ------------------------------------------------------------ 操作

    def on_save(self):
        if self._busy():
            return
        running = core.is_game_running()
        n = sum(1 for s in self.store.list() if not s.auto) + 1
        dlg = SaveDialog(self, f"存档 {n}", running, Path(self.settings.save_dir), self.settings.capture_screenshot)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, note, shot = dlg.values()
        if running:
            self.settings.capture_screenshot = shot
            self.settings.save()
        self._create(name, note, shot, running, notify_tray=False)

    def on_quick_save(self):
        if self._busy():
            return
        running = core.is_game_running()
        self._create(f"快速存档 {datetime.now():%H:%M:%S}", "", running, running, notify_tray=not self.isActiveWindow())

    def _create(self, name, note, shot, running, notify_tray):
        save_dir = self.settings.save_dir

        def task(progress):
            thumb = None
            if shot:
                progress("正在截取游戏画面…")
                try:
                    thumb = capture.grab_game_thumbnail()
                except Exception:  # noqa: BLE001 - 截图失败不影响存档
                    thumb = None
            progress("正在保存存档…")
            return self.store.create(save_dir, name, note, thumb=thumb, game_running=running)

        def done(snap: Snapshot):
            self.search.clear()
            self.reload(select_id=snap.id)
            self.toast.show_message(f"已保存「{snap.name}」")
            if notify_tray:
                winsound.MessageBeep(winsound.MB_OK)
                self.tray.showMessage("存档已保存", snap.name, app_icon(), 2500)

        def fail(msg):
            if notify_tray:
                winsound.MessageBeep(winsound.MB_ICONHAND)
                self.tray.showMessage("存档失败", msg, QSystemTrayIcon.MessageIcon.Warning, 4000)
            else:
                alert(self, "保存失败", msg)

        self._run("正在保存存档…", task, done, fail)

    def on_load(self):
        snap = self.current
        if not snap or self._busy():
            return
        self._flush_note()
        running = core.is_game_running()
        dlg = LoadDialog(self, snap, running, self.settings)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        backup, launch = dlg.values()
        self.settings.auto_backup_before_load = backup
        self.settings.launch_after_load = launch
        self.settings.save()
        s = self.settings

        def task(progress):
            if core.is_game_running():
                progress("正在关闭游戏…")
                core.close_game(s.close_timeout)
                if s.sync_wait:
                    progress("等待 Steam 完成云同步…")
                    time.sleep(s.sync_wait)
            save_dir = Path(s.save_dir)
            if backup and save_dir.is_dir() and any(save_dir.iterdir()):
                progress("正在备份当前存档…")
                self.store.create(save_dir, "加载前自动备份", f"加载「{snap.name}」之前自动创建", auto=True)
                self.store.prune_auto(s.auto_backup_keep, exclude={snap.id})
            progress(f"正在写入「{snap.name}」…")
            self.store.restore(snap, save_dir)
            if launch:
                progress("正在启动游戏…")
                core.launch_game(s.launch_method, s.game_exe)
                time.sleep(1.2)
            return launch

        def done(launched):
            self.reload(select_id=snap.id)
            self.toast.show_message(f"已加载「{snap.name}」" + ("，游戏正在启动" if launched else ""))

        self._run("正在准备…", task, done)

    def on_launch(self):
        try:
            core.launch_game(self.settings.launch_method, self.settings.game_exe)
            self.toast.show_message("正在启动游戏…")
        except SaveError as e:
            alert(self, "无法启动", str(e))

    def on_rename(self):
        snap = self.current
        if not snap or self._busy():
            return
        name = ask_text(self, "重命名存档", "新的名称", snap.name)
        if name and name != snap.name:
            self.store.rename(snap, name)
            self.reload(select_id=snap.id)

    def on_delete(self):
        snap = self.current
        if not snap or self._busy():
            return
        if not confirm(self, "删除存档", f"确定要删除「{snap.name}」吗？\n删除后无法恢复。", "删除", danger=True):
            return
        idx = self.list.currentRow()
        try:
            self.store.delete(snap)
        except OSError as e:
            alert(self, "删除失败", str(e))
            return
        self.thumbs.forget(snap.id)
        self.current = None
        self.reload()
        if self.list.count():
            self.list.setCurrentRow(min(idx, self.list.count() - 1))
        self.toast.show_message(f"已删除「{snap.name}」", "warn")

    def on_settings(self):
        dlg = SettingsDialog(self, self.settings)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        old_root = self.store.root
        self.settings = dlg.apply()
        self.settings.save()
        if Path(self.settings.backup_root) != old_root:
            try:
                self.store = SaveStore(self.settings.backup_root)
            except OSError as e:
                alert(self, "存档库不可用", str(e))
            self.current = None
        self._apply_hotkey()
        self.reload()
        self.toast.show_message("设置已保存")

    # ------------------------------------------------------------ 杂项

    def _open_dir(self, path: Path):
        if path and path.exists():
            os.startfile(str(path))
        else:
            self.toast.show_message(f"文件夹不存在：{path}", "error")

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def showEvent(self, e):
        set_dark_titlebar(int(self.winId()), (17, 20, 25))
        super().showEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.overlay.setGeometry(self.centralWidget().rect())
        if self.toast.isVisible():
            self.toast.reposition()

    def closeEvent(self, e):
        if self._busy():
            self.toast.show_message("正在处理存档，请等待完成后再关闭", "warn")
            e.ignore()
            return
        self._flush_note()
        if self._hotkey:
            self._hotkey.stop()
        self.tray.hide()
        super().closeEvent(e)


def run() -> int:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PassTheFear.SaveManager")
    except (AttributeError, OSError):
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("Pass the Fear 存档管理器")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    apply_palette(app)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())

    def excepthook(etype, value, tb):
        # pythonw 下没有控制台，未捕获的异常会被静默吞掉：写日志并提示
        text = "".join(traceback.format_exception(etype, value, tb))
        try:
            with open(APP_DIR / "error.log", "a", encoding="utf-8") as f:
                f.write(f"==== {datetime.now():%Y-%m-%d %H:%M:%S}\n{text}\n")
        except OSError:
            pass
        alert(QApplication.activeWindow(), "程序出错", f"{etype.__name__}: {value}\n\n详细信息已写入 error.log")

    sys.excepthook = excepthook

    lock = QLockFile(str(APP_DIR / ".savetool.lock"))
    if not lock.tryLock(100):
        alert(None, "已在运行", "存档管理器已经打开了，请在任务栏或系统托盘中找到它。")
        return 0

    win = MainWindow()
    win.show()
    return app.exec()
