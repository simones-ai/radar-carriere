@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Radar Carriere
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python non e' installato.
    echo     Scaricalo da https://www.python.org/downloads/ - versione 3.10 o successiva
    echo     e durante l'installazione spunta "Add python.exe to PATH".
    pause
    exit /b 1
)
python radar.py
pause
