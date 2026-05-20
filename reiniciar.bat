@echo off
echo Reiniciando todas las instancias del sistema (Servidor y Clientes)...

:: Verificar si el usuario ha solicitado recompilar el frontend
if "%1"=="build" (
    echo.
    echo [RECOPILANDO CLIENTE WEB] Detectado parámetro 'build'...
    echo Esto puede tardar unos 30-40 segundos...
    cd /d "%~dp0override_app"
    call flutter build web --release
    cd /d "%~dp0"
    if not exist "%~dp0override_app\build\web\sound" mkdir "%~dp0override_app\build\web\sound"
    xcopy /Y /Q "%~dp0sound\*.mp3" "%~dp0override_app\build\web\sound\" >nul
    echo Recompilación finalizada con éxito. Sonidos restaurados.
    echo.
) else (
    echo [CONSEJO] Si has hecho cambios en la UI de Flutter, ejecuta: .\reiniciar.bat build
)

echo Cerrando procesos activos de la ronda anterior...

:: Cerrar procesos de Edge (los emuladores de navegador)
taskkill /IM msedge.exe /F >nul 2>&1

:: Cerrar procesos de Dart/Flutter (los compiladores y runners)
taskkill /IM dart.exe /F >nul 2>&1

:: Cerrar procesos de Python (servidor central y servidor web estatico)
taskkill /IM python.exe /F >nul 2>&1

:: Cerrar todas las consolas de cmd que tengan en su titulo "flutter", "logica.py", "python" o "server"
taskkill /F /FI "WINDOWTITLE eq *flutter*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq *logica.py*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq *python*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq *server*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq *static-server*" >nul 2>&1

echo.
echo Todo limpio. Relanzando el entorno completo...
:: Usamos ping en vez de timeout para evitar errores de redireccion de consola
ping -n 3 127.0.0.1 >nul
call "%~dp0envioroment.bat"
