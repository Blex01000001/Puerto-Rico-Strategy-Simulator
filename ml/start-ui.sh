#!/usr/bin/env sh
# Starts the ML UI at http://localhost:8501 (only reachable from this machine). Ctrl+C stops the UI; running jobs keep going.
cd "$(dirname "$0")/.." || exit 1
exec python3 -m streamlit run ml/ui.py --server.address localhost --server.port 8501 --client.toolbarMode viewer --browser.gatherUsageStats false "$@"
