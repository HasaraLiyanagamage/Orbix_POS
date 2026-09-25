@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt
py -3 desktop.py
