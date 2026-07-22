@echo off
echo Looking for Phone UI Server on port 39201...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :39201 ^| findstr LISTENING') do (
    echo Found Phone UI Server running with PID: %%a
    echo Killing process %%a...
    taskkill /F /PID %%a
    echo Server killed. The background watchdog will automatically restart it within 15 seconds!
    pause
    exit /b
)

echo No server found running on port 39201.
pause
