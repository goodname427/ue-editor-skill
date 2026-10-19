"""
UE 编辑器窗口截图。在 Agent 侧通过 Win32 PrintWindow 抓取，不进入编辑器进程。
依赖 pywin32、Pillow。
"""

import ctypes

import win32gui
import win32process
import win32ui
from PIL import Image

# 取物理像素，避免高 DPI 下窗口尺寸被缩放
ctypes.windll.user32.SetProcessDPIAware()

_PW_RENDERFULLCONTENT = 2
_MAIN_TITLE_SUFFIX = ' - Unreal Editor'


def _enum_ue_windows():
    """按 Z 序（最上层在前）列出所有 UE 编辑器进程的可见顶层窗口。"""
    all_wins = []

    def _enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        # 下拉菜单、右键菜单、提示框等 Slate 弹出层是无标题的独立窗口，也要纳入
        title = win32gui.GetWindowText(hwnd)
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        if r - l < 20 or b - t < 20:
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        all_wins.append({'hwnd': hwnd, 'title': title, 'pid': pid, 'rect': [l, t, r - l, b - t], 'size': [r - l, b - t]})

    win32gui.EnumWindows(_enum, None)
    ue_pids = {w['pid'] for w in all_wins if w['title'].endswith(_MAIN_TITLE_SUFFIX)}
    return [w for w in all_wins if w['pid'] in ue_pids]


def list_windows():
    """列出所有 UE 编辑器进程的可见顶层窗口，主窗口在前。"""
    wins = _enum_ue_windows()
    wins.sort(key=lambda w: not w['title'].endswith(_MAIN_TITLE_SUFFIX))
    return wins


def window_at(x, y):
    """返回包含桌面坐标 (x, y) 的最上层 UE 窗口。"""
    for w in _enum_ue_windows():
        l, t, width, height = w['rect']
        if l <= x < l + width and t <= y < t + height:
            return w
    return None


def top_popup():
    """返回最上层的无标题 UE 窗口（下拉菜单、右键菜单等弹出层），没有则 None。"""
    for w in _enum_ue_windows():
        if not w['title']:
            return w
    return None


def find_window(title=None):
    """按标题子串（不区分大小写）查找 UE 窗口；未指定时返回主窗口。"""
    wins = list_windows()
    if not wins:
        return None
    if not title:
        return wins[0]
    key = title.lower()
    for w in wins:
        if key in w['title'].lower():
            return w
    return None


def capture(hwnd, out_path, crop=None, max_width=1600):
    """抓取窗口并保存 PNG。crop 为原始像素下的 (x, y, w, h)；max_width<=0 时不缩放。"""
    if win32gui.IsIconic(hwnd):
        raise RuntimeError('窗口已最小化，无法截图，请先还原窗口。')
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    width, height = r - l, b - t

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    mem_dc = src_dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    try:
        bmp.CreateCompatibleBitmap(src_dc, width, height)
        mem_dc.SelectObject(bmp)
        if not ctypes.windll.user32.PrintWindow(hwnd, mem_dc.GetSafeHdc(), _PW_RENDERFULLCONTENT):
            raise RuntimeError('PrintWindow 调用失败。')
        info = bmp.GetInfo()
        img = Image.frombuffer('RGB', (info['bmWidth'], info['bmHeight']), bmp.GetBitmapBits(True), 'raw', 'BGRX', 0, 1)
    finally:
        win32gui.DeleteObject(bmp.GetHandle())
        mem_dc.DeleteDC()
        src_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)

    if crop:
        x, y, w, h = crop
        img = img.crop((x, y, x + w, y + h))
    origin_size = list(img.size)
    if max_width and max_width > 0 and img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
    img.save(out_path)
    return {'path': out_path, 'origin_size': origin_size, 'saved_size': list(img.size)}
