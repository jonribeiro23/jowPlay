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

# Com o app aberto, o PyInstaller apagaria parte de dist\ytDown e só então falharia.
$running = Get-Process ytDown -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$PSScriptRoot\dist\*" }
if ($running) { throw "Feche o ytDown antes de gerar o executável: ele está aberto a partir da pasta dist." }

$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source

& $python -m PyInstaller --noconfirm --clean --windowed --name ytDown `
    --icon icon.ico `
    --add-data "icon.ico;." `
    --add-data "default_cover.jpg;." `
    --add-binary "$ffmpeg;ffmpeg" `
    app.py
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o executável." }

# O ffmpeg embutido é GPL: a licença e a indicação do código-fonte acompanham o app.
$ffmpegRoot = Split-Path (Split-Path $ffmpeg)
$licenses = "dist\ytDown\licencas\ffmpeg"
New-Item -ItemType Directory -Force $licenses | Out-Null
foreach ($file in "LICENSE", "README.txt") {
    $source = Join-Path $ffmpegRoot $file
    if (Test-Path $source) {
        Copy-Item $source (Join-Path $licenses $(if ($file -eq "LICENSE") { "LICENSE.txt" } else { $file }))
    } else {
        Write-Warning "Não encontrei $source; inclua a licença do ffmpeg manualmente antes de distribuir."
    }
}

Write-Host "Pronto: dist\ytDown\ytDown.exe"
