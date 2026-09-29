"""Start at login with a LaunchAgent (from the next login on), restarted by launchd if it crashes."""

import plistlib
import subprocess
from pathlib import Path

from platformdirs import user_log_path

LABEL = "com.aiwa.agent"
ACTIVITYWATCH_DIRS = [
    Path("/Applications/ActivityWatch.app/Contents/MacOS"),
    Path.home() / "Applications" / "ActivityWatch.app" / "Contents" / "MacOS",
]
EXECUTABLE_SUFFIX = ""

# system windows that come and go on their own; never worth a question
SYSTEM_APPS = {
    "loginwindow", "Dock", "SystemUIServer", "ControlCenter", "NotificationCenter",
    "UserNotificationCenter", "Spotlight", "ScreenSaverEngine", "SecurityAgent",
    "CoreServicesUIAgent", "universalAccessAuthWarn", "WindowManager", "Window Server",
}
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
    # Not loaded now: macOS loads LaunchAgents at the next login. Loading it
    # here would start a second aiwa next to the one that's running.


def uninstall_autostart() -> None:
    # Only unregister (effective from the next login). Unloading it now would
    # quit the aiwa that's running, if macOS started this one at login.
    PLIST.unlink(missing_ok=True)


def autostart_installed() -> bool:
    return PLIST.exists()


def lock_screen() -> None:
    # Display sleep locks the Mac when "require password after sleep" is on (the default).
    subprocess.Popen(["pmset", "displaysleepnow"])
