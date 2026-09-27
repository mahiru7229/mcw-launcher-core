from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import threading
import time
from typing import Callable

from src.core.system.platform_info import PlatformInfo

logger = logging.getLogger(__name__)


class GameWindowActivator:
    """Monitors and activates the Minecraft game window directly to the foreground."""

    @classmethod
    def allow_foreground(cls, pid: int | None = None) -> bool:
        """Grants permission for the specified process to set the foreground window on Windows."""
        if not PlatformInfo.is_windows():
            return False
        try:
            user32 = ctypes.windll.user32
            # ASFW_ANY = -1 allows any process, or target a specific PID
            target = int(pid) if isinstance(pid, int) and pid > 0 else -1
            result = user32.AllowSetForegroundWindow(target)
            return bool(result)
        except Exception as error:
            logger.debug("AllowSetForegroundWindow failed: %s", error)
            return False

    @classmethod
    def find_window_for_pid(cls, pid: int) -> int | None:
        """Finds the main visible game window handle (HWND) for the given process PID."""
        if not PlatformInfo.is_windows():
            return None
        try:
            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
            user32.EnumWindows.restype = wintypes.BOOL

            matched_hwnd: int | None = None

            def enum_proc(hwnd: int, _lparam: int) -> bool:
                nonlocal matched_hwnd
                try:
                    if not user32.IsWindowVisible(hwnd):
                        return True

                    window_pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))

                    # Filter out 0x0 or tiny dummy helper windows
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    width = rect.right - rect.left
                    height = rect.bottom - rect.top
                    if width < 100 or height < 100:
                        return True

                    if window_pid.value == pid:
                        matched_hwnd = hwnd
                        return False

                    # Secondary check: title contains "Minecraft" while our process is active
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        if "minecraft" in buf.value.casefold():
                            matched_hwnd = hwnd
                            return False
                except Exception:
                    pass

                return True

            cb = WNDENUMPROC(enum_proc)
            user32.EnumWindows(cb, 0)
            return matched_hwnd
        except Exception as error:
            logger.debug("find_window_for_pid failed: %s", error)
            return None

    @classmethod
    def activate_window(cls, hwnd: int) -> bool:
        """Brings the specified window handle to the top foreground and focuses it."""
        if not PlatformInfo.is_windows():
            return False
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            # Restore if minimized
            SW_RESTORE = 9
            user32.ShowWindow(hwnd, SW_RESTORE)

            # Synthesize ALT key press to reset Windows foreground lock timeout
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            current_thread = kernel32.GetCurrentThreadId()
            target_thread = user32.GetWindowThreadProcessId(hwnd, None)
            foreground_hwnd = user32.GetForegroundWindow()
            foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None) if foreground_hwnd else 0

            attached_current = False
            attached_foreground = False
            try:
                if current_thread != target_thread:
                    attached_current = bool(user32.AttachThreadInput(current_thread, target_thread, True))
                if foreground_thread and foreground_thread != target_thread:
                    attached_foreground = bool(user32.AttachThreadInput(foreground_thread, target_thread, True))

                # Pop to top of z-order: HWND_TOPMOST (-1) then HWND_NOTOPMOST (-2)
                user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001)
                user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0040)
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.SetFocus(hwnd)
            finally:
                if attached_current:
                    user32.AttachThreadInput(current_thread, target_thread, False)
                if attached_foreground:
                    user32.AttachThreadInput(foreground_thread, target_thread, False)

            return True
        except Exception as error:
            logger.debug("activate_window failed: %s", error)
            return False

    @classmethod
    def watch_and_activate(
        cls,
        process: object,
        timeout_seconds: float = 90.0,
        poll_interval: float = 0.25,
        on_window_found: Callable[[int], None] | None = None,
    ) -> threading.Thread | None:
        """Watches for the Minecraft window to appear, activates it, and invokes on_window_found."""
        pid = getattr(process, "pid", None)
        if not isinstance(pid, int) or pid <= 0:
            return None

        # Give the process permission to set foreground immediately
        cls.allow_foreground(pid)

        def worker() -> None:
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                poll = getattr(process, "poll", None)
                if callable(poll) and poll() is not None:
                    # Process exited before window appeared
                    break

                hwnd = cls.find_window_for_pid(pid)
                if hwnd is not None:
                    cls.activate_window(hwnd)
                    if on_window_found is not None:
                        try:
                            on_window_found(hwnd)
                        except Exception as cb_err:
                            logger.debug("on_window_found error: %s", cb_err)
                    break

                time.sleep(poll_interval)

        thread = threading.Thread(target=worker, name=f"mcw-window-activator-{pid}", daemon=True)
        thread.start()
        return thread
