param(
    [string]$Toolchain = 'D:\Agant\toolchain',
    [string]$Iscc = '',
    [switch]$Deliver,
    [ValidateSet('Quick','Runtime','Full','None')][string]$TestMode = 'Quick',
    [switch]$SkipTests,
    [switch]$RuntimeChecks,
    [switch]$Clean,
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
if ($SkipTests -and $RuntimeChecks) { throw 'Do not combine SkipTests and RuntimeChecks.' }
$taskMode = if ($SkipTests) {'None'} elseif ($RuntimeChecks) {'Runtime'} else {$TestMode}
$taskSkip = $taskMode -eq 'None'
$taskExtended = $taskMode -in @('Runtime','Full')
$taskScopeArgs = if ($taskMode -eq 'Full') {@()} else {@('--runtime-check')}
$taskCompilerArgs = @('--noconfirm')
if ($Clean) { $taskCompilerArgs += '--clean' }
New-Item -ItemType Directory -Path artifacts -Force | Out-Null
$taskLock = [IO.File]::Open((Join-Path $PSScriptRoot 'artifacts\release.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
$taskPriorFixture = $env:FISHDOCK_NATIVE_LAUNCH_FIXTURE
$taskValidations = [Collections.Generic.List[object]]::new()
$taskTestSeconds = 0.0
$taskBuildTimer = [Diagnostics.Stopwatch]::StartNew()
function Invoke-TaskCheck([string]$Target,[string]$Output,[string]$Kind,[string[]]$Options) {
    $taskTimer = [Diagnostics.Stopwatch]::StartNew()
    & $taskPython run_isolated_test.py --target $Target --timeout 160 --output $Output @Options
    $taskExit = $LASTEXITCODE
    $taskTimer.Stop()
    $script:taskTestSeconds += $taskTimer.Elapsed.TotalSeconds
    if ($taskExit -ne 0) { throw ($Kind + ' failed') }
    $taskResult = Join-Path $Output 'result.json'
    $taskValidations.Add([ordered]@{kind=$Kind;path=$taskResult.Replace('\','/');sha256=(Get-FileHash -LiteralPath $taskResult -Algorithm SHA256).Hash.ToLowerInvariant();seconds=[math]::Round($taskTimer.Elapsed.TotalSeconds,2)})
}
try {
    if ($taskMode -eq 'Full') {
        $taskGcc = Join-Path $Toolchain 'mingw\mingw64\bin\gcc.exe'
        if (Test-Path -LiteralPath $taskGcc) {
            & $taskGcc -static -municode native_launch_probe.c -o artifacts/native_launch_probe.exe
            if ($LASTEXITCODE -ne 0) { throw 'Native launch fixture compilation failed' }
            $env:FISHDOCK_NATIVE_LAUNCH_FIXTURE = (Resolve-Path -LiteralPath artifacts/native_launch_probe.exe).Path
        }
    }
    $taskVersion = & $taskPython release_tools.py prepare
    if ($LASTEXITCODE -ne 0) { throw 'Version preparation failed' }
    if ($taskExtended) { Invoke-TaskCheck 'dock.py' 'artifacts/source-test' 'source-runtime' $taskScopeArgs }
    & $taskPython -m PyInstaller @taskCompilerArgs BigFishDockpro.spec
    if ($LASTEXITCODE -ne 0) { throw 'Directory build failed' }
    if ($taskExtended) {
        Invoke-TaskCheck 'dist/BigFishDockpro/BigFishDockpro.exe' 'artifacts/bundle-test' 'directory-runtime' $taskScopeArgs
        Invoke-TaskCheck 'dist/BigFishDockpro/BigFishDockpro.exe' 'artifacts/startup-manual-test' 'manual-startup' @('--startup')
        Invoke-TaskCheck 'dist/BigFishDockpro/BigFishDockpro.exe' 'artifacts/startup-auto-test' 'autostart' @('--startup','--autostart')
        Invoke-TaskCheck 'dist/BigFishDockpro/BigFishDockpro.exe' 'artifacts/startup-fresh-test' 'fresh-startup' @('--startup','--fresh-profile')
    } elseif (-not $taskSkip) {
        Invoke-TaskCheck 'dist/BigFishDockpro/BigFishDockpro.exe' 'artifacts/quick-bundle-startup' 'directory-fresh-startup' @('--startup','--fresh-profile')
    }
    & $Iscc "/DAppVersion=$taskVersion" installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
    if ($SingleFile) {
        $taskOldBundleMode = $env:FISHDOCK_ONEFILE
        try {
            $env:FISHDOCK_ONEFILE = '1'
            & $taskPython -m PyInstaller @taskCompilerArgs --distpath release BigFishDockpro.spec
            if ($LASTEXITCODE -ne 0) { throw 'Single-file build failed' }
        } finally { $env:FISHDOCK_ONEFILE = $taskOldBundleMode }
        if (-not $taskSkip) {
            $taskOutput = if ($taskExtended) {'artifacts/singlefile-test'} else {'artifacts/quick-runtime-test'}
            Invoke-TaskCheck 'release/BigFishDockpro.exe' $taskOutput 'singlefile-runtime' $taskScopeArgs
        }
    } elseif ($taskMode -eq 'Quick') {
        Invoke-TaskCheck 'dist/BigFishDockpro/BigFishDockpro.exe' 'artifacts/quick-runtime-test' 'directory-runtime' @('--runtime-check')
    }
    $taskHash = Get-FileHash -LiteralPath release/BigFishDockpro-Setup-x64.exe -Algorithm SHA256
    ('{0}  BigFishDockpro-Setup-x64.exe' -f $taskHash.Hash.ToLowerInvariant()) | Set-Content release/SHA256SUMS.txt -Encoding utf8
    $taskSingleHash = $null
    if (Test-Path -LiteralPath release/BigFishDockpro.exe) {
        $taskSingleHash = Get-FileHash -LiteralPath release/BigFishDockpro.exe -Algorithm SHA256
        ('{0}  BigFishDockpro.exe' -f $taskSingleHash.Hash.ToLowerInvariant()) | Add-Content release/SHA256SUMS.txt -Encoding utf8
    }
    $taskBuildTimer.Stop()
    $taskScope = switch ($taskMode) {'Quick' {'quick-runtime'} 'Runtime' {'current-ui-runtime'} 'Full' {'full'} default {'none'}}
    $taskReceipt=[ordered]@{tests_skipped=$taskSkip;test_scope=$taskScope;validation_results=@($taskValidations.ToArray());test_seconds=[math]::Round($taskTestSeconds,2);build_seconds=[math]::Round($taskBuildTimer.Elapsed.TotalSeconds,2);installer_sha256=$taskHash.Hash.ToLowerInvariant();singlefile_sha256=$(if($taskSingleHash){$taskSingleHash.Hash.ToLowerInvariant()}else{''});version=$taskVersion}
    $taskReceipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath artifacts/build-validation.json -Encoding utf8
    if ($Deliver) {
        $taskDeliveryArgs=@('release_tools.py','deliver','--source',$SourceDirectory,'--release',$ReleaseDirectory)
        if($taskSkip){$taskDeliveryArgs+='--skip-tests'}
        & $taskPython @taskDeliveryArgs
        if ($LASTEXITCODE -ne 0) { throw 'Delivery failed' }
    }
} finally { $env:FISHDOCK_NATIVE_LAUNCH_FIXTURE = $taskPriorFixture; $taskLock.Dispose() }
