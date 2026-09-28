"""Start at login with a LaunchAgent, restarted by launchd if it crashes."""

import os
import plistlib
import subprocess
from pathlib import Path

from platformdirs import user_log_path

LABEL = "com.aiwa.agent"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def install_autostart(command: list[str]) -> None:
    log = user_log_path("aiwa") / "aiwa.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(
        plistlib.dumps(
            {
                "Label": LABEL,
                "ProgramArguments": command,
                "RunAtLoad": True,
                "KeepAlive": {"SuccessfulExit": False},  # restart only after a crash
                "ProcessType": "Interactive",
                "StandardOutPath": str(log),
                "StandardErrorPath": str(log),
            }
        )
    )
    _launchctl("bootout", str(PLIST))  # replace any previous version
    _launchctl("bootstrap", str(PLIST))


def uninstall_autostart() -> None:
    if PLIST.exists():
        _launchctl("bootout", str(PLIST))
        PLIST.unlink()


def autostart_installed() -> bool:
    return PLIST.exists()


def _launchctl(action: str, plist: str) -> None:
    subprocess.run(
        ["launchctl", action, f"gui/{os.getuid()}", plist],
        check=False,
        capture_output=True,
    )
