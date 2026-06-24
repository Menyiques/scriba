@echo off
REM Construye el .tap de Next del juego: convierte imagenes, genera, compila y
REM empaqueta. EJECUTAR con el Python que usas para el editor (Pillow + PyYAML).
REM Cambia el nombre del .yaml si tu juego es otro.
python construye_nextap.py operacion_tifon_negro.yaml 42
echo.
pause
