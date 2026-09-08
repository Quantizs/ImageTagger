@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" export_polygons.py %*
) else (
    python export_polygons.py %*
)
if errorlevel 1 (
    echo.
    echo Az export sikertelen. Lasd a fenti hibauzenetet es a README.md fajlt.
    pause
)
