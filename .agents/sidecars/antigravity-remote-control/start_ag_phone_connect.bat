@echo off
setlocal enabledelayedexpansion
title Antigravity Phone Connect

:: Navigate to the script's directory
cd /d "%~dp0"

:: Check for .env file
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] .env file not found. Creating from .env.example...
        copy .env.example .env >nul
        echo [SUCCESS] .env created from template!
        echo [ACTION] Please update .env if you wish to change defaults.
        echo.
    )
)

echo ===================================================
echo   Antigravity Phone Connect Launcher
echo ===================================================
echo.

echo [STARTING] Launching via Unified Launcher...
chcp 65001 >nul
set PYTHONUTF8=1

"C:\Program Files\Tailscale\tailscale.exe" status >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "TAILSCALE_AVAILABLE=true"
    
    :: Extract Tailscale Domain
    python -c "import json, subprocess; out = b''; exec('try:\n out = subprocess.check_output([\'C:/Program Files/Tailscale/tailscale.exe\', \'status\', \'--json\'])\n data=json.loads(out)\n dns = data.get(\'Self\', {}).get(\'DNSName\', \'\')\n print(dns.rstrip(\'.\'))\nexcept Exception:\n pass')" > "%TEMP%\ts_domain.txt" 2>nul
    set /p TAILSCALE_DOMAIN=<"%TEMP%\ts_domain.txt"
    del "%TEMP%\ts_domain.txt"
    
    if not "!TAILSCALE_DOMAIN!"=="" (
        echo [INFO] Detected Tailscale Domain: !TAILSCALE_DOMAIN!
        echo [INFO] Generating Tailscale SSL certificates...
        if not exist "certs\" mkdir certs
        "C:\Program Files\Tailscale\tailscale.exe" cert -cert-file certs\server.cert -key-file certs\server.key !TAILSCALE_DOMAIN!
        if !errorlevel! neq 0 (
            echo [WARNING] Failed to generate Tailscale certificates. Server will fall back to HTTP if certificates are missing.
        )
    ) else (
        echo [INFO] Could not detect Tailscale domain.
    )
) else (
    set "TAILSCALE_AVAILABLE=false"
    echo [INFO] Tailscale daemon is not running or authenticated. Skipping domain extraction.
)

if not exist "venv\" (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
)
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

if "%TAILSCALE_AVAILABLE%"=="true" (
    :: Detect Tailscale IPv4 address
    for /f "tokens=*" %%i in ('"C:\Program Files\Tailscale\tailscale.exe" ip -4 2^>nul') do set "TAILSCALE_IP=%%i"
    if defined TAILSCALE_IP (
        set "HOST=!TAILSCALE_IP!"
        echo [INFO] Tailscale IP detected: !TAILSCALE_IP!
    ) else (
        echo [INFO] Tailscale IP not detected. Falling back to default host.
    )
)

python launcher.py --mode local

:: Keep window open if server crashes
echo.
echo [INFO] Server stopped. Press any key to exit.
pause >nul

