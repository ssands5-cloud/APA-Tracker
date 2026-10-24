@echo off
setlocal
cd /d "%~dp0.."
echo APA Ultimate Coach Refresh
echo Working folder: "%CD%"
echo Log in only on the real APA website when the browser opens.
echo Both outputs and their database are delivered together after validation.
if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,12),(3,13)) else 1)" >nul 2>&1
  if not errorlevel 1 goto venv
)
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 goto py312
py -3.13 -c "import sys" >nul 2>&1
if not errorlevel 1 goto py313
echo FAILED AT STEP 1 INTERPRETER: Python 3.12 or 3.13 is required.
set "RC=2"
goto finished
:venv
"venv\Scripts\python.exe" -u -m pipeline.ultimate_coach_refresh --open %*
goto result
:py312
py -3.12 -u -m pipeline.ultimate_coach_refresh --open %*
goto result
:py313
py -3.13 -u -m pipeline.ultimate_coach_refresh --open %*
:result
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo Refresh did not complete. See the failed step above and REFRESH_STATUS.txt in ultimate-coach-runs\refresh.
:finished
if not "%APA_REFRESH_NO_PAUSE%"=="1" pause
exit /b %RC%
