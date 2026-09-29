"""Start at login through an XDG autostart entry. Not yet tested.

Works on GNOME, KDE, XFCE and most desktops. On Wayland, ActivityWatch needs
the `awatcher` window watcher, and popups cannot choose their position.
"""

import shlex
import subprocess
from pathlib import Path

from platformdirs import user_config_path

DESKTOP_FILE = user_config_path("autostart") / "aiwa.desktop"
ACTIVITYWATCH_DIRS = [Path.home() / "activitywatch", Path("/opt/activitywatch"), Path("/usr/lib/activitywatch")]
EXECUTABLE_SUFFIX = ""


def install_autostart(command: list[str]) -> None:
    DESKTOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    DESKTOP_FILE.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=aiwa\n"
        f"Exec={shlex.join(command)}\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def uninstall_autostart() -> None:
    Path(DESKTOP_FILE).unlink(missing_ok=True)


def autostart_installed() -> bool:
    return DESKTOP_FILE.exists()


def lock_screen() -> None:
    subprocess.Popen(["loginctl", "lock-session"])
