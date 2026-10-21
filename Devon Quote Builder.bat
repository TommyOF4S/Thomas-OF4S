@echo off
rem Double-click to open the Devon quote builder in your browser.
cd /d "%~dp0"
python -m devon_quote serve
if errorlevel 1 (
  echo.
  echo Could not start. Install Python 3 from python.org, then run:  pip install -r requirements.txt
  pause
)
