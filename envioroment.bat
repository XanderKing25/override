@echo off
echo Iniciando protocolo de despliegue del sistema...

:: Consola 1 (Server)
echo Levantando servidor central...
start "server" cmd /k ".\venv\Scripts\activate && python logica.py"

:: Consolas de Clientes Flutter
echo Desplegando cliente d1...
start "d1" cmd /k "cd /d %~dp0override_app && flutter run -d edge"

echo Desplegando cliente d2...
start "d2" cmd /k "cd /d %~dp0override_app && flutter run -d edge"

echo Desplegando cliente d3...
start "d3" cmd /k "cd /d %~dp0override_app && flutter run -d edge"

echo Desplegando cliente d4...
start "d4" cmd /k "cd /d %~dp0override_app && flutter run -d edge"

echo Todas las instancias han sido inyectadas.
exit