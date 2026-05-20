@echo off
echo Cerrando todas las instancias del sistema (Servidor y Clientes)...

echo Cerrando procesos activos de la ronda anterior...

:: Cerrar procesos de Edge (los emuladores de navegador)
taskkill /IM msedge.exe /F >nul 2>&1

:: Cerrar procesos de Dart/Flutter (los compiladores y runners)
taskkill /IM dart.exe /F >nul 2>&1

:: Cerrar procesos de Python (el servidor Flask backend)
taskkill /IM python.exe /F >nul 2>&1

:: Cerrar todas las consolas de cmd que tengan en su titulo "flutter" o "logica.py"
taskkill /F /FI "WINDOWTITLE eq *flutter*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq *logica.py*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq *python*" >nul 2>&1

echo.
echo Todas las instancias han sido cerradas.