param(
    [string]$Toolchain = 'D:\Agant\toolchain',
    [string]$Iscc = '',
    [switch]$Deliver,
    [switch]$SingleFile = $true,
    [string]$SourceDirectory = 'D:\Agant\Github_Source\BigFishDockpro',
    [string]$ReleaseDirectory = 'D:\Agant\Github_Releases\BigFishDockpro'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $Iscc) { $Iscc = Join-Path $Toolchain 'inno_setup\ISCC.exe' }
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run bootstrap.ps1 first.' }
if (-not (Test-Path -LiteralPath $Iscc)) { throw "Missing shared Inno Setup compiler: $Iscc" }
New-Item -ItemType Directory -Path artifacts -Force | Out-Null
$taskLock = [IO.File]::Open((Join-Path $PSScriptRoot 'artifacts\release.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
    $taskVersion = & $taskPython release_tools.py prepare
    if ($LASTEXITCODE -ne 0) { throw 'Version preparation failed' }
    & $taskPython run_isolated_test.py --target dock.py --timeout 100 --output artifacts/source-test
    if ($LASTEXITCODE -ne 0) { throw 'Source verification failed' }
    & $taskPython -m PyInstaller --noconfirm --clean BigFishDockpro.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    & $taskPython run_isolated_test.py --target dist/BigFishDockpro/BigFishDockpro.exe --timeout 100 --output artifacts/bundle-test
    if ($LASTEXITCODE -ne 0) { throw 'Bundle verification failed' }
    & $taskPython run_isolated_test.py --target dist/BigFishDockpro/BigFishDockpro.exe --startup --output artifacts/startup-manual-test
    if ($LASTEXITCODE -ne 0) { throw 'Manual startup verification failed' }
    & $taskPython run_isolated_test.py --target dist/BigFishDockpro/BigFishDockpro.exe --startup --autostart --output artifacts/startup-auto-test
    if ($LASTEXITCODE -ne 0) { throw 'Autostart verification failed' }
    & $taskPython run_isolated_test.py --target dist/BigFishDockpro/BigFishDockpro.exe --startup --fresh-profile --output artifacts/startup-fresh-test
    if ($LASTEXITCODE -ne 0) { throw 'Fresh-profile startup verification failed' }
    & $Iscc "/DAppVersion=$taskVersion" installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
    if ($SingleFile) {
        $taskOldBundleMode = $env:FISHDOCK_ONEFILE
        try {
            $env:FISHDOCK_ONEFILE = '1'
            & $taskPython -m PyInstaller --noconfirm --clean --distpath release BigFishDockpro.spec
            if ($LASTEXITCODE -ne 0) { throw 'Single-file build failed' }
        } finally { $env:FISHDOCK_ONEFILE = $taskOldBundleMode }
        & $taskPython run_isolated_test.py --target release/BigFishDockpro.exe --timeout 100 --output artifacts/singlefile-test
        if ($LASTEXITCODE -ne 0) { throw 'Single-file verification failed' }
    }
    $taskHash = Get-FileHash -LiteralPath release/BigFishDockpro-Setup-x64.exe -Algorithm SHA256
    ('{0}  BigFishDockpro-Setup-x64.exe' -f $taskHash.Hash.ToLowerInvariant()) | Set-Content release/SHA256SUMS.txt -Encoding utf8
    if (Test-Path -LiteralPath release/BigFishDockpro.exe) {
        $taskSingleHash = Get-FileHash -LiteralPath release/BigFishDockpro.exe -Algorithm SHA256
        ('{0}  BigFishDockpro.exe' -f $taskSingleHash.Hash.ToLowerInvariant()) | Add-Content release/SHA256SUMS.txt -Encoding utf8
    }
    if ($Deliver) {
        & $taskPython release_tools.py deliver --source $SourceDirectory --release $ReleaseDirectory
        if ($LASTEXITCODE -ne 0) { throw 'Delivery verification failed' }
    }
} finally { $taskLock.Dispose() }
