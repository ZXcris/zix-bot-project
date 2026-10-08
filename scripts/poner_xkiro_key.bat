@echo off
REM Doble clic: pide tu XKIRO_API_KEY sin mostrarla y la guarda en tu Windows.
REM No escribe la key en ningun archivo del proyecto.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0set_xkiro_key.ps1"
pause
