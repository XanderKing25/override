@echo off
echo Reiniciando todas las instancias del sistema (Servidor y Clientes)...

echo Cerrando procesos activos de la ronda anterior...
taskkill /F /FI "WINDOWTITLE eq d1" /T >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq d2" /T >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq d3" /T >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq d4" /T >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq server" /T >nul 2>&1

:: Cerrar procesos residuales de Dart/Flutter para liberar puertos y locks
taskkill /IM dart.exe /F >nul 2>&1

echo.
echo Todo limpio. Relanzando el entorno completo...
timeout /t 2 /nobreak >nul
call "%~dp0envioroment.bat"
