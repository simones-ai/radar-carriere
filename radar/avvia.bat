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
rem Certificati di sicurezza aggiornati (evita l'errore "certificate has expired" su alcuni PC Windows)
python -c "import certifi" >nul 2>&1
if errorlevel 1 (
    echo Installo i certificati di sicurezza aggiornati, solo la prima volta...
    python -m pip install --quiet --disable-pip-version-check certifi
)
python radar.py
pause
