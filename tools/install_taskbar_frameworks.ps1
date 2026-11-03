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
    if ($BackendDirectory -and -not (Test-Path -LiteralPath (Join-Path $BackendDirectory 'TranslucentTB.exe') -PathType Leaf)) {
        $parent = Split-Path -Parent $BackendDirectory
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        $staging = Join-Path $parent ([guid]::NewGuid().ToString('N'))
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'backend') -Destination $staging -Recurse
        [IO.Directory]::Move($staging, $BackendDirectory)
    }
} catch {
    $_ | Out-String | Set-Content -LiteralPath (Join-Path $env:TEMP 'BigFishDockpro-taskbar-install.log') -Encoding UTF8
    exit 1
}
