@echo off
REM ============================================================
REM  Compila ScribaPlayer.exe: el REPRODUCTOR GENERICO portable.
REM ============================================================
REM  Se compila UNA SOLA VEZ. Despues viaja junto a Scriba.exe y la
REM  exportacion "Exportar para Windows" solo lo copia con el juego al
REM  lado: el usuario final NO necesita instalar nada.
REM
REM  Requisitos (solo para compilar este reproductor, una vez):
REM      pip install pyinstaller pyyaml pillow
REM
REM  Resultado:  dist\ScribaPlayer.exe   (deja una copia junto a Scriba.exe)
REM ============================================================

python -m PyInstaller --noconfirm --onefile --windowed --name ScribaPlayer ^
  --hidden-import interpreter ^
  --hidden-import paws_lang ^
  --hidden-import fx_engine ^
  --hidden-import afx ^
  --hidden-import yaml ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageTk ^
  player.py

echo.
echo ------------------------------------------------------------
echo  Listo: dist\ScribaPlayer.exe
echo  Copialo a la MISMA carpeta donde este Scriba.exe.
echo  (Solo hay que hacer esto una vez.)
echo ------------------------------------------------------------
pause
