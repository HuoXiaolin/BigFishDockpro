param([string]$Toolchain = 'D:\Agant\toolchain')
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'tools\bootstrap.ps1') -Toolchain $Toolchain
if ($LASTEXITCODE) { exit $LASTEXITCODE }
