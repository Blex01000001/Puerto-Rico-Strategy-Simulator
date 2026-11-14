@echo off
rem Starts the ML UI at http://localhost:8501 (only reachable from this machine). Ctrl+C stops the UI; running jobs keep going.
rem Uses the first Python that has the ML UI packages (PR_PYTHON = full path of python.exe to force one).
rem When none is ready, ml\check_env.py prints the exact command to fix it (with the full path of that Python).
cd /d "%~dp0.."
set "PRPY="
if defined PR_PYTHON (
  "%PR_PYTHON%" ml\check_env.py >nul 2>&1 && set "PRPY=%PR_PYTHON%"
  if not defined PRPY ( "%PR_PYTHON%" ml\check_env.py & goto fail )
  goto run
)
for %%C in (python py) do (
  %%C ml\check_env.py >nul 2>&1 && ( set "PRPY=%%C" & goto run )
)
where python >nul 2>&1 && ( python ml\check_env.py & goto fail )
where py >nul 2>&1 && ( py ml\check_env.py & goto fail )
echo Python 3 not found. Install Python 3 (tick "Add to PATH"), then run: python -m pip install -r ml\requirements.txt
:fail
echo.
pause
exit /b 1
:run
"%PRPY%" -m streamlit run ml/ui.py --server.address localhost --server.port 8501 --client.toolbarMode viewer --browser.gatherUsageStats false %*
