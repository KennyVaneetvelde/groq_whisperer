@echo off
cd /d "%~dp0"
call C:\Users\%USERNAME%\anaconda3\Scripts\activate.bat
python main.py
pause
