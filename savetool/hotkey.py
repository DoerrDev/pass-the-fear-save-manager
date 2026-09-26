"""全局热键：游戏里也能一键快速存档。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QThread, Signal

from .win32 import WM_HOTKEY, WM_QUIT, kernel32, user32

_MODS = {"CTRL": 0x2, "CONTROL": 0x2, "ALT": 0x1, "SHIFT": 0x4, "WIN": 0x8, "META": 0x8}
_KEYS = {"HOME": 0x24, "END": 0x23, "INS": 0x2D, "INSERT": 0x2D, "PGUP": 0x21, "PAGEUP": 0x21,
         "PGDOWN": 0x22, "PAGEDOWN": 0x22, "PAUSE": 0x13, "SPACE": 0x20, "`": 0xC0, "-": 0xBD, "=": 0xBB}
MOD_NOREPEAT = 0x4000


def parse_hotkey(seq: str) -> tuple[int, int]:
    parts = [p for p in seq.replace(" ", "").upper().split("+") if p]
    if not parts:
        raise ValueError("快捷键为空")
    *mods, key = parts
    mask = 0
    for m in mods:
        if m not in _MODS:
            raise ValueError(f"不支持的修饰键：{m}")
        mask |= _MODS[m]
    if len(key) == 1 and key.isalnum():
        vk = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])
    elif key in _KEYS:
        vk = _KEYS[key]
    else:
        raise ValueError(f"不支持的按键：{key}")
    return mask, vk


class GlobalHotkey(QThread):
    triggered = Signal()
    failed = Signal(str)

    def __init__(self, seq: str, parent=None):
        super().__init__(parent)
        self.seq = seq
        self._tid = 0

    def run(self):
        try:
            mods, vk = parse_hotkey(self.seq)
        except ValueError as e:
            self.failed.emit(str(e))
            return
        if not user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk):
            self.failed.emit(f"快捷键 {self.seq} 注册失败，可能已被其他程序占用。")
            return
        self._tid = kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                self.triggered.emit()
        user32.UnregisterHotKey(None, 1)

    def stop(self):
        if self.isRunning() and self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        self.wait(1500)
