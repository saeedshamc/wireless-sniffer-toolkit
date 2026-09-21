@echo off
setlocal
cd /d "%~dp0\.."

echo Cleaning build artifacts...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist, *.spec; Write-Host 'Clean done.'"

pause
endlocal
