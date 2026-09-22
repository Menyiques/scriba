# -*- coding: utf-8 -*-
"""
verify_pack.py - El juego pegado al .exe de Windows.

Comprueba lo unico que importa de scriba_pack: que el juego vuelve entero, que
no se lee nada por el camino, y que el .exe seguiria arrancando.

Lo ultimo no es paranoia: el arranque de PyInstaller encuentra su archivo
escaneando el fichero de atras hacia delante y quedandose con la PRIMERA
aparicion de su patron de 8 bytes. Si nuestro bloque lo contuviera por
casualidad, el .exe dejaria de arrancar -- y no en nuestra maquina, sino en la
del jugador. Por eso se comprueba en cada empaquetado y tambien aqui.

    python verify_pack.py [juego.yaml]
"""
import io
import os
import sys

import yaml

import scriba_pack as sp

POR_DEFECTO = os.path.join('Games', 'Operacion Tifon Negro',
                           'Operacion Tifon Negro.yaml')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    yaml_path = argv[0] if argv else POR_DEFECTO
    raiz = os.path.dirname(os.path.abspath(yaml_path))
    game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
    img_dir = os.path.join(raiz, 'img', 'Original')
    img_dir = img_dir if os.path.isdir(img_dir) else None

    res = []

    def chk(nombre, ok):
        res.append((nombre, bool(ok)))
        return ok

    bloque = sp.empaqueta(game, img_dir, titulo='Prueba')
    juego, imgs, titulo = sp.abre(bloque)

    chk('el juego vuelve identico, clave por clave', juego == game)
    chk('el titulo viaja aparte', titulo == 'Prueba')

    if img_dir:
        enteras = True
        for fn in sorted(os.listdir(img_dir)):
            if fn.lower().endswith(sp.EXTS):
                with open(os.path.join(img_dir, fn), 'rb') as f:
                    enteras = enteras and imgs.get(fn) == f.read()
        chk('las %d imagenes vuelven byte a byte' % len(imgs), enteras)
        chk('y se sacan por el id de la localizacion',
            sp.imagen(imgs, sorted(game['locations'])[0]) is not None
            or not imgs)

    # Nada legible: ni frases del juego ni el patron de PyInstaller
    frases = [l.strip() for l in io.open(yaml_path, encoding='utf-8').read().split('\n')
              if len(l.strip()) > 25]
    fuera = [f for f in frases
             if f.encode('utf-8') in bloque or f.encode('latin-1', 'ignore') in bloque]
    chk('ninguna de las %d frases largas del juego se lee en el bloque'
        % len(frases), not fuera)
    chk('el bloque no lleva el patron que busca PyInstaller',
        sp.MAGIC_PYI not in bloque)

    otro = sp.empaqueta(game, img_dir, titulo='Prueba')
    chk('dos empaquetados del mismo juego no se parecen (sal distinta)',
        otro != bloque and len(otro) == len(bloque))

    # Un .exe de mentira con la cabecera de PyInstaller al final, como en Windows
    import tempfile
    tmp = tempfile.mkdtemp(prefix='scriba_pack_')
    try:
        base = os.path.join(tmp, 'player.exe')
        with open(base, 'wb') as f:
            f.write(b'MZ' + os.urandom(4096) + sp.MAGIC_PYI + os.urandom(80))
        juego_exe = os.path.join(tmp, 'juego.exe')
        sp.pega(base, juego_exe, bloque)
        leido = sp.lee_de(juego_exe)
        chk('el .exe devuelve el juego al releerlo',
            leido is not None and leido[0] == game)
        datos = open(juego_exe, 'rb').read()
        chk('la cabecera de PyInstaller sigue siendo la ultima del fichero',
            datos.rfind(sp.MAGIC_PYI) == len(datos) - len(bloque) - 80 - 8)
        chk('un .exe sin bloque no devuelve nada', sp.lee_de(base) is None)
        try:
            sp.pega(juego_exe, os.path.join(tmp, 'doble.exe'), bloque)
            doble = False
        except ValueError:
            doble = True
        chk('no deja pegar un juego sobre otro ya pegado', doble)

        # Y el reproductor lo encuentra solo, como hara en la maquina del jugador
        import player
        frozen, ejecutable = getattr(sys, 'frozen', None), sys.executable
        try:
            sys.frozen = True
            sys.executable = juego_exe
            g, ims, tit = player.cargar_config([juego_exe])
            chk('el reproductor carga el juego del propio .exe',
                g == game and tit == 'Prueba' and len(ims) == len(imgs))
        finally:
            sys.executable = ejecutable
            if frozen is None:
                del sys.frozen
            else:
                sys.frozen = frozen
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    bien = sum(1 for _, ok in res if ok)
    for nombre, ok in res:
        print('  %s  %s' % ('OK  ' if ok else 'FALLA', nombre))
    print()
    print('%d/%d   (bloque: %s bytes)'
          % (bien, len(res), '{:,}'.format(len(bloque)).replace(',', '.')))
    return 0 if bien == len(res) else 1


if __name__ == '__main__':
    sys.exit(main())
