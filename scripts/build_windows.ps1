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

# Módulos que o app não usa. O Tkinter saiu na JOW-21; os do Qt vêm do spike (docs/arquitetura-2.0.md).
$excludedModules = @(
    "tkinter",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtVirtualKeyboard",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtMultimediaWidgets"
)
$excludeArgs = $excludedModules | ForEach-Object { "--exclude-module", $_ }

# Caminhos absolutos: com --specpath, o PyInstaller resolve os relativos a partir de build\.
& $python -m PyInstaller --noconfirm --clean --windowed --name ytDown `
    --specpath "$root\build" --workpath "$root\build" --distpath "$root\dist" `
    --icon "$root\assets\icon.ico" `
    --add-data "$root\assets\icon.ico;assets" `
    --add-data "$root\assets\default_cover.jpg;assets" `
    --add-data "$root\assets\theme;assets\theme" `
    --add-binary "$ffmpeg;ffmpeg" `
    @excludeArgs `
    "$root\main.py"
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o executável." }

$app = "$root\dist\ytDown"
$qt = "$app\_internal\PySide6"

# Arquivos do Qt que o PyInstaller copia mesmo sem uso (medidos no spike, JOW-9).
$unusedQtFiles = @(
    "opengl32sw.dll",
    "Qt6Quick.dll", "Qt6Qml.dll", "Qt6QmlMeta.dll", "Qt6QmlModels.dll", "Qt6QmlWorkerScript.dll",
    "Qt6VirtualKeyboard.dll", "Qt6OpenGL.dll", "Qt6MultimediaWidgets.dll", "QtMultimediaWidgets.pyd",
    "plugins\platforminputcontexts", "plugins\tls", "plugins\networkinformation",
    "plugins\platforms\qdirect2d.dll", "plugins\platforms\qoffscreen.dll", "plugins\platforms\qminimal.dll"
)
foreach ($item in $unusedQtFiles) {
    $path = Join-Path $qt $item
    if (Test-Path $path) { Remove-Item $path -Recurse -Force }
}
# Traduções do Qt: só português do Brasil.
Get-ChildItem "$qt\translations" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notin "qtbase_pt_BR.qm", "qtmultimedia_pt_BR.qm" } |
    Remove-Item -Force

# O que o app precisa para funcionar; sem isso, ele abriria sem ícones ou sem conseguir converter.
$required = @(
    "$app\ytDown.exe", "$app\_internal\ffmpeg\ffmpeg.exe", "$app\_internal\assets\theme\ytdown.qss",
    "$app\_internal\assets\theme\icons\play.svg", "$qt\Qt6Svg.dll",
    "$qt\plugins\iconengines\qsvgicon.dll", "$qt\plugins\imageformats\qsvg.dll", "$qt\plugins\platforms\qwindows.dll"
)
$missing = $required | Where-Object { -not (Test-Path $_) }
if ($missing) { throw "Faltam arquivos no pacote: $($missing -join ', ')" }
if (Test-Path "$app\_internal\tcl", "$app\_internal\_tkinter.pyd" | Where-Object { $_ }) {
    throw "O Tkinter não deveria estar no pacote."
}

# Licenças de terceiros que acompanham o app.
# O ffmpeg embutido é GPL: a licença e a indicação do código-fonte vão junto.
$ffmpegRoot = Split-Path (Split-Path $ffmpeg)
$licenses = "$app\licencas"
New-Item -ItemType Directory -Force "$licenses\ffmpeg" | Out-Null
foreach ($file in "LICENSE", "README.txt") {
    $source = Join-Path $ffmpegRoot $file
    if (Test-Path $source) {
        Copy-Item $source (Join-Path "$licenses\ffmpeg" $(if ($file -eq "LICENSE") { "LICENSE.txt" } else { $file }))
    } else {
        Write-Warning "Não encontrei $source; inclua a licença do ffmpeg manualmente antes de distribuir."
    }
}
# O Qt (PySide6) é LGPLv3: texto da licença, onde achar o código-fonte e a versão usada.
New-Item -ItemType Directory -Force "$licenses\qt" | Out-Null
Copy-Item "$root\licencas\qt\*" "$licenses\qt" -Force
$versions = & $python -c "import PySide6, PySide6.QtCore as c; print(f'PySide6 {PySide6.__version__}, Qt {c.qVersion()}')"
Set-Content -Path "$licenses\qt\VERSAO.txt" -Value $versions -Encoding UTF8

$size = (Get-ChildItem $app -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Pronto: dist\ytDown\ytDown.exe ({0:N1} MB)" -f $size)
