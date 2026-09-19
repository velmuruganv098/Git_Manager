@echo off
cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo.
echo Starting Local GitHub Manager...
echo Open http://127.0.0.1:5757 in your browser.
echo Press CTRL+C in this window to stop it.
echo.

python app.py

pause
