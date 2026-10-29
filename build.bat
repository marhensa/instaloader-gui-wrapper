@echo off
echo ========================================
echo Cleaning up previous builds...
echo ========================================
if exist build rd /s /q build
if exist dist rd /s /q dist
if exist *.spec del /q *.spec
echo Done.

echo ========================================
echo Building Instaloader GUI Wrapper
echo ========================================

REM Activate virtual environment if exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Install PyInstaller if not installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

REM Prepare data bundling arguments
set "DATA_ARGS="
if exist "icon.ico" set DATA_ARGS=%DATA_ARGS% --add-data "icon.ico;."
if exist "assets" set DATA_ARGS=%DATA_ARGS% --add-data "assets;assets"

REM Build the executable
echo Building executable...
if exist "icon.ico" (
    pyinstaller --onefile --windowed --name "Instaloader-GUI-Wrapper" --icon=icon.ico %DATA_ARGS% run.py
) else (
    echo Note: icon.ico not found, building without custom icon
    pyinstaller --onefile --windowed --name "Instaloader-GUI-Wrapper" %DATA_ARGS% run.py
)

if errorlevel 1 (
    echo.
    echo ========================================
    echo [ERROR] PyInstaller build failed!
    echo ========================================
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build complete!
echo Executable: dist\Instaloader-GUI-Wrapper.exe
echo ========================================
pause
