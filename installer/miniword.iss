#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif

[Setup]
AppName=MiniWord
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\MiniWord
DefaultGroupName=MiniWord
OutputDir=Output
OutputBaseFilename=MiniWord-{#MyAppVersion}-setup
Compression=lzma
SolidCompression=yes
SetupIconFile=..\miniword\icons\miniword.ico
UninstallDisplayIcon={app}\MiniWord.exe

[Files]
Source: "..\dist\MiniWord\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\MiniWord"; Filename: "{app}\MiniWord.exe"
Name: "{commondesktop}\MiniWord"; Filename: "{app}\MiniWord.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
