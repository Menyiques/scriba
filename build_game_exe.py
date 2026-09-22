# -*- coding: utf-8 -*-
"""
build_game_exe.py — Empaqueta un juego de Scriba en un .exe de Windows por juego.

Mete dentro del ejecutable el juego entero —texto e imágenes— en el mismo
bloque cifrado que usa «Exportar para Windows» del editor (scriba_pack), junto
con el reproductor de ventana (player.py) y el intérprete. El jugador solo
tiene que hacer doble clic.

Hasta la v2.54 esto metía el `.yaml` tal cual, y un .exe onefile de PyInstaller
se descomprime al arrancar en una carpeta temporal: el juego volvía a estar en
texto plano, con todas las soluciones. Ahora lo que viaja (y lo que aparece en
ese temporal) es el bloque cifrado.

Para un solo fichero sin compilar nada, el camino corto es el del editor:
copia ScribaPlayer.exe y le pega el bloque detrás.

Uso:
    python build_game_exe.py <juego.yaml> [--name NOMBRE]

Requisitos (una vez):  pip install pyinstaller pyyaml pillow
El .exe final queda en  dist/Windows/<NOMBRE>.exe
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile


def _sanitiza(nombre):
    nombre = re.sub(r'[^\w .\-]+', '', nombre, flags=re.UNICODE).strip()
    return nombre or 'Aventura'


def main():
    ap = argparse.ArgumentParser(description='Empaqueta un juego Scriba en .exe')
    ap.add_argument('yaml', help='Ruta al .yaml del juego')
    ap.add_argument('--name', default=None, help='Nombre del .exe (def.: título)')
    args = ap.parse_args()

    aqui = os.path.dirname(os.path.abspath(__file__))
    player = os.path.join(aqui, 'player.py')
    if not os.path.isfile(player):
        sys.exit('No encuentro player.py junto a build_game_exe.py')

    yaml_path = os.path.abspath(args.yaml)
    if not os.path.isfile(yaml_path):
        sys.exit('No existe el juego: ' + yaml_path)
    game_dir = os.path.dirname(yaml_path)

    # Título (para el nombre del .exe y el cfg)
    titulo = None
    try:
        import yaml as _y
        meta = (_y.safe_load(open(yaml_path, encoding='utf-8')) or {}).get(
            'metadata', {})
        titulo = meta.get('title')
    except Exception:
        pass
    titulo = titulo or os.path.splitext(os.path.basename(yaml_path))[0]
    nombre = _sanitiza(args.name or titulo)

    # Carpeta de staging con los recursos que irán dentro del .exe
    stage = tempfile.mkdtemp(prefix='scriba_exe_')
    try:
        sys.path.insert(0, aqui)
        import yaml as _yaml
        import scriba_pack
        juego = _yaml.safe_load(open(yaml_path, encoding='utf-8'))
        orig = os.path.join(game_dir, 'img', 'Original')
        bloque = scriba_pack.empaqueta(
            juego, orig if os.path.isdir(orig) else None, titulo=titulo)
        with open(os.path.join(stage, 'juego.pak'), 'wb') as f:
            f.write(bloque)
        n_img = len(scriba_pack.abre(bloque)[1])

        sep = os.pathsep  # ';' en Windows, ':' en otros
        datos = [os.path.join(stage, 'juego.pak') + sep + '.']

        distdir = os.path.join(game_dir, 'dist', 'Windows')
        cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile',
               '--windowed', '--name', nombre,
               '--distpath', distdir,
               '--workpath', os.path.join(stage, 'build'),
               '--specpath', stage]
        for d in datos:
            cmd += ['--add-data', d]
        for hi in ('interpreter', 'paws_lang', 'scriba_pack', 'yaml', 'PIL',
                   'PIL.Image', 'PIL.ImageTk'):
            cmd += ['--hidden-import', hi]
        cmd += ['--paths', aqui, player]

        print('Empaquetando "%s"  (%d imágenes)…' % (titulo, n_img))
        print('  ' + ' '.join(cmd))
        r = subprocess.run(cmd, cwd=aqui)
        if r.returncode != 0:
            sys.exit('PyInstaller falló (código %d).' % r.returncode)
        exe = os.path.join(distdir, nombre + '.exe')
        print('\nListo: ' + exe if os.path.isfile(exe)
              else '\nTerminado; revisa la carpeta dist/Windows/.')
    finally:
        # Conservamos dist/; limpiamos el staging temporal.
        shutil.rmtree(stage, ignore_errors=True)


if __name__ == '__main__':
    main()
