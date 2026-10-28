; =============================================================================
; Script do Instalador Windows (Inno Setup 6) — Plutos Desktop Nativo (v1.2.0)
; Compila um instalador completo versionado (Plutos_Setup_1.2.0.exe) que:
; 1. Instala o executável nativo Plutos.exe e bibliotecas em Program Files (ou AppData)
; 2. Cria automaticamente todas as pastas de banco de dados, backups e exportação
; 3. Inicializa o banco SQLite padrão limpo (base_padrao.sqlite) sem sobrescrever dados existentes,
;    e inclui também a base demonstrativa (joao_brasileiro_5000_modelo.sqlite)
; 4. Cria atalhos com o ícone do Plutos no Menu Iniciar e na Área de Trabalho
; =============================================================================

#define MyAppName "Plutos - Controle Financeiro Pessoal"
#define MyAppShortName "Plutos"
#ifndef MyAppVersion
#define MyAppVersion "1.1.1"
#endif
#define MyAppPublisher "Plutos Financeiro Desktop Offline"
#define MyAppExeName "Plutos.exe"

[Setup]
AppId={{8F9C3E52-4A1E-4B9D-9B2C-6E5F1A7D2026}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist\Instalador
OutputBaseFilename=Plutos_Setup_{#MyAppVersion}
SetupIconFile=..\app\assets\images\plutos.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
; Cria todas as pastas necessárias para persistência SQLite, backups automáticos (6 arquivos / 3h) e planilhas
Name: "{localappdata}\Plutos"; Flags: uninsneveruninstall
Name: "{localappdata}\Plutos\dados_usuario"; Flags: uninsneveruninstall
Name: "{localappdata}\Plutos\dados_usuario\backups"; Flags: uninsneveruninstall
Name: "{localappdata}\Plutos\exportacoes"; Flags: uninsneveruninstall

[Files]
; Copia todos os binários compilados pelo PyInstaller e ativos visuais/SQL/templates Excel
Source: "..\dist\Plutos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Inicializa a base SQLite padrão limpa (base_padrao.sqlite -> plutos.sqlite) sem sobrescrever se o usuário já tiver dados
Source: "..\dados_usuario\base_padrao.sqlite"; DestDir: "{localappdata}\Plutos\dados_usuario"; DestName: "plutos.sqlite"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "..\dados_usuario\base_padrao.sqlite"; DestDir: "{localappdata}\Plutos\dados_usuario"; DestName: "base_padrao.sqlite"; Flags: ignoreversion uninsneveruninstall

; Inclui também o banco demonstrativo alimentado (João Brasileiro R$ 5.000/mês) para consulta opcional
Source: "..\dados_usuario\joao_brasileiro_5000_modelo.sqlite"; DestDir: "{localappdata}\Plutos\dados_usuario"; DestName: "joao_brasileiro_5000_modelo.sqlite"; Flags: ignoreversion uninsneveruninstall

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
