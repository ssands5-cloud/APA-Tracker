@echo off
setlocal
cd /d "%~dp0"
title APA Coach Cockpit - Game Night Refresh

echo.
echo ============================================================
echo   APA COACH COCKPIT - GAME NIGHT REFRESH
echo ============================================================
echo.
echo This will open the real APA site for you to log in normally.
echo Your password and access token are never written to this file.
echo After login it will refresh, verify, build, and open the Cockpit.
echo.

if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,12),(3,13)) else 1)" >nul 2>&1
  if not errorlevel 1 goto run_venv
)

py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 goto run_312

py -3.13 -c "import sys" >nul 2>&1
if not errorlevel 1 goto run_313

echo ERROR: APA Tracker requires Python 3.12 or 3.13.
echo Install Python 3.12, then run this launcher again.
echo.
pause
exit /b 2

:run_venv
"venv\Scripts\python.exe" tools\capture_apa_graphql.py --game-night
goto finished

:run_312
py -3.12 tools\capture_apa_graphql.py --game-night
goto finished

:run_313
py -3.13 tools\capture_apa_graphql.py --game-night

:finished
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo Game-night Cockpit completed successfully.
) else (
  echo Game-night refresh stopped safely with exit code %RC%.
  echo Your prior production database and prior Cockpit remain available
  echo unless the screen above explicitly says promotion already succeeded.
)
echo.
pause
exit /b %RC%
