@echo off
REM ============================================================
REM  Empaqueta UN juego de Scriba en un .exe de Windows.
REM ============================================================
REM  Requisitos (solo la primera vez):
REM      pip install pyinstaller pyyaml pillow
REM
REM  Uso:
REM      build_player.bat "ruta\al\juego.yaml"
REM  Ejemplo:
REM      build_player.bat "Games\Operacion Tifon Negro\Operacion Tifon Negro.yaml"
REM
REM  La ventana del juego es redimensionable y el texto se ajusta solo a su
REM  ancho (sin columnas fijas).
REM  El .exe final queda en  <carpeta del juego>\dist\Windows\<Titulo>.exe
REM ============================================================

if "%~1"=="" (
  echo Uso: build_player.bat "ruta\al\juego.yaml"
  exit /b 1
)

python build_game_exe.py "%~1"

echo.
pause
