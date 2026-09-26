"""存档快照的存储、还原，以及游戏进程控制。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
import winreg
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import psutil

from . import win32

APP_ID = 3561220
EXE_NAME = "PassTheFear.exe"
PROCESS_NAMES = {EXE_NAME.lower()}

Progress = Callable[[str], None]


class SaveError(Exception):
    pass


# ---------------------------------------------------------------- 文件工具

def _retry(fn, attempts: int = 6, delay: float = 0.4):
    for i in range(attempts):
        try:
            return fn()
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay)


def _copy_tree(src: Path, dst: Path, fresh_mtime: bool = False) -> None:
    # 还原时用新的修改时间，让 Steam 云把它识别为本地的新改动
    copy = shutil.copy if fresh_mtime else shutil.copy2
    for root, _dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for name in files:
            _retry(lambda: copy(Path(root) / name, dst / rel / name))


def _rm(path: Path) -> None:
    def onerror(func, p, _exc):
        os.chmod(p, 0o666)
        func(p)

    if path.is_dir() and not path.is_symlink():
        _retry(lambda: shutil.rmtree(path, onerror=onerror))
    elif path.exists():
        _retry(path.unlink)


def dir_stats(path: Path) -> tuple[int, int]:
    size = count = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                size += (Path(root) / name).stat().st_size
                count += 1
            except OSError:
                pass
    return size, count


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


# ---------------------------------------------------------------- 快照

@dataclass
class Snapshot:
    id: str
    name: str
    created: str
    note: str = ""
    size: int = 0
    files: int = 0
    auto: bool = False
    game_running: bool = False
    root: Path = field(default=None, repr=False, compare=False)

    @property
    def data_dir(self) -> Path:
        return self.root / SaveStore.DATA

    @property
    def thumb_path(self) -> Path:
        return self.root / SaveStore.THUMB

    @property
    def created_dt(self) -> datetime:
        return datetime.fromisoformat(self.created)

    def to_json(self) -> dict:
        d = asdict(self)
        d.pop("root")
        return d


class SaveStore:
    META = "meta.json"
    DATA = "GameData"
    THUMB = "thumb.jpg"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[Snapshot]:
        snaps = []
        for d in self.root.iterdir():
            meta = d / self.META
            if d.name.startswith(".") or not meta.is_file():
                continue
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                snaps.append(Snapshot(**{k: v for k, v in data.items() if k != "root"}, root=d))
            except (OSError, ValueError, TypeError):
                continue
        snaps.sort(key=lambda s: s.created, reverse=True)
        return snaps

    def get(self, sid: str) -> Snapshot | None:
        return next((s for s in self.list() if s.id == sid), None)

    def create(self, src: str | Path, name: str, note: str = "", auto: bool = False,
               thumb: bytes | None = None, game_running: bool = False) -> Snapshot:
        src = Path(src)
        if not src.is_dir():
            raise SaveError(f"找不到游戏存档目录：\n{src}")
        if not any(src.iterdir()):
            raise SaveError("游戏存档目录是空的，没有可以保存的内容。")
        now = datetime.now()
        sid = now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        tmp = self.root / f".tmp-{sid}"
        try:
            _copy_tree(src, tmp / self.DATA)
            size, count = dir_stats(tmp / self.DATA)
            snap = Snapshot(id=sid, name=name.strip() or "未命名存档", created=now.isoformat(timespec="seconds"),
                            note=note, size=size, files=count, auto=auto, game_running=game_running)
            if thumb:
                (tmp / self.THUMB).write_bytes(thumb)
            (tmp / self.META).write_text(json.dumps(snap.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.rename(self.root / sid)
        except Exception:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            raise
        snap.root = self.root / sid
        return snap

    def save_meta(self, snap: Snapshot) -> None:
        (snap.root / self.META).write_text(json.dumps(snap.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")

    def rename(self, snap: Snapshot, name: str) -> None:
        snap.name = name.strip() or snap.name
        self.save_meta(snap)

    def set_note(self, snap: Snapshot, note: str) -> None:
        snap.note = note
        self.save_meta(snap)

    def delete(self, snap: Snapshot) -> None:
        _rm(snap.root)

    def prune_auto(self, keep: int, exclude: set[str] = frozenset()) -> None:
        autos = [s for s in self.list() if s.auto and s.id not in exclude]
        for s in autos[max(keep, 0):]:
            self.delete(s)

    def restore(self, snap: Snapshot, dst: str | Path) -> None:
        src, dst = snap.data_dir, Path(dst)
        if not src.is_dir() or not any(src.iterdir()):
            raise SaveError("这个存档的数据已损坏或缺失，无法加载。")
        dst.mkdir(parents=True, exist_ok=True)
        for item in dst.iterdir():
            _rm(item)
        _copy_tree(src, dst, fresh_mtime=True)


# ---------------------------------------------------------------- 游戏进程

def game_processes() -> list[psutil.Process]:
    procs = []
    for p in psutil.process_iter(["name"]):
        if (p.info.get("name") or "").lower() in PROCESS_NAMES:
            procs.append(p)
    return procs


def is_game_running() -> bool:
    return bool(game_processes())


def main_game_window() -> int | None:
    pids = {p.pid for p in game_processes()}
    if not pids:
        return None
    wins = win32.windows_for_pids(pids)
    return max(wins, key=win32.window_area) if wins else None


def close_game(timeout: int = 8) -> bool:
    """先发送 WM_CLOSE 让游戏正常退出，超时后强制结束。返回是否关闭过游戏。"""
    procs = game_processes()
    if not procs:
        return False
    for hwnd in win32.windows_for_pids({p.pid for p in procs}):
        win32.user32.PostMessageW(hwnd, win32.WM_CLOSE, 0, 0)
    _gone, alive = psutil.wait_procs(procs, timeout=timeout)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(alive, timeout=5)
    if game_processes():
        raise SaveError("无法关闭游戏进程，请手动退出游戏后再试。")
    return True


def launch_game(method: str, exe: str = "") -> None:
    if method == "exe":
        path = Path(exe)
        if not path.is_file():
            raise SaveError(f"找不到游戏程序：\n{exe or '（未设置）'}")
        subprocess.Popen([str(path)], cwd=str(path.parent),
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        os.startfile(f"steam://rungameid/{APP_ID}")


def steam_path() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        return None


def find_game_exe() -> Path | None:
    sp = steam_path()
    if not sp:
        return None
    libs = [sp]
    try:
        vdf = (sp / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="ignore")
        libs += [Path(m.replace("\\\\", "\\")) for m in re.findall(r'"path"\s+"([^"]+)"', vdf)]
    except OSError:
        pass
    for lib in libs:
        manifest = lib / "steamapps" / f"appmanifest_{APP_ID}.acf"
        try:
            m = re.search(r'"installdir"\s+"([^"]+)"', manifest.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if m:
            exe = lib / "steamapps" / "common" / m.group(1) / EXE_NAME
            if exe.is_file():
                return exe
    return None
