@echo off
setlocal
cd /d "%~dp0"

echo.
echo ===============================================
echo   ORBIX Technologies - POS and IT Installer Build
echo ===============================================
echo.

echo Building the latest desktop application files...
call build_windows.bat
if errorlevel 1 exit /b 1

set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not exist "%ISCC%" (
  echo Inno Setup 7 or 6 was not found.
  echo Install it from: https://jrsoftware.org/isdl.php
  echo Then run this file again.
  pause
  exit /b 1
)

echo Creating ORBIX Technologies POS setup...
"%ISCC%" /DAppEdition=pos installer.iss
if errorlevel 1 (
  echo POS installer build failed.
  pause
  exit /b 1
)

echo Creating ORBIX Technologies IT setup...
"%ISCC%" /DAppEdition=it installer.iss
if errorlevel 1 (
  echo IT installer build failed.
  pause
  exit /b 1
)

echo.
echo Installers created:
echo   release\ORBIX-Technologies-POS-Setup.exe
echo   release\ORBIX-Technologies-IT-Setup.exe
pause
