# Gera dist\ytDown\ytDown.exe usando a versão mais recente do yt-dlp.
# Uso, na raiz do projeto: powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot
Set-Location $root

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o ambiente virtual." }
}

& $python -m pip install --quiet --upgrade -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependências." }

& $python -m unittest discover -s tests -t .
if ($LASTEXITCODE -ne 0) { throw "Os testes falharam." }

# Com o app aberto, o PyInstaller apagaria parte de dist\ytDown e só então falharia.
$running = Get-Process ytDown -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$root\dist\*" }
if ($running) { throw "Feche o ytDown antes de gerar o executável: ele está aberto a partir da pasta dist." }

$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source

# Caminhos absolutos: com --specpath, o PyInstaller resolve os relativos a partir de build\.
& $python -m PyInstaller --noconfirm --clean --windowed --name ytDown `
    --specpath "$root\build" --workpath "$root\build" --distpath "$root\dist" `
    --icon "$root\assets\icon.ico" `
    --add-data "$root\assets\icon.ico;assets" `
    --add-data "$root\assets\default_cover.jpg;assets" `
    --add-binary "$ffmpeg;ffmpeg" `
    "$root\main.py"
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
