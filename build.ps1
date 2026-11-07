# Gera dist\ytDown\ytDown.exe usando a versão mais recente do yt-dlp.
# Uso: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o ambiente virtual." }
}

& $python -m pip install --quiet --upgrade -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependências." }

& $python -m unittest
if ($LASTEXITCODE -ne 0) { throw "Os testes falharam." }

$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source

& $python -m PyInstaller --noconfirm --clean --windowed --name ytDown `
    --icon icon.ico `
    --add-data "icon.ico;." `
    --add-binary "$ffmpeg;ffmpeg" `
    app.py
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o executável." }

Write-Host "Pronto: dist\ytDown\ytDown.exe"
