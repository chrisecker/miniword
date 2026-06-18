#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif

[Setup]
AppName=miniword
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\miniword
DefaultGroupName=miniword
OutputDir=Output
OutputBaseFilename=miniword-{#MyAppVersion}-setup
Compression=lzma
SolidCompression=yes
SetupIconFile=..\miniword\icons\miniword.ico
UninstallDisplayIcon={app}\miniword.exe

[Files]
Source: "..\dist\miniword\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\miniword"; Filename: "{app}\miniword.exe"
Name: "{commondesktop}\miniword"; Filename: "{app}\miniword.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
