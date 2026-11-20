"""Checks that THIS Python has the ML UI's packages; prints the exact command to fix it when not.

    python ml/check_env.py          (exit code 0 = ready, 1 = packages missing)

Used by ml/start-ui.cmd / start-ui.sh and by the Dashboard's 「啟動 ML UI」 button before the ML UI starts.
A common trap on Windows: two Pythons (e.g. Anaconda and python.org) where `pip` installs into one and the ML UI runs
with the other. The fix command therefore names this interpreter explicitly ("<path>" -m pip install ...).
"""
import importlib.util
import os
import sys

# module name -> pip package (ml/requirements.txt)
REQUIRED = {"streamlit": "streamlit", "lightgbm": "lightgbm", "numpy": "numpy", "pandas": "pandas", "altair": "altair"}


def missing_modules():
    return [m for m in REQUIRED if importlib.util.find_spec(m) is None]


def fix_command():
    req = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    return f'"{sys.executable}" -m pip install -r "{req}"'


TEXT = {
    "en": ("This Python is missing packages the ML UI needs: {names}", "Python: {python}",
           "Run this line (it uses the same Python, so nothing is installed into another one):"),
    "zh-TW": ("這個 Python 缺少 ML UI 需要的套件：{names}", "Python：{python}",
              "請執行這一行（用的是同一個 Python，不會裝到別的 Python 去）："),
}


def main(argv=None):
    """Language of the report: --lang en|zh-TW, else the PR_LANG environment variable, else English."""
    argv = list(sys.argv[1:] if argv is None else argv)
    lang = argv[argv.index("--lang") + 1] if "--lang" in argv and argv.index("--lang") + 1 < len(argv) else os.environ.get("PR_LANG", "en")
    first, second, third = TEXT.get(lang, TEXT["en"])
    missing = missing_modules()
    if not missing:
        print(f"ML UI packages OK ({sys.executable})")
        return 0
    print(first.format(names=", ".join(missing)))
    print(second.format(python=sys.executable))
    print(third)
    print(fix_command())
    return 1


if __name__ == "__main__":
    sys.exit(main())
