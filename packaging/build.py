"""一键打包：生成图标 → PyInstaller 编译 → NSIS 生成安装包。

用法：python packaging/build.py
输出：dist/PassTheFearSaveManager/（绿色版目录）和 dist/PassTheFearSaveManager-Setup-<版本>.exe
"""
from __future__ import annotations

import io
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
APP_NAME = "PassTheFearSaveManager"

sys.path.insert(0, str(ROOT))
from savetool import __version__  # noqa: E402


def make_icon() -> Path:
    from PIL import Image
    from PySide6.QtCore import QBuffer, QIODevice, QSize
    from PySide6.QtWidgets import QApplication

    from savetool.theme import app_icon

    _app = QApplication.instance() or QApplication([])
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.ReadWrite)
    app_icon().pixmap(QSize(256, 256)).toImage().save(buf, "PNG")
    img = Image.open(io.BytesIO(bytes(buf.data())))
    out = BUILD / "app.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return out


def write_version_file() -> Path:
    nums = (__version__.split(".") + ["0"] * 4)[:4]
    tup = ", ".join(str(int(n)) for n in nums)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup})),
  kids=[
    StringFileInfo([StringTable('080404B0', [
      StringStruct('FileDescription', 'Pass the Fear 存档管理器'),
      StringStruct('ProductName', 'Pass the Fear 存档管理器'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('ProductVersion', '{__version__}'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('InternalName', '{APP_NAME}'),
    ])]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""
    out = BUILD / "version_info.txt"
    out.write_text(text, encoding="utf-8")
    return out


def pyinstaller(icon: Path, version_file: Path) -> Path:
    shutil.rmtree(DIST / APP_NAME, ignore_errors=True)
    cmd = [
        sys.executable, "-m", "PyInstaller", str(ROOT / "main.py"),
        "--name", APP_NAME,
        "--noconfirm", "--clean", "--windowed",
        "--icon", str(icon),
        "--version-file", str(version_file),
        "--add-data", f"{ROOT / 'savetool' / 'assets'};savetool/assets",
        "--hidden-import", "PySide6.QtSvg",  # 复选框的 SVG 图标需要
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
    ]
    for mod in ("tkinter", "numpy", "PIL", "matplotlib", "scipy", "pandas", "IPython"):
        cmd += ["--exclude-module", mod]
    subprocess.run(cmd, check=True, cwd=ROOT)
    app_dir = DIST / APP_NAME
    prune(app_dir / "_internal" / "PySide6")
    return app_dir


# 只用到 QtCore/QtGui/QtWidgets(+Svg)，下面这些是插件顺带拉进来的，删掉能省一半体积
PRUNE_FILES = [
    "opengl32sw.dll",  # 软件 OpenGL 渲染器，Widgets 界面用不到
    "Qt6Quick.dll", "Qt6Qml.dll", "Qt6QmlModels.dll", "Qt6QmlMeta.dll", "Qt6QmlWorkerScript.dll",
    "Qt6Pdf.dll", "Qt6Network.dll", "Qt6OpenGL.dll", "Qt6VirtualKeyboard.dll",
    "plugins/imageformats/qpdf.dll",
    "plugins/tls", "plugins/networkinformation", "plugins/platforminputcontexts",
]
KEEP_TRANSLATIONS = ("qtbase_zh_CN.qm", "qt_zh_CN.qm")


def prune(qt_dir: Path) -> None:
    for rel in PRUNE_FILES:
        p = qt_dir / rel
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    tr = qt_dir / "translations"
    if tr.is_dir():
        for f in tr.iterdir():
            if f.name not in KEEP_TRANSLATIONS:
                f.unlink()


def makensis(app_dir: Path, icon: Path) -> Path:
    exe = shutil.which("makensis")
    if not exe:
        sys.exit("找不到 makensis，请先安装 NSIS（例如：scoop install nsis 或 winget install NSIS.NSIS）")
    out = DIST / f"{APP_NAME}-Setup-{__version__}.exe"
    subprocess.run([
        exe, "-INPUTCHARSET", "UTF8",
        f"-DVERSION={__version__}",
        f"-DAPP_DIR={app_dir}",
        f"-DICON={icon}",
        f"-DOUTFILE={out}",
        str(PKG / "installer.nsi"),
    ], check=True)
    return out


def main():
    icon = make_icon()
    app_dir = pyinstaller(icon, write_version_file())
    setup = makensis(app_dir, icon)
    size = setup.stat().st_size / 1024 / 1024
    print(f"\n完成：\n  绿色版目录  {app_dir}\n  安装包      {setup}  ({size:.1f} MB)")


if __name__ == "__main__":
    main()
