@echo off
setlocal
cd /d "%~dp0"
set "FISHDOCK_PYTHON=D:\Agant\toolchain\python_3.12.14\python.exe"
if not exist "%FISHDOCK_PYTHON%" (
  echo Missing shared Python. See README.
  pause
  exit /b 1
)
"%FISHDOCK_PYTHON%" -m venv "%~dp0.venv"
if errorlevel 1 exit /b 1
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements-build.txt"
pause
endlocal
