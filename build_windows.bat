@echo off
setlocal
cd /d "%~dp0"

echo.
echo ===============================================
echo   ORBIX Technologies - Windows Applications Build
echo ===============================================
echo.

py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3 was not found.
  echo Install Python 3 from https://www.python.org/downloads/windows/
  echo and select "Add Python to PATH" during installation.
  pause
  exit /b 1
)

echo Installing application build requirements...
py -3 -m pip install --disable-pip-version-check --upgrade pip
if errorlevel 1 (
  echo Could not update pip. Check the internet connection and try again.
  pause
  exit /b 1
)

py -3 -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Could not download pywebview and PyInstaller from pypi.org.
  echo Connect this build PC to the internet, then run this file again.
  pause
  exit /b 1
)

py -3 -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo PyInstaller is not installed. Run this file again while connected to the internet.
  pause
  exit /b 1
)

echo Building ORBIX Technologies POS.exe...
py -3 -m PyInstaller --noconfirm --clean --windowed --onedir --name "ORBIX Technologies POS" ^
  --add-data "assets;assets" ^
  --add-data "orbix.db;." ^
  --add-data "index.html;." ^
  --add-data "app.js;." ^
  --add-data "enterprise.js;." ^
  --add-data "payment-ui.js;." ^
  --add-data "daily-report.js;." ^
  --collect-all webview ^
  --collect-all qrcode ^
  --collect-all PIL ^
  --hidden-import webview.platforms.edgechromium ^
  desktop.py

if errorlevel 1 (
  echo The desktop application build failed. Read the error above and try again.
  pause
  exit /b 1
)

echo Building ORBIX Technologies IT.exe...
py -3 -m PyInstaller --noconfirm --clean --windowed --onedir --name "ORBIX Technologies IT" ^
  --add-data "assets;assets" ^
  --add-data "orbix.db;." ^
  --add-data "index.html;." ^
  --add-data "app.js;." ^
  --add-data "enterprise.js;." ^
  --add-data "payment-ui.js;." ^
  --add-data "daily-report.js;." ^
  --collect-all webview ^
  --collect-all qrcode ^
  --collect-all PIL ^
  --hidden-import webview.platforms.edgechromium ^
  desktop_it.py

if errorlevel 1 (
  echo The ORBIX Technologies IT desktop build failed. Read the error above and try again.
  pause
  exit /b 1
)

echo.
echo Build complete.
echo POS application: dist\ORBIX Technologies POS\ORBIX Technologies POS.exe
echo IT application:  dist\ORBIX Technologies IT\ORBIX Technologies IT.exe
echo To create both installable setup files, run: create_installer.bat
pause
