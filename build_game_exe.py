# -*- coding: utf-8 -*-
"""
build_game_exe.py — Empaqueta un juego de Scriba en un .exe de Windows por juego.

Mete dentro del ejecutable el .yaml del juego, sus imágenes originales
(img/Original) y la configuración (columnas), junto con el reproductor de ventana
(player.py) y el intérprete. El jugador solo tiene que hacer doble clic.

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
        shutil.copy2(yaml_path, os.path.join(stage, 'game.yaml'))
        with open(os.path.join(stage, 'player_cfg.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({'game': 'game.yaml', 'title': titulo}, f,
                      ensure_ascii=False)
        # Imágenes originales (si las hay)
        orig = os.path.join(game_dir, 'img', 'Original')
        stage_img = os.path.join(stage, 'img', 'Original')
        n_img = 0
        if os.path.isdir(orig):
            os.makedirs(stage_img, exist_ok=True)
            for fn in os.listdir(orig):
                if fn.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    shutil.copy2(os.path.join(orig, fn),
                                 os.path.join(stage_img, fn))
                    n_img += 1

        sep = os.pathsep  # ';' en Windows, ':' en otros
        datos = [
            os.path.join(stage, 'game.yaml') + sep + '.',
            os.path.join(stage, 'player_cfg.json') + sep + '.',
        ]
        if n_img:
            datos.append(stage_img + sep + os.path.join('img', 'Original'))

        distdir = os.path.join(game_dir, 'dist', 'Windows')
        cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile',
               '--windowed', '--name', nombre,
               '--distpath', distdir,
               '--workpath', os.path.join(stage, 'build'),
               '--specpath', stage]
        for d in datos:
            cmd += ['--add-data', d]
        for hi in ('interpreter', 'paws_lang', 'yaml', 'PIL', 'PIL.Image',
                   'PIL.ImageTk'):
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
