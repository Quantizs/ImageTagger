@echo off
cd /d "%~dp0"
python image_tagger.py %*
if errorlevel 1 (
    echo.
    echo Nem sikerult elinditani az alkalmazast. Lasd a fenti hibauzenetet es a README.md fajlt.
    pause
)
