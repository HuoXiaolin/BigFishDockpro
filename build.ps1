param(
    [string]$Toolchain = 'D:\Agant\toolchain',
    [string]$Iscc = '',
    [switch]$Deliver,
    [switch]$LocalCursorStyles,
    [switch]$BundleDotNet,
    [ValidateSet('Auto','Quick','Runtime','Full','None')][string]$TestMode = 'Auto',
    [switch]$SkipTests,
    [switch]$RuntimeChecks,
    [switch]$Clean,
    [switch]$SingleFile = $true,
    [string]$SourceDirectory = 'D:\Agant\Github_Source\BigFishDockpro',
    [string]$ReleaseDirectory = 'D:\Agant\Github_Releases\BigFishDockpro'
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'tools\build.ps1') @PSBoundParameters
if ($LASTEXITCODE) { exit $LASTEXITCODE }
