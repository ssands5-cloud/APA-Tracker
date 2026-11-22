@echo off
setlocal EnableExtensions
rem Ultimate Coach refresh launcher (QUICK_REFRESH.bat / FULL refresh call this with --mode).
rem Readable report: the chosen interpreter, base database and identity file are printed before the refresh starts,
rem every step is written to ultimate-coach-runs\refresh\REFRESH_STATUS.txt, and the exit code is 0 only when the
rem database, workbook and HTML were delivered together. Exit codes: 0 done, 1 refresh failed (previous files kept),
rem 2 no usable Python, 3 configured database missing.
cd /d "%~dp0.."
echo APA Ultimate Coach Refresh
echo Working folder: "%CD%"
echo Log in only on the real APA website when the browser opens.
echo The database, workbook and HTML are delivered together after validation; on failure nothing is replaced.

rem ---- STEP 0a: a Python 3.12/3.13 that has every refresh dependency (venv first, then the system launcher) ----
set "PYEXE="
set "CHECK=import sys, importlib.util as u; ok=sys.version_info[:2] in ((3,12),(3,13)) and all(u.find_spec(m) for m in ('yaml','openpyxl','playwright','sqlalchemy','win32com')); raise SystemExit(0 if ok else 1)"
for %%P in ("venv312\Scripts\python.exe" "venv\Scripts\python.exe") do (
  if not defined PYEXE if exist %%P (
    %%P -c "%CHECK%" >nul 2>&1 && set "PYEXE=%%~P"
  )
)
if not defined PYEXE (
  py -3.12 -c "%CHECK%" >nul 2>&1 && set "PYEXE=py -3.12"
)
if not defined PYEXE (
  py -3.13 -c "%CHECK%" >nul 2>&1 && set "PYEXE=py -3.13"
)
if not defined PYEXE (
  echo FAILED AT STEP 0 INTERPRETER: no Python 3.12/3.13 with yaml, openpyxl, playwright, sqlalchemy and pywin32.
  echo Fix: py -3.12 -m pip install -r requirements.txt pywin32
  set "RC=2"
  goto finished
)
echo Interpreter: %PYEXE%

rem ---- STEP 0b: the base database named in apa_config.yaml (refresh.source_database) must exist ----
set "BASEDB="
for /f "usebackq delims=" %%D in (`%PYEXE% -c "import yaml; c=yaml.safe_load(open('apa_config.yaml',encoding='utf-8')); print((c.get('refresh') or {}).get('source_database') or 'data/ultimate_coach_staging.db')"`) do set "BASEDB=%%D"
if not exist "%BASEDB%" (
  echo FAILED AT STEP 0 DATABASE: base database "%BASEDB%" not found. Nothing was changed.
  echo See REFRESH_GUIDE in the release folder for how the authoritative database is placed.
  set "RC=3"
  goto finished
)
for %%F in ("%BASEDB%") do echo Base database: %%~fF  ^(%%~zF bytes, %%~tF^)

rem ---- STEP 0c: owner-reviewed identity bindings, when Paul has approved some ----
set "OVERRIDES="
if exist "data\identity_overrides.json" (
  set "OVERRIDES=--identity-overrides data\identity_overrides.json"
  echo Identity overrides: data\identity_overrides.json
) else (
  echo Identity overrides: none
)

%PYEXE% -u -m pipeline.ultimate_coach_refresh --open %OVERRIDES% %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo RESULT: SUCCESS - see ultimate-coach-runs\refresh\CURRENT.json for the delivered files.
) else (
  echo RESULT: FAILED ^(exit %RC%^) - previous files kept. The failed step is above and in
  echo         ultimate-coach-runs\refresh\REFRESH_STATUS.txt
)
:finished
if not "%APA_REFRESH_NO_PAUSE%"=="1" pause
exit /b %RC%
