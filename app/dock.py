# -*- coding: utf-8 -*-
"""
Liquid Glass Dock —— Windows 11 仿 macOS / iOS 液态玻璃桌面图标栏
================================================================
运行环境：Windows 10/11 + 官方 Python 3.9 及以上 + PyQt5
特点：
  * 屏幕底部居中悬浮，真毛玻璃（自己抓屏模糊）+ 液态玻璃高光
  * macOS 风格鼠标放大（鱼眼）效果，点击有回弹动画
  * Dock 右键可管理应用、打开设置，支持快捷方式拖入和独立桌面收纳
  * 一键设置开机自启动（写入注册表 HKCU Run）
  * 配置文件：%APPDATA%\\LiquidGlassDock\\config.json
  * 日志文件：%APPDATA%\\LiquidGlassDock\\dock.log

调试：命令行运行  python dock.py --preview 预览.png  可以导出一张预览图
     命令行运行  python dock.py --reset          清空所有已固定的图标
"""

import ctypes
from collections import OrderedDict
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import tempfile
import time
import traceback
from ctypes import wintypes
from feature_config import DEFAULTS as FEATURE_DEFAULTS, normalize as normalize_features

# ----------------------------------------------------------------------------
# 基本常量
# ----------------------------------------------------------------------------
APP_NAME = "BigFishDockpro"         # 当前项目标识
COMPAT_NAME = "BigFishDock"          # 保留原配置、启动项和互斥键，兼容既有用户数据
APP_TITLE = "大肥鱼Dock"           # 显示给用户看的名字
from app_version import VERSION
LEGACY_APP_NAME = "LiquidGlassDock"  # 旧名字，用来迁移配置和清理旧自启动项

# 打包成 exe 之后（PyInstaller），__file__ 指向临时解包目录，不能用；
# 这时程序目录就是 exe 自己所在的目录。
IS_FROZEN = bool(getattr(sys, "frozen", False))
if IS_FROZEN:
    SCRIPT_PATH = os.path.abspath(sys.executable)
    APP_DIR = os.path.dirname(SCRIPT_PATH)
else:
    SCRIPT_PATH = str(Path(__file__).resolve().parent.parent/'dock.py')
    APP_DIR = os.path.dirname(SCRIPT_PATH)
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), COMPAT_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
LOG_PATH = os.path.join(CONFIG_DIR, "dock.log")
LEGACY_CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), LEGACY_APP_NAME)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

DEFAULT_CONFIG = {
    "items": [],          # [{"path": "...", "name": "..."}]
    "icon_size": 52,      # 图标基准尺寸（像素）
    "magnify": True,      # 鼠标放大效果
    "glass": True,        # 毛玻璃（背景模糊）效果
    "running_dots": True, # 运行中的程序显示小圆点
    "show_name": True,    # 鼠标悬停时在图标上方显示程序名称
    "transparency": 40,   # 玻璃通透度 0~100（越大越透）
    "theme": "auto",      # 颜色模式：auto=跟随系统 / light=浅色 / dark=深色
    "layer": "bottom",    # 窗口层级：bottom=置底（不挡窗口）/ top=置顶
    "blur_mode": "smart", # 背景抓取频率：smart/fast/normal/slow/off
    "blur_px": 6,         # 毛玻璃模糊程度（缩小的倍数，越大越糊）
    "bump_level": "mid",  # 拉伸鼓包程度：low/mid/high
    "lang": "zh",         # 界面语言：zh=中文 / en=English
    "reorder": False,     # 允许拖动图标排序（默认关闭，防止误拖）
    "sep_split": True,    # 分隔符隔断模式：夹在两图标之间的分隔符会切开玻璃背景
    "position": "bottom", # 位置：bottom=底部 / top=顶部 / custom=自定义
    "custom_bottom": 200, # 自定义位置时，距屏幕底部多少像素
    "autostart": False,   # 开机自启动
    "bottom_margin": 6,   # 距离任务栏上方的高度
}

DEFAULT_CONFIG.update(FEATURE_DEFAULTS)
ICON_SIZES = [("小", 42), ("中", 52), ("大", 62), ("特大", 74)]

# 玻璃通透度（数值越大越透，越能看见背后的模糊画面）
TRANSPARENCIES = [("默认", 40), ("通透", 60), ("很通透", 80)]

# 语言
LANGS = [("简体中文", "zh"), ("English", "en")]

# 颜色模式
THEMES = [("跟随系统", "auto"), ("浅色", "light"), ("深色", "dark")]

# 窗口层级
LAYERS = [("置底（不挡任何窗口，推荐）", "bottom"), ("置顶（始终看得见）", "top")]

# 窗口位置
POSITIONS = [("屏幕底部（默认）", "bottom"), ("屏幕顶部", "top"), ("自定义…", "custom")]

# 背景抓取频率（毫秒）。静态壁纸不需要频繁抓，智能模式平时几乎不干活。
BLUR_MODES = [("智能（省电，推荐）", "smart"), ("实时（每秒一次）", "fast"),
              ("普通（每 3 秒）", "normal"), ("省电（每 10 秒）", "slow"),
              ("停止抓取（静态壁纸，只抓一次）", "off")]
BLUR_INTERVAL = {"smart": 8000, "fast": 1000, "normal": 3000, "slow": 10000, "off": 0}

# 毛玻璃模糊程度（数值 = 缩小的倍数，越大越模糊）
BLUR_LEVELS = [("低（更清晰）", 3), ("中（默认）", 6), ("高（更朦胧）", 11)]

# 拉伸鼓包程度：key, 显示名, 幅度系数（1.0 是默认，约等于图标高度的 24%）
BUMP_LEVELS = [("low", "低（轻微）", 0.62),
               ("mid", "中（默认）", 1.00),
               ("high", "高（明显）", 1.45)]
BUMP_SCALE = {k: v for k, _, v in BUMP_LEVELS}

# ----------------------------------------------------------------------------
# 语言：托盘里可以中英切换。英文直接查表，查不到就原样返回中文。
# ----------------------------------------------------------------------------
LANG = {"cur": "zh"}

EN = {
    # 主菜单
    "显示 / 隐藏 Dock": "Show / Hide Dock",
    "添加图标…": "Add Icon…",
    "添加分隔符": "Add Separator",
    "分隔符隔断背景": "Split Background at Separators",
    "图标顺序可拖动": "Draggable Icon Order",
    "移除图标": "Remove Icon",
    "—— 分隔符 ——": "—— Separator ——",
    "（还没有固定任何图标）": "(nothing pinned yet)",
    # 图标大小
    "图标大小": "Icon Size",
    "小": "Small",
    "中": "Medium",
    "大": "Large",
    "特大": "Extra Large",
    "%s（%d 像素）": "%s (%d px)",
    "自定义…（当前 %d 像素）": "Custom… (%d px now)",
    # 颜色模式
    "颜色模式": "Color Mode",
    "跟随系统": "Follow System",
    "浅色": "Light",
    "深色": "Dark",
    "光感": "Glossy",
    # 层级
    "窗口层级": "Window Layer",
    "置底（不挡任何窗口，推荐）": "Bottom (recommended)",
    "置顶（始终看得见）": "Top (always visible)",
    # 位置
    "窗口位置": "Window Position",
    "屏幕底部（默认）": "Screen Bottom (default)",
    "屏幕顶部": "Screen Top",
    "自定义…": "Custom…",
    "调整自定义高度…（当前距底部 %d 像素）": "Custom Height… (%d px from bottom)",
    # 背景抓取
    "背景抓取频率": "Background Capture",
    "智能（省电，推荐）": "Smart (power saving)",
    "实时（每秒一次）": "Realtime (every second)",
    "普通（每 3 秒）": "Normal (every 3 s)",
    "省电（每 10 秒）": "Low power (every 10 s)",
    "停止抓取（静态壁纸，只抓一次）": "Never (static wallpaper)",
    "立即刷新一次背景": "Refresh Background Now",
    # 放大与鼓包
    "放大与拉伸": "Magnify & Stretch",
    "启用鼠标放大与拉伸": "Enable Magnify & Stretch",
    "拉伸鼓包程度": "Stretch Bulge",
    "拉伸鼓包程度：%s": "Stretch Bulge: %s",
    "低（轻微）": "Low (subtle)",
    "中（默认）": "Medium (default)",
    "高（明显）": "High (obvious)",
    # 毛玻璃
    "毛玻璃（背景模糊）": "Frosted Glass",
    "启用毛玻璃效果": "Enable Frosted Glass",
    "模糊程度：%s": "Blur: %s",
    "低（更清晰）": "Low (clearer)",
    "高（更朦胧）": "High (hazier)",
    "模糊程度：自定义…（当前 %d）": "Blur: Custom… (%d now)",
    # 其它开关
    "运行中的程序显示小圆点": "Show Running Dots",
    "悬停时显示程序名称": "Show App Name on Hover",
    "玻璃通透度": "Glass Transparency",
    "默认": "Default",
    "通透": "Clear",
    "很通透": "Very Clear",
    "%s（%d%%）": "%s (%d%%)",
    "开机自动启动": "Start with Windows",
    # 语言本身
    "语言 / Language": "语言 / Language",
    "简体中文": "简体中文",
    "English": "English",
    # 底部
    "使用说明": "User Guide",
    "打开配置文件夹": "Open Config Folder",
    "退出": "Quit",
    # 对话框与提示
    "选择要固定到 Dock 的程序（可多选）": "Choose programs to pin (multi-select)",
    "程序与快捷方式 (*.exe *.lnk *.bat *.cmd *.url *.msc *.ps1);;所有文件 (*.*)":
        "Programs & shortcuts (*.exe *.lnk *.bat *.cmd *.url *.msc *.ps1);;All files (*.*)",
    "已添加 %d 个图标到 Dock": "Added %d icon(s) to the dock",
    "毛玻璃模糊强度：\n（3 ~ 30，数字越大越模糊、越朦胧）":
        "Blur strength:\n(3 ~ 30, bigger = hazier)",
    "玻璃条距离屏幕底部多少像素？\n（Dock 始终水平居中，数字越大越往上）":
        "How many pixels from the bottom of the screen?\n(the dock stays horizontally centered)",
    "请输入图标像素大小：\n（建议 32 ~ 160，数字越大图标越大）":
        "Icon size in pixels:\n(32 ~ 160 recommended)",
    "已开启开机自启动": "Autostart enabled",
    "已取消开机自启动": "Autostart disabled",
    "设置失败，请查看日志：\n": "Failed, please check the log:\n",
    "请在托盘菜单里操作：添加图标 / 移除图标。": "Use the tray menu: Add Icon / Remove Icon.",
    "请在右下角托盘图标上右键 → 添加图标": "Right-click the tray icon → Add Icon",
    "Dock 已经在运行了（请看右下角托盘）。": "The dock is already running (see the tray).",
}


def T(s):
    """把界面文字翻成当前语言。"""
    if LANG["cur"] == "en":
        return EN.get(s, s)
    return s


def set_lang(v):
    LANG["cur"] = "en" if str(v) == "en" else "zh"

# SetWindowPos 用的常量
HWND_TOPMOST = -1
HWND_BOTTOM = 1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010


# ----------------------------------------------------------------------------
# 日志
# ----------------------------------------------------------------------------
def log(msg):
    try:
        if not os.path.isdir(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _excepthook(etype, value, tb):
    log("未捕获异常:\n" + "".join(traceback.format_exception(etype, value, tb)))


sys.excepthook = _excepthook


# ----------------------------------------------------------------------------
# 配置读写
# ----------------------------------------------------------------------------
def migrate_legacy():
    """从旧名字（LiquidGlassDock）迁移配置，并清掉旧的自启动项。

    这样改名之后用户原来的图标列表和设置都不会丢，也不会开机启动两次。
    """
    try:
        if (not os.path.exists(CONFIG_PATH)) and os.path.isdir(LEGACY_CONFIG_DIR):
            old = os.path.join(LEGACY_CONFIG_DIR, "config.json")
            if os.path.exists(old):
                if not os.path.isdir(CONFIG_DIR):
                    os.makedirs(CONFIG_DIR, exist_ok=True)
                shutil.copy2(old, CONFIG_PATH)
                log("已从旧目录迁移配置: " + old)
    except Exception:
        log("迁移配置失败: " + traceback.format_exc())
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                             winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
        try:
            winreg.DeleteValue(key, LEGACY_APP_NAME)
            log("已清理旧的自启动项")
        except FileNotFoundError:
            pass
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in DEFAULT_CONFIG:
                if k in data:
                    cfg[k] = data[k]
    except Exception:
        pass
    if not isinstance(cfg.get("items"), list):
        cfg["items"] = []
    if str(cfg.get("theme")) == "fog":
        cfg["theme"] = "gloss"        # 旧的"雾透模式"改名成"光感"
    cfg = normalize_features(cfg)
    clean = []
    for it in cfg["items"]:
        if not isinstance(it, dict):
            continue
        if it.get("sep"):
            clean.append({"sep": True})
        elif it.get("path"):
            clean.append({"path": it["path"],
                          "name": it.get("name") or os.path.splitext(os.path.basename(it["path"]))[0],
                          "group": str(it.get('group') or '未分类')[:40],
                          **({'icon': it['icon']} if isinstance(it.get('icon'), str) and it['icon'].strip() else {})})
    cfg["items"] = clean
    return cfg


def save_config(cfg):
    temporary=None
    try:
        os.makedirs(CONFIG_DIR,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=CONFIG_DIR,prefix='config.',suffix='.tmp',delete=False) as stream:
            temporary=stream.name;json.dump(cfg,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,CONFIG_PATH);temporary=None;return True
    except Exception:
        log('保存配置失败: '+traceback.format_exc());return False
    finally:
        if temporary:
            try:os.unlink(temporary)
            except OSError:pass


# ----------------------------------------------------------------------------
# Windows 系统相关的小工具（全部用 ctypes，不需要额外库）
# ----------------------------------------------------------------------------
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
comctl32 = ctypes.windll.comctl32

# --- 屏幕捕获排除（抓背景时把自己藏起来） --------------------------------
WDA_NONE = 0x0
WDA_EXCLUDEFROMCAPTURE = 0x11


# --- 图标提取（尽量拿高分辨率图标） --------------------------------------
class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


# IID_IImageList
_IID_IIMAGELIST = _GUID(0x46EB5926, 0x582E, 0x4017,
                        (ctypes.c_ubyte * 8)(0x9F, 0xDF, 0xE8, 0x99, 0x8D, 0xAA, 0x09, 0x50))

try:
    # SHGetImageList 在 shell32 里只有序号 727，没有名字导出，只能按序号取：
    # 注意写法是 (序号, 库)，不是把序号当第二个参数传
    _SHGetImageList = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_int, ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p))((727, shell32))
    _SHGetImageList.restype = ctypes.c_long
    _SHGetImageList.argtypes = [ctypes.c_int, ctypes.POINTER(_GUID),
                                ctypes.POINTER(ctypes.c_void_p)]
except Exception:
    _SHGetImageList = None
    log("SHGetImageList 绑定失败: " + traceback.format_exc())


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [("hIcon", wintypes.HICON),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260),
                ("szTypeName", wintypes.WCHAR * 80)]


def extract_shell_hicon(path, size=256):
    """用 Windows 外壳的"超大图标"列表取图标。

    文件夹、URL 快捷方式、商店应用这些没法用 PrivateExtractIconsW 抠图标，
    只能问外壳要。QFileIconProvider 只给 32/40 像素，放大会糊，
    这里直接取 256 像素那一档（取不到再退 48 / 32）。
    """
    if _SHGetImageList is None:
        return None
    try:
        SHGFI_SYSICONINDEX = 0x000004000
        info = SHFILEINFOW()
        pidl = ctypes.c_void_p()
        if path.lower().startswith('shell:'):
            shell32.SHParseDisplayName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD, ctypes.c_void_p]
            if shell32.SHParseDisplayName(path, None, ctypes.byref(pidl), 0, None) != 0: return None
        try:
            r = shell32.SHGetFileInfoW(pidl if pidl else ctypes.c_wchar_p(path), 0, ctypes.byref(info),
                                       ctypes.sizeof(info), SHGFI_SYSICONINDEX | (8 if pidl else 0))
        finally:
            if pidl:
                ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
                ctypes.windll.ole32.CoTaskMemFree(pidl)
        if not r:
            return None
        comctl32.ImageList_GetIcon.restype = wintypes.HICON
        comctl32.ImageList_GetIcon.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.UINT]
        # SHIL_JUMBO=4(256px) → SHIL_EXTRALARGE=2(48px) → SHIL_LARGE=0(32px)
        for shil in (4, 2, 0):
            himl = ctypes.c_void_p()
            if _SHGetImageList(shil, ctypes.byref(_IID_IIMAGELIST), ctypes.byref(himl)) != 0:
                continue
            if not himl:
                continue
            hicon = comctl32.ImageList_GetIcon(himl, int(info.iIcon), 0x1)
            if hicon:
                return int(hicon)
    except Exception:
        log("extract_shell_hicon 失败 %s: %s" % (path, traceback.format_exc()))
    return None


def extract_hicon(path, size=256):
    """用 PrivateExtractIconsW 从 exe/dll/ico 里取出指定尺寸的 HICON。"""
    try:
        fn = user32.PrivateExtractIconsW
    except AttributeError:
        return None
    try:
        fn.restype = wintypes.UINT
        fn.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                       ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.UINT),
                       wintypes.UINT, wintypes.UINT]
        hicon = wintypes.HICON(0)
        n = fn(path, 0, size, size, ctypes.byref(hicon), None, 1, 0)
        if n and hicon.value:
            return hicon.value
    except Exception:
        log("extract_hicon 失败 %s: %s" % (path, traceback.format_exc()))
    return None


def hicon_to_qimage(hicon):
    """HICON -> QImage（带透明通道）。"""
    from PyQt5.QtGui import QImage
    from PyQt5.QtCore import Qt
    info = ICONINFO()
    if not user32.GetIconInfo(wintypes.HICON(int(hicon)), ctypes.byref(info)):
        return None
    hdc = None
    memdc = None
    hdib = None
    try:
        if not info.hbmColor:
            return None
        bm = BITMAP()
        if not gdi32.GetObjectW(wintypes.HGDIOBJ(int(info.hbmColor)), ctypes.sizeof(BITMAP), ctypes.byref(bm)):
            return None
        w, h = int(bm.bmWidth), int(bm.bmHeight)
        if w <= 0 or h <= 0:
            return None
        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h          # 负数 = 从上到下的行序
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0      # BI_RGB
        hdc = user32.GetDC(None)
        bits = ctypes.c_void_p()
        hdib = gdi32.CreateDIBSection(wintypes.HDC(hdc), ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        if not hdib:
            return None
        memdc = gdi32.CreateCompatibleDC(wintypes.HDC(hdc))
        old = gdi32.SelectObject(wintypes.HDC(memdc), wintypes.HGDIOBJ(hdib))
        user32.DrawIconEx(wintypes.HDC(memdc), 0, 0, wintypes.HICON(int(hicon)), w, h, 0, None, 3)  # DI_NORMAL
        buf = ctypes.string_at(bits, w * h * 4)
        img = QImage(buf, w, h, w * 4, QImage.Format_ARGB32_Premultiplied).copy()
        gdi32.SelectObject(wintypes.HDC(memdc), old)
        return img.convertToFormat(QImage.Format_ARGB32)
    except Exception:
        log("hicon_to_qimage 失败: " + traceback.format_exc())
        return None
    finally:
        try:
            if hdib:
                gdi32.DeleteObject(wintypes.HGDIOBJ(hdib))
            if memdc:
                gdi32.DeleteDC(wintypes.HDC(memdc))
            if hdc:
                user32.ReleaseDC(None, wintypes.HDC(hdc))
            if info.hbmColor:
                gdi32.DeleteObject(wintypes.HGDIOBJ(info.hbmColor))
            if info.hbmMask:
                gdi32.DeleteObject(wintypes.HGDIOBJ(info.hbmMask))
            user32.DestroyIcon(wintypes.HICON(int(hicon)))
        except Exception:
            pass


def resolve_lnk_target(path):
    from shortcut_targets import lnk_target
    return lnk_target(path) if path.lower().endswith('.lnk') else None


# --- 正在运行的进程 ------------------------------------------------------
class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260)]


def get_running_exe_names():
    """返回当前正在运行的进程的可执行文件名集合（小写）。

    用 CreateToolhelp32Snapshot 一次拿全，比逐个 OpenProcess 快十倍以上
    （后者要 6ms 左右，每几秒跑一次会造成动画微卡顿）。
    """
    names = set()
    try:
        TH32CS_SNAPPROCESS = 0x00000002
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snap or int(snap) == -1:
            return names
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            ok = kernel32.Process32FirstW(wintypes.HANDLE(snap), ctypes.byref(entry))
            while ok:
                name = entry.szExeFile
                if name:
                    names.add(name.lower())
                ok = kernel32.Process32NextW(wintypes.HANDLE(snap), ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(wintypes.HANDLE(snap))
    except Exception:
        log("get_running_exe_names 失败: " + traceback.format_exc())
    return names


# --- 开机自启动 ----------------------------------------------------------
def pythonw_path():
    """返回 pythonw.exe 的绝对路径（用它启动才不会弹出黑色控制台窗口）。"""
    exe = sys.executable or ""
    d = os.path.dirname(exe)
    cand = os.path.join(d, "pythonw.exe")
    if os.path.exists(cand):
        return cand
    return exe


def autostart_command():
    """开机自启动要执行的命令行。打包成 exe 后直接就是 exe 自己。"""
    if IS_FROZEN:
        return '"%s" --autostart' % SCRIPT_PATH
    return '"%s" "%s" --autostart' % (pythonw_path(), SCRIPT_PATH)


def set_autostart(enable):
    import winreg
    try:
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
    except Exception:
        return False
    try:
        if enable:
            cmd = autostart_command()
            winreg.SetValueEx(key, COMPAT_NAME, 0, winreg.REG_SZ, cmd)
            log("已设置开机自启动: " + cmd)
        else:
            try:
                winreg.DeleteValue(key, COMPAT_NAME)
                log("已取消开机自启动")
            except FileNotFoundError:
                pass
        return True
    except Exception:
        log("设置开机自启动失败: " + traceback.format_exc())
        return False
    finally:
        winreg.CloseKey(key)


def get_autostart():
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE)
        try:
            val, _ = winreg.QueryValueEx(key, COMPAT_NAME)
            return bool(val)
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def system_is_light():
    """读注册表判断 Windows 当前是不是浅色模式（读不到就当作深色）。"""
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                             0, winreg.KEY_QUERY_VALUE)
    except Exception:
        return False
    try:
        for name in ("SystemUsesLightTheme", "AppsUseLightTheme"):
            try:
                v, _ = winreg.QueryValueEx(key, name)
                return bool(int(v))
            except FileNotFoundError:
                continue
        return False
    except Exception:
        return False
    finally:
        winreg.CloseKey(key)


def start_menu_dirs():
    out = []
    for p in (os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
              os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs")):
        if p and os.path.isdir(p):
            out.append(p)
    return out


# ----------------------------------------------------------------------------
# PyQt5 部分
# ----------------------------------------------------------------------------
from dpi_support import prepare as prepare_dpi
prepare_dpi()

from PyQt5.QtCore import (Qt, QTimer, QPoint, QPointF, QRectF, QSize, QFileInfo,
                          QSharedMemory, QEvent, pyqtSignal)
from PyQt5.QtGui import (QColor, QIcon, QImage, QPainter, QPainterPath, QPixmap,
                         QLinearGradient, QRadialGradient, QPen, QBrush, QFont,
                         QFontMetrics, QGuiApplication, QCursor)
from PyQt5.QtWidgets import (QApplication, QWidget, QSystemTrayIcon, QMenu,
                             QAction, QActionGroup, QFileDialog, QMessageBox,
                             QFileIconProvider, QToolTip, QInputDialog)


class IconProvider(object):
    """负责把文件路径变成好看的图标（会缓存）。"""

    def __init__(self):
        self.provider = QFileIconProvider()
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.max_cache_bytes = 6*1024*1024
        self.max_cache_entries = 128

    def get(self, path, px, custom=False, shell_state=False, hide_shortcut=False):
        state=None
        if shell_state:
            import time
            try:
                stat=os.stat(path,follow_symlinks=False)
                state=(stat.st_mtime_ns,stat.st_ctime_ns,getattr(stat,'st_file_attributes',0),int(time.monotonic()//15))
            except OSError:state=('unavailable',int(time.monotonic()//15))
        key = (path.lower(), int(px), custom, state, bool(hide_shortcut))
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        pm = None
        if shell_state:
            try:
                from card_file_ui import extract_card_hicon
                api=sys.modules[__name__]
                hicon=extract_card_hicon(api,path,px,hide_shortcut=hide_shortcut)
                if hicon:
                    img=hicon_to_qimage(hicon)
                    if img is not None and not img.isNull():pm=QPixmap.fromImage(img)
            except Exception:log('卡片 Shell 状态图标读取失败：'+traceback.format_exc())
        if custom and path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif')):
            pm = QPixmap(path)
        # 1) exe / dll / ico：直接抠出大图标，最清晰
        real = path
        if path.lower().endswith(".lnk"):
            t = resolve_lnk_target(path)
            if t:
                real = t
        if (pm is None or pm.isNull()) and real.lower().endswith((".exe", ".dll", ".ico")) and os.path.exists(real):
            hicon = extract_hicon(real, max(64, int(px)))
            if hicon:
                img = hicon_to_qimage(hicon)
                if img is not None and not img.isNull():
                    # 预乘格式是 Qt 平滑缩放/合成的快路径（每帧都要缩放图标，
                    # 不转的话那一步会慢好几倍）
                    if img.format() != QImage.Format_ARGB32_Premultiplied:
                        img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
                    pm = QPixmap.fromImage(img)
        # 2) 兜底一：问 Windows 外壳要"超大图标"（文件夹、URL 快捷方式、商店应用都靠这个，
        #    能拿到 256 像素，比 QFileIconProvider 的 32/40 像素清楚得多）
        if pm is None or pm.isNull():
            hicon = extract_shell_hicon(path, 256)
            if hicon:
                img = hicon_to_qimage(hicon)
                if img is not None and not img.isNull():
                    if img.format() != QImage.Format_ARGB32_Premultiplied:
                        img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
                    pm = QPixmap.fromImage(img)
        # 3) 兜底二：交给 Qt 自带的方式
        if pm is None or pm.isNull():
            try:
                ic = self.provider.icon(QFileInfo(path))
                if not ic.isNull():
                    pm = ic.pixmap(QSize(int(px), int(px)))
            except Exception:
                pm = None
        if pm is None or pm.isNull():
            pm = QPixmap(int(px), int(px))
            pm.fill(Qt.transparent)
        else:
            img = pm.toImage()
            if img.format() != QImage.Format_ARGB32_Premultiplied:
                img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
            # 源图太大就先缩到合适尺寸：外壳给的"超大图标"是 256 像素，
            # 而实际只会画到 60~90 像素，每帧从 256 缩下来很慢
            cap = max(96, int(px * 1.6))
            if img.width() > cap:
                img = img.scaled(cap, cap, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm = QPixmap.fromImage(img)
        cost = pm.width()*pm.height()*pm.depth()//8
        if cost <= self.max_cache_bytes:
            while self.cache and (len(self.cache)>=self.max_cache_entries or self.cache_bytes+cost>self.max_cache_bytes):
                _, discarded = self.cache.popitem(last=False)
                self.cache_bytes -= discarded.width()*discarded.height()*discarded.depth()//8
            self.cache[key] = pm
            self.cache_bytes += cost
        return pm

    def clear(self):
        self.cache.clear()
        self.cache_bytes = 0


from ui_style import AlignedMenu as QMenu

WM_OPEN_SETTINGS = 0x8000 + 804
EMPTY_DOCK_HINT = "拖入应用或快捷方式即可添加\n右键：应用批量管理 · 设置\n桌面卡片可在设置中开启"


class Dock(QWidget):
    """悬浮在桌面底部的 Dock 图标栏。"""

    running_ready = pyqtSignal(object)     # 后台线程扫描完进程后回传结果

    def __init__(self, cfg, tray=None, preview=False):
        super(Dock, self).__init__(None)
        self.cfg = cfg
        self.tray = tray
        self.preview = preview
        self.lite_mode = False
        self.icons = IconProvider()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setWindowTitle(APP_TITLE)

        from screen_layout import screen_records, scale
        displays=screen_records()
        self.display_scale=scale(cfg.get('display_layout',{}).get('dock',{}),displays[0] if displays else None)
        self.base_icon = int(cfg["icon_size"])
        self.ui_mult = self._ui_mult()
        self.icon_size = self._scaled(self.base_icon)
        self.font_pt = max(5, int(round(9 * self.ui_mult * getattr(self,'display_scale',1.0))))
        self.pad_x = int(self.icon_size * 0.36)
        self.pad_y = int(self.icon_size * 0.34)
        self.gap_ratio = 0.26
        self.max_scale = 1.55
        self.corner_n = 4.0            # 超椭圆圆角指数（越大越"方"，2=正圆）
        self.mouse_x = -99999.0
        self.mouse_smooth = -99999.0   # 平滑后的鼠标位置，用于顶边拉伸
        self.stretch = 0.0             # 顶边拉伸程度 0~1（带过渡动画）
        self.stretch_target = 0.0
        self.label_alpha = 0.0         # 名称气泡的淡入淡出
        self.spec_x = -99999.0
        self.spec_alpha = 0.0
        self.spec_target = 0.0
        self.hover_index = -1
        self.pressed = -1
        self.drag_idx = -1
        self.drag_moved = False
        self.drag_from_x = 0.0
        self.items = []
        self.page_index = int(cfg.get("dock_page", 0))
        self.page_count = 1
        self.page_offset = 0
        self.cur = []
        self.tgt = []
        self.pops = []
        self.rects = []
        self.running = set()
        self.backdrop = None          # 模糊后的背景画面
        self.backdrop_ok = None       # 是否支持屏幕捕获排除
        self._sys_light = system_is_light()   # 缓存的系统深浅色状态
        self.label_below = False      # 名称是否画在玻璃条下方（贴屏幕顶部时为 True）
        self._last_move_calc = 0.0    # 上次重算目标尺寸的时间（鼠标事件节流用）
        self._split_flags = []
        self._logged_once = False

        self.timer = QTimer(self)
        self.timer.setInterval(16)     # ~60fps
        self.timer.timeout.connect(self._tick)

        self.proc_timer = QTimer(self)
        self.proc_timer.setInterval(8000)
        self.proc_timer.timeout.connect(self.refresh_running)
        self.running_ready.connect(self._apply_running)
        self._proc_busy = False

        self.geo_timer = QTimer(self)
        self.geo_timer.setInterval(2500)
        self.geo_timer.timeout.connect(self.check_position)

        # 定期重新抓一次背后的画面，让毛玻璃里的内容保持新鲜。
        # 具体间隔由"背景抓取频率"设置决定，智能模式下平时几乎不抓，
        # 只在显示、鼠标靠近、改设置时抓一次。
        self.blur_timer = QTimer(self)
        self.blur_timer.setInterval(BLUR_INTERVAL["smart"])
        self.blur_timer.timeout.connect(self.refresh_backdrop)

        self._build_items()
        self.reposition()
        if not preview:
            self.proc_timer.start()
            self.geo_timer.start()
            self.refresh_running()

    def nativeEvent(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_OPEN_SETTINGS and self.tray:
            runtime = getattr(self.tray,'runtime',None)
            QTimer.singleShot(0,runtime.show_settings if runtime else self.tray.show_settings)
            return True, 0
        return super().nativeEvent(event_type,message)

    def is_light(self):
        """当前是不是浅色系（文字/小圆点用深色）。光感模式也算浅色系。"""
        t = str(self.cfg.get("theme", "auto"))
        if t in ("light", "gloss", "fog"):
            return True
        if t == "dark":
            return False
        return bool(self._sys_light)

    def theme_colors(self):
        from liquid_glass import tint_palette, material_palette
        colors = material_palette(tint_palette(self.base_theme_colors(), self.cfg.get('theme_color', '')), self.cfg.get('dock_material','liquid'))
        strength = self.cfg.get('dock_highlight', 45)/45
        for key in ('grad', 'hl'):
            colors[key] = [(position, min(255, round(alpha*strength))) for position, alpha in colors[key]]
        colors['border'].setAlpha(min(255, round(colors['border'].alpha()*strength)))
        colors['spec'] = min(255, round(colors['spec']*strength))
        return colors

    def base_theme_colors(self, theme=None):
        """按当前模式返回整套配色与外观参数。

        公共字段：
          tint / tint_scale / tint_floor  玻璃底色和它的浓度曲线
          grad / hl                       竖向渐变与顶部高光（会被合成为一条）
          border / border_w               描边颜色与粗细
          corner                          圆角半径占条高的比例
          tile / tile_*                   图标是否带圆角底板（iOS 那种）
        """
        t = str(self.cfg.get("theme", "auto") if theme is None else theme)
        if t in ("gloss", "fog"):
            # ── 光感模式：玻璃上有一道明显的光照（上方光源 + 顶边亮线 + 斜向光斑） ──
            #     不做白色图标底板，图标保持原样，整体是"湿润的玻璃"质感
            return dict(
                light=True,
                gloss=True,
                tint=QColor(238, 243, 252),
                tint_scale=0.62,          # 比浅色模式透一点，光才透得出来
                tint_floor=36,
                fg=QColor(40, 46, 62),
                # 上亮 → 中暗 → 下亮的经典光泽曲线
                grad=[(0.00, 150), (0.18, 96), (0.52, 40), (0.80, 30), (1.00, 74)],
                hl=[(0.00, 118), (0.42, 34), (1.00, 0)],
                border=QColor(255, 255, 255, 178),
                border_w=1.2,
                corner=0.44,
                spec=150,                          # 跟随鼠标的高光更强（就是"光照"）
                spec_wide=1.9,                     # 光斑更宽更柔
                shadow=QColor(255, 255, 255, 190),
                label_bg=QColor(250, 251, 255, 234),
                label_border=QColor(255, 255, 255, 176),
                label_fg=QColor(34, 40, 56, 246),
                tile=False,
            )
        if t == 'light' or (t == 'auto' and self._sys_light):
            return dict(
                light=True,
                tint=QColor(247, 247, 251),        # 玻璃底色（偏白）
                tint_scale=0.70,
                tint_floor=45,
                fg=QColor(34, 34, 44),             # 小圆点/提示文字
                grad=[(0.00, 88), (0.30, 48), (0.72, 26), (1.00, 60)],
                hl=[(0.00, 150), (0.55, 48), (1.00, 0)],
                border=QColor(88, 88, 104, 46),
                border_w=1.0,
                corner=0.40,
                spec=86,
                shadow=QColor(255, 255, 255, 150),
                label_bg=QColor(250, 250, 253, 238),
                label_border=QColor(80, 80, 96, 42),
                label_fg=QColor(28, 28, 38, 244),
                tile=False,
            )
        return dict(
            light=False,
            tint=QColor(16, 16, 20),
            tint_scale=1.0,
            tint_floor=0,
            fg=QColor(255, 255, 255),
            grad=[(0.00, 30), (0.28, 12), (0.70, 6), (1.00, 18)],
            hl=[(0.00, 76), (0.55, 20), (1.00, 0)],
            border=QColor(255, 255, 255, 78),
            border_w=1.0,
            corner=0.40,
            spec=70,
            shadow=QColor(0, 0, 0, 130),
            label_bg=QColor(16, 16, 20, 228),
            label_border=QColor(255, 255, 255, 62),
            label_fg=QColor(255, 255, 255, 242),
            tile=False,
        )

    def apply_theme_follow(self):
        """跟随系统模式下，定期检查系统有没有切换深浅色。"""
        cur = system_is_light()
        if cur != self._sys_light:
            self._sys_light = cur
            self.update()
            runtime = getattr(getattr(self, 'tray', None), 'runtime', None)
            if runtime:
                for panel in runtime.panels.windows.values(): panel.apply_options()

    # ---------------- 尺寸与布局 ----------------
    def _ui_mult(self):
        # Qt owns per-monitor DPI. Multiplying by GetDpiForSystem applies it twice
        # or retains the previous monitor's system DPI after a hot switch.
        return 1.0

    def _scaled(self, v):
        return max(12, int(round(v * self.ui_mult * getattr(self,'display_scale',1.0))))

    def bar_h(self):
        height = self.icon_size + self.pad_y * 2
        if not self.items:
            height = max(height,QFontMetrics(QFont("Microsoft YaHei UI",self.font_pt)).height()*3+16)
        return height

    def sep_width(self):
        """分隔符竖条本身的宽度（很窄）。"""
        return max(7.0, self.icon_size * 0.17)

    def sep_gap_width(self):
        """隔断模式下，被切开的玻璃条之间留出的空隙宽度。"""
        return max(14.0, self.icon_size * 0.42)

    def is_split_sep(self, i):
        """第 i 项是不是"隔断分隔符"：本身是分隔符，且左右两边都还有图标。

        结果在 _compute_split_flags() 里一次算好，避免每次查询都切片扫描列表
        （鼠标事件里会频繁调用，性能关键）。
        """
        flags = getattr(self, "_split_flags", None)
        if not flags or not (0 <= i < len(flags)):
            return False
        return flags[i]

    def _compute_split_flags(self):
        n = len(self.items)
        first_icon = -1
        last_icon = -1
        for i, it in enumerate(self.items):
            if not it.get("sep"):
                if first_icon < 0:
                    first_icon = i
                last_icon = i
        on = bool(self.cfg.get("sep_split", True))
        self._split_flags = [
            bool(on and self.items[i].get("sep") and first_icon >= 0 and first_icon < i < last_icon)
            for i in range(n)
        ]

    def item_slot_width(self, i):
        """第 i 项在排版里占的宽度。"""
        if not (0 <= i < len(self.items)):
            return float(self.icon_size)
        if not self.items[i].get("sep"):
            return float(self.icon_size)
        if self.is_split_sep(i):
            return self.sep_gap_width()
        return self.sep_width()

    def head_room(self):
        # 玻璃条【上方】留出的透明空间，用来放：
        #   1) 放大后凸出条子的图标（苹果 Dock 就是这样）
        #   2) 顶边被"拉起来"的那一块
        #   3) 悬停时显示的程序名称
        # 贴屏幕顶部时整个 Dock 是镜像的（图标向下长、鼓包也向下、名称也在下面），
        # 上方就不需要留白了。
        if self.bump_down():
            return 0
        room = int(max(self.icon_size * 0.55, self.bump_max())) + 8
        if self.cfg.get("show_name", True) and not self.label_below:
            room += self.label_height() + 8
        return room

    def bump_down(self):
        """贴屏幕顶部时，拉伸改为【底边向下鼓】，免得顶边鼓出屏幕被切掉。"""
        return bool(self.label_below)

    def bump_max(self):
        return self.icon_size * 0.36 * self.bump_scale()

    def foot_room(self):
        """玻璃条【下方】留出的透明空间。

        贴屏幕顶部时整个 Dock 镜像：图标向下生长、鼓包向下、名称也在下面，
        所以下方要一次留够；否则会被窗口边缘切掉。
        """
        if not self.bump_down():
            return 0
        grow = int(max(self.icon_size * 0.62, self.bump_max())) + 8   # 图标向下放大 + 鼓包
        room = grow
        if self.cfg.get("show_name", True):
            room = max(room, int(self.label_height() + grow + 6))
        return room

    def label_top_y(self, bar):
        """名称气泡的顶部 y 坐标（窗口坐标）。

        名称放下方时，要躲开向下鼓出去的那块，所以额外留出鼓包的高度。
        """
        if self.label_below:
            return bar.bottom() + self.bump_max() * self.stretch + 4.0
        return 2.0

    def label_height(self):
        fm = QFontMetrics(QFont("Microsoft YaHei UI", self.font_pt))
        return float(fm.height() + 10)

    def side_room(self):
        """左右两侧预留的透明空间：拉伸时玻璃条会往这两边撑出去。

        这个值同时决定了"放大时能有多少额外空间可用"——留够的话，
        鼠标滑过时其它图标就不用被压缩了（留太少会因为放不下而整体缩一圈）。
        """
        return int(self.icon_size * 0.55) + 4

    def side_expand(self):
        return self.side_room() * self.stretch

    def bar_rect_f(self):
        """当前玻璃条的矩形（会随拉伸向左右外扩，底边固定不动）。"""
        e = self.side_expand()
        left = self.side_room() - e
        return QRectF(left, float(self.head_room()),
                      float(self.width()) - 2.0 * left, float(self.bar_h()))

    def total_size(self):
        n = len(self.items)
        if n == 0:
            w = max(330, int(self.icon_size * 5.1))
        else:
            gap = self.icon_size * self.gap_ratio
            body = sum(self.item_slot_width(i) for i in range(n))
            w = int(self.pad_x * 2 + body + (n - 1) * gap)
        # 左右各留一条透明带，给"外扩"用
        h = int(self.bar_h() + self.head_room() + self.foot_room())
        return QSize(w + self.side_room() * 2, h)

    def _build_items(self):
        self.items = []
        self.running = set()
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry().width() if screen else 1920
        page_size = max(1, int((available-self.side_room()*2-self.pad_x*2-40) / (self.icon_size*(1+self.gap_ratio))))
        self.page_count = max(1, math.ceil(len(self.cfg['items']) / page_size))
        self.page_index = min(self.page_index, self.page_count-1)
        self.page_offset = self.page_index*page_size
        for it in self.cfg["items"][self.page_offset:self.page_offset+page_size]:
            if it.get("sep"):
                self.items.append({"sep": True, "path": "", "name": "",
                                   "pixmap": None, "exe": ""})
                continue
            path = it["path"]
            self.items.append({
                "path": path,
                "name": it.get("name") or os.path.splitext(os.path.basename(path))[0],
                "pixmap": self.icons.get(it.get("icon") or path, max(96, int(self.icon_size * 2.0)), bool(it.get("icon"))),
                "exe": self._exe_name(path),
            })
        n = len(self.items)
        self.cur = []
        self.tgt = []
        self.pops = [0.0] * n
        self._compute_split_flags()
        if n == 0:
            self.stretch_target = 0.0
            self.stretch = 0.0
        self.resize(self.total_size())
        self._recalc(uniform=True)

    @staticmethod
    def _exe_name(path):
        real = path
        if path.lower().endswith(".lnk"):
            real = resolve_lnk_target(path) or path
        base = os.path.basename(real)
        return base.lower()

    def _recalc(self, uniform=False, light=False):
        n = len(self.items)
        if n == 0:
            self.tgt = []
            self.cur = []
            self.rects = []
            return
        S = float(self.icon_size)
        gap = S * self.gap_ratio
        sep_idx = [i for i, it in enumerate(self.items) if it.get("sep")]
        icon_idx = [i for i, it in enumerate(self.items) if not it.get("sep")]
        m = len(icon_idx)
        # 图标可用宽度 = 玻璃条宽度 - 左右内边距 - 间距 - 分隔符占用
        # 注意两件事：
        #   1) 要先减掉两侧给"外扩"预留的透明边距，否则图标会排到条子外面去
        #   2) 拉伸时玻璃条会向左右各撑出 side_expand()，这块空间要算给图标，
        #      否则鼠标滑过时放不下，只能把所有图标整体缩小（看起来就是"图标变小了"）
        bar_w = (float(self.width()) - self.side_room() * 2
                 + self.side_expand() * 2.0)
        sep_total = sum(self.item_slot_width(i) for i in sep_idx)
        avail = bar_w - self.pad_x * 2 - gap * (n - 1) - sep_total
        avail = max(S * 0.5, avail)
        # 先算"静止状态"下每个图标的中心，鱼眼放大要按它来算。
        # 注意起点要和 _layout 里一致（玻璃条左边 + 内边距），
        # 否则鱼眼的中心会和真实图标错开一段，看起来像"指到 A 却放大了 B"。
        rest = {}
        x = (self.side_room() - self.side_expand()) + float(self.pad_x)
        for i in range(n):
            w = self.item_slot_width(i)
            rest[i] = x + w / 2.0
            x += w + gap
        if (not uniform) and not self.lite_mode and self.cfg["magnify"] and self.mouse_x > -9000 and m:
            R = S * 2.35
            ms = []
            for i in icon_idx:
                d = abs(self.mouse_x - rest[i])
                if d >= R:
                    ms.append(1.0)
                else:
                    t = d / R
                    ms.append(1.0 + (self.max_scale - 1.0) * 0.5 * (1.0 + math.cos(math.pi * t)))
        else:
            ms = [1.0] * m
        raw = [S * v for v in ms]
        tot = sum(raw) or 1.0
        k = avail / tot
        tgt = [self.item_slot_width(i) for i in range(n)]
        for j, i in enumerate(icon_idx):
            tgt[i] = raw[j] * k
        self.tgt = tgt
        if uniform or len(self.cur) != n:
            self.cur = list(self.tgt)
        if not light:
            # light=True 时只更新目标值，排版和重绘交给 16ms 的动画帧去做，
            # 这样鼠标移动时不会一帧算两遍（性能优化）
            self._layout()
            self.update(self.repaint_rect())

    def repaint_rect(self):
        """需要重绘的区域。比整个窗口小一圈，能明显省下绘制开销。

        注意：只要开着名称显示，就必须**无条件**把名称那一条也圈进来。
        名称画在玻璃条外面的透明区，如果只在"名称正在显示"时才重绘那一块，
        淡出的最后一帧就不会被擦掉，屏幕上的旧名称会一直残留。
        """
        bar = self.bar_rect_f()
        r = QRectF(bar).adjusted(-3, -self.icon_size * 0.55, 3, 4)
        if self.cfg.get("show_name", True):
            th = self.label_height()
            ly = self.label_top_y(bar)
            r = r.united(QRectF(0.0, ly, float(self.width()), th))
        return r.toAlignedRect()

    # ---------------- 外形 ----------------
    def bump_scale(self):
        """鼓包（拉伸）幅度系数，对应托盘里的低/中/高三档。"""
        return BUMP_SCALE.get(str(self.cfg.get("bump_level", "mid")), 1.0)

    def bump_at(self, x, R=None):
        """顶边在横坐标 x 处被"拉起来"的高度。

        以鼠标位置为中心做一条平滑的钟形曲线，越靠鼠标越高；
        影响半径 R 由调用方按段宽给（见 _one_shape），所以离开口两端很远的地方
        就已经开始慢慢抬起来了，而不是只在鼠标旁边鼓一小块。
        """
        A = self.icon_size * 0.36 * self.bump_scale() * self.stretch
        if A <= 0.25 or self.mouse_smooth < -9000:
            return 0.0
        d = abs(x - self.mouse_smooth)
        if R is None:
            R = self.icon_size * 2.2
        if d >= R:
            return 0.0
        prof = 0.5 * (1.0 + math.cos(math.pi * d / R))
        return A * prof

    def _corner_sets_for(self, r):
        """缓存的超椭圆（苹果式连续曲率）圆角采样点。

        普通圆角用的是正圆，圆弧和直边的接缝处曲率会突变，看着有一点"折"；
        超椭圆的曲率在接缝处正好为 0，所以过渡是连续的 —— 这就是苹果圆角更顺滑的原因。
        每段的圆角完全一样，所以只算一次缓存起来（性能关键）。
        """
        key = (round(r, 2), round(self.corner_n, 2))
        if getattr(self, "_corn_key", None) != key:
            e = 2.0 / max(2.01, self.corner_n)
            sets = {}
            for name, t0, t1 in (("tr", -math.pi / 2.0, 0.0), ("br", 0.0, math.pi / 2.0),
                                 ("bl", math.pi / 2.0, math.pi), ("tl", math.pi, math.pi * 1.5)):
                lst = []
                for i in range(1, 17):
                    t = t0 + (t1 - t0) * (i / 16.0)
                    cc, ss = math.cos(t), math.sin(t)
                    lst.append((math.copysign(abs(cc) ** e, cc),
                                math.copysign(abs(ss) ** e, ss)))
                sets[name] = lst
            self._corn_key = key
            self._corn_sets = sets
        return self._corn_sets

    def _add_corner_cached(self, path, cx, cy, r, name):
        for dx, dy in self._corn_sets[name]:
            path.lineTo(cx + dx * r, cy + dy * r)

    def corner_ratio(self):
        """圆角半径占条高的比例。光感模式更圆一些。"""
        t = str(self.cfg.get("theme", "auto"))
        return 0.44 if t in ("gloss", "fog") else 0.40

    def corner_radius(self):
        return max(8.0, min(self.bar_h() * self.corner_ratio(), self.bar_h() / 2.0))

    def shape_segments(self):
        """把玻璃背景按"隔断分隔符"切成若干段，返回 [(x_left, x_right), ...]。

        只有夹在两个图标中间的分隔符才会隔断；放在最左/最右的不生效。
        """
        bar = self.bar_rect_f()
        n = len(self.items)
        if n == 0 or not self.rects:
            return [(bar.left(), bar.right())]
        segs = []
        start = bar.left()
        gap_w = self.sep_gap_width()
        for i in range(n):
            if not self.is_split_sep(i):
                continue
            if i >= len(self.rects):
                continue
            c = self.rects[i][0]
            segs.append((start, c - gap_w / 2.0))
            start = c + gap_w / 2.0
        segs.append((start, bar.right()))
        # 太窄的段直接丢掉，避免画出怪东西
        return [(a, b) for (a, b) in segs if b - a > 12.0]

    def _one_shape(self, x_l, x_r, top0, bot):
        """画一段玻璃：苹果式连续曲率圆角矩形 + 拉伸鼓起。

        鼓起的边跟着 Dock 的位置走：
          · 平时（贴屏幕底部）→ 顶边向上鼓
          · 贴屏幕顶部时      → 底边向下鼓，否则顶边会鼓出屏幕被切掉
        """
        w = x_r - x_l
        if w <= 2.0:
            return None
        r = min(self.corner_radius(), w / 2.0 - 0.5, (bot - top0) / 2.0)
        self._corner_sets_for(r)
        span = max(1.0, w - 2.0 * r)

        # 影响半径：至少 2.2 个图标宽，并且不小于这一段的 60%
        # —— 这样从很靠近两端的地方就已经开始慢慢抬起了，不是只在鼠标旁边鼓一小块
        R = max(self.icon_size * 2.2, span * 0.60)
        bump_here = (self.stretch > 0.02 and self.mouse_smooth > -9000
                     and (x_l - R) <= self.mouse_smooth <= (x_r + R))
        down = self.bump_down()

        def edge_y(x, base):
            b = self.bump_at(x, R)
            if b <= 0.0:
                return base
            t = (x - (x_l + r)) / span
            # 收口宽度：0.16 → 0.30，让凸起一直延伸到很靠近圆角的地方才回落
            k = min(1.0, t / 0.30, (1.0 - t) / 0.30)
            if k <= 0.0:
                return base
            k = k * k * (3.0 - 2.0 * k)     # smoothstep，收口更自然
            return base - b * k if not down else base + b * k

        n_steps = max(4, int(span / 8.0))
        path = QPainterPath()
        path.moveTo(x_l + r, top0)
        if bump_here and not down:
            for i in range(1, n_steps + 1):
                x = x_l + r + span * i / n_steps
                path.lineTo(x, edge_y(x, top0))
        else:
            path.lineTo(x_r - r, top0)
        self._add_corner_cached(path, x_r - r, top0 + r, r, "tr")
        path.lineTo(x_r, bot - r)
        self._add_corner_cached(path, x_r - r, bot - r, r, "br")
        if bump_here and down:
            # 底边是从右往左走的
            for i in range(1, n_steps + 1):
                x = x_r - r - span * i / n_steps
                path.lineTo(x, edge_y(x, bot))
        else:
            path.lineTo(x_l + r, bot)
        self._add_corner_cached(path, x_l + r, bot - r, r, "bl")
        path.lineTo(x_l, top0 + r)
        self._add_corner_cached(path, x_l + r, top0 + r, r, "tl")
        path.closeSubpath()
        return path

    def shape_paths(self):
        """整条玻璃的全部形状（隔断模式下会是好几段）。"""
        bar = self.bar_rect_f()
        top0 = bar.top()
        bot = bar.bottom()
        out = []
        for (a, b) in self.shape_segments():
            pa = self._one_shape(a, b, top0, bot)
            if pa is not None:
                out.append(pa)
        return out

    def shape_path(self):
        """兼容用：返回第一段形状（没有隔断时就等于整条）。"""
        ps = self.shape_paths()
        return ps[0] if ps else QPainterPath()

    def _layout(self):
        n = len(self.items)
        if n == 0:
            self.rects = []
            return
        bar = self.bar_rect_f()
        # rects 里第 4 个值存的是"锚点"：
        #   平时（贴屏幕底部）= 图标底边，放大时向上长
        #   贴屏幕顶部时      = 图标顶边，放大时向下长（整体镜像，不会被屏幕边缘切掉）
        if self.bump_down():
            base_y = bar.top() + self.pad_y
        else:
            base_y = bar.top() + self.bar_h() - self.pad_y
        widths = [self.cur[i] if i < len(self.cur) else self.icon_size for i in range(n)]
        if n == 1:
            w = widths[0]
            cx = bar.left() + (bar.width() - w) / 2.0 + w / 2.0
            self.rects = [(cx, w, w, base_y, bool(self.items[0].get("sep")))]
            return
        # 间距用固定公式算（和旧版一致）：图标的尺寸在动画中是连续的，
        # 如果间距改成"剩余空间平摊"，间距就会跟着每帧变，
        # 整排图标会一起左右轻微滑动，看起来就是"抽搐"。
        gap = float(self.icon_size) * self.gap_ratio
        e = self.side_expand()
        if n > 1:
            gap += (2.0 * e) / (n - 1.0)     # 外扩的宽度平摊到各段间距上
        # 安全网：只有在真的放不下时才压缩（正常动画不会触发），
        # 保证图标永远不会排到玻璃条外面
        usable = bar.width() - self.pad_x * 2.0
        need = sum(widths)
        if need + gap * (n - 1.0) > usable:
            gap = max(0.0, (usable - need) / (n - 1.0))
            if need > 0 and need + gap * (n - 1.0) > usable:
                k = max(0.0, (usable - gap * (n - 1.0)) / need)
                widths = [w * k for w in widths]
        x = bar.left() + self.pad_x
        out = []
        for i, it in enumerate(self.items):
            w = widths[i]
            out.append((x + w / 2.0, w, w, base_y, bool(it.get("sep"))))
            x += w + gap
        self.rects = out

    # ---------------- 位置 ----------------
    def layout_position(self):
        """算出玻璃条应该贴在哪，并决定程序名称放条子上方还是下方。

        返回 (玻璃条顶边的 y 坐标, 屏幕可用区域)。
        Dock 永远是水平居中的。
        """
        scr = QGuiApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else None
        if geo is None:
            return 100, QRectF(0, 0, 1920, 1080)
        mode = str(self.cfg.get("position", "bottom"))
        margin = round(int(self.cfg.get("bottom_margin", 6))*getattr(self,"display_scale",1.0))
        if mode == "top":
            bar_top = geo.top() + margin
        elif mode == "custom":
            off = round(int(self.cfg.get("custom_bottom", 200))*getattr(self,"display_scale",1.0))
            bar_top = geo.bottom() + 1 - off - self.bar_h()
        else:
            bar_top = geo.bottom() + 1 - margin - self.bar_h()
        # 上方空间不够放名称时，把名称改放到玻璃条下面
        need_above = int(self.icon_size * 0.55) + 8
        if self.cfg.get("show_name", True):
            need_above += int(self.label_height() + 8)
        self.label_below = bool(bar_top - geo.top() < need_above)
        return bar_top, geo

    def target_pos(self):
        bar_top, geo = self.layout_position()
        x = geo.left() + (geo.width() - self.width()) // 2
        y = bar_top - self.head_room()
        return QPoint(int(x), int(y))

    def reposition(self):
        # 必须先算位置（这一步会决定名称放上面还是下面），
        # 再按算好的结果调整窗口大小，最后才移动。
        # 顺序反了的话，换位置的第一次会用到旧的名称方向，位置就会错一格。
        self.layout_position()
        want = self.total_size()
        if want != self.size():
            self.resize(want)
        self.move(self.target_pos())
        # 窗口尺寸 / 名称方向可能变了，图标坐标必须跟着重算，
        # 否则会出现"玻璃条位置对了、图标还停在旧位置"的现象
        self.cur = []
        self.tgt = []
        self._recalc(uniform=True)

    def apply_layer(self):
        """把窗口放到指定层级。

        置底用 HWND_BOTTOM：Dock 会退到所有普通窗口的下面（和桌面同级），
        这样最大化窗口、全屏应用都不会被它挡住；因为有定时重设，
        其它窗口激活改变 z 序后它会自动再沉下去。
        """
        if self.preview:
            return
        try:
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND,
                                            ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            user32.SetWindowPos.restype = wintypes.BOOL
            hwnd = wintypes.HWND(int(self.winId()))
            layer = str(self.cfg.get("layer", "bottom"))
            target = HWND_TOPMOST if layer == "top" else HWND_BOTTOM
            user32.SetWindowPos(hwnd, wintypes.HWND(target), 0, 0, 0, 0,
                                SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        except Exception:
            log("apply_layer 失败: " + traceback.format_exc())

    def check_position(self):
        was_below = self.label_below
        self.layout_position()          # 顺带更新 label_below
        size = self.total_size()
        changed = size != self.size()
        if changed:
            self.resize(size)
        want = self.target_pos()
        moved = want != self.pos()
        if moved:
            self.move(want)
        # 尺寸或名称方向变了，图标坐标要重算（否则图标会停在旧位置）
        if changed or self.label_below != was_below:
            self.cur = []
            self.tgt = []
            self._recalc(uniform=True)
        self.apply_theme_follow()
        self.apply_layer()

    # ---------------- 运行状态 ----------------
    def refresh_running(self):
        """扫描"哪些程序正在运行"。

        这个扫描要 6~8 毫秒，放在主线程里每几秒就会让动画卡一下，
        所以丢到后台线程做，扫完用信号把结果传回来。
        """
        if self.lite_mode:
            return
        if not self.cfg["running_dots"]:
            if self.running:
                self.running = set()
                self.update()
            return
        if getattr(self, "_proc_busy", False):
            return
        self._proc_busy = True
        threading.Thread(target=self._scan_procs, daemon=True).start()

    def _scan_procs(self):
        try:
            names = get_running_exe_names()
        except Exception:
            names = set()
        try:
            self.running_ready.emit(names)
        except Exception:
            pass

    def _apply_running(self, names):
        self._proc_busy = False
        if self.lite_mode:
            return
        if names != self.running:
            self.running = names
            self.update()

    # ---------------- 动画 ----------------
    def _tick(self):
        moving = False
        for i in range(len(self.cur)):
            d = self.tgt[i] - self.cur[i]
            if abs(d) > 0.4:
                self.cur[i] += d * 0.30
                moving = True
            elif self.cur[i] != self.tgt[i]:
                self.cur[i] = self.tgt[i]
                moving = True
        for i in range(len(self.pops)):
            if self.pops[i] > 0.0:
                self.pops[i] = max(0.0, self.pops[i] - 0.075)
                moving = True
        d = self.spec_target - self.spec_alpha
        if abs(d) > 0.02:
            self.spec_alpha += d * 0.18
            moving = True
        else:
            self.spec_alpha = self.spec_target
        # 顶边拉伸的渐变 + 鼠标位置平滑（让鼓起的地方跟着鼠标滑过去，而不是瞬间跳）
        d = self.stretch_target - self.stretch
        if abs(d) > 0.004:
            self.stretch += d * 0.16
            moving = True
            # 拉伸会改变玻璃条宽度，图标能分到的空间也跟着变，
            # 所以要顺带把目标尺寸重算一遍；否则动画过程中尺寸和条宽对不上，
            # 图标会跑到条子外面去（这也是"滑动时露出背景范围"的原因）。
            self._recalc(light=True)
        else:
            if self.stretch != self.stretch_target:
                self.stretch = self.stretch_target
                self._recalc(light=True)
        if self.mouse_x > -9000:
            d = self.mouse_x - self.mouse_smooth
            if abs(d) > 0.5:
                self.mouse_smooth = self.mouse_x if self.mouse_smooth < -9000 else self.mouse_smooth + d * 0.35
                moving = True
            else:
                self.mouse_smooth = self.mouse_x
        # 名称气泡淡入淡出
        lt = 1.0 if (0 <= self.hover_index < len(self.items)) else 0.0
        d = lt - self.label_alpha
        if abs(d) > 0.03:
            self.label_alpha += d * 0.28
            moving = True
        else:
            self.label_alpha = lt
        if moving:
            self._layout()
        else:
            self.timer.stop()
        self.update(self.repaint_rect())

    def _kick(self):
        if not self.timer.isActive():
            self.timer.start()

    # ---------------- 鼠标 ----------------
    def enterEvent(self, e):
        self.spec_target = 1.0
        try:
            if self.items and e.pos().y() >= (self.bar_rect_f().top() - 12):
                self.stretch_target = 1.0
        except Exception:
            pass
        if self.mouse_x > -9000:
            self.mouse_smooth = self.mouse_x
        if str(self.cfg.get("blur_mode", "smart")) != "off":
            self.refresh_backdrop()      # 鼠标靠近时补抓一次，保证玻璃里画面是新的
        self._kick()
        super(Dock, self).enterEvent(e)

    def leaveEvent(self, e):
        self.mouse_x = -99999.0
        self.spec_target = 0.0
        self.stretch_target = 0.0
        self.hover_index = -1
        self.pressed = -1
        self.setCursor(Qt.ArrowCursor)
        QToolTip.hideText()
        self._recalc()
        self._kick()
        super(Dock, self).leaveEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.pos()
        self.mouse_x = float(pos.x())
        self.spec_x = float(pos.x())
        # 拖动排序模式：按住左键移动 = 排序
        if self.drag_idx >= 0 and (e.buttons() & Qt.LeftButton):
            if abs(pos.x() - self.drag_from_x) > 4:
                self.drag_moved = True
            if self.drag_moved:
                self._drag_reorder(float(pos.x()))
                self.hover_index = self.drag_idx      # 名称气泡跟着被拖的图标
                self._recalc(light=True)
                self._kick()
                super(Dock, self).mouseMoveEvent(e)
                return
        # 只有鼠标进到玻璃条附近才触发拉伸；上方留白（放名称的地方）不触发，
        # 免得鼠标从上面路过时整条乱动。
        near = pos.y() >= (self.bar_rect_f().top() - 12)
        self.stretch_target = 1.0 if (self.items and near) else 0.0
        idx = self._hit(pos)
        if idx != self.hover_index:
            self.hover_index = idx
            QToolTip.hideText()
            # 只有悬停目标变了才设置鼠标形状（SetCursor 是系统调用，别每次都调）
            self.setCursor(Qt.PointingHandCursor if idx >= 0 else Qt.ArrowCursor)
            self._recalc(light=True)
        else:
            # 高刷新率鼠标每秒能上报上千次移动，没必要每次运动都全量重算；
            # 限制到约 120Hz，剩下的交给 60fps 的动画帧去插值，肉眼看不出差别。
            now = time.perf_counter()
            if now - self._last_move_calc >= 0.008:
                self._last_move_calc = now
                self._recalc(light=True)
        self._kick()
        super(Dock, self).mouseMoveEvent(e)

    def _hit(self, pos):
        if not self.rects:
            return -1
        y = float(pos.y())
        x = float(pos.x())
        for i, r in enumerate(self.rects):
            if r[4]:            # 分隔符不响应鼠标
                continue
            cx, w, h, by = r[0], r[1], r[2], r[3]
            if abs(x - cx) > w / 2.0:
                continue
            if self.bump_down():
                # by 是图标顶边
                if (by - 6) <= y <= (by + h + 10):
                    return i
            else:
                # by 是图标底边
                if (by - h - 4) <= y <= (by + 10):
                    return i
        return -1

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.pressed = self._hit(e.pos())
            self.drag_idx = -1
            self.drag_moved = False
            if (self.cfg.get("reorder") and self.pressed >= 0
                    and not self.items[self.pressed].get("sep")):
                self.drag_idx = self.pressed
                self.drag_from_x = float(e.pos().x())
        super(Dock, self).mousePressEvent(e)

    def _drag_reorder(self, x):
        """拖动排序：跟紧邻的图标/分隔符「一步一步」交换位置。

        带迟滞（要多越过邻居中心 30% 图标宽度才换），所以不会在临界点反复横跳；
        换位后也不重置图标尺寸，避免忽大忽小的闪烁。
        """
        n = len(self.items)
        if self.drag_idx < 0 or n < 2:
            return
        margin = self.icon_size * 0.30
        # 找左右两边最近的"非自己"条目（分隔符也参与，这样才能被拖到分隔符后面）
        left = None
        for i in range(self.drag_idx - 1, -1, -1):
            if i != self.drag_idx:
                left = i
                break
        right = None
        for i in range(self.drag_idx + 1, n):
            right = i
            break
        target = -1
        if left is not None and x < self.rects[left][0] - margin:
            target = left
        elif right is not None and x > self.rects[right][0] + margin:
            target = right
        if target < 0 or target == self.drag_idx:
            return
        it = self.items.pop(self.drag_idx)
        self.items.insert(target, it)
        ci = self.cfg["items"].pop(self.page_offset + self.drag_idx)
        self.cfg["items"].insert(self.page_offset + target, ci)
        self.drag_idx = target
        self.pressed = target
        # 顺序变了，"哪些分隔符要隔断背景"必须跟着重算，
        # 否则把图标拖到分隔符两边时不会出现隔断效果
        self._compute_split_flags()
        self._recalc()          # 不重置尺寸，保持放大状态，避免闪烁
        self._kick()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self.drag_idx >= 0:
                if self.drag_moved:
                    save_config(self.cfg)      # 拖完把新顺序存下来
                    self.drag_idx = -1
                    self.pressed = -1
                    self._kick()
                    super(Dock, self).mouseReleaseEvent(e)
                    return
                self.drag_idx = -1
            idx = self._hit(e.pos())
            if idx >= 0 and idx == self.pressed:
                self.pops[idx] = 1.0
                self._kick()
                self.launch(self.items[idx]["path"])
            self.pressed = -1
        super(Dock, self).mouseReleaseEvent(e)

    def launch(self, path, source='dock_launch'):
        log("启动: " + path)
        try:
            from external_launch import launch
            launch(path)
        except Exception:
            log("启动失败，尝试 os.startfile: " + traceback.format_exc())
            try:
                from external_launch import startfile
                startfile(path)
            except Exception:
                log("启动彻底失败: " + traceback.format_exc())
                return
        from usage_stats import record
        record(self,source)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def change_page(self, delta):
        if self.page_count <= 1:
            return
        self.page_index = (self.page_index+delta) % self.page_count
        self.cfg["dock_page"] = self.page_index
        save_config(self.cfg)
        self.mouse_x = self.mouse_smooth = -99999.0
        self.hover_index = self.pressed = self.drag_idx = -1
        self._build_items()
        self.reposition()
        self._kick()

    def wheelEvent(self, event):
        if self.page_count > 1:
            self.change_page(1 if event.angleDelta().y() < 0 else -1)
            event.accept()
        else:
            super().wheelEvent(event)

    def dropEvent(self, event):
        if not self.tray or not hasattr(self.tray, 'importer'):
            event.ignore()
            return
        candidates = [{'path': url.toLocalFile()} for url in event.mimeData().urls() if url.isLocalFile()]
        if not candidates:
            event.ignore()
            return
        self.tray.importer.pin(candidates)
        event.setDropAction(Qt.CopyAction)
        event.accept()

    def icon_context_menu(self, idx):
        m = QMenu(self)
        if idx >= 0 and not self.items[idx].get("sep"):
            it = self.items[idx]
            a = QAction("打开 " + it["name"], m)
            a.triggered.connect(lambda _=False, p=it["path"]: self.launch(p))
            m.addAction(a)
            m.addAction('图标设置…').triggered.connect(lambda _=False, index=self.page_offset+idx: self.edit_icon(index))
            m.addAction('移除').triggered.connect(lambda _=False, index=self.page_offset+idx, entry=dict(self.cfg['items'][self.page_offset+idx]): self.remove_icon(index, entry))
            m.addSeparator()
        if self.tray:
            if 0<=idx<len(self.items) and self.items[idx].get('sep'):
                snapshot=[dict(item) for item in self.cfg['items']]
                index=self.page_offset+idx
                m.addAction('移除此分隔符').triggered.connect(lambda checked=False:self.tray.remove_separator(index,snapshot));m.addSeparator()
            from tray_menu import common_actions
            insert_at=self.page_offset+idx+1 if 0<=idx<len(self.items) else None
            common_actions(m,self.tray,dock_context=True,insert_at=insert_at)
        return m

    def edit_icon(self, index):
        from icon_settings import IconSettings
        dialog = IconSettings(self, index)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()

    def remove_icon(self, index, entry):
        # Guard against a reorder while the context menu was open.
        if 0 <= index < len(self.cfg['items']) and self.cfg['items'][index] == entry:
            items = [dict(item) for item in self.cfg['items']]
            del items[index]
            self.tray.importer.apply_items(items)

    def contextMenuEvent(self, e):
        index=self._hit(e.pos())
        if index<0:
            x,y=float(e.pos().x()),float(e.pos().y())
            for i,rect in enumerate(self.rects):
                if not rect[4] or abs(x-rect[0])>max(7,rect[1]/2):continue
                by,h=rect[3],rect[2]
                hit=(by-6<=y<=by+h+10) if self.bump_down() else (by-h-10<=y<=by+6)
                if hit:index=i;break
        menu = self.icon_context_menu(index)
        menu.exec_(e.globalPos())
        menu.deleteLater()

    # ---------------- 绘制 ----------------
    @staticmethod
    def _stop_alpha(stops, t):
        """在一条渐变的色标里插值取值。"""
        if t <= stops[0][0]:
            return float(stops[0][1])
        for i in range(1, len(stops)):
            p0, a0 = stops[i - 1]
            p1, a1 = stops[i]
            if t <= p1:
                if p1 <= p0:
                    return float(a1)
                return a0 + (a1 - a0) * (t - p0) / (p1 - p0)
        return float(stops[-1][1])

    def merged_grad_stops(self, c):
        """把"竖向渐变"和"顶部高光"合并成一条渐变。

        两者都是白色的竖向渐变，合成一条之后每段只要裁切一次、填充一次，
        能省掉一次昂贵的路径裁切光栅化（性能关键）。
        """
        hl_span = 0.42
        out = []
        for f in (0.0, 0.10, 0.20, 0.28, 0.42, 0.70, 1.0):
            a1 = self._stop_alpha(c["grad"], f)
            a2 = self._stop_alpha(c["hl"], f / hl_span) if f <= hl_span else 0.0
            m = 1.0 - (1.0 - a1 / 255.0) * (1.0 - a2 / 255.0)
            out.append((f, int(round(m * 255))))
        return out

    def icon_scaled(self, it, size):
        """取"已经缩放到目标尺寸"的图标（按 2 像素一档缓存）。

        每帧都对 256×256 的原始图标做一次平滑缩放很贵；缓存之后大部分帧
        变成 1:1 贴图，只有尺寸跨档时才重新缩一次。
        """
        q = max(4, int(round(size / 2.0)) * 2)
        cache = it.get("_scaled")
        if cache is None:
            cache = {}
            it["_scaled"] = cache
        pm = cache.get(q)
        if pm is not None:
            return pm
        src = it.get("pixmap")
        if src is None or src.isNull():
            return None
        if q == src.width() and q == src.height():
            pm = src                      # 尺寸刚好一样，直接用（省一次缩放）
        else:
            # 一定要缩放到目标尺寸：源图可能比目标小（文件夹图标以前常常只有 40 像素），
            # 直接返回源图的话画出来会又小又偏（是按左上角贴的，不是按格子居中）
            pm = src.scaled(q, q, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        # 缓存满了就淘汰最旧的一个，不要整体清空 ——
        # 整体清空会让那一帧所有图标都重新缩放，滑动时每隔十几帧卡一下（抽搐感来源之一）
        if len(cache) >= 4:
            cache.pop(next(iter(cache)), None)
        cache[q] = pm
        return pm

    def _paint_glass_piece(self, p, path, path_rect, bar, c, tint_a, stops):
        from liquid_glass import paint_liquid_glass
        paint_liquid_glass(self, p, path, path_rect, bar, c, tint_a, stops)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        bar = self.bar_rect_f()
        paths = self.shape_paths()
        prects = [pa.boundingRect() for pa in paths]
        path = paths[0] if paths else QPainterPath()
        path_rect = prects[0] if prects else bar

        # 玻璃整体：自己抓屏 + 自己模糊，模糊区域完全跟随玻璃形状，
        # 四个角天生透明，不会有方形轮廓。
        #
        # 通透度作用于【整块玻璃】：
        #   tp<=40 时整块玻璃保持不透明，只是压在背景上的深色变淡（偏实 → 默认）
        #   tp>40  时整块玻璃（模糊画面 + 深色 + 高光 + 描边）一起变淡，
        #           于是无论背后是亮壁纸还是深色窗口，都能明显看出"更通透"了
        tp = max(0, min(100, int(self.cfg.get("transparency", 40))))
        c = self.theme_colors()
        base_a = 235.0 * (100 - tp) / 100.0
        # 各模式用各自的"底色浓度曲线"：深色 1.0 倍、浅色 0.70+45、雾透 0.40+24
        tint_a = int(round(min(255.0, base_a * c["tint_scale"] + c["tint_floor"])))
        glass_a = 1.0 - max(0.0, tp - 40.0) / 60.0 * 0.58
        glass_a = max(0.32, min(1.0, glass_a))

        p.save()
        p.setOpacity(glass_a)

        stops = self.merged_grad_stops(c)
        for pa, pr in zip(paths, prects):
            self._paint_glass_piece(p, pa, pr, bar, c, tint_a, stops)

        p.restore()      # 玻璃画完，透明度恢复，下面的名称和图标始终是全不透明的

        # 悬停时的程序名称：默认画在最上方（图标、拉伸动画的上方），不挡任何东西；
        # 如果 Dock 贴着屏幕顶部，就改画在玻璃条下面，保证看得清。
        if (self.cfg.get("show_name", True) and self.label_alpha > 0.02
                and 0 <= self.hover_index < len(self.items)):
            name = self.items[self.hover_index]["name"]
            f = QFont("Microsoft YaHei UI", self.font_pt)
            fm = QFontMetrics(f)
            tw = float(fm.width(name) + 24)
            th = self.label_height()
            cx = self.rects[self.hover_index][0]
            lx = min(max(cx - tw / 2.0, 4.0), max(4.0, self.width() - tw - 4.0))
            ly = self.label_top_y(bar)
            lab = QRectF(lx, ly, tw, th)
            lp = QPainterPath()
            rad = min(th / 2.0, 9.0 * self.ui_mult)
            lp.addRoundedRect(lab, rad, rad)
            p.save()
            p.setOpacity(self.label_alpha)
            p.fillPath(lp, c["label_bg"])
            lg = QLinearGradient(lab.topLeft(), lab.bottomLeft())
            lg.setColorAt(0.0, QColor(255, 255, 255, 44 if not c["light"] else 120))
            lg.setColorAt(1.0, QColor(255, 255, 255, 8 if not c["light"] else 30))
            p.fillPath(lp, QBrush(lg))
            p.setPen(QPen(c["label_border"], 1.0))
            p.setBrush(Qt.NoBrush)
            p.drawPath(lp)
            p.setFont(f)
            p.setPen(c["label_fg"])
            p.drawText(lab, Qt.AlignCenter, name)
            p.restore()

        if not self.items:
            hint = EMPTY_DOCK_HINT if LANG["cur"]!="en" else "Drop apps or shortcuts here\nRight-click: Manage Apps · Settings\nEnable desktop cards in Settings"
            f = QFont("Microsoft YaHei UI", self.font_pt)
            p.setFont(f)
            p.setPen(c["fg"])
            p.drawText(bar, Qt.AlignCenter, hint)
            return

        # 图标 / 分隔符（点击时弹一下：平时以底边为支点往上弹，贴屏幕顶部时反过来）
        down = self.bump_down()
        for i, it in enumerate(self.items):
            cx, w, h, by = self.rects[i][0], self.rects[i][1], self.rects[i][2], self.rects[i][3]
            if self.rects[i][4] or it.get("sep"):
                # 分隔符：一根居中的圆头细竖条，长度约为图标区的 44%
                sh = max(9.0, self.icon_size * 0.44)
                swid = max(1.6, self.icon_size * 0.055)
                dc = QColor(c["fg"])
                dc.setAlpha(96 if c["light"] else 120)
                p.setPen(Qt.NoPen)
                p.setBrush(dc)
                cy = (by + self.icon_size / 2.0) if down else (by - self.icon_size / 2.0)
                p.drawRoundedRect(QRectF(cx - swid / 2.0, cy - sh / 2.0, swid, sh),
                                  swid / 2.0, swid / 2.0)
                continue
            pop = self.pops[i]
            extra = 1.0 + 0.20 * math.sin(math.pi * pop) if pop > 0.0 else 1.0
            dw = w * extra
            dh = h * extra
            top_y = by if down else (by - dh)
            rect = QRectF(cx - dw / 2.0, top_y, dw, dh)
            # 运行中的小圆点：始终在图标【下方】，而且是先画它、再画图标，
            # 所以它的层级低于图标 —— 图标放大盖过来时会挡住圆点，而不是压在图标上面。
            if self.cfg["running_dots"] and it["exe"] and it["exe"] in self.running:
                dot = max(3.0, self.icon_size * 0.075)
                dc = QColor(c["fg"])
                dc.setAlpha(210)
                p.setPen(Qt.NoPen)
                p.setBrush(dc)
                if down:
                    # 贴屏幕顶部时图标是从上边缘向下长的，点放在"静止时图标的下边"
                    dy = by + self.icon_size + dot * 1.4
                else:
                    dy = by + dot * 1.6
                p.drawEllipse(QPointF(cx, dy), dot, dot)
            pm = self.icon_scaled(it, dw)
            if pm is None:
                pass
            elif c.get("tile"):
                # 雾透模式：图标坐在一块白色圆角底板上（iOS 那种观感）
                tile_r = dw * float(c.get("tile_radius", 0.30))
                tile = QRectF(rect)
                # 柔和投影：先画一块略深、往下偏一点的圆角块
                p.setPen(Qt.NoPen)
                p.setBrush(c["tile_shadow"])
                p.drawRoundedRect(tile.adjusted(dw * 0.02, dh * 0.045,
                                                -dw * 0.02, dh * 0.045),
                                  tile_r, tile_r)
                p.setBrush(c["tile_color"])
                p.drawRoundedRect(tile, tile_r, tile_r)
                # 原图标按比例缩小画在底板正中
                k = float(c.get("tile_icon", 0.60))
                iw = dw * k
                ih = dh * k
                p.drawPixmap(QRectF(tile.center().x() - iw / 2.0,
                                    tile.center().y() - ih / 2.0, iw, ih),
                             pm, QRectF(pm.rect()))
            else:
                # 按精确矩形缩放绘制（缓存图只是"接近目标尺寸"的中间图）。
                # 不能直接 1:1 贴：缓存是按 2 像素分档的，直接贴会让图标尺寸
                # 一跳一跳地变（鼠标滑动时看起来就是"抽搐"）。
                p.drawPixmap(rect, pm, QRectF(pm.rect()))

    # ---------------- 背景模糊（自己实现的真毛玻璃） ----------------
    def _capture_behind(self):
        """抓取 Dock 背后真实的桌面画面。

        关键一步：抓图之前先把本窗口标记成"不参与屏幕捕获"
        (WDA_EXCLUDEFROMCAPTURE)，否则会把 Dock 自己拍进去，形成无限套娃。
        抓完立刻恢复原状，所以你自己截图时 Dock 依然会正常出现。
        返回 (截图, 是否成功)。
        """
        from glass_capture import capture_behind,surface_windows
        pixmap=capture_behind(self,surface_windows(self))
        return pixmap,pixmap is not None

    def blur_divisor(self):
        """毛玻璃模糊程度：把背景缩小到 1/div 再放大回来，div 越大越糊。"""
        try:
            from liquid_glass import material_blur
            return material_blur(int(self.cfg.get("blur_px", 6)),self.cfg.get("dock_material","liquid"))
        except Exception:
            return 6

    def refresh_backdrop(self):
        """抓背景 → 缩小再放大（等于一次大半径模糊）→ 作为玻璃后面的画面。"""
        if self.lite_mode:
            self.blur_timer.stop()
            self.backdrop = None
            return
        if self.preview:
            return
        if not self.cfg["glass"] or self.cfg.get('clear_background', False) or self.cfg.get('dock_material') in ('clear','solid'):
            # 关掉毛玻璃：完全不抓屏，直接用半透明底色
            self.blur_timer.stop()
            if self.backdrop is not None:
                self.backdrop = None
                self.update()
            return
        pm, ok = self._capture_behind()
        if not ok:
            if self.backdrop_ok is not False:
                self.backdrop_ok = False
                log("本机不支持屏幕捕获排除，毛玻璃降级为普通半透明（不影响使用）")
            self.backdrop = None
            self.update()
            return
        if pm is None or pm.isNull():
            return
        self.backdrop_ok = True
        try:
            dpr = float(pm.devicePixelRatio()) or 1.0
            div = self.blur_divisor()
            w, h = max(2, pm.width() // div), max(2, pm.height() // div)
            small = pm.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            small = small.scaled(max(1, w // 2), max(1, h // 2),
                                 Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            # 注意：要还原成"设备像素"尺寸并标好缩放比，
            # 否则在 125%/150%/200% 缩放的屏幕上玻璃里的画面会被拉糊。
            out = small.scaled(max(1, int(round(self.width() * dpr))),
                               max(1, int(round(self.height() * dpr))),
                               Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            out.setDevicePixelRatio(dpr)
            self.backdrop = out
        except Exception:
            log("模糊处理失败: " + traceback.format_exc())
            return
        self.update()

    def start_backdrop(self):
        if self.lite_mode or self.cfg.get('clear_background', False) or self.cfg.get('dock_material') in ('clear','solid'):
            self.blur_timer.stop()
            self.backdrop = None
            return
        if self.preview:
            return
        mode = str(self.cfg.get("blur_mode", "smart"))
        self.blur_timer.setInterval(BLUR_INTERVAL.get(mode, BLUR_INTERVAL["smart"]))
        if not self._logged_once:
            self._logged_once = True
            try:
                scr = QGuiApplication.primaryScreen()
                try:
                    dpi_sys = int(user32.GetDpiForSystem())
                except Exception:
                    dpi_sys = -1
                try:
                    dpi_win = int(user32.GetDpiForWindow(wintypes.HWND(int(self.winId()))))
                except Exception:
                    dpi_win = -1
                log("屏幕=%dx%d 可用=%dx%d 缩放=%s 系统DPI=%d 窗口DPI=%d 倍率=%.2f 图标=%d 窗口=%dx%d 位置=(%d,%d) 毛玻璃=%s 层级=%s 抓取=%s"
                    % (scr.geometry().width(), scr.geometry().height(),
                       scr.availableGeometry().width(), scr.availableGeometry().height(),
                       scr.devicePixelRatio(), dpi_sys, dpi_win, self.ui_mult, self.icon_size,
                       self.width(), self.height(), self.x(), self.y(), self.cfg["glass"],
                       self.cfg.get("layer", "bottom"), mode))
            except Exception:
                pass
        if not self.cfg["glass"]:
            self.backdrop = None
            self.blur_timer.stop()
            self.update()
            return
        self.refresh_backdrop()
        if mode == "off":
            # "停止抓取"：只抓这一次，之后一次都不再抓。
            # Dock 在桌面层，背后永远只有壁纸，所以这一张画面可以一直用下去。
            self.blur_timer.stop()
        elif self.backdrop_ok and not self.blur_timer.isActive():
            self.blur_timer.start()

    def showEvent(self, e):
        super(Dock, self).showEvent(e)
        QTimer.singleShot(50, self.start_backdrop)
        self.apply_layer()
        QTimer.singleShot(0,self.apply_layer)
        QTimer.singleShot(250,self.apply_layer)
        QTimer.singleShot(1000,self.apply_layer)

    def hideEvent(self, e):
        self.blur_timer.stop()
        super(Dock, self).hideEvent(e)

    def closeEvent(self, e):
        # Session shutdown must not turn a temporary native hide into user intent.
        if QApplication.instance().isSavingSession():
            e.accept();return
        # 关闭 Dock 窗口 = 退出整个程序
        try:
            QApplication.instance().quit()
        except Exception:
            pass
        super(Dock, self).closeEvent(e)

    def reload(self):
        self.base_icon = int(self.cfg["icon_size"])
        self.ui_mult = self._ui_mult()
        self.icon_size = self._scaled(self.base_icon)
        self.font_pt = max(5, int(round(9 * self.ui_mult * getattr(self,'display_scale',1.0))))
        self.pad_x = int(self.icon_size * 0.36)
        self.pad_y = int(self.icon_size * 0.34)
        self.icons.clear()
        self._build_items()
        self.reposition()
        self.start_backdrop()
        self._kick()

    def refresh_geometry(self):
        """只重新算尺寸和位置（比如开关名称显示、开关隔断时布局变了）。

        reposition() 内部已经会算好位置、调整窗口大小并重算图标坐标，
        这里不用再重复一遍。
        """
        self.reposition()
        self.start_backdrop()
        self._kick()


# ----------------------------------------------------------------------------
# 托盘图标
# ----------------------------------------------------------------------------
_TRAY_ICON_CACHE = []


def make_tray_icon(size=64):
    """托盘图标：优先用程序目录里的 dock.ico（软件图标），拿不到就自己画一个。"""
    if _TRAY_ICON_CACHE:
        return _TRAY_ICON_CACHE[0]
    icon = None
    try:
        p = os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "assets", "dock.ico")
        if os.path.exists(p):
            ic = QIcon(p)
            if not ic.isNull():
                icon = ic
    except Exception:
        icon = None
    if icon is None:
        # 打包成 exe 后如果没带 ico 文件，就从 exe 自身把图标抠出来
        try:
            if IS_FROZEN:
                pm = IconProvider().get(SCRIPT_PATH, 128)
                if pm is not None and not pm.isNull():
                    icon = QIcon(pm)
        except Exception:
            icon = None
    if icon is None:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(2, 2, size - 4, size - 4)
        path = QPainterPath()
        path.addRoundedRect(r, size * 0.28, size * 0.28)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0.0, QColor(110, 195, 255))
        g.setColorAt(1.0, QColor(178, 140, 255))
        p.fillPath(path, QBrush(g))
        p.setPen(QPen(QColor(255, 255, 255, 190), 2))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 235))
        d = size * 0.11
        for i in (-1, 0, 1):
            p.drawEllipse(QPointF(size / 2.0 + i * size * 0.26, size / 2.0), d, d)
        p.end()
        icon = QIcon(pm)
    _TRAY_ICON_CACHE.append(icon)
    return icon


class DockTray(QSystemTrayIcon):
    def __init__(self, dock):
        super(DockTray, self).__init__(make_tray_icon())
        self.dock = dock
        self.cfg = dock.cfg
        set_lang(self.cfg.get("lang", "zh"))     # 按配置设好界面语言
        self.menu = QMenu()
        self.setContextMenu(self.menu)
        self.menu.aboutToShow.connect(self.rebuild)
        self.activated.connect(self._activated)
        self.rebuild()
        self.setToolTip(APP_TITLE + " —— 右键管理图标")

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.menu.popup(QCursor.pos())

    # ---------- 菜单 ----------
    def rebuild(self):
        from tray_menu import rebuild
        rebuild(self)

    def _show_dock(self):
        self.dock.reposition()
        self.dock.show()
        self.dock.apply_layer()
        self.dock.start_backdrop()

    def show_settings(self):
        from usage_stats import record
        record(self.dock,'settings_open')
        if hasattr(self, 'runtime'):
            self.runtime.settings_open = True
            self.runtime.lite_timer.stop()
            if self.runtime.lite:
                self.runtime.set_lite(False)
        if not hasattr(self, 'settings_dialog'):
            from settings_dialog import SettingsDialog
            # Use this module's globals even when launched as the frozen __main__.
            self.settings_dialog = SettingsDialog(self, sys.modules[__name__])
        if hasattr(self, 'runtime') and not getattr(self.settings_dialog, '_runtime_bound', False):
            self.settings_dialog.finished.connect(lambda _: self.runtime.settings_closed())
            self.settings_dialog._runtime_bound = True
        if self.settings_dialog.isVisible() and not self.settings_dialog.isMinimized():
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
        else:
            self.settings_dialog.reveal()

    def add_icons(self):
        start = ""
        dirs = start_menu_dirs()
        if dirs:
            start = dirs[0]
        files, _ = QFileDialog.getOpenFileNames(
            None,
            T("选择要固定到 Dock 的程序（可多选）"),
            start,
            T("程序与快捷方式 (*.exe *.lnk *.bat *.cmd *.url *.msc *.ps1);;所有文件 (*.*)"))
        if not files:
            return
        if hasattr(self, 'importer'):
            self.importer.pin([{'path': f} for f in files])
            self.runtime.set_dock_visible(True) if hasattr(self,'runtime') else self._show_dock()
            return
        added = 0
        for f in files:
            f = os.path.abspath(f)
            if any((not it.get("sep")) and str(it.get("path", "")).lower() == f.lower()
                   for it in self.cfg["items"]):
                continue
            name = os.path.splitext(os.path.basename(f))[0]
            self.cfg["items"].append({"path": f, "name": name})
            added += 1
        save_config(self.cfg)
        self.dock.reload()
        self.runtime.set_dock_visible(True) if hasattr(self,'runtime') else self._show_dock()
        if added:
            self.showMessage(APP_TITLE, T("已添加 %d 个图标到 Dock") % added, make_tray_icon(), 2000)

    def add_separator(self,index=None):
        items=[dict(item) for item in self.cfg['items']]
        slot=max(0,min(len(items),index)) if type(index) is int else len(items)
        items.insert(slot,{'sep':True})
        if self.importer.apply_items(items):
            self.runtime.set_dock_visible(True) if hasattr(self,'runtime') else self._show_dock()

    def remove_separator(self,index=None,snapshot=None):
        current=self.cfg['items']
        if snapshot is not None and current!=snapshot:
            self.showMessage(APP_TITLE,'Dock 列表已变化，请重新打开菜单后操作。',self.icon(),3000);return False
        if index is None:items=[dict(item) for item in current if not item.get('sep')]
        elif type(index) is int and 0<=index<len(current) and current[index].get('sep'):
            items=[dict(item) for i,item in enumerate(current) if i!=index]
        else:return False
        return self.importer.apply_items(items)

    def remove_index(self, idx):
        try:
            self.cfg["items"].pop(idx)
        except Exception:
            return
        save_config(self.cfg)
        self.dock.reload()

    def set_icon_size(self, px):
        self.cfg["icon_size"] = int(px)
        save_config(self.cfg)
        self.dock.reload()

    def set_bump(self, key):
        self.cfg["bump_level"] = str(key)
        save_config(self.cfg)
        self.dock.update()

    def set_language(self, val):
        self.cfg["lang"] = "en" if str(val) == "en" else "zh"
        save_config(self.cfg)
        set_lang(self.cfg["lang"])
        self.rebuild()                    # 菜单立刻换成对应语言
        self.dock.update()                # Dock 上的提示文字也跟着换

    def set_blur(self, val):
        self.cfg["blur_px"] = int(val)
        save_config(self.cfg)
        self.dock.refresh_backdrop()      # 立刻按新的模糊程度重抓一次

    def ask_blur(self):
        cur = int(self.cfg.get("blur_px", 6))
        val, ok = QInputDialog.getInt(
            None, APP_TITLE,
            T("毛玻璃模糊强度：\n（3 ~ 30，数字越大越模糊、越朦胧）"),
            cur, 3, 30, 1)
        if ok:
            self.set_blur(val)

    def set_transparency(self, val):
        self.cfg["transparency"] = int(val)
        save_config(self.cfg)
        self.dock.update()

    def set_theme(self, val):
        self.cfg["theme"] = val
        save_config(self.cfg)
        if val == "auto":
            self.dock._sys_light = system_is_light()
        from ui_style import apply_theme
        apply_theme(QApplication.instance(), self.dock.is_light())
        self.dock.update()

    def set_layer(self, val):
        self.cfg["layer"] = val
        save_config(self.cfg)
        self.dock.apply_layer()

    def set_position(self, val):
        if val == "custom":
            self.ask_custom_position()
            return
        self.cfg["position"] = val
        save_config(self.cfg)
        self.dock.reposition()
        self.dock.refresh_backdrop()      # 换了位置，背后的画面也要重抓一次

    def ask_custom_position(self):
        cur = int(self.cfg.get("custom_bottom", 200))
        val, ok = QInputDialog.getInt(
            None, APP_TITLE,
            T("玻璃条距离屏幕底部多少像素？\n（Dock 始终水平居中，数字越大越往上）"),
            cur, 0, 2000, 5)
        if not ok:
            return
        self.cfg["custom_bottom"] = int(val)
        self.cfg["position"] = "custom"
        save_config(self.cfg)
        self.dock.reposition()
        self.dock.refresh_backdrop()      # 换了位置，背后的画面也要重抓一次

    def set_blur_mode(self, val):
        self.cfg["blur_mode"] = val
        save_config(self.cfg)
        self.dock.start_backdrop()

    def refresh_now(self):
        self.dock.refresh_backdrop()

    def custom_icon_size(self):
        cur = int(self.cfg["icon_size"])
        val, ok = QInputDialog.getInt(
            None, APP_TITLE,
            T("请输入图标像素大小：\n（建议 32 ~ 160，数字越大图标越大）"),
            cur, 20, 256, 1)
        if ok:
            self.set_icon_size(val)

    def set_flag(self, key, value, glass=False, running=False, geometry=False):
        self.cfg[key] = bool(value)
        save_config(self.cfg)
        if glass:
            self.dock.start_backdrop()
        if running:
            self.dock.refresh_running()
        if geometry:
            self.dock.refresh_geometry()
        self.dock.update()

    def toggle_autostart(self, value):
        ok = set_autostart(bool(value))
        self.cfg["autostart"] = bool(value)
        save_config(self.cfg)
        if ok:
            self.showMessage(APP_TITLE,
                             T("已开启开机自启动") if value else T("已取消开机自启动"),
                             make_tray_icon(), 2000)
        else:
            QMessageBox.warning(None, APP_TITLE, T("设置失败，请查看日志：\n") + LOG_PATH)

    def open_readme(self):
        for name in ("使用说明.txt", "使用说明.md"):
            p = os.path.join(APP_DIR, name)
            if os.path.exists(p):
                from external_launch import startfile
                startfile(p)
                return
        QMessageBox.information(None, APP_TITLE, "将应用或快捷方式拖入 Dock，或右键打开应用批量管理、设置。桌面卡片可在设置中开启。")


# ----------------------------------------------------------------------------
# 预览模式（用于截图检查外观，不影响正常使用）
# ----------------------------------------------------------------------------
def run_preview(out_path, hover_index=None, size_px=None):
    app = QApplication(sys.argv)
    cfg = load_config()
    if not cfg["items"]:
        demo = []
        for p in (r"C:\Windows\explorer.exe", r"C:\Windows\system32\notepad.exe",
                  r"C:\Windows\system32\mspaint.exe", r"C:\Windows\system32\calc.exe",
                  r"C:\Windows\system32\cmd.exe", r"C:\Windows\system32\mstsc.exe",
                  r"C:\Windows\system32\control.exe"):
            if os.path.exists(p):
                demo.append({"path": p, "name": os.path.splitext(os.path.basename(p))[0]})
        cfg["items"] = demo
    if size_px:
        cfg["icon_size"] = int(size_px)
    dock = Dock(cfg, None, preview=True)
    dock.show()
    app.processEvents()
    if hover_index is not None and 0 <= hover_index < len(dock.items):
        cx = dock.rects[hover_index][0]
        dock.mouse_x = cx
        dock.mouse_smooth = cx
        dock.stretch = 1.0
        dock.stretch_target = 1.0
        dock.spec_x = cx
        dock.spec_alpha = 1.0
        dock.spec_target = 1.0
        dock.hover_index = hover_index
        dock._recalc()
        dock.cur = list(dock.tgt)
        dock._layout()
    app.processEvents()

    # 造一个假的桌面背景，方便看毛玻璃质感
    W, H = 1400, 460
    bg = QImage(W, H, QImage.Format_ARGB32)
    bp = QPainter(bg)
    bp.setRenderHint(QPainter.Antialiasing, True)
    g = QLinearGradient(0, 0, W, H)
    g.setColorAt(0.0, QColor(28, 42, 92))
    g.setColorAt(0.45, QColor(96, 74, 150))
    g.setColorAt(0.75, QColor(196, 108, 140))
    g.setColorAt(1.0, QColor(240, 176, 120))
    bp.fillRect(0, 0, W, H, QBrush(g))
    bp.setBrush(QColor(255, 255, 255, 26))
    bp.setPen(Qt.NoPen)
    for i in range(9):
        bp.drawEllipse(QPointF(W * (0.08 + i * 0.11), H * (0.25 + 0.4 * math.sin(i))), 90, 90)
    bp.end()

    pm = QPixmap(dock.size())
    pm.fill(Qt.transparent)
    dock.render(pm)
    out = QImage(W, H, QImage.Format_ARGB32)
    out.fill(Qt.transparent)
    op = QPainter(out)
    op.drawImage(0, 0, bg)
    x = (W - pm.width()) // 2
    y = H - 46 - pm.height()
    op.drawPixmap(x, y, pm)
    op.end()
    out.save(out_path)
    print("预览已保存:", out_path, "尺寸:", pm.width(), "x", pm.height())
    return 0


# ----------------------------------------------------------------------------
# 主程序
# ----------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    probe = None
    if '--startup-test' in args:
        from startup_probe import StartupProbe
        probe = StartupProbe(args, sys.modules[__name__])

    if '--clipboard-test' in args:
        from clipboard_tests import run
        return run(args[args.index('--clipboard-test')+1])

    if '--runtime-check' in args:
        from current_ui_tests import run
        return run(args[args.index('--runtime-check')+1])

    if '--self-test' in args:
        from smoke_test import run
        return run(args[args.index('--self-test') + 1])

    if "--stop" in args:
        try:
            user32.FindWindowW.restype = wintypes.HWND
            user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            hwnd = user32.FindWindowW(None, APP_TITLE)
            if hwnd:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
                print("已通知 Dock 退出。")
            else:
                print("没有找到正在运行的 Dock。")
        except Exception:
            print("退出失败：" + traceback.format_exc())
        return 0

    if "--reset" in args:
        cfg = load_config()
        cfg["items"] = []
        save_config(cfg)
        print("已清空 Dock 上固定的图标。")
        return 0

    if "--preview" in args:
        i = args.index("--preview")
        out = args[i + 1] if len(args) > i + 1 else "preview.png"
        hover = None
        if "--hover" in args:
            try:
                hover = int(args[args.index("--hover") + 1])
            except Exception:
                hover = None
        size_px = None
        if "--size" in args:
            try:
                size_px = int(args[args.index("--size") + 1])
            except Exception:
                size_px = None
        return run_preview(out, hover, size_px)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 关掉窗口不退出，常驻托盘
    app.setApplicationName(APP_TITLE)

    # 只允许运行一个实例
    shm = QSharedMemory(COMPAT_NAME + (('_test_'+os.environ['FISHDOCK_TEST_DESKTOP']) if probe else "_single_instance"))
    if not shm.create(1):
        if "--autostart" in args: return 0
        cfg0 = load_config()
        set_lang(cfg0.get("lang", "zh"))
        user32.FindWindowW.restype = wintypes.HWND
        user32.PostMessageW.argtypes = [wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        handle = user32.FindWindowW(None,APP_TITLE)
        if handle and user32.PostMessageW(handle,WM_OPEN_SETTINGS,0,0): return 0
        QMessageBox.information(None,APP_TITLE,'大肥鱼Dock 已在运行，请从 Dock 右键进入设置。')
        return 0

    if not probe:
        migrate_legacy()          # 从旧名字迁移配置 + 清理旧自启动项
    cfg = load_config()
    set_lang(cfg.get("lang", "zh"))

    state = {}

    def initialize():
        from platform_services import set_priority
        set_priority(cfg['startup_priority'])
        dock = Dock(cfg)
        tray = DockTray(dock)
        dock.tray = tray
        from batch_import import BatchImporter
        tray.importer = BatchImporter(dock, tray, save_config, log)
        from ui_style import apply_theme
        apply_theme(app, dock.is_light())
        tray.setVisible(not cfg['hide_tray'])
        if cfg.get('autostart'):
            set_autostart(True)
        if cfg.get('dock_visible', True):
            dock.show()
            dock.start_backdrop()
        from runtime_controller import RuntimeController
        tray.runtime = RuntimeController(dock, tray, sys.modules[__name__])
        dock.winId()  # A hidden instance still needs its settings-wake HWND.
        state.update(dock=dock, tray=tray, runtime=tray.runtime)
        if probe:
            QTimer.singleShot(200, lambda: probe.complete(state))
        if cfg['check_updates_on_start']:
            QTimer.singleShot(2000, tray.runtime.updater.check)
        log('启动完成，共 %d 个入口' % len(cfg['items']))

    delay_ms = cfg['startup_delay']*1000 if '--autostart' in args else 0
    QTimer.singleShot(delay_ms, initialize)
    try:
        return app.exec_()
    finally:
        if state.get('runtime'): state['runtime'].close()
        if state.get('tray') and getattr(state['tray'], 'importer', None): state['tray'].importer.close()
        from ui_style import shutdown_ui
        shutdown_ui(app)


if __name__ == "__main__":
    sys.exit(main())
