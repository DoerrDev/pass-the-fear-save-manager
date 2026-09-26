"""对话框：保存、加载确认、设置、通用确认/输入。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout,
                               QKeySequenceEdit, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QRadioButton,
                               QSpinBox, QVBoxLayout, QWidget)

from . import core
from .config import DEFAULT_SAVE_DIR, Settings
from .core import Snapshot, human_size
from .theme import G
from .widgets import friendly_time
from .win32 import set_dark_titlebar


def button(text: str, kind: str = "", icon=None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if icon is not None:
        b.setIcon(icon)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def banner(text: str, kind: str = "info") -> QLabel:
    icon = {"warn": G.warning, "error": G.warning, "info": G.info}[kind]
    lbl = QLabel(f"<span style='font-family:\"Segoe Fluent Icons\",\"Segoe MDL2 Assets\"'>{icon}</span>&nbsp;&nbsp;{text}")
    lbl.setObjectName("Banner")
    lbl.setProperty("kind", kind)
    lbl.setWordWrap(True)
    return lbl


class Dialog(QDialog):
    def __init__(self, parent, title: str, width: int = 460):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(26, 22, 26, 22)
        self.body.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("DialogTitle")
        self.body.addWidget(heading)

    def showEvent(self, e):
        set_dark_titlebar(int(self.winId()), (13, 15, 19))
        super().showEvent(e)

    def add_buttons(self, ok_text: str, ok_kind: str = "primary", cancel_text: str = "取消") -> QPushButton:
        row = QHBoxLayout()
        row.setContentsMargins(0, 8, 0, 0)
        row.addStretch(1)
        if cancel_text:
            cancel = button(cancel_text, "ghost")
            cancel.clicked.connect(self.reject)
            row.addWidget(cancel)
        ok = button(ok_text, ok_kind)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        self.body.addLayout(row)
        return ok


def confirm(parent, title: str, text: str, ok_text: str = "确定", danger: bool = False) -> bool:
    d = Dialog(parent, title, 420)
    lbl = QLabel(text)
    lbl.setObjectName("DialogText")
    lbl.setWordWrap(True)
    d.body.addWidget(lbl)
    d.add_buttons(ok_text, "danger" if danger else "primary")
    return d.exec() == QDialog.DialogCode.Accepted


def alert(parent, title: str, text: str) -> None:
    d = Dialog(parent, title, 420)
    lbl = QLabel(text)
    lbl.setObjectName("DialogText")
    lbl.setWordWrap(True)
    d.body.addWidget(lbl)
    d.add_buttons("知道了", cancel_text="")
    d.exec()


def ask_text(parent, title: str, label: str, value: str) -> str | None:
    d = Dialog(parent, title, 420)
    lbl = QLabel(label)
    lbl.setObjectName("Muted")
    d.body.addWidget(lbl)
    edit = QLineEdit(value)
    edit.selectAll()
    d.body.addWidget(edit)
    ok = d.add_buttons("确定")
    edit.textChanged.connect(lambda t: ok.setEnabled(bool(t.strip())))
    if d.exec() == QDialog.DialogCode.Accepted:
        return edit.text().strip()
    return None


class SaveDialog(Dialog):
    PRESETS = ["第一章", "第二章开始", "Boss 前", "商店后", "回到大厅", "联机前"]

    def __init__(self, parent, default_name: str, running: bool, save_dir: Path, shot: bool):
        super().__init__(parent, "保存当前进度", 480)
        lbl = QLabel("存档名称")
        lbl.setObjectName("SectionLabel")
        self.body.addWidget(lbl)
        self.name = QLineEdit(default_name)
        self.name.selectAll()
        self.name.setMaxLength(60)
        self.body.addWidget(self.name)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        for text in self.PRESETS:
            c = button(text, "chip")
            c.setAutoDefault(False)
            c.clicked.connect(lambda _=False, t=text: (self.name.setText(t), self.name.setFocus()))
            chips.addWidget(c)
        chips.addStretch(1)
        self.body.addLayout(chips)

        lbl = QLabel("备注（可选）")
        lbl.setObjectName("SectionLabel")
        self.body.addWidget(lbl)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("队伍配置、谁当房主、当前进度……")
        self.note.setFixedHeight(80)
        self.body.addWidget(self.note)

        self.shot = QCheckBox("附带游戏截图作为存档封面")
        self.shot.setChecked(shot)
        self.shot.setEnabled(running)
        if not running:
            self.shot.setText("附带游戏截图作为存档封面（游戏未运行）")
        self.body.addWidget(self.shot)

        ok_enabled = save_dir.is_dir()
        if not ok_enabled:
            self.body.addWidget(banner(f"找不到游戏存档目录：{save_dir}<br>请先进一次游戏，或在设置中修改路径。", "error"))
        elif running:
            self.body.addWidget(banner("游戏正在运行。建议在检查点 / 结算 / 回到大厅后再保存，"
                                       "否则可能拿到还没写入的旧进度。", "warn"))
        ok = self.add_buttons("保存存档")
        ok.setIcon(parent.icon_white(G.save))
        ok.setEnabled(ok_enabled)
        self.name.textChanged.connect(lambda t: ok.setEnabled(ok_enabled and bool(t.strip())))

    def values(self) -> tuple[str, str, bool]:
        return self.name.text().strip(), self.note.toPlainText().strip(), self.shot.isChecked() and self.shot.isEnabled()


class LoadDialog(Dialog):
    def __init__(self, parent, snap: Snapshot, running: bool, settings: Settings):
        super().__init__(parent, "加载存档", 480)
        title = QLabel(f"加载「{snap.name}」？")
        title.setStyleSheet("font-size: 12pt; font-weight: 700;")
        title.setWordWrap(True)
        self.body.addWidget(title)
        meta = QLabel(f"保存于 {friendly_time(snap.created_dt)} · {human_size(snap.size)}")
        meta.setObjectName("Muted")
        self.body.addWidget(meta)

        steps = []
        if running:
            steps.append("关闭正在运行的游戏")
        steps += ["备份当前存档（可在列表中找回）", "用这个存档覆盖游戏存档", "重新启动游戏"]
        self._steps_label = QLabel()
        self._steps_label.setObjectName("DialogText")
        self._steps = steps
        self.body.addWidget(self._steps_label)

        self.backup = QCheckBox("加载前自动备份当前存档（推荐）")
        self.backup.setChecked(settings.auto_backup_before_load)
        self.launch = QCheckBox("加载完成后自动启动游戏")
        self.launch.setChecked(settings.launch_after_load)
        for cb in (self.backup, self.launch):
            cb.toggled.connect(self._render_steps)
            self.body.addWidget(cb)
        self._render_steps()

        self.body.addWidget(banner("联机时只有<b>房主</b>回档才会影响整队进度。"
                                   "若 Steam 弹出云存档冲突，请选择<b>本地</b>存档。", "info"))
        ok = self.add_buttons("加载并重启游戏" if running else "加载存档")
        ok.setIcon(parent.icon_white(G.play))
        self.launch.toggled.connect(lambda on: ok.setText(("加载并重启游戏" if running else "加载并启动游戏") if on else "仅加载存档"))
        self.launch.toggled.emit(self.launch.isChecked())

    def _render_steps(self):
        steps = [s for s in self._steps
                 if not (s.startswith("备份") and not self.backup.isChecked())
                 and not (s.startswith("重新启动") and not self.launch.isChecked())]
        self._steps_label.setText("<br>".join(f"<span style='color:#e5484d'>{i}</span>&nbsp;&nbsp;{s}"
                                              for i, s in enumerate(steps, 1)))

    def values(self) -> tuple[bool, bool]:
        return self.backup.isChecked(), self.launch.isChecked()


class SettingsDialog(Dialog):
    def __init__(self, parent, settings: Settings):
        super().__init__(parent, "设置", 620)
        self.s = settings
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        row = 0

        def label(text):
            l = QLabel(text)
            l.setObjectName("SectionLabel")
            return l

        def path_row(edit: QLineEdit, *buttons: QPushButton) -> QWidget:
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            h.addWidget(edit, 1)
            for b in buttons:
                b.setAutoDefault(False)
                h.addWidget(b)
            return w

        self.save_dir = QLineEdit(settings.save_dir)
        self.save_dir.setCursorPosition(0)
        b1, b2 = button("浏览…"), button("默认", "ghost")
        b1.clicked.connect(lambda: self._pick_dir(self.save_dir))
        b2.clicked.connect(lambda: self.save_dir.setText(str(DEFAULT_SAVE_DIR)))
        grid.addWidget(label("游戏存档目录"), row, 0)
        grid.addWidget(path_row(self.save_dir, b1, b2), row, 1)
        row += 1

        self.backup_root = QLineEdit(settings.backup_root)
        b3 = button("浏览…")
        b3.clicked.connect(lambda: self._pick_dir(self.backup_root))
        grid.addWidget(label("存档库位置"), row, 0)
        grid.addWidget(path_row(self.backup_root, b3), row, 1)
        row += 1

        self.m_steam = QRadioButton("通过 Steam 启动（推荐）")
        self.m_exe = QRadioButton("直接运行游戏程序")
        grp = QButtonGroup(self)
        grp.addButton(self.m_steam)
        grp.addButton(self.m_exe)
        (self.m_exe if settings.launch_method == "exe" else self.m_steam).setChecked(True)
        mh = QHBoxLayout()
        mh.addWidget(self.m_steam)
        mh.addSpacing(16)
        mh.addWidget(self.m_exe)
        mh.addStretch(1)
        grid.addWidget(label("启动方式"), row, 0)
        grid.addLayout(mh, row, 1)
        row += 1

        self.exe = QLineEdit(settings.game_exe)
        self.exe.setCursorPosition(0)
        self.exe.setPlaceholderText(f"{core.EXE_NAME} 的完整路径")
        b4, b5 = button("浏览…"), button("自动查找", "ghost")
        b4.clicked.connect(self._pick_exe)
        b5.clicked.connect(self._detect_exe)
        grid.addWidget(label("游戏程序"), row, 0)
        grid.addWidget(path_row(self.exe, b4, b5), row, 1)
        row += 1

        self.hk_on = QCheckBox("启用全局快速存档快捷键（游戏内也可用）")
        self.hk_on.setChecked(settings.hotkey_enabled)
        self.hk = QKeySequenceEdit(QKeySequence(settings.hotkey))
        self.hk.setMaximumSequenceLength(1)
        self.hk.setFixedWidth(160)
        hh = QHBoxLayout()
        hh.addWidget(self.hk)
        hh.addSpacing(10)
        hh.addWidget(self.hk_on)
        hh.addStretch(1)
        grid.addWidget(label("快捷键"), row, 0)
        grid.addLayout(hh, row, 1)
        row += 1

        def spin(value, lo, hi, suffix):
            sp = QSpinBox()
            sp.setRange(lo, hi)
            sp.setValue(value)
            sp.setSuffix(suffix)
            sp.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            sp.setFixedWidth(90)
            return sp

        self.close_timeout = spin(settings.close_timeout, 1, 60, " 秒")
        self.sync_wait = spin(settings.sync_wait, 0, 30, " 秒")
        self.keep = spin(settings.auto_backup_keep, 1, 100, " 个")
        grid.addWidget(label("高级"), row, 0)
        for text, w in (("关闭游戏时最多等待（超时强制结束）", self.close_timeout),
                        ("关闭游戏后等待 Steam 云同步", self.sync_wait),
                        ("自动备份最多保留", self.keep)):
            h = QHBoxLayout()
            h.addWidget(w)
            h.addSpacing(6)
            h.addWidget(QLabel(text, objectName="Muted"))
            h.addStretch(1)
            grid.addLayout(h, row, 1)
            row += 1
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)
        self.body.addWidget(banner("存档库就是一个普通文件夹，每个存档是其中一个子目录，可以直接复制或分享给队友。", "info"))
        self.add_buttons("保存设置")

    def _pick_dir(self, edit: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹", edit.text())
        if d:
            edit.setText(str(Path(d)))

    def _pick_exe(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择游戏程序", self.exe.text(), "程序 (*.exe)")
        if f:
            self.exe.setText(str(Path(f)))
            self.m_exe.setChecked(True)

    def _detect_exe(self):
        exe = core.find_game_exe()
        if exe:
            self.exe.setText(str(exe))
        else:
            alert(self, "未找到", "没有在 Steam 库中找到 Pass the Fear，请手动选择游戏程序。")

    def apply(self) -> Settings:
        s = self.s
        s.save_dir = self.save_dir.text().strip() or str(DEFAULT_SAVE_DIR)
        s.backup_root = self.backup_root.text().strip() or s.backup_root
        s.launch_method = "exe" if self.m_exe.isChecked() else "steam"
        s.game_exe = self.exe.text().strip()
        s.hotkey_enabled = self.hk_on.isChecked()
        seq = self.hk.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if seq:
            s.hotkey = seq
        s.close_timeout = self.close_timeout.value()
        s.sync_wait = self.sync_wait.value()
        s.auto_backup_keep = self.keep.value()
        return s
