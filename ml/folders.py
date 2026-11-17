"""Opens a project folder in the file manager of the machine the ML UI runs on (the UI is local, so that is the user's computer).

Only folders inside the project are opened, so a crafted path can never launch anything else."""
import os
import subprocess
import sys


def open_folder(path, root):
    """Opens `path` (a folder, or a file: its folder) in Explorer / Finder / the desktop's file manager.

    Returns (True, "") or (False, reason in Chinese for the user)."""
    folder = os.path.abspath(path)
    if not os.path.isdir(folder):
        folder = os.path.dirname(folder)
    root = os.path.abspath(root)
    if os.path.commonpath([folder, root]) != root:
        return False, "只能開啟專案裡的資料夾"
    if not os.path.isdir(folder):
        return False, "資料夾還不存在"
    try:
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 - a folder inside the project, opened by Explorer
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        return False, f"開不了資料夾（這台機器沒有檔案管理員？）：{e}"
    return True, ""
