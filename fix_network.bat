@echo off
:: Fix Camera Network - Sets static IP 192.168.1.100 on Ethernet adapter
:: Auto-detects the Ethernet interface — works on any laptop.
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

:: Auto-detect the Ethernet adapter index (picks the first UP or disconnected Ethernet NIC)
echo [0/3] Detecting Ethernet adapter...
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-NetAdapter | Where-Object { $_.InterfaceDescription -notmatch 'Wi-Fi|Wireless|VirtualBox|VMware|Hyper-V|Loopback|Bluetooth' -and $_.InterfaceDescription -match 'Ethernet|LAN|GbE|Realtek|Intel.*Ethernet|Killer.*Ethernet' } | Select-Object -First 1 -ExpandProperty ifIndex"') do (
    set ETH_IDX=%%i
)

:: Fallback: just grab the first non-wireless, non-virtual adapter
if not defined ETH_IDX (
    for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-NetAdapter | Where-Object { $_.PhysicalMediaType -eq '802.3' } | Select-Object -First 1 -ExpandProperty ifIndex"') do (
        set ETH_IDX=%%i
    )
)

if not defined ETH_IDX (
    echo [ERROR] Could not find an Ethernet adapter. Check Device Manager.
    pause
    exit /b 1
)

:: Also grab the adapter name for display
for /f "tokens=*" %%n in ('powershell -NoProfile -Command "Get-NetAdapter -InterfaceIndex %ETH_IDX% | Select-Object -ExpandProperty Name"') do (
    set ETH_NAME=%%n
)

echo [INFO] Found adapter: "%ETH_NAME%"  (Index: %ETH_IDX%)
echo.

echo [1/3] Removing old autoconfigured IP...
powershell -NoProfile -Command "Remove-NetIPAddress -InterfaceIndex %ETH_IDX% -Confirm:$false -ErrorAction SilentlyContinue"
powershell -NoProfile -Command "Remove-NetRoute -InterfaceIndex %ETH_IDX% -Confirm:$false -ErrorAction SilentlyContinue"

echo [2/3] Assigning static IP 192.168.1.100...
powershell -NoProfile -Command "New-NetIPAddress -InterfaceIndex %ETH_IDX% -IPAddress 192.168.1.100 -PrefixLength 24 -DefaultGateway 192.168.1.1"
powershell -NoProfile -Command "Set-DnsClientServerAddress -InterfaceIndex %ETH_IDX% -ServerAddresses 8.8.8.8"

echo [3/3] Verifying IP...
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
echo  Done! Now run: python main.py
echo ================================================
pause
