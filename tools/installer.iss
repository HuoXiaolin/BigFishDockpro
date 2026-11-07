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
Name: "pawnio"; Description: "安装 CPU 温度与功率驱动（PawnIO）"; Flags: unchecked; Check: NeedsPawnIO
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
Filename: "{app}\_internal\resource-probe\PawnIO_setup.exe"; Verb: "runas"; Parameters: "-install -silent"; Tasks: pawnio; Check: CheckedPawnInstaller; Flags: shellexec waituntilterminated; StatusMsg: "安装 CPU 传感器驱动…"
Filename: "{app}\BigFishDockpro.exe"; Description: "启动大肥鱼Dock"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\BigFishDockpro.exe"; Parameters: "--remove-startup"; Flags: runhidden; RunOnceId: "RemoveOwnedLogonTask"

[Code]
function NeedsPawnIO: Boolean;
var
  Current: String;
  InstalledVersion, RequiredVersion: Int64;
begin
  Result := True;
  if RegQueryStringValue(HKLM64, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO', 'DisplayVersion', Current)
    and StrToVersion(Current, InstalledVersion) and StrToVersion('2.2.0.0', RequiredVersion) then
    Result := InstalledVersion < RequiredVersion;
end;

function CheckedPawnInstaller: Boolean;
begin
  Result := NeedsPawnIO and (CompareText(GetSHA256OfFile(ExpandConstant('{app}\_internal\resource-probe\PawnIO_setup.exe')),
    '1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032') = 0);
end;

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
