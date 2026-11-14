@echo off
rem Starts the ML UI at http://localhost:8501 (only reachable from this machine). Ctrl+C stops the UI; running jobs keep going.
cd /d "%~dp0.."
py -m streamlit run ml/ui.py --server.address localhost --server.port 8501 --client.toolbarMode viewer --browser.gatherUsageStats false %*
if errorlevel 9009 python -m streamlit run ml/ui.py --server.address localhost --server.port 8501 --client.toolbarMode viewer --browser.gatherUsageStats false %*
