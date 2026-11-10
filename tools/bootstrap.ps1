param([string]$Toolchain = 'D:\Agant\toolchain')
$taskRoot = Split-Path -Parent $PSScriptRoot
$ErrorActionPreference = 'Stop'
$taskBasePython = Join-Path $Toolchain 'python_3.12.14\python.exe'
$taskDotnet = Join-Path $Toolchain 'dotnet\dotnet.exe'
if (-not (Test-Path -LiteralPath $taskBasePython)) { throw "Missing shared Python: $taskBasePython" }
if (-not (Test-Path -LiteralPath $taskDotnet -PathType Leaf)) { throw "Missing shared .NET 10 SDK: $taskDotnet" }
& $taskBasePython -m venv (Join-Path $taskRoot '.venv')
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
& (Join-Path $taskRoot '.venv\Scripts\python.exe') -m pip install -r (Join-Path $PSScriptRoot 'requirements-build.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& (Join-Path $taskRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'prepare_bluetooth.py') --dotnet $taskDotnet
if ($LASTEXITCODE -ne 0) { throw 'Resource probe compilation failed' }
& (Join-Path $taskRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'prepare_pawnio.py')
if ($LASTEXITCODE -ne 0) { throw 'PawnIO preparation failed' }
& (Join-Path $taskRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'prepare_presentmon.py')
if ($LASTEXITCODE -ne 0) { throw 'FPS probe preparation failed' }
