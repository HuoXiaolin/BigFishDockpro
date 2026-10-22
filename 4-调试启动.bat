@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run bootstrap.ps1 first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0dock.py"
pause
endlocal
