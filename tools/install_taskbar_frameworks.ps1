param([string]$BackendDirectory)
$ErrorActionPreference = 'Stop'
function Install-FrameworkIfMissing {
    param([string]$Name, [version]$MinimumVersion, [string]$File)
    $installed = Get-AppxPackage -Name $Name | Where-Object {
        $_.PublisherId -eq '8wekyb3d8bbwe' -and $_.Architecture -eq 'X64' -and
        [version]$_.Version -ge $MinimumVersion
    }
    if (-not $installed) {
        Add-AppxPackage -Path (Join-Path $PSScriptRoot $File)
        $installed = Get-AppxPackage -Name $Name | Where-Object {
            $_.PublisherId -eq '8wekyb3d8bbwe' -and $_.Architecture -eq 'X64' -and
            [version]$_.Version -ge $MinimumVersion
        }
        if (-not $installed) { throw "Framework registration failed: $Name" }
    }
}
try {
    Install-FrameworkIfMissing 'Microsoft.VCLibs.140.00' '14.0.33519.0' 'VCLibs-x64.appx'
    Install-FrameworkIfMissing 'Microsoft.UI.Xaml.2.8' '8.2501.31001.0' 'WinUI-x64.appx'
    if ($BackendDirectory) {
        $BackendDirectory = [IO.Path]::GetFullPath($BackendDirectory)
        $parent = Split-Path -Parent $BackendDirectory
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        $source = Join-Path $PSScriptRoot 'backend'
        foreach ($name in 'TranslucentTB.exe','ExplorerTAP.dll','ExplorerHooks.dll','Xaml.dll','ProgramLog.dll','resources.pri') {
            if ((Get-Item -LiteralPath (Join-Path $source $name)).Length -le 0) { throw "Incomplete backend: $name" }
        }
        $stageName = 'taskbar-install-' + [guid]::NewGuid().ToString('N')
        $staging = Join-Path $parent $stageName
        try {
            Copy-Item -LiteralPath $source -Destination $staging -Recurse
            if (-not [IO.Directory]::Exists($BackendDirectory)) {
                try { [IO.Directory]::Move($staging, $BackendDirectory) }
                catch [IO.IOException] { if (-not [IO.Directory]::Exists($BackendDirectory)) { throw } }
            }
            if ([IO.Directory]::Exists($staging)) {
                foreach ($file in Get-ChildItem -LiteralPath $staging -File -Recurse) {
                    $relative = $file.FullName.Substring($staging.Length + 1)
                    $target = Join-Path $BackendDirectory $relative
                    if ([IO.File]::Exists($target)) {
                        if ((Get-Item -LiteralPath $target).Length -eq 0) {
                            [IO.File]::Replace($file.FullName, $target, (Join-Path $staging ([guid]::NewGuid().ToString('N'))))
                        }
                    } else {
                        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
                        try { [IO.File]::Move($file.FullName, $target) }
                        catch [IO.IOException] { if (-not [IO.File]::Exists($target)) { throw } }
                    }
                }
            }
        } finally {
            if ([IO.Directory]::Exists($staging) -and
                (Resolve-Path -LiteralPath $staging).ProviderPath -eq (Join-Path $parent $stageName)) {
                Remove-Item -LiteralPath $staging -Recurse -Force
            }
        }
    }
} catch {
    $_ | Out-String | Set-Content -LiteralPath (Join-Path $env:TEMP 'BigFishDockpro-taskbar-install.log') -Encoding UTF8
    exit 1
}
