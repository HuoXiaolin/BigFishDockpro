#ifndef AppVersion
  #error "Use build.ps1 to supply the version from version.json"
#endif
[Setup]
AppId={{EA308E7C-37E0-4CC4-858F-04342D329791}
AppName=大肥鱼Dock
AppVersion={#AppVersion}
AppPublisher=HuoXiaolin
AppPublisherURL=https://github.com/HuoXiaolin/BigFishDockpro
DefaultDirName={localappdata}\Programs\BigFishDockpro
DefaultGroupName=大肥鱼Dock
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=BigFishDockpro-Setup-x64
SetupIconFile=..\assets\dock.ico
UninstallDisplayIcon={app}\BigFishDockpro.exe
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=2
LicenseFile=..\LICENSE
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

Name: "taskbar"; Description: "安装 Windows 11 任务栏效果组件（离线）"; Check: SupportsTaskbarComponent

[Files]
Source: "..\dist\BigFishDockpro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "..\artifacts\taskbar-payload\backend\*"; DestDir: "{localappdata}\BigFishDock\TaskbarBackend\2026.2"; Tasks: taskbar; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\artifacts\taskbar-payload\VCLibs-x64.appx"; Flags: dontcopy
Source: "..\artifacts\taskbar-payload\WinUI-x64.appx"; Flags: dontcopy
Source: "install_taskbar_frameworks.ps1"; Flags: dontcopy

[Icons]
Name: "{group}\大肥鱼Dock"; Filename: "{app}\BigFishDockpro.exe"
Name: "{group}\卸载大肥鱼Dock"; Filename: "{uninstallexe}"
Name: "{autodesktop}\大肥鱼Dock"; Filename: "{app}\BigFishDockpro.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BigFishDockpro.exe"; Description: "启动大肥鱼Dock"; Flags: nowait postinstall skipifsilent

[Code]
function SupportsTaskbarComponent: Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  Result := IsX64OS and (Version.Major = 10) and (Version.Build >= 22000);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if SupportsTaskbarComponent and WizardIsTaskSelected('taskbar') then
  begin
    ExtractTemporaryFile('VCLibs-x64.appx');
    ExtractTemporaryFile('WinUI-x64.appx');
    ExtractTemporaryFile('install_taskbar_frameworks.ps1');
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
      ExpandConstant('{tmp}\install_taskbar_frameworks.ps1') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ExitCode) or (ExitCode <> 0) then
      Result := '任务栏组件依赖安装失败。可返回取消勾选该组件后继续安装。日志：%TEMP%\BigFishDockpro-taskbar-install.log';
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  RunValue: String;
begin
  if CurUninstallStep = usUninstall then
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'BigFishDock', RunValue) then
      if Pos('"' + ExpandConstant('{app}\BigFishDockpro.exe') + '"', RunValue) = 1 then
        RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'BigFishDock');
end;
