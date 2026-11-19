@echo off
setlocal
cd /d "%~dp0"
title APA League Catch-up
echo.
echo ============================================================
echo   APA LEAGUE CATCH-UP - fetch every missing scoresheet
echo ============================================================
echo.
echo Uses your saved APA login (run FULL_APA_REFRESH.bat first if it expired).
echo Read-only on APA. Everything is saved locally under
echo tmp\ultimate-coach-release\league-catchup (never committed to git).
echo Already-saved scoresheets are skipped, so re-running is quick.
echo Add --dry-run to only count what is missing.
echo.
set "PY="
set "PYARG="
if exist "venv312\Scripts\python.exe" set "PY=venv312\Scripts\python.exe"
if not defined PY if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY if exist "%~dp0..\..\venv312\Scripts\python.exe" set "PY=%~dp0..\..\venv312\Scripts\python.exe"
if not defined PY (
  py -3.12 -c "import sys" >nul 2>&1 && set "PY=py" && set "PYARG=-3.12"
)
if not defined PY (
  echo ERROR: Python 3.12 was not found.
  set "RC=2"
  goto finished
)
"%PY%" %PYARG% -u tools\league_catchup.py %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (echo Catch-up finished. Summary: tmp\ultimate-coach-release\league-catchup\LAST_RUN.json) else (echo Catch-up finished with problems - see the messages above.)
:finished
if not "%APA_REFRESH_NO_PAUSE%"=="1" pause
exit /b %RC%
