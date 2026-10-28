<#
.SYNOPSIS
    Script automatizado de compilação do Executável Nativo (Plutos.exe)
    e do Instalador Windows Versionado (Plutos_Setup_1.1.0.exe).
#>

param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

# Se nenhuma versão for passada via CLI, lê automaticamente da fonte única da verdade (app/version.py)
if (-not $Version) {
    $VersionPy = Join-Path $ProjectRoot "app\version.py"
    if (Test-Path $VersionPy) {
        $Raw = Get-Content -LiteralPath $VersionPy -Raw
        if ($Raw -match '__version__\s*=\s*["'']([^"'']+)["'']') {
            $Version = $Matches[1].Trim()
        }
    }
}
if (-not $Version) {
    try {
        $Version = (py -c "import app.version; print(app.version.__version__)" 2>$null).Trim()
    } catch {}
}
if (-not $Version) {
    $Version = "1.1.1"
}

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " [0/4] Encerrando instâncias abertas de Plutos.exe / MinhasFinancas.exe..." -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

Get-Process -Name "Plutos", "MinhasFinancas" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " [1/4] Verificando PyInstaller no ambiente Python..." -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

py -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Instalando PyInstaller..." -ForegroundColor Yellow
    py -m pip install pyinstaller
}

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " [2/4] Compilando executável nativo (Plutos.exe v$Version)..." -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

py -m PyInstaller --noconfirm --clean "$ProjectRoot\Plutos.spec"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller falhou com código $LASTEXITCODE"
}

$DistAppDir = Join-Path $ProjectRoot "dist\Plutos"
$ExePath = Join-Path $DistAppDir "Plutos.exe"

if (-not (Test-Path $ExePath)) {
    throw "Falha ao gerar $ExePath"
}

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " [3/4] Criando estrutura de pastas e bancos na distribuição portátil..." -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

$PortableUserData = Join-Path $DistAppDir "dados_usuario"
$PortableBackups  = Join-Path $PortableUserData "backups"
$PortableExports  = Join-Path $DistAppDir "exportacoes"

New-Item -ItemType Directory -Force -Path $PortableUserData | Out-Null
New-Item -ItemType Directory -Force -Path $PortableBackups  | Out-Null
New-Item -ItemType Directory -Force -Path $PortableExports  | Out-Null

$BasePadrao = Join-Path $ProjectRoot "dados_usuario\base_padrao.sqlite"
$BaseDemo   = Join-Path $ProjectRoot "dados_usuario\joao_brasileiro_5000_modelo.sqlite"

if (Test-Path $BasePadrao) {
    Copy-Item -Path $BasePadrao -Destination (Join-Path $PortableUserData "base_padrao.sqlite") -Force
    $ActivePortableDb = Join-Path $PortableUserData "plutos.sqlite"
    if (-not (Test-Path $ActivePortableDb)) {
        Copy-Item -Path $BasePadrao -Destination $ActivePortableDb -Force
    }
}
if (Test-Path $BaseDemo) {
    Copy-Item -Path $BaseDemo -Destination (Join-Path $PortableUserData "joao_brasileiro_5000_modelo.sqlite") -Force
}

Write-Host "Executável compilado com sucesso em: $ExePath" -ForegroundColor Green

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " [4/4] Compilando Instalador Windows Versionado (Inno Setup 6)..." -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

$CmdIscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
$RawCandidates = @(
    $(if ($CmdIscc) { $CmdIscc.Source } else { $null }),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$IsccExe = $RawCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if ($IsccExe) {
    Write-Host "Usando Inno Setup em: $IsccExe" -ForegroundColor Green
    & "$IsccExe" "/DMyAppVersion=$Version" "$ProjectRoot\installer\Plutos_Setup.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao compilar o instalador no Inno Setup (código $LASTEXITCODE)."
    }
    Write-Host "Instalador gerado com sucesso em: $ProjectRoot\dist\Instalador\Plutos_Setup_$Version.exe" -ForegroundColor Green
} else {
    Write-Host "Aviso: Inno Setup 6 (ISCC.exe) não encontrado no sistema." -ForegroundColor Yellow
}
