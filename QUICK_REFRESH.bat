@echo off
setlocal
call "%~dp0tools\launch_apa_refresh.bat" --mode quick %*
exit /b %ERRORLEVEL%
