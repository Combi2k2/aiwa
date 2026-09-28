"""The only OS-specific code. Each module exposes the same interface:

    install_autostart(command: list[str]) -> None
    uninstall_autostart() -> None
    autostart_installed() -> bool
    ACTIVITYWATCH_DIRS: list[Path]   where ActivityWatch's programs usually are
    EXECUTABLE_SUFFIX: str           "" or ".exe"
"""

import sys
from types import ModuleType


def current() -> ModuleType:
    if sys.platform == "darwin":
        from aiwa.platforms import macos as mod
    elif sys.platform == "win32":
        from aiwa.platforms import windows as mod
    elif sys.platform.startswith("linux"):
        from aiwa.platforms import linux as mod
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
    return mod
