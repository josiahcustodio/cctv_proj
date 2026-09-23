@echo off
:: Fix Camera Network - Sets static IP 192.168.1.100 on Ethernet adapter
:: Must be run as Administrator

echo ================================================
echo  CCTV Camera Network Fix
echo  Setting Ethernet to 192.168.1.100/24
echo ================================================
echo.

:: Check admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Please right-click this file and choose "Run as administrator"
    pause
    exit /b 1
)

echo [1/3] Removing old autoconfigured IP...
powershell -Command "Remove-NetIPAddress -InterfaceIndex 4 -Confirm:$false -ErrorAction SilentlyContinue"
powershell -Command "Remove-NetRoute -InterfaceIndex 4 -Confirm:$false -ErrorAction SilentlyContinue"

echo [2/3] Assigning static IP 192.168.1.100...
powershell -Command "New-NetIPAddress -InterfaceIndex 4 -IPAddress 192.168.1.100 -PrefixLength 24 -DefaultGateway 192.168.1.1"
powershell -Command "Set-DnsClientServerAddress -InterfaceIndex 4 -ServerAddresses 8.8.8.8"

echo [3/3] Verifying...
ipconfig | findstr /i "192.168.1"

echo.
echo ================================================
echo  Pinging cameras...
echo ================================================
ping 192.168.1.109 -n 1 -w 2000
ping 192.168.1.111 -n 1 -w 2000
ping 192.168.1.112 -n 1 -w 2000
ping 192.168.1.113 -n 1 -w 2000

echo.
echo ================================================
echo  Done! Now run: python test_rtsp.py
echo ================================================
pause
