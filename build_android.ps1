# Gera dist\ytDown-celular.apk. Precisa do JDK 17 e do Android SDK em %LOCALAPPDATA%\Android.
# Uso: powershell -ExecutionPolicy Bypass -File build_android.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "android")

$base = Join-Path $env:LOCALAPPDATA "Android"
$env:JAVA_HOME = Join-Path $base "jdk-17"
$env:ANDROID_HOME = Join-Path $base "Sdk"
foreach ($required in $env:JAVA_HOME, $env:ANDROID_HOME) {
    if (-not (Test-Path $required)) { throw "Não encontrado: $required" }
}

& .\gradlew.bat --no-daemon --console=plain testDebugUnitTest assembleDebug
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o APK." }

$dist = Join-Path $PSScriptRoot "dist"
New-Item -ItemType Directory -Force $dist | Out-Null
Copy-Item "app\build\outputs\apk\debug\app-debug.apk" (Join-Path $dist "ytDown-celular.apk") -Force
Write-Host "Pronto: dist\ytDown-celular.apk"
