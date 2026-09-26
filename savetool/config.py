from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent

SETTINGS_FILE = APP_DIR / "settings.json"
DEFAULT_SAVE_DIR = Path(os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\PlayMudStudio\Pass the fear\GameData"))


@dataclass
class Settings:
    save_dir: str = str(DEFAULT_SAVE_DIR)
    backup_root: str = str(APP_DIR / "backups")
    launch_method: str = "steam"  # steam | exe
    game_exe: str = ""
    hotkey_enabled: bool = True
    hotkey: str = "Ctrl+Alt+S"
    capture_screenshot: bool = True
    auto_backup_before_load: bool = True
    launch_after_load: bool = True
    auto_backup_keep: int = 10
    close_timeout: int = 8
    sync_wait: int = 3

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return s
        for f in fields(cls):
            if f.name in data and isinstance(data[f.name], type(getattr(s, f.name))):
                setattr(s, f.name, data[f.name])
        return s

    def save(self) -> None:
        SETTINGS_FILE.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
