param([string]$Toolchain = 'D:\Agant\toolchain')
$taskRoot = Split-Path -Parent $PSScriptRoot
$ErrorActionPreference = 'Stop'
$taskBasePython = Join-Path $Toolchain 'python_3.12.14\python.exe'
if (-not (Test-Path -LiteralPath $taskBasePython)) { throw "Missing shared Python: $taskBasePython" }
& $taskBasePython -m venv (Join-Path $taskRoot '.venv')
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
& (Join-Path $taskRoot '.venv\Scripts\python.exe') -m pip install -r (Join-Path $PSScriptRoot 'requirements-build.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
