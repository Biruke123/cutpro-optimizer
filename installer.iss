; ============================================
; CutPro v3.0 - Inno Setup Installer Script
; Build: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
; ============================================

#define MyAppName "CutPro"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "BLM"
#define MyAppURL "https://cutpro.example.com"
#define MyAppExeName "CutPro.exe"

[Setup]
AppId={{7C3F5A2E-1B8D-4E9F-A6C2-D1E4F8B03A57}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=CutPro_Staging\LICENSE.txt
OutputDir=dist_installer
OutputBaseFilename=CutProSetup_v3.0
SetupIconFile=CutPro_Package\CutPro.ico
UninstallDisplayIcon={app}\CutPro.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
DisableDirPage=no
DisableReadyPage=no
AllowNoIcons=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "sketchupplugin"; Description: "Install the SketchUp plugin (CutPro_Scatter.rb)"; GroupDescription: "SketchUp integration:"; Flags: checkedonce
Name: "launchapp"; Description: "Launch CutPro after installation"; GroupDescription: "After install:"; Flags: checkedonce

[Files]
Source: "CutPro_Staging\CutPro.exe";           DestDir: "{app}"; Flags: ignoreversion
Source: "CutPro_Staging\CutPro.ico";           DestDir: "{app}"; Flags: ignoreversion
Source: "CutPro_Staging\CutPro_Scatter.rb";    DestDir: "{app}"; Flags: ignoreversion
Source: "CutPro_Staging\install_sketchup_plugin.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "CutPro_Staging\README.txt";           DestDir: "{app}"; Flags: ignoreversion
Source: "CutPro_Staging\LICENSE.txt";          DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";              Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\CutPro.ico"
Name: "{group}\Uninstall {#MyAppName}";    Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";        Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\CutPro.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent; Tasks: launchapp

Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install_sketchup_plugin.ps1"""; \
  StatusMsg: "Installing SketchUp plugin..."; \
  Flags: runhidden waituntilterminated; \
  Tasks: sketchupplugin

[UninstallRun]
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-ChildItem -Path $env:APPDATA\SketchUp, $env:LOCALAPPDATA\SketchUp, 'C:\Program Files\SketchUp', 'C:\Program Files (x86)\SketchUp' -Recurse -Filter 'CutPro_Scatter.rb' -ErrorAction SilentlyContinue | Remove-Item -Force"""; \
  Flags: runhidden; \
  RunOnceId: "RemoveSketchUpPlugin"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\uploads"
Type: filesandordirs; Name: "{app}\frontend"