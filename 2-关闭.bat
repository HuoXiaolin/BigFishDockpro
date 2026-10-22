@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" exit /b 1
"%~dp0.venv\Scripts\python.exe" "%~dp0dock.py" --stop
endlocal
