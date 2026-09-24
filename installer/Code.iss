; ---------------------------------------------------------------------------
; Layer 3 of 4: old-version detection & removal, running-instance handling,
; best-effort portable-copy cleanup, data preservation.
; Included from RedactionTool.iss (which owns [Setup]/[Files]/[Icons]).
;
; DATA PRESERVATION (intentional, by construction):
;   %USERPROFILE%\.redaction_tool\ (settings.json + presets\) is the app's
;   runtime data directory. Nothing in this file -- no DelTree, DeleteFile,
;   [UninstallDelete] or [InstallDelete] entry -- ever targets it, so user
;   presets and settings survive upgrades AND uninstalls. Do not add cleanup
;   for this path without an explicit product decision.
;
; Upgrade mechanics (verified against Inno Setup 6 docs):
;   When AppId matches and the DefaultDirName is unchanged, Setup does NOT
;   auto-run the old uninstaller; it *appends to the existing uninstall log*
;   and replaces files in place, keeping one combined uninstall entry.
;   UpdateUninstallLogAppName is not needed. The old exe is superseded by the
;   new copy; stale files the new install no longer ships are handled by the
;   portable-copy sweep below where safe to do so.
; ---------------------------------------------------------------------------
[Code]

const
  APP_EXE_NAME = 'RedactionTool.exe';
  UNINST_KEY = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
    '{DDD851B8-828F-4C2E-B9B8-5CC23F929068}_is1';
  UNINST_KEY_WOW = 'Software\WOW6432Node\Microsoft\Windows\' +
    'CurrentVersion\Uninstall\{DDD851B8-828F-4C2E-B9B8-5CC23F929068}_is1';
  SCAN_MAX_ENTRIES = 200;                    { portable-scan match cap }
  SCAN_MAX_DEPTH = 1;                        { recurse at most 1 level }
  SCAN_MAX_VISITS = 5000;                    { portable-scan entry cap }

var
  GPortableCandidates: TStringList;          { full paths awaiting decision }
  GScanVisits: Integer;                      { entries visited this sweep }
  GPriorInstallFound: Boolean;
  GPriorVersion: String;                    { prior installed DisplayVersion }
  GPriorLocation: String;                   { prior InstallLocation }
  GPriorIcon: String;                       { prior DisplayIcon path }

{ --- version helpers ------------------------------------------------------ }

{ Compare "1.2.3.4" dotted strings numerically component-wise.
  Returns <0 (A older), 0 (equal), >0 (A newer). Missing/non-numeric parts
  count as 0. }
function CompareVersions(const A, B: String): Integer;
var
  A2, B2, sa, sb: String;
  av, bv: Integer;
begin
  Result := 0;
  A2 := A;
  B2 := B;
  while True do begin
    sa := Trim(Copy(A2, 1, Pos('.', A2 + '.') - 1));
    sb := Trim(Copy(B2, 1, Pos('.', B2 + '.') - 1));
    av := StrToIntDef(sa, 0);
    bv := StrToIntDef(sb, 0);
    if av <> bv then begin
      if av < bv then Result := -1 else Result := 1;
      exit;
    end;
    if Pos('.', A2) > 0 then Delete(A2, 1, Pos('.', A2)) else A2 := '';
    if Pos('.', B2) > 0 then Delete(B2, 1, Pos('.', B2)) else B2 := '';
    if (A2 = '') and (B2 = '') then begin Result := 0; exit; end;
  end;
end;

function IsDevVersion(const V: String): Boolean;
begin
  Result := (V = '') or (Pos('-dev', V) > 0);
end;

{ --- item 1: registry detection of a prior INSTALLED version -------------- }

{ Reads DisplayVersion/DisplayIcon/InstallLocation from one uninstall subkey,
  checking both the 64-bit (HKCU64) and 32-bit (HKCU32, WOW6432Node) views.
  Returns True when a DisplayVersion was read; leaves existing values
  untouched when absent. }
function ReadUninstallValues(const SubKey: String; var Version,
  InstallLocation, DisplayIcon: String; var HadVersion: Boolean): Boolean;
begin
  Result := False;
  if RegQueryStringValue(HKCU64, SubKey, 'DisplayVersion', Version)
     and (Version <> '') then begin
    HadVersion := True;
    Result := True;
  end;
  RegQueryStringValue(HKCU64, SubKey, 'DisplayIcon', DisplayIcon);
  if InstallLocation = '' then
    RegQueryStringValue(HKCU64, SubKey, 'InstallLocation', InstallLocation);
  if RegQueryStringValue(HKCU32, SubKey, 'DisplayVersion', Version)
     and (Version <> '') then begin
    HadVersion := True;
    Result := True;
  end;
  RegQueryStringValue(HKCU32, SubKey, 'DisplayIcon', DisplayIcon);
  if InstallLocation = '' then
    RegQueryStringValue(HKCU32, SubKey, 'InstallLocation', InstallLocation);
end;

{ Returns True when a prior install exists (uninstall key present in either
  registry view); fills Version/InstallLocation/DisplayIcon and sets
  HadVersion when a DisplayVersion was readable. }
function GetInstalledVersion(var Version, InstallLocation, DisplayIcon: String;
  var HadVersion: Boolean): Boolean;
begin
  Result := False;
  Version := '';
  InstallLocation := '';
  DisplayIcon := '';
  HadVersion := False;
  if RegKeyExists(HKCU64, UNINST_KEY) or RegKeyExists(HKCU32, UNINST_KEY) then
  begin
    Result := True;
    ReadUninstallValues(UNINST_KEY, Version, InstallLocation, DisplayIcon,
      HadVersion);
  end else if RegKeyExists(HKCU64, UNINST_KEY_WOW) or
    RegKeyExists(HKCU32, UNINST_KEY_WOW) then begin
    Result := True;
    ReadUninstallValues(UNINST_KEY_WOW, Version, InstallLocation, DisplayIcon,
      HadVersion);
  end;
  if Result then GPriorInstallFound := True;
end;

{ --- item 3: running-instance detection ---------------------------------- }

{ True when RedactionTool.exe is currently running. Primary probe: tasklist
  (authoritative, catches background instances with no window); fallback:
  FindWindowByWindowName against the app's exact main-window titles (FindWindow
  does exact matching only, so both known titles are tried). }
function IsAppRunning(): Boolean;
var
  Output: TExecOutput;
  ResultCode: Integer;
  i: Integer;
  line: String;
begin
  Result := False;
  if ExecAndCaptureOutput(ExpandConstant('{sys}\tasklist.exe'),
     '/FI "IMAGENAME eq ' + APP_EXE_NAME + '" /NH', '', SW_HIDE,
     ewWaitUntilTerminated, ResultCode, Output) then begin
    for i := 0 to GetArrayLength(Output.StdOut) - 1 do begin
      line := Output.StdOut[i];
      { tasklist prints "<image name>" + PID + session when found, or a
        "INFO: No tasks..." message when not. }
      if Pos(LowerCase(APP_EXE_NAME), LowerCase(line)) > 0 then begin
        Result := True;
        exit;
      end;
    end;
  end;
  { Fallback: tasklist unavailable/failed -- look for the main window.
    FindWindow matches the window name exactly, so both known titles are
    tried: the full title Tk sets (U+2014 em dash) and the bare name that
    older builds used. A missing window only means "not visible", which is
    fine here -- tasklist is authoritative when it ran. }
  if FindWindowByWindowName('Redaction Tool ' + #8212 + ' FERPA / HIPAA') <> 0
  then
    Result := True
  else if FindWindowByWindowName('Redaction Tool') <> 0 then
    Result := True;
end;

{ Ask the user to close the app; offer to end it, with a Retry/Cancel loop
  if the instance is still running afterwards. Returns True when safe to
  proceed. Returns False if the user cancels. In silent mode we proceed --
  CloseApplications=yes plus the Restart Manager covers the rest. }
function EnsureAppNotRunning(): Boolean;
var
  attempt, ResultCode: Integer;
begin
  Result := True;
  if WizardSilent then exit;
  attempt := 0;
  while IsAppRunning() do begin
    attempt := attempt + 1;
    if attempt > 10 then begin Result := False; exit; end; { safety valve }
    if MsgBox('Redaction Tool is still open.'#13#10#13#10 +
      'Please close the app (click its X button) so the installer can ' +
      'update its files, then choose Retry.'#13#10#13#10 +
      'If the app is not responding, choose "End it" to close it for you.',
      mbConfirmation, MB_RETRYCANCEL or MB_DEFBUTTON1) = IDRETRY then begin
      if not IsAppRunning() then begin Result := True; exit; end;
      if MsgBox('The app is still running. End it now?'#13#10#13#10 +
        'Unsaved work in Redaction Tool would be lost. It is usually ' +
        'safe if you have saved your changes.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then begin
        Exec(ExpandConstant('{sys}\taskkill.exe'),
          '/IM "' + APP_EXE_NAME + '"', '', SW_HIDE, ewWaitUntilTerminated,
          ResultCode);
        Sleep(1000);
      end;
    end else begin
      Result := False;
      exit;
    end;
  end;
end;

{ --- item 4: best-effort portable-copy cleanup --------------------------- }

{ Appends a full path to the candidate list, deduplicated, excluding the
  directory we are installing into. }
procedure AddCandidate(const FileName: String);
var
  i: Integer;
  appDir: String;
begin
  if GPortableCandidates.Count >= SCAN_MAX_ENTRIES then exit;
  appDir := LowerCase(ExpandConstant('{app}'));
  if Pos(appDir, LowerCase(FileName)) = 1 then exit;
  for i := 0 to GPortableCandidates.Count - 1 do
    if CompareText(GPortableCandidates[i], FileName) = 0 then exit;
  GPortableCandidates.Add(FileName);
end;

{ One bounded directory probe: lists Dir's entries (counted against
  SCAN_MAX_ENTRIES for the whole sweep), collecting stray APP_EXE_NAME
  files and recursing into subdirectories one level deep. }
procedure ScanDir(const Dir: String; Depth: Integer);
var
  FindRec: TFindRec;
  FullPath: String;
begin
  if (GPortableCandidates.Count >= SCAN_MAX_ENTRIES) or
     (GScanVisits >= SCAN_MAX_VISITS) then exit;
  if FindFirst(AddBackslash(Dir) + '*', FindRec) then begin
    try begin
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then begin
          GScanVisits := GScanVisits + 1;
          FullPath := AddBackslash(Dir) + FindRec.Name;
          if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then begin
            if Depth < SCAN_MAX_DEPTH then
              ScanDir(FullPath, Depth + 1);
          end else if CompareText(FindRec.Name, APP_EXE_NAME) = 0 then
            AddCandidate(FullPath);
          if (GPortableCandidates.Count >= SCAN_MAX_ENTRIES) or
             (GScanVisits >= SCAN_MAX_VISITS) then exit;
        end;
      until not FindNext(FindRec);
    end
    finally
      FindClose(FindRec);
    end;
  end;
end;

{ Sweep the known portable-copy locations for stray RedactionTool.exe files.
  Bounds: 1 level of recursion, SCAN_MAX_ENTRIES matches overall. }
procedure FindPortableCopies();
var
  Roots: array[0..5] of String;
  i: Integer;
begin
  GPortableCandidates.Clear;
  GScanVisits := 0;
  Roots[0] := ExpandConstant('{userdesktop}');
  Roots[1] := ExpandConstant('{userfavorites}');
  Roots[2] := ExpandConstant('{userprograms}');
  Roots[3] := ExpandConstant('{userappdata}');
  Roots[4] := ExpandConstant('{localappdata}');
  Roots[5] := ExpandConstant('{userpf}');
  for i := 0 to 5 do begin
    if (GPortableCandidates.Count >= SCAN_MAX_ENTRIES) or
       (GScanVisits >= SCAN_MAX_VISITS) then exit;
    ScanDir(Roots[i], 0);
  end;
end;

{ Narrows the candidate list to files that are SAFE to delete:
  - version resource readable AND strictly older than {#AppVersion};
  - never delete on version ambiguity (equal, newer, or unreadable version),
    and never delete anything when the installer itself is a dev build;
  - never the installed exe (already excluded via the install directory
    in AddCandidate).
  What remains is shown to the user for explicit confirmation. }
procedure FilterOldPortableCopies();
var
  i: Integer;
  ver: String;
begin
  if IsDevVersion('{#AppVersion}') then begin
    Log('Portable sweep: installer is a dev build, skipping cleanup.');
    GPortableCandidates.Clear;
    exit;
  end;
  i := 0;
  while i < GPortableCandidates.Count do begin
    if GetVersionNumbersString(GPortableCandidates[i], ver)
       and (ver <> '')
       and (CompareVersions(ver, '{#AppVersion}') < 0) then begin
      Log('Portable candidate (older, ' + ver + '): ' + GPortableCandidates[i]);
      i := i + 1;
    end else begin
      Log('Portable copy kept (same/newer/unknown version): ' +
        GPortableCandidates[i]);
      GPortableCandidates.Delete(i);
    end;
  end;
end;

{ Deletes the confirmed candidates, returning how many were removed.
  Re-checks that no instance of the app is running first (the app was
  closed by EnsureAppNotRunning, but it may have been relaunched). }
function DeletePortableCopies(): Integer;
var
  i: Integer;
begin
  Result := 0;
  if GPortableCandidates.Count = 0 then exit;
  if IsAppRunning() then begin
    Log('Portable sweep: app is running again, aborting deletion.');
    exit;
  end;
  for i := 0 to GPortableCandidates.Count - 1 do
    if DeleteFile(GPortableCandidates[i]) then begin
      Log('Removed stale portable copy: ' + GPortableCandidates[i]);
      Result := Result + 1;
    end else
      Log('Could not remove (in use or access denied): ' +
        GPortableCandidates[i]);
end;

{ --- item 2: downgrade refusal ------------------------------------------- }

{ True when /ForceDowngrade was passed (any common boolean spelling). }
function ForceDowngradeRequested(): Boolean;
var
  i: Integer;
  p: String;
begin
  Result := False;
  for i := 1 to ParamCount do begin
    p := LowerCase(ParamStr(i));
    if (p = '/forcedowngrade') or (p = '-forcedowngrade') or
       (p = '/forcedowngrade=true') or (p = '/forcedowngrade=1') or
       (p = '/forcedowngrade=yes') then begin
      Result := True;
      exit;
    end;
  end;
end;

{ --- event functions ------------------------------------------------------ }
{ Flow:
  InitializeSetup   -> detect prior install; refuse a downgrade (unless
                       /ForceDowngrade); create the candidate list.
  PrepareToInstall  -> ensure the app is closed (Retry/Cancel, optional
                       "End it"); sweep portable copies, filter to strictly
                       older files, ask the user, then delete on Yes.
  Cleanup           -> free the candidate list.                            }

function InitializeSetup(): Boolean;
var
  HadVersion: Boolean;
begin
  Result := True;
  GPortableCandidates := TStringList.Create;

  { Item 1: detect a prior INSTALLED version via the Inno uninstall key. }
  GPriorInstallFound := GetInstalledVersion(GPriorVersion, GPriorLocation,
    GPriorIcon, HadVersion);
  if GPriorInstallFound then begin
    if HadVersion then
      Log(Format('Prior installed version found: %s (dir: %s)', [GPriorVersion,
        GPriorLocation]))
    else
      Log('Prior installed version found (no DisplayVersion readable).');
  end else
    Log('No prior installed version found (fresh install or portable use).');

  { Upgrade mechanics (Inno Setup 6): because AppId and DefaultDirName are
    unchanged, Setup does NOT run the old uninstaller -- it appends to the
    existing uninstall log and replaces files in place, keeping a single
    uninstall entry. This code therefore only detects/supersedes; the old
    exe is superseded by the new copy. }

  { Item 2: refuse to downgrade a NEWER installed version unless the user
    explicitly passes /ForceDowngrade. Portable copies of equal/newer
    version are protected separately in FilterOldPortableCopies. }
  if HadVersion and (not IsDevVersion('{#AppVersion}')) and
     (not IsDevVersion(GPriorVersion)) and
     (CompareVersions(GPriorVersion, '{#AppVersion}') > 0) then begin
    if ForceDowngradeRequested() then
       Log(Format('Downgrade %s -> %s forced via /ForceDowngrade.', [GPriorVersion,
        '{#AppVersion}']))
    else begin
      MsgBox('A newer version of Redaction Tool is already installed (' +
         GPriorVersion + '), but this installer is for version ' +
        '{#AppVersion}.'#13#10#13#10 +
        'Installing an older version over a newer one can leave the ' +
        'program in a mixed state. Please download the latest ' +
        'installer instead.'#13#10#13#10 +
        '(To install this older version anyway, run the installer ' +
        'again with the /ForceDowngrade switch.)',
        mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  i: Integer;
  Msg, Location, NewDir, DirPart: String;
  Found: Boolean;
begin
  Result := '';

  { Item 3: no instance of the app may be running before we touch files.
    Cancelling here aborts the installation cleanly. }
  if not EnsureAppNotRunning() then begin
    Result := 'Redaction Tool is still running. Please close it, then ' +
      'run the installer again.';
    exit;
  end;

  { Item 4: best-effort sweep of stray portable copies, always with an
    explicit user confirmation -- never silent. }
  FindPortableCopies();
  FilterOldPortableCopies();

  { Guard: if the previous install's recorded location (InstallLocation,
    or the DisplayIcon path) points at an exe outside our install folder
    -- e.g. someone relocated the app or a portable copy lives there --
    show it alongside the sweep results so the user can decide. If it is
    strictly older than this version it joins the deletable list. }
  if GPriorInstallFound then begin
    Location := GPriorLocation;
    if Location = '' then Location := GPriorIcon;
    if Location <> '' then begin
      if Pos(',', Location) > 0 then
        Location := Copy(Location, 1, Pos(',', Location) - 1);
      Location := Trim(Location);
      if (Pos(LowerCase(APP_EXE_NAME), LowerCase(Location)) > 0) and
         FileExists(Location) then begin
        NewDir := LowerCase(ExpandConstant('{app}'));
        DirPart := LowerCase(ExtractFileDir(Location));
        if (DirPart <> '') and (Pos(NewDir, DirPart) <> 1) then begin
          Found := False;
          for i := 0 to GPortableCandidates.Count - 1 do
            if CompareText(GPortableCandidates[i], Location) = 0 then
              Found := True;
          if not Found then begin
            if IsDevVersion('{#AppVersion}') then
              Log('Prior-install exe kept (dev build): ' + Location)
            else begin
              { Only queue it when its version resource proves it is older. }
              if GetVersionNumbersString(Location, Msg) and (Msg <> '') and
                 (CompareVersions(Msg, '{#AppVersion}') < 0) then
                GPortableCandidates.Add(Location)
              else
                Log('Prior-install exe kept (same/newer/unknown version): ' +
                  Location);
            end;
          end;
        end;
      end;
    end;
  end;

  if GPortableCandidates.Count > 0 then begin
    Msg := 'Setup found an older portable copy of RedactionTool.exe ' +
      '(outside the installed program folder):'#13#10#13#10;
    for i := 0 to GPortableCandidates.Count - 1 do
      Msg := Msg + '  ' + GPortableCandidates[i] + #13#10;
    Msg := Msg + #13#10 + 'Remove these old copies now? Your Redaction ' +
      'Tool presets and settings are never touched.'#13#10#13#10 +
      'Choosing No keeps the files where they are.';
    if MsgBox(Msg, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      Log(Format('Portable copies removed: %d', [DeletePortableCopies()]))
    else
      Log('User chose to keep portable copies.');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    { Nothing to clean here -- all deletion happens in PrepareToInstall.
      This hook only frees the candidate list once the wizard is done with
      it. }
    if GPortableCandidates <> nil then begin
      GPortableCandidates.Free;
      GPortableCandidates := nil;
    end;
  end;
end;

