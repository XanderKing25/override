@echo off
echo Iniciando protocolo de despliegue del sistema...

:: Consola 1 (Server Backend Flask)
echo Levantando servidor central (Flask) en puerto 5000...
start "server" cmd /c ".\venv\Scripts\activate && python logica.py"

:: Consola 2 (Static Web Server)
echo Levantando servidor web estatico (Python) en puerto 8080...
start "static-server" cmd /c "python -m http.server 8080 --directory override_app/build/web"

:: Esperar a que los servidores se levanten (usamos ping para evitar errores de redirección)
ping -n 3 127.0.0.1 >nul

:: Abrir 4 pestañas en el mismo navegador Edge apuntando al cliente web
echo Desplegando 4 instancias del cliente en Microsoft Edge...
start msedge "http://localhost:8080"
start msedge "http://localhost:8080"
start msedge "http://localhost:8080"
start msedge "http://localhost:8080"

echo Todas las instancias han sido inyectadas y desplegadas.
exit