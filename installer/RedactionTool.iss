; Redaction Tool - Inno Setup script (per-user, no elevation).
;
; Version is single-sourced: layer 4 passes the package version from
; redaction_tool/__init__.py at build time, e.g.
;   ISCC /D AppVersion=1.2.0 installer\RedactionTool.iss
; The fallback below is only for local compile checks.
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

; Permanent application identity. Do NOT change once released: later layers
; rely on this AppId to detect and upgrade older installs.
#define AppIdGuid "{DDD851B8-828F-4C2E-B9B8-5CC23F929068}"

[Setup]
AppId=#AppIdGuid
AppName=Redaction Tool
AppVersion={#AppVersion}
AppVerName=Redaction Tool {#AppVersion}
AppPublisher=oe-marscruz
AppPublisherURL=https://github.com/oe-marscruz/redaction-tool
AppSupportURL=https://github.com/oe-marscruz/redaction-tool/issues
AppUpdatesURL=https://github.com/oe-marscruz/redaction-tool/releases

; Per-user install: no admin/UAC prompt, no install-location questions.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
DefaultDirName={localappdata}\Programs\RedactionTool
DefaultGroupName=Redaction Tool
DisableProgramGroupPage=yes

; x64 only.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

UninstallDisplayName=Redaction Tool
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
VersionInfoProductTextVersion={#AppVersion}
VersionInfoTextVersion={#AppVersion}
VersionInfoDescription=Redaction Tool Setup
VersionInfoCompany=oe-marscruz
VersionInfoOriginalFileName=RedactionTool-Setup-{#AppVersion}.exe

OutputDir=Output
OutputBaseFilename=RedactionTool-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; SetupIconFile intentionally omitted: no .ico asset ships in the repo.
; CloseApplications left at its default - layer 3 owns running-instance
; handling.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\RedactionTool.exe"; DestDir: "{app}"; \
  Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; \
  DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Redaction Tool"; \
  Filename: "{app}\RedactionTool.exe"
Name: "{autodesktop}\Redaction Tool"; \
  Filename: "{app}\RedactionTool.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RedactionTool.exe"; \
  Description: "{cm:LaunchProgram,Redaction Tool}"; \
  Flags: nowait postinstall skipifsilent

; ---------------------------------------------------------------------------
; [Code]
; Intentionally empty in this layer. Layer 3 hooks in here: old-version
; detection, running-process blocking, portable-copy cleanup, and data
; preservation in %USERPROFILE%\.redaction_tool.
; ---------------------------------------------------------------------------
