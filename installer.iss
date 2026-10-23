; ScreenStash Inno Setup Script
; Builds a modern, Notion-style per-user installer for ScreenStash.
; Installs into %LOCALAPPDATA%\Programs\ScreenStash (no UAC / admin privileges needed)

#define MyAppName "ScreenStash"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "ScreenStash AI"
#define MyAppURL "https://github.com/guptapiyush16/ScreenStash"
#define MyAppExeName "ScreenStash.exe"

[Setup]
; App Identity
AppId={{D9B78A52-32E8-48BF-B8C2-320F8A5D6E31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation Directory (Per-User Notion/VS Code Style)
; Does not require Administrator elevation
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Output Configuration
OutputDir=dist-installer
OutputBaseFilename=ScreenStash-Setup
SetupIconFile=app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Branding & Visuals
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startmenuicon"; Description: "Create Start Menu icon"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Dist directory produced by PyInstaller (onedir)
Source: "dist\ScreenStash\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu Shortcut
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Comment: "ScreenStash — Local AI Screenshot-to-Plan"
; Optional Desktop Shortcut
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon; Comment: "ScreenStash — Local AI Screenshot-to-Plan"

[Run]
; Option to launch ScreenStash immediately after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
