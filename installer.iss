; Shared installer definition. create_installer.bat builds it twice: once for
; the POS edition and once for the independent IT edition.

#ifndef AppEdition
  #define AppEdition "pos"
#endif

#define AppVersion "1.4.2"
#define AppPublisher "ORBIX Technologies"

#if AppEdition == "it"
  #define AppName "ORBIX Technologies (IT)"
  #define AppExeName "ORBIX Technologies IT.exe"
  #define SourceFolder "ORBIX Technologies IT"
  #define InstallFolder "ORBIX Technologies IT"
  #define InstallerFileName "ORBIX-Technologies-IT-Setup"
  #define InstallerAppId "{{D1B8B7E7-5E38-4EEB-9C48-C360DA521AC3}"
#else
  #define AppName "ORBIX Technologies POS"
  #define AppExeName "ORBIX Technologies POS.exe"
  #define SourceFolder "ORBIX Technologies POS"
  #define InstallFolder "ORBIX Technologies POS"
  #define InstallerFileName "ORBIX-Technologies-POS-Setup"
  ; Keep this ID so the POS setup upgrades earlier POS installations.
  #define InstallerAppId "{{7C389A0C-25CE-4D60-858F-D1C2D78414D7}"
#endif

[Setup]
AppId={#InstallerAppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#InstallFolder}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=release
OutputBaseFilename={#InstallerFileName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayName={#AppName}

[Files]
Source: "dist\{#SourceFolder}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2ClientKey = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function ValidWebView2Version(const Version: String): Boolean;
begin
  Result := (Version <> '') and (Version <> '0.0.0.0');
end;

function WebView2RuntimeInstalled(): Boolean;
var
  Version: String;
begin
  Result :=
    (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WebView2ClientKey, 'pv', Version) and ValidWebView2Version(Version)) or
    (RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2ClientKey, 'pv', Version) and ValidWebView2Version(Version)) or
    (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + WebView2ClientKey, 'pv', Version) and ValidWebView2Version(Version));
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not WebView2RuntimeInstalled() then
    MsgBox(
      'Microsoft Edge WebView2 Runtime is required for the ORBIX POS screen and buttons to work.' + #13#10 + #13#10 +
      'Install WebView2 Runtime from Microsoft, restart Windows, then open ORBIX Technologies POS.',
      mbInformation,
      MB_OK
    );
end;
