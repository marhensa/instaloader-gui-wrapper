@echo off
echo ========================================
echo Building Instaloader GUI Wrapper
echo ========================================

REM Activate virtual environment if exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Install PyInstaller if not installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

REM Build the executable
echo Building executable...
if exist "icon.ico" (
    pyinstaller --onefile --windowed --name "Instaloader-GUI-Wrapper" --icon=icon.ico --add-data "icon.ico;." run.py
) else (
    echo Note: icon.ico not found, building without custom icon
    pyinstaller --onefile --windowed --name "Instaloader-GUI-Wrapper" run.py
)

echo.
echo ========================================
echo Build complete!
echo Executable: dist\Instaloader-GUI-Wrapper.exe
echo ========================================
pause
