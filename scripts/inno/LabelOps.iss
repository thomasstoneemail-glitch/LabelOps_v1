; LabelOps Inno Setup Script
; Compile using the Inno Setup GUI:
; 1) Open this .iss file in the Inno Setup Compiler.
; 2) Update the ReleaseDir path below to point at your build output.
; 3) Click Build > Compile.

#define AppName "LabelOps"
#define AppVersion "0.1.0"
#define ReleaseDir "D:\\LabelOps\\dist\\LabelOps_0.1.0_YYYYMMDD"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={pf}\LabelOps
DefaultGroupName=LabelOps
OutputBaseFilename=LabelOpsInstaller
Compression=lzma
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Dirs]
Name: "D:\\LabelOps"; Permissions: users-full
Name: "D:\\LabelOps\\config"; Permissions: users-full
Name: "D:\\LabelOps\\assets"; Permissions: users-full
Name: "D:\\LabelOps\\Clients"; Permissions: users-full
Name: "D:\\LabelOps\\Logs"; Permissions: users-full

[Files]
; Application binaries
Source: "{#ReleaseDir}\LabelOpsGUI\*"; DestDir: "{app}\LabelOpsGUI"; Flags: recursesubdirs createallsubdirs
Source: "{#ReleaseDir}\LabelOpsDaemon\*"; DestDir: "{app}\LabelOpsDaemon"; Flags: recursesubdirs createallsubdirs
Source: "{#ReleaseDir}\LabelOpsPipeline\*"; DestDir: "{app}\LabelOpsPipeline"; Flags: recursesubdirs createallsubdirs

; Starter config + assets copied into D:\LabelOps
Source: "{#ReleaseDir}\config\clients.yaml"; DestDir: "D:\\LabelOps\\config"; Flags: onlyifdoesntexist
Source: "{#ReleaseDir}\config\telegram_allowlist.json"; DestDir: "D:\\LabelOps\\config"; Flags: onlyifdoesntexist
Source: "{#ReleaseDir}\assets\ClickDrop_import_template_no_header.xlsx"; DestDir: "D:\\LabelOps\\assets"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\LabelOps GUI"; Filename: "{app}\LabelOpsGUI\LabelOpsGUI.exe"
Name: "{group}\LabelOps Daemon"; Filename: "{app}\LabelOpsDaemon\LabelOpsDaemon.exe"
