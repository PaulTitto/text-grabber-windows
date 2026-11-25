"""Native Windows System Tray & Notification helper using pure Win32 ctypes."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import threading
from typing import Callable

WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
MF_STRING = 0x0000
MF_CHECKED = 0x0008
MF_SEPARATOR = 0x0800

ID_OPEN = 1001
ID_GRAB = 1002
ID_FRAME = 1003
ID_SILENT = 1004
ID_EXIT = 1005

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


class WinTrayIcon:
    """Manages a native Windows system tray icon and balloon notifications."""

    def __init__(
        self,
        icon_path: str,
        tooltip: str,
        on_open: Callable[[], None],
        on_grab: Callable[[], None],
        on_frame: Callable[[], None],
        on_toggle_silent: Callable[[], None],
        is_silent: Callable[[], bool],
        on_exit: Callable[[], None],
    ) -> None:
        self.icon_path = icon_path
        self.tooltip = tooltip[:127]
        self.on_open = on_open
        self.on_grab = on_grab
        self.on_frame = on_frame
        self.on_toggle_silent = on_toggle_silent
        self.is_silent = is_silent
        self.on_exit = on_exit

        self._hwnd: int | None = None
        self._hicon: int | None = None
        self._thread: threading.Thread | None = None
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=1.5)

    def stop(self) -> None:
        if self._hwnd:
            user32 = ctypes.windll.user32
            nid = self._make_nid(0)
            ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            user32.PostMessageW(self._hwnd, WM_DESTROY, 0, 0)
            self._hwnd = None

    def show_toast(self, title: str, message: str) -> None:
        if not self._hwnd:
            return
        nid = self._make_nid(NIF_INFO)
        nid.szInfoTitle = title[:63]
        nid.szInfo = message[:255]
        nid.dwInfoFlags = NIIF_INFO
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _make_nid(self, flags: int) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd or 0
        nid.uID = 1
        nid.uFlags = flags
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._hicon or 0
        nid.szTip = self.tooltip
        return nid

    def _run_loop(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hinst = kernel32.GetModuleHandleW(None)
        class_name = "TextGrabberTrayClass"

        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        self._hwnd = user32.CreateWindowExW(0, class_name, "TextGrabberTray", 0, 0, 0, 0, 0, 0, 0, hinst, 0)
        self._hicon = user32.LoadImageW(0, self.icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if not self._hicon:
            self._hicon = user32.LoadIconW(0, 32512)  # IDI_APPLICATION

        nid = self._make_nid(NIF_MESSAGE | NIF_ICON | NIF_TIP)
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self._ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _show_menu(self) -> None:
        user32 = ctypes.windll.user32
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, ID_GRAB, "Grab Screen (Ctrl+Alt+G)")
        user32.AppendMenuW(menu, MF_STRING, ID_FRAME, "Grab Frame (Ctrl+Alt+F)")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        silent_flag = MF_STRING | (MF_CHECKED if self.is_silent() else 0)
        user32.AppendMenuW(menu, silent_flag, ID_SILENT, "Silent Background Mode")
        user32.AppendMenuW(menu, MF_STRING, ID_OPEN, "Open Text Grabber")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_EXIT, "Exit")

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self._hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, pt.x, pt.y, 0, self._hwnd, None)
        user32.DestroyMenu(menu)

        if cmd == ID_OPEN:
            self.on_open()
        elif cmd == ID_GRAB:
            self.on_grab()
        elif cmd == ID_FRAME:
            self.on_frame()
        elif cmd == ID_SILENT:
            self.on_toggle_silent()
        elif cmd == ID_EXIT:
            self.on_exit()

    def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_TRAYICON:
            if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self.on_open()
            elif lparam == WM_RBUTTONUP:
                self._show_menu()
            return 0
        if msg == WM_DESTROY:
            ctypes.windll.user32.PostQuitMessage(0)
            return 0
        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)
