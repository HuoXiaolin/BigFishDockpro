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
OutputDir=release
OutputBaseFilename=BigFishDockpro-Setup-x64
SetupIconFile=dock.ico
UninstallDisplayIcon={app}\BigFishDockpro.exe
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=2
LicenseFile=LICENSE
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\BigFishDockpro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\大肥鱼Dock"; Filename: "{app}\BigFishDockpro.exe"
Name: "{group}\卸载大肥鱼Dock"; Filename: "{uninstallexe}"
Name: "{autodesktop}\大肥鱼Dock"; Filename: "{app}\BigFishDockpro.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BigFishDockpro.exe"; Description: "启动大肥鱼Dock"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  RunValue: String;
begin
  if CurUninstallStep = usUninstall then
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'BigFishDock', RunValue) then
      if Pos('"' + ExpandConstant('{app}\BigFishDockpro.exe') + '"', RunValue) = 1 then
        RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'BigFishDock');
end;
