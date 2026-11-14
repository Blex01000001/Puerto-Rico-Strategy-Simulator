#!/usr/bin/env sh
# Starts the ML UI at http://localhost:8501 (only reachable from this machine). Ctrl+C stops the UI; running jobs keep going.
# Uses the first Python that has the ML UI packages (PR_PYTHON = path of a python to force one); when none is ready,
# ml/check_env.py prints the exact command to fix it.
cd "$(dirname "$0")/.." || exit 1
for py in ${PR_PYTHON:-python3 python}; do
  if command -v "$py" >/dev/null 2>&1 && "$py" ml/check_env.py >/dev/null 2>&1; then
    exec "$py" -m streamlit run ml/ui.py --server.address localhost --server.port 8501 --client.toolbarMode viewer --browser.gatherUsageStats false "$@"
  fi
done
for py in ${PR_PYTHON:-python3 python}; do
  if command -v "$py" >/dev/null 2>&1; then "$py" ml/check_env.py; exit 1; fi
done
echo "Python 3 not found. Install Python 3, then run: python3 -m pip install -r ml/requirements.txt" >&2
exit 1
