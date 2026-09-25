; Redaction Tool - Inno Setup script (per-user, no elevation).
;
; Version is single-sourced: layer 4 passes the package version from
; redaction_tool/__init__.py at build time, e.g.
;   ISCC /DAppVersion=1.2.0 installer\RedactionTool.iss
; The fallback below is only for local compile checks.
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

; [Setup] VersionInfo* directives accept only numeric x.y.z[.w] versions, so a
; suffix like "0.0.0-dev" or "1.2.0-rc.1" must be stripped before use there.
; AppVersion / AppVerName / OutputBaseFilename keep the full display string.
#define VersionInfoNumeric Pos("-", AppVersion) > 0 ? Copy(AppVersion, 0, Pos("-", AppVersion) - 1) : AppVersion

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
VersionInfoVersion={#VersionInfoNumeric}
VersionInfoProductVersion={#VersionInfoNumeric}
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

; Belt-and-braces companion to the [Code] running-instance handling: if the
; Restart Manager reports our exe in use during the file-copy phase, ask to
; close it (non-silent) instead of failing outright.
CloseApplications=yes

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
; [Code] lives in Code.iss, included below: layer 3 -- old-version detection
; & removal, running-instance handling, portable-copy cleanup, and the
; (intentional) guarantee that %USERPROFILE%\.redaction_tool user data is
; never deleted on upgrade or uninstall. See that file's header.
; ---------------------------------------------------------------------------

#include "Code.iss"
