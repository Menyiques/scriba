@echo off
REM ============================================================
REM  Construye Scriba.exe (Windows) con PyInstaller
REM ============================================================
REM  Requisitos (solo la primera vez):
REM      pip install pyinstaller pyyaml
REM  Ejecuta este .bat en la carpeta del proyecto (donde esta editor.py).
REM  El ejecutable final queda en  dist\Scriba.exe
REM ============================================================

REM  Nombre del .exe derivado de SCRIBA_VERSION en editor.py (1.2 -> Scriba_v_1_2)
for /f "usebackq tokens=2 delims='" %%v in (`findstr /b "SCRIBA_VERSION" editor.py`) do set SVER=%%v
set SNAME=Scriba_v_%SVER:.=_%

python -m PyInstaller --noconfirm --onefile --windowed --name %SNAME% ^
  --add-data "print42_es.bas;." ^
  --add-data "print64_es.bas;." ^
  --add-data "print42_pt.bas;." ^
  --add-data "print64_pt.bas;." ^
  --add-data "scriba_logo.png;." ^
  --add-data "Scriba manual v2.2.pdf;." ^
  --add-data "player.py;." ^
  --add-data "build_game_exe.py;." ^
  --add-data "interpreter.py;." ^
  --add-data "paws_lang.py;." ^
  --hidden-import spectrum_export ^
  --hidden-import compiler ^
  --hidden-import paws_lang ^
  --hidden-import interpreter ^
  --hidden-import yaml ^
  --hidden-import next_export ^
  --hidden-import empaqueta_nextap ^
  --hidden-import mensajes ^
  --hidden-import traduccion ^
  --hidden-import png2next ^
  --hidden-import png2spectrum ^
  --hidden-import cpc_export ^
  --hidden-import png2cpc ^
  --hidden-import empaqueta_cpc ^
  --hidden-import mid2psg ^
  --hidden-import txtpack ^
  --hidden-import z80asm ^
  --hidden-import game_engine ^
  --hidden-import nativecc ^
  --hidden-import cpc_font ^
  --hidden-import dsk ^
  --hidden-import cpc_nativo ^
  --hidden-import paws_lang ^
  --hidden-import capabilities ^
  --hidden-import fx_engine ^
  --hidden-import afx ^
  editor.py

REM  Copia el .exe versionado a Scriba.exe para que Scriba.exe sea SIEMPRE la
REM  ultima version compilada.
if exist "dist\%SNAME%.exe" (
  copy /Y "dist\%SNAME%.exe" "dist\Scriba.exe" >nul
  echo  Actualizado dist\Scriba.exe a la version %SVER%.
) else (
  echo  AVISO: no se genero dist\%SNAME%.exe; no se actualizo Scriba.exe.
)

echo.
echo ------------------------------------------------------------
echo  Listo. Ejecutables en:
echo     dist\%SNAME%.exe   (versionado)
echo     dist\Scriba.exe    (siempre la ultima version)
echo  (scriba_build.json se creara junto al .exe la primera vez.)
echo ------------------------------------------------------------
pause
