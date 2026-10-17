@echo off
setlocal
call "%~dp0tools\launch_apa_refresh.bat" --mode full %*
exit /b %ERRORLEVEL%
