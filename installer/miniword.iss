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
ChangesAssociations=yes

[Files]
Source: "..\dist\MiniWord\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\MiniWord"; Filename: "{app}\MiniWord.exe"
Name: "{commondesktop}\MiniWord"; Filename: "{app}\MiniWord.exe"; Tasks: desktopicon

[Registry]
; .txl: MiniWord is the program for it
Root: HKA; Subkey: "Software\Classes\.txl"; ValueType: string; ValueName: ""; ValueData: "MiniWord.Document"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\MiniWord.Document"; ValueType: string; ValueName: ""; ValueData: "MiniWord Document"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\MiniWord.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\MiniWord.exe,0"
Root: HKA; Subkey: "Software\Classes\MiniWord.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\MiniWord.exe"" ""%1"""
; .md, .markdown, .txt: offered under "Open with"; the default stays
; the user's choice
Root: HKA; Subkey: "Software\Classes\.md\OpenWithProgids"; ValueType: string; ValueName: "MiniWord.Markdown"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.markdown\OpenWithProgids"; ValueType: string; ValueName: "MiniWord.Markdown"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.txt\OpenWithProgids"; ValueType: string; ValueName: "MiniWord.Text"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\MiniWord.Markdown"; ValueType: string; ValueName: ""; ValueData: "Markdown Document"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\MiniWord.Markdown\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\MiniWord.exe,0"
Root: HKA; Subkey: "Software\Classes\MiniWord.Markdown\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\MiniWord.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\MiniWord.Text"; ValueType: string; ValueName: ""; ValueData: "Text Document"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\MiniWord.Text\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\MiniWord.exe,0"
Root: HKA; Subkey: "Software\Classes\MiniWord.Text\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\MiniWord.exe"" ""%1"""

[Tasks]
Name: desktopicon; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
