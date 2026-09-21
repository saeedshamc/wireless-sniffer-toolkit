#Requires -Version 5.1
<#
.SYNOPSIS
  ساخت فایل اجرایی WiFi-Monitor-Suite با PyInstaller

.EXAMPLE
  .\scripts\build_exe.ps1
  .\scripts\build_exe.ps1 -Clean
  .\scripts\build_exe.ps1 -OneFile
  .\scripts\build_exe.ps1 -SkipInstall
#>
param(
    [switch]$Clean,
    [switch]$SkipInstall,
    [switch]$OneFile,
    [string]$Name = "WiFi-Monitor-Suite"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "main_gui.py"))) {
    $Root = (Get-Location).Path
}
Set-Location $Root

Write-Host "==> Root: $Root" -ForegroundColor Cyan

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "python پیدا نشد. Python را نصب کنید و دوباره تلاش کنید."
}

Write-Host "==> Python: $($python.Source)" -ForegroundColor Cyan
& python -c "import sys; print(sys.version)"

if (-not $SkipInstall) {
    Write-Host "==> نصب وابستگی‌های اجرا و بیلد..." -ForegroundColor Cyan
    & python -m pip install --upgrade pip
    & python -m pip install -r (Join-Path $Root "requirements.txt")
    & python -m pip install -r (Join-Path $Root "requirements-build.txt")
}

$dist = Join-Path $Root "dist"
$build = Join-Path $Root "build"
$spec = Join-Path $Root "$Name.spec"
$exe = Join-Path $dist "$Name.exe"
$onedirExe = Join-Path $dist $Name "$Name.exe"

if ($Clean) {
    Write-Host "==> پاک‌سازی build/dist/spec قبلی..." -ForegroundColor Yellow
    Get-Process -Name $Name -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "    توقف فرآیند در حال اجرا: $($_.Id)" -ForegroundColor Yellow
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
    foreach ($p in @($build, $dist, $spec)) {
        if (Test-Path $p) {
            try {
                Remove-Item -Recurse -Force $p -ErrorAction Stop
            } catch {
                Write-Host "    هشدار: نتوانست پاک شود ($p) — $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
    }
}

$env:PYTHONPATH = $Root

$bundleMode = if ($OneFile) { "--onefile" } else { "--onedir" }
Write-Host "==> حالت بسته‌بندی: $bundleMode" -ForegroundColor Cyan

$pyArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    $bundleMode,
    "--name", $Name,
    "--paths", $Root,
    "--collect-submodules", "core",
    "--collect-submodules", "ui",
    "--hidden-import", "core",
    "--hidden-import", "core.engine_factory",
    "--hidden-import", "core.engine_windows",
    "--hidden-import", "core.engine_linux",
    "--hidden-import", "core.engine_macos",
    "--hidden-import", "core.capture_display",
    "--hidden-import", "core.platform_utils",
    "--hidden-import", "core.export_utils",
    "--hidden-import", "core.process_utils",
    "--hidden-import", "core.base_engine",
    "--hidden-import", "core.settings",
    "--hidden-import", "core.alerts",
    "--hidden-import", "core.oui_lookup",
    "--hidden-import", "core.elevate",
    "--hidden-import", "core.session_log",
    "--hidden-import", "core.hardware_hints",
    "--hidden-import", "ui.charts",
    "--exclude-module", "PySide6.QtWebEngineCore",
    "--exclude-module", "PySide6.QtWebEngineWidgets",
    "--exclude-module", "PySide6.QtWebEngineQuick",
    "--exclude-module", "PySide6.Qt3DCore",
    "--exclude-module", "PySide6.Qt3DRender",
    "--exclude-module", "PySide6.QtCharts",
    "--exclude-module", "PySide6.QtDataVisualization",
    "--exclude-module", "matplotlib",
    "--exclude-module", "numpy",
    "--exclude-module", "pandas",
    "main_gui.py"
)

Write-Host "==> شروع PyInstaller..." -ForegroundColor Cyan
& python @pyArgs
if ($LASTEXITCODE -ne 0) {
    throw "بیلد PyInstaller ناموفق بود (exit=$LASTEXITCODE)."
}

$outPath = if ($OneFile) { $exe } else { $onedirExe }
if (-not (Test-Path $outPath)) {
    throw "فایل خروجی پیدا نشد: $outPath"
}

$sizeMb = [math]::Round(((Get-Item $outPath).Length) / 1MB, 1)
Write-Host ""
Write-Host "OK  ساخته شد: $outPath" -ForegroundColor Green
Write-Host "    اندازه فایل اصلی: $sizeMb MB" -ForegroundColor Green
Write-Host "    برای مانیتور مود: Run as Administrator" -ForegroundColor Yellow
