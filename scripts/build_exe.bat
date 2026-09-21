@echo off
setlocal
cd /d "%~dp0\.."

echo Running build_exe.ps1 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1" %*
if errorlevel 1 (
  echo.
  echo Build FAILED.
  pause
  exit /b 1
)

echo.
echo Build OK. EXE is in the dist\ folder.
pause
endlocal
