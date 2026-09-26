; Inno Setup script for OverLex.
; Built by CI via: ISCC installer\OverLex.iss /DAppVersion=<version>
; Expects dist\OverLex\ (the PyInstaller onedir output) and build\icon.ico to already
; exist - run build_win.py first.
;
; AppId must NEVER change across releases: Inno Setup uses it (not the version number)
; to recognize "this machine already has OverLex installed" and upgrade in place -
; same install directory, same Start Menu entry, no duplicate Add/Remove Programs row.
#define AppId "{8FAF97B8-273B-4EF5-BC01-10AD80DE9B1F}"

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={#AppId}
AppName=OverLex
AppVersion={#AppVersion}
AppPublisher=OverLex
DefaultDirName={autopf}\OverLex
DefaultGroupName=OverLex
UninstallDisplayIcon={app}\OverLex.exe
OutputDir=..\dist
OutputBaseFilename=OverLex-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\build\icon.ico
; Program Files is a per-machine location, so writing to it needs elevation - that
; UAC prompt is unavoidable on Windows. The installed app itself still runs unprivileged.
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Detect a running OverLex.exe (this version or an older one already installed) via
; Windows Restart Manager, close it, and relaunch the freshly installed copy afterward -
; so an upgrade never leaves an old process running as orphaned "garbage".
CloseApplications=force
CloseApplicationsFilter=OverLex.exe
RestartApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Launch OverLex automatically when Windows starts"; GroupDescription: "Additional options:"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional options:"; Flags: unchecked

[Files]
Source: "..\dist\OverLex\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\OverLex"; Filename: "{app}\OverLex.exe"
Name: "{group}\Uninstall OverLex"; Filename: "{uninstallexe}"
Name: "{autodesktop}\OverLex"; Filename: "{app}\OverLex.exe"; Tasks: desktopicon

; Same registry value the app's own tray "Launch at login" toggle writes
; (APP_NAME="OverLex" under HKCU Run) - installer and in-app toggle stay in sync
; instead of fighting over two different entries.
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "OverLex"; ValueData: """{app}\OverLex.exe"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\OverLex.exe"; Description: "Launch OverLex now"; Flags: nowait postinstall skipifsilent
