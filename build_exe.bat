@echo off
cd /d "%~dp0"
set PYTHON="C:\Users\PaulTitto\AppData\Local\Programs\Python\Python312\python.exe"

%PYTHON% -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    %PYTHON% -m pip install pyinstaller
)

%PYTHON% -m PyInstaller --noconfirm --onefile --windowed ^
    --name "TextGrabber" ^
    --icon "app_icon.ico" ^
    --add-binary "ocr_engine.exe;." ^
    --add-data "app_icon.ico;." ^
    --add-data "Install_Shortcut.ps1;." ^
    text_grabber_app.py

echo.
echo Build complete! Standalone executable is at: dist\TextGrabber.exe
pause
