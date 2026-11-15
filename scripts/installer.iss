; Kiru - Windows installer (Inno Setup 6.6 or newer)
; Installs for the current user only, into %LOCALAPPDATA%\Kiru: no administrator rights, no UAC prompt.
; Build:  python scripts\build_installer.py      (or: ISCC.exe scripts\installer.iss after dist\Kiru exists)
; © 2026 Aden. All rights reserved.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6E0F0D0A-4B1C-4E57-9C1B-4B49525501A7}
AppName=Kiru
AppVersion={#AppVersion}
AppVerName=Kiru {#AppVersion}
AppPublisher=Aden
AppCopyright=© 2026 Aden. All rights reserved.
VersionInfoCopyright=© 2026 Aden. All rights reserved.
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Kiru
DefaultGroupName=Kiru
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
UsePreviousAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=KiruSetup
SetupIconFile=..\assets\kiru.ico
UninstallDisplayIcon={app}\Kiru.exe
UninstallDisplayName=Kiru
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
; the look: modern wizard, dark, Kiru's colours
WizardStyle=modern dark
WizardImageFile=..\assets\installer-side.bmp
WizardSmallImageFile=..\assets\installer-small.bmp
WizardImageAlphaFormat=none
ShowLanguageDialog=no
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Welcome to Kiru
WelcomeLabel2=Beat-synced edits, a timeline editor and an image editor in one app.%n%nKiru installs just for you, into your own user folder. No administrator password is needed.
FinishedLabel=Kiru is installed. Everything runs on this PC: nothing you load is uploaded.

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Kiru\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\templates"
Name: "{app}\fonts"
Name: "{app}\Exports"

[Icons]
Name: "{userprograms}\Kiru"; Filename: "{app}\Kiru.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\Kiru"; Filename: "{app}\Kiru.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Kiru.exe"; Description: "Start Kiru"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Uninstalling removes everything Kiru put on this PC: the whole %LOCALAPPDATA%\Kiru folder.
; (Exported videos are the one thing you are asked about first: see [Code] below.)
Type: filesandordirs; Name: "{app}\_temp"
Type: filesandordirs; Name: "{app}\_webview"
Type: filesandordirs; Name: "{app}\ai_models"
Type: filesandordirs; Name: "{app}\ai_model"
Type: filesandordirs; Name: "{app}\templates"
Type: filesandordirs; Name: "{app}\fonts"
Type: filesandordirs; Name: "{app}\locales"
Type: filesandordirs; Name: "{app}\ffmpeg"
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\settings.json"
Type: files; Name: "{app}\settings.json.tmp"
Type: files; Name: "{app}\*.log"
Type: dirifempty; Name: "{app}"

; (build_installer.py compiles once more with /DNoCode if this section should ever fail to compile: the installer is then
;  made without the "keep my exported videos?" question, and uninstalling removes the listed folders only)
#ifndef NoCode
[Code]
var
  KeepExports: Boolean;

function FolderHasFiles(const Dir: string): Boolean;
var
  FR: TFindRec;
begin
  Result := False;
  if FindFirst(Dir + '\*', FR) then
  begin
    try
      repeat
        if (FR.Name <> '.') and (FR.Name <> '..') then
        begin
          Result := True;
          Break;
        end;
      until not FindNext(FR);
    finally
      FindClose(FR);
    end;
  end;
end;

function InitializeSetup(): Boolean;
var
  R: Integer;
begin
  { an earlier Kiru still running (also one without a window) would keep its files locked: end it before installing }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /t /im Kiru.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
  Result := True;
end;

function InitializeUninstall(): Boolean;
var
  R: Integer;
begin
  { Kiru (and any FFmpeg it started) must not be running, or its files cannot be removed }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /t /im Kiru.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
  KeepExports := False;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Src, Dst: string;
  N: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    { the videos you exported are yours: ask before they go (a silent uninstall keeps them) }
    Src := ExpandConstant('{app}\Exports');
    if DirExists(Src) and FolderHasFiles(Src) then
    begin
      if UninstallSilent or (MsgBox('The Kiru "Exports" folder still holds videos you exported.' + #13#10 + #13#10 +
           'Keep them? They are moved to "Kiru Exports" in your Documents folder.' + #13#10 +
           'Choose No to delete them together with everything else.', mbConfirmation, MB_YESNO) = IDYES) then
      begin
        Dst := ExpandConstant('{userdocs}\Kiru Exports');
        N := 1;
        while DirExists(Dst) do
        begin
          N := N + 1;
          Dst := ExpandConstant('{userdocs}\Kiru Exports ') + IntToStr(N);
        end;
        if not RenameFile(Src, Dst) then
        begin
          KeepExports := True;
          MsgBox('The videos could not be moved, so they are left where they are:' + #13#10 + Src, mbInformation, MB_OK);
        end;
      end;
    end;
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    { whatever is left of %LOCALAPPDATA%\Kiru goes too - nothing stays behind on the drive }
    if not KeepExports then
      DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
#endif
