"""Windows API 绑定（窗口枚举、截图、全局热键、深色标题栏）。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

HANDLE = ctypes.c_void_p
WM_CLOSE = 0x0010
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


def _sig(fn, argtypes, restype=wintypes.BOOL):
    fn.argtypes = argtypes
    fn.restype = restype


_sig(user32.EnumWindows, [EnumWindowsProc, wintypes.LPARAM])
_sig(user32.GetWindowThreadProcessId, [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD)
_sig(user32.IsWindowVisible, [wintypes.HWND])
_sig(user32.IsIconic, [wintypes.HWND])
_sig(user32.GetWindowTextLengthW, [wintypes.HWND], ctypes.c_int)
_sig(user32.GetClientRect, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)])
_sig(user32.GetWindowRect, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)])
_sig(user32.ClientToScreen, [wintypes.HWND, ctypes.POINTER(wintypes.POINT)])
_sig(user32.PostMessageW, [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM])
_sig(user32.GetForegroundWindow, [], wintypes.HWND)
_sig(user32.GetDC, [wintypes.HWND], HANDLE)
_sig(user32.ReleaseDC, [wintypes.HWND, HANDLE], ctypes.c_int)
_sig(user32.PrintWindow, [wintypes.HWND, HANDLE, wintypes.UINT])
_sig(user32.RegisterHotKey, [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT])
_sig(user32.UnregisterHotKey, [wintypes.HWND, ctypes.c_int])
_sig(user32.GetMessageW, [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT])
_sig(user32.PostThreadMessageW, [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM])
_sig(kernel32.GetCurrentThreadId, [], wintypes.DWORD)
_sig(gdi32.CreateCompatibleDC, [HANDLE], HANDLE)
_sig(gdi32.CreateCompatibleBitmap, [HANDLE, ctypes.c_int, ctypes.c_int], HANDLE)
_sig(gdi32.SelectObject, [HANDLE, HANDLE], HANDLE)
_sig(gdi32.BitBlt, [HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    HANDLE, ctypes.c_int, ctypes.c_int, wintypes.DWORD])
_sig(gdi32.DeleteObject, [HANDLE])
_sig(gdi32.DeleteDC, [HANDLE])
_sig(gdi32.GetDIBits, [HANDLE, HANDLE, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                       ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT], ctypes.c_int)
_sig(dwmapi.DwmSetWindowAttribute, [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD], ctypes.c_long)


def windows_for_pids(pids: set[int]) -> list[int]:
    """返回属于指定进程、可见且有标题的顶层窗口。"""
    found: list[int] = []

    @EnumWindowsProc
    def _cb(hwnd, _lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            found.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    return found


def window_area(hwnd: int) -> int:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return max(0, r.right - r.left) * max(0, r.bottom - r.top)


def _grab(hwnd: int, from_screen: bool) -> tuple[bytes, int, int] | None:
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    src_wnd = None if from_screen else hwnd
    hdc_src = user32.GetDC(src_wnd)
    hdc = gdi32.CreateCompatibleDC(hdc_src)
    bmp = gdi32.CreateCompatibleBitmap(hdc_src, w, h)
    old = gdi32.SelectObject(hdc, bmp)
    try:
        if from_screen:
            pt = wintypes.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(pt))
            ok = gdi32.BitBlt(hdc, 0, 0, w, h, hdc_src, pt.x, pt.y, 0x00CC0020 | 0x40000000)  # SRCCOPY | CAPTUREBLT
        else:
            ok = user32.PrintWindow(hwnd, hdc, 0x1 | 0x2)  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
        if not ok:
            return None
        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth, bmi.biHeight = w, -h  # 负高度 = 自上而下
        bmi.biPlanes, bmi.biBitCount = 1, 32
        buf = ctypes.create_string_buffer(w * h * 4)
        if gdi32.GetDIBits(hdc, bmp, 0, h, buf, ctypes.byref(bmi), 0) != h:
            return None
        return buf.raw, w, h
    finally:
        gdi32.SelectObject(hdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(hdc)
        user32.ReleaseDC(src_wnd, hdc_src)


def print_window(hwnd: int) -> tuple[bytes, int, int] | None:
    """用 PrintWindow(PW_RENDERFULLCONTENT) 抓取窗口客户区，返回 BGRA 数据。"""
    return _grab(hwnd, from_screen=False)


def screen_grab(hwnd: int) -> tuple[bytes, int, int] | None:
    """直接从屏幕上截取窗口客户区所在的区域（窗口需在最前面）。"""
    return _grab(hwnd, from_screen=True)


def set_dark_titlebar(hwnd: int, caption_rgb: tuple[int, int, int] | None = None) -> None:
    try:
        on = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), 4)  # DWMWA_USE_IMMERSIVE_DARK_MODE
        if caption_rgb:
            r, g, b = caption_rgb
            color = ctypes.c_uint(r | (g << 8) | (b << 16))
            dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), 4)  # DWMWA_CAPTION_COLOR (Win11)
    except OSError:
        pass
