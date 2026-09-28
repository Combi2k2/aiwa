"""Start at login through the per-user registry Run key. Not yet tested.

A Windows Service would not work here: services run in an isolated session
and cannot show tray icons or popups.
"""

import subprocess
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "aiwa"


def install_autostart(command: list[str]) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command))


def uninstall_autostart() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, NAME)
    except FileNotFoundError:
        pass


def autostart_installed() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, NAME)
        return True
    except FileNotFoundError:
        return False
