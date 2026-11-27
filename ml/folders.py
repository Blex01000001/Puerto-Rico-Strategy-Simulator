"""Opens a project folder in the file manager of the machine the ML UI runs on (the UI is local, so that is the user's computer).

Only folders inside the project are opened, so a crafted path can never launch anything else."""
import os
import subprocess
import sys

import i18n


def open_folder(path, root, lang="zh-TW"):
    """Opens `path` (a folder, or a file: its folder) in Explorer / Finder / the desktop's file manager.

    Returns (True, "") or (False, the reason for the user in `lang`: i18n keys folder.*)."""
    folder = os.path.abspath(path)
    if not os.path.isdir(folder):
        folder = os.path.dirname(folder)
    root = os.path.abspath(root)
    if os.path.commonpath([folder, root]) != root:
        return False, i18n.translate(lang, "folder.outside")
    if not os.path.isdir(folder):
        return False, i18n.translate(lang, "folder.missing")
    try:
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 - a folder inside the project, opened by Explorer
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        return False, i18n.translate(lang, "folder.no_manager", error=e)
    return True, ""
