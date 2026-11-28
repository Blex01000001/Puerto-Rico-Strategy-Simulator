@echo off
rem Updates the program from GitHub (git pull) and starts the ML UI again.
rem Close the ML UI window first. Jobs running in the background are not stopped by closing the UI.
rem Your own files (ml\local, results, publish) are ignored by git and are never touched.
cd /d "%~dp0.."

where git >nul 2>&1 || ( echo git is not installed or not on PATH. & goto fail )
git rev-parse --is-inside-work-tree >nul 2>&1 || ( echo This folder is not a git clone, so it cannot be updated with git pull. & goto fail )

rem 1. the ML UI must be closed (it keeps the old program in memory)
netstat -ano | findstr /R /C:":8501 .*LISTENING" >nul 2>&1
if not errorlevel 1 ( echo The ML UI is still running on port 8501. Close its window first, then run this again. & goto fail )

rem 2. a Python for the job check and the packages: the first one that already has the ML UI packages, else the first one found
set "PRPY="
if defined PR_PYTHON set "PRPY=%PR_PYTHON%"
if not defined PRPY (
  for %%C in (python py) do (
    if not defined PRPY ( %%C ml\check_env.py >nul 2>&1 && set "PRPY=%%C" )
  )
)
if not defined PRPY (
  for %%C in (python py) do (
    if not defined PRPY ( where %%C >nul 2>&1 && set "PRPY=%%C" )
  )
)
if not defined PRPY ( echo Python 3 not found. Install Python 3 ^(tick "Add to PATH"^) and run this again. & goto fail )

rem 3. jobs that are running or queued
"%PRPY%" ml\update_check.py
if errorlevel 2 (
  echo.
  echo The jobs above are still running or queued. Updating is safe for jobs that are already running
  echo ^(they keep the old program until they finish^), but a new job will use the new one.
  choice /c YN /m "Update anyway"
  if errorlevel 2 goto cancelled
)

rem 4. changes you made to tracked files would block the update: show them instead of overwriting anything
set "DIRTY="
for /f "delims=" %%L in ('git status --porcelain --untracked-files=no') do set "DIRTY=1"
if defined DIRTY (
  echo These tracked files were changed on this computer, so the update was not started:
  git status --short --untracked-files=no
  echo Ask for help before discarding them ^(git restore ^<file^) so nothing you need is lost.
  goto fail
)

rem 5. update (fast-forward only: it never creates a merge or overwrites local work)
for /f %%H in ('git rev-parse HEAD') do set "OLD=%%H"
git pull --ff-only
if errorlevel 1 ( echo. & echo git pull failed ^(see the message above^). Nothing was changed. & goto fail )
for /f %%H in ('git rev-parse HEAD') do set "NEW=%%H"

echo.
if "%OLD%"=="%NEW%" (
  echo Already up to date.
) else (
  echo Updated. What changed:
  git log --oneline --no-decorate %OLD%..%NEW%
  git diff --name-only %OLD% %NEW% -- Engine Runner Directory.Build.props | findstr . >nul 2>&1 && echo Engine or Runner changed: the Runner is published again automatically at the next data or match job ^(needs the .NET 8 SDK^). To do it now: dotnet publish Runner -c Release -o publish/runner
)

rem 6. packages (quick when nothing is new; a failure here is only a warning)
"%PRPY%" -m pip install -q -r ml\requirements.txt || echo Warning: could not install the Python packages ^(no internet?^). The ML UI may ask for them.

echo.
echo Starting the ML UI...
call "%~dp0start-ui.cmd"
exit /b 0

:cancelled
echo Cancelled. Nothing was changed.
:fail
echo.
pause
exit /b 1
