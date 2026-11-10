# Gera dist\ytDown-celular.apk. Precisa do JDK 17 e do Android SDK em %LOCALAPPDATA%\Android.
# Uso, na raiz do projeto: powershell -ExecutionPolicy Bypass -File scripts\build_android.ps1
param([switch]$Offline)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot
Set-Location (Join-Path $root "android")

$base = Join-Path $env:LOCALAPPDATA "Android"
$env:JAVA_HOME = Join-Path $base "jdk-17"
$env:ANDROID_HOME = Join-Path $base "Sdk"
$gradle = ".\gradlew.bat"
foreach ($required in $env:JAVA_HOME, $env:ANDROID_HOME) {
    if (-not (Test-Path $required)) { throw "Não encontrado: $required" }
}
if ($Offline) {
    # O wrapper pode baixar a distribuição antes de o Gradle receber --offline.
    $gradleHome = if ($env:GRADLE_USER_HOME) { $env:GRADLE_USER_HOME } else { Join-Path $env:USERPROFILE ".gradle" }
    $cachedGradle = Get-ChildItem (Join-Path $gradleHome "wrapper\dists\gradle-8.9-bin\*\gradle-8.9\bin\gradle.bat") -ErrorAction SilentlyContinue
    if (-not $cachedGradle) { throw "Modo offline requer Gradle 8.9 já instalado no cache do wrapper." }
    $gradle = @($cachedGradle)[0].FullName
}

$gradleArgs = @("--no-daemon", "--console=plain")
if ($Offline) { $gradleArgs += "--offline" }
& $gradle @gradleArgs testDebugUnitTest assembleDebug
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o APK." }

$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force $dist | Out-Null
Copy-Item "app\build\outputs\apk\debug\app-debug.apk" (Join-Path $dist "ytDown-celular.apk") -Force
Write-Host "Pronto: dist\ytDown-celular.apk"
