@echo off
echo Activating Anaconda environment...
call C:\Users\%USERNAME%\anaconda3\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo Failed to activate Anaconda environment. Please check Anaconda installation and path.
    pause
    exit /b %errorlevel%
)

echo Anaconda environment activated.
echo Running Python script enhanced.py...
python .\enhanced.py
if %errorlevel% neq 0 (
    echo Python script enhanced.py encountered an error.
    pause
    exit /b %errorlevel%
)

echo Python script finished execution.
pause
