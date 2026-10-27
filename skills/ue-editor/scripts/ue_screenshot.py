"""
UE 编辑器窗口截图。在 Agent 侧通过 Win32 PrintWindow 抓取，不进入编辑器进程。
依赖 pywin32、Pillow。
"""

import ctypes
import time

import win32gui
import win32process
import win32ui
from PIL import Image, ImageChops, ImageStat

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


def _grab(hwnd, crop):
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
    return (l, t), img


def _difference(a, b):
    """缩到 160 宽灰度后的平均像素差（0~255）；淡入/加载约 5 以上，静止画面的雾气、时钟约 0.2~0.4。"""
    size = (160, max(1, round(a.height * 160 / a.width)))
    return ImageStat.Stat(ImageChops.difference(a.convert('L').resize(size), b.convert('L').resize(size))).mean[0]


def capture(hwnd, out_path, crop=None, max_width=1600, stable=0.0):
    """抓取窗口并保存 PNG。crop 为原始像素下的 (x, y, w, h)；max_width<=0 时不缩放。
    stable>0 时每 0.2 秒重抓，相邻两帧差值低于 1 才落盘，最多等 stable 秒；超时仍保存最后一帧并标 stable=false。"""
    if win32gui.IsIconic(hwnd):
        raise RuntimeError('窗口已最小化，无法截图，请先还原窗口。')
    (l, t), img = _grab(hwnd, crop)
    extra = {}
    if stable > 0:
        begin = time.monotonic()
        diff = None
        while True:
            time.sleep(0.2)
            (l, t), current = _grab(hwnd, crop)
            diff = _difference(img, current) if current.size == img.size else 255.0
            img = current
            if diff < 1.0 or time.monotonic() - begin >= stable:
                break
        extra = {'stable': diff < 1.0, 'waited': round(time.monotonic() - begin, 2), 'last_diff': round(diff, 2)}
    origin_size = list(img.size)
    if max_width and max_width > 0 and img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
    img.save(out_path)
    x, y = crop[:2] if crop else (0, 0)
    return dict({'path': out_path, 'rect': [l + x, t + y, *origin_size],
                 'origin_size': origin_size, 'saved_size': list(img.size)}, **extra)
