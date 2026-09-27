"""Small Windows collector and explicit normal-close adapter. Never force-kills."""

from __future__ import annotations

import ctypes
import hashlib
import os
import time
from ctypes import wintypes

import psutil

from .core import Item

NAMES = {
    "msedge.exe": "Microsoft Edge",
    "chrome.exe": "Google Chrome",
    "code.exe": "Visual Studio Code",
    "notepad.exe": "记事本",
    "explorer.exe": "文件资源管理器",
    "wechat.exe": "微信",
    "weixin.exe": "微信",
    "qq.exe": "QQ",
    "steam.exe": "Steam",
    "epicgameslauncher.exe": "Epic Games",
    "codex.exe": "Codex",
    "windowsterminal.exe": "Windows Terminal",
    "obs64.exe": "OBS Studio",
}
PROTECTED = {
    "system",
    "registry",
    "idle",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "dwm.exe",
    "explorer.exe",
    "msmpeng.exe",
    "securityhealthservice.exe",
    "sihost.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe",
    "ctfmon.exe",
    "fontdrvhost.exe",
    "audiodg.exe",
    "codex.exe",
}
COMPLEX = {
    "msedge.exe",
    "chrome.exe",
    "firefox.exe",
    "code.exe",
    "devenv.exe",
    "obs64.exe",
    "powershell.exe",
    "pwsh.exe",
    "cmd.exe",
    "windowsterminal.exe",
    "conhost.exe",
}


def user32():
    dll = ctypes.WinDLL("user32", use_last_error=True)
    dll.GetForegroundWindow.restype = wintypes.HWND
    dll.IsWindow.argtypes = [wintypes.HWND]
    dll.IsWindowVisible.argtypes = [wintypes.HWND]
    dll.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    dll.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    return dll


def foreground() -> tuple[int, int]:
    if os.name != "nt":
        return 0, 0
    dll = user32()
    hwnd = dll.GetForegroundWindow()
    pid = wintypes.DWORD()
    dll.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value, int(hwnd or 0)


def visible_windows() -> dict[int, list[int]]:
    if os.name != "nt":
        return {}
    dll = user32()
    result: dict[int, list[int]] = {}
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd, _):
        if dll.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            dll.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                result.setdefault(pid.value, []).append(int(hwnd))
        return True

    dll.EnumWindows(visit, 0)
    return result


def fullscreen_other() -> bool:
    if os.name != "nt":
        return False
    dll = user32()
    pid, hwnd = foreground()
    if not hwnd or pid == os.getpid():
        return False
    dll.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    dll.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    dll.MonitorFromWindow.restype = wintypes.HANDLE

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("flags", wintypes.DWORD),
        ]

    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    rect = wintypes.RECT()
    monitor = dll.MonitorFromWindow(hwnd, 2)
    dll.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    if not dll.GetMonitorInfoW(monitor, ctypes.byref(info)) or not dll.GetWindowRect(
        hwnd, ctypes.byref(rect)
    ):
        return False
    # Explorer's desktop covers a monitor but is not a full-screen work session.
    try:
        if psutil.Process(pid).name().lower() == "explorer.exe":
            return False
    except psutil.Error:
        return False
    return (
        rect.left <= info.rcMonitor.left
        and rect.top <= info.rcMonitor.top
        and rect.right >= info.rcMonitor.right
        and rect.bottom >= info.rcMonitor.bottom
    )


class ProcessReader:
    """Fail cheaply on protected processes; avoid psutil's expensive Windows fallback scans."""

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "peak_ws",
                "rss",
                "peak_paged",
                "paged",
                "peak_nonpaged",
                "nonpaged",
                "pagefile",
                "peak_pagefile",
                "private_commit",
            )
        ]

    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.kernel.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(self.Counters),
            wintypes.DWORD,
        ]

    def read(self, pid: int, cache: dict) -> dict | None:
        handle = self.kernel.OpenProcess(0x1000 | 0x0010, False, pid)
        if not handle:
            return None
        try:
            created, exited, kernel, user = [wintypes.FILETIME() for _ in range(4)]
            if not self.kernel.GetProcessTimes(
                handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)
            ):
                return None
            birth = ((created.dwHighDateTime << 32) | created.dwLowDateTime) / 10_000_000 - 11644473600
            memory = self.Counters()
            memory.cb = ctypes.sizeof(memory)
            if not self.psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
                return None
            key = (pid, birth)
            if key not in cache:
                length = wintypes.DWORD(32768)
                buffer = ctypes.create_unicode_buffer(length.value)
                if not self.kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                    return None
                path = buffer.value
                try:
                    owner = psutil.Process(pid).username()
                except psutil.Error:
                    return None
                cache[key] = (path, hashlib.sha256(path.casefold().encode()).hexdigest()[:24], owner)
            path, stable, owner = cache[key]
            return {
                "pid": pid,
                "create_time": birth,
                "rss": memory.rss,
                "name": os.path.basename(path),
                "path": path,
                "stable": stable,
                "username": owner,
            }
        finally:
            self.kernel.CloseHandle(handle)


class Collector:
    def __init__(self):
        self.last_work_pid = 0
        self.cache: dict[tuple[int, float], tuple[str, str, str]] = {}
        self.self_cpu = psutil.Process()
        self.self_cpu.cpu_percent(None)
        self.own_user = self.self_cpu.username()
        self.own_tree = {os.getpid(), *[p.pid for p in self.self_cpu.parents()]}
        self.reader = ProcessReader() if os.name == "nt" else None

    def sample(self) -> dict:
        memory = psutil.virtual_memory()
        own = self.self_cpu.memory_info()
        return {
            "at": time.time(),
            "total": memory.total,
            "available": memory.available,
            "used_percent": memory.percent,
            "own_rss": own.rss,
            "own_cpu_one_core_percent": self.self_cpu.cpu_percent(None),
        }

    def collect(self, now: float) -> list[Item]:
        if os.name != "nt":
            return []
        windows = visible_windows()
        active_pid, _ = foreground()
        if active_pid and active_pid != os.getpid():
            self.last_work_pid = active_pid
        groups: dict[str, list[dict]] = {}
        live_keys = set()
        for pid in psutil.pids():
            info = self.reader.read(pid, self.cache)
            if info:
                live_keys.add((pid, info["create_time"]))
                groups.setdefault(info["stable"], []).append(info)
        self.cache = {key: value for key, value in self.cache.items() if key in live_keys}
        items = []
        for stable, group in groups.items():
            group.sort(key=lambda p: (p["pid"] not in windows, p["create_time"], p["pid"]))
            p = group[0]
            name = p["name"].lower()
            pids = {n["pid"] for n in group}
            active = bool(pids & {active_pid, self.last_work_pid})
            protection = []
            if name in PROTECTED or any(n["username"] != self.own_user for n in group):
                protection.append("系统或受保护应用")
            if pids & self.own_tree:
                protection.append("助手及其运行环境")
            if active:
                protection.append("正在使用")
            hwnds = [h for pid in pids for h in windows.get(pid, [])]
            closeable = len(hwnds) == 1 and name not in PROTECTED | COMPLEX and not protection
            # A visible normal-close target is manual only. There is no universal saved-state API.
            hwnd = hwnds[0] if closeable else 0
            if hwnd:
                for candidate in group:
                    if hwnd in windows.get(candidate["pid"], []):
                        p = candidate
                        break
            memory = sum(n["rss"] for n in group)
            items.append(
                Item(
                    id=f"process:{p['pid']}:{p['create_time']}",
                    stable_key=f"app:{stable}",
                    name=NAMES.get(name, p["name"].removesuffix(".exe")),
                    kind="app",
                    observed_at=now,
                    version=f"{p['pid']}:{p['create_time']}:{hwnd}",
                    memory_bytes=memory,
                    active=active,
                    protections=tuple(protection),
                    allowed_action="request_exit" if closeable else "none",
                    auto_eligible=False,
                    pid=p["pid"],
                    created=p["create_time"],
                    hwnd=hwnd,
                    details="占用为进程工作集之和，可能包含共享页面；不代表可释放量。",
                )
            )
        return sorted(items, key=lambda i: -(i.memory_bytes or 0))


def request_normal_close(item: Item) -> tuple[bool, str]:
    """Requires a user-selected live Item; WM_CLOSE can prompt to save or only hide to tray."""
    if os.name != "nt" or not item.hwnd or item.allowed_action != "request_exit":
        return False, "没有可验证的正常关闭入口"
    try:
        p = psutil.Process(item.pid)
        if abs(p.create_time() - item.created) > 0.01:
            return False, "应用实例已变化"
        active_pid, _ = foreground()
        if (
            item.pid in {active_pid, os.getpid()}
            or item.protections
            or p.name().lower() in PROTECTED | COMPLEX
        ):
            return False, "当前状态需要保留"
        dll = user32()
        actual = wintypes.DWORD()
        dll.GetWindowThreadProcessId(item.hwnd, ctypes.byref(actual))
        if not dll.IsWindow(item.hwnd) or actual.value != item.pid:
            return False, "窗口归属已变化"
        if not dll.PostMessageW(item.hwnd, 0x0010, 0, 0):
            return False, "应用未接受正常关闭请求"
        return True, "已请求正常关闭；如有保存提示请在应用中处理"
    except (psutil.Error, OSError):
        return False, "应用已退出或没有访问权限"


def has_exited(item: Item) -> bool:
    try:
        return abs(psutil.Process(item.pid).create_time() - item.created) > 0.01
    except psutil.NoSuchProcess:
        return True
    except psutil.Error:
        return False
