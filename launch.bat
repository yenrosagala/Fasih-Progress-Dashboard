@echo off
cd /d "%~dp0"

set "PYTHON_BIN=%~dp0venv\Scripts\python.exe"

if not exist "%PYTHON_BIN%" (
    echo Could not find the project Python at:
    echo %PYTHON_BIN%
    echo.
    echo Create the virtual environment and install dependencies first:
    echo python -m venv venv
    echo venv\Scripts\activate.bat
    echo pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

call "%~dp0venv\Scripts\activate.bat"

echo.
echo ========================================
echo    fasih-analytics
echo ========================================
echo.

"%PYTHON_BIN%" make_manual_session.py --from-clipboard
if errorlevel 1 (
    echo.
    echo Could not create inputs\manual_session.json from the clipboard.
    echo Copy the Cookie header from Chrome DevTools and try again.
    echo.
    pause
    exit /b 1
)

"%PYTHON_BIN%" main.py

echo.
echo ========================================
echo    Done. Press any key to close.
echo ========================================
pause >nul
