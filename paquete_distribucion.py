# -*- coding: utf-8 -*-
"""Monta el paquete de distribucion de Scriba, 'Scriba vX.Y.zip', en la
carpeta del proyecto. Lo llama build_exe.bat al terminar de compilar.

    Scriba vX.Y/
        Scriba.exe                  (dist/Scriba.exe)
        Scriba manual vX.Y.pdf      (Scriba_Manual.pdf)
        NOVEDADES.md                (NOVEDADES_distribucion.md, la del usuario)
        Games/el_faro/el_faro.yaml
        Games/operacion_tifon_negro_demo/   (el .yaml, img/ y music/)

La version (X.Y) sale de scriba_info.SCRIBA_VERSION. De los ejemplos van solo
el juego, sus imagenes y su musica: ni temp/ ni dist/, que son intermedios y
compilados del autor. Al terminar se relee el zip y se compara fichero a
fichero con el original.

    python paquete_distribucion.py
"""
import hashlib
import os
import sys
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import scriba_info  # noqa: E402

VERSION = scriba_info.SCRIBA_VERSION
RAIZ = 'Scriba v%s' % VERSION
SALIDA = os.path.join(AQUI, RAIZ + '.zip')
DEMO = os.path.join(AQUI, 'Games', 'operacion_tifon_negro_demo')

# (fichero del proyecto, ruta dentro del paquete)
FIJOS = [
    (os.path.join(AQUI, 'dist', 'Scriba.exe'), 'Scriba.exe'),
    (os.path.join(AQUI, 'Scriba_Manual.pdf'), 'Scriba manual v%s.pdf' % VERSION),
    (os.path.join(AQUI, 'NOVEDADES_distribucion.md'), 'NOVEDADES.md'),
    (os.path.join(AQUI, 'el_faro.yaml'), 'Games/el_faro/el_faro.yaml'),
    (os.path.join(DEMO, 'operacion_tifon_negro_demo.yaml'),
     'Games/operacion_tifon_negro_demo/operacion_tifon_negro_demo.yaml'),
]
# carpetas de la demo que van enteras
CARPETAS_DEMO = ('img', 'music')


def ficheros():
    out = list(FIJOS)
    for sub in CARPETAS_DEMO:
        for d, _dirs, fs in os.walk(os.path.join(DEMO, sub)):
            for f in sorted(fs):
                p = os.path.join(d, f)
                out.append((p, 'Games/operacion_tifon_negro_demo/' +
                            os.path.relpath(p, DEMO).replace('\\', '/')))
    return out


def main():
    fs = ficheros()
    faltan = [p for p, _a in fs if not os.path.isfile(p)]
    if faltan:
        raise SystemExit('paquete_distribucion: faltan ficheros:\n  ' + '\n  '.join(faltan))
    carpetas = sorted({RAIZ + '/' + '/'.join(a.split('/')[:i]) + '/'
                       for _p, a in fs for i in range(1, a.count('/') + 1)} | {RAIZ + '/'})
    tmp = SALIDA + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for c in carpetas:
            z.writestr(zipfile.ZipInfo(c), b'')
        for p, a in fs:
            z.write(p, RAIZ + '/' + a)
    os.replace(tmp, SALIDA)
    # releer y comparar
    with zipfile.ZipFile(SALIDA) as z:
        if z.testzip() is not None:
            raise SystemExit('paquete_distribucion: el zip ha salido corrupto')
        for p, a in fs:
            with open(p, 'rb') as f:
                if hashlib.sha256(z.read(RAIZ + '/' + a)).digest() != hashlib.sha256(f.read()).digest():
                    raise SystemExit('paquete_distribucion: %s no coincide en el zip' % a)
    print(' Paquete: %s (%d ficheros, %.1f MB)' % (os.path.basename(SALIDA), len(fs),
                                                  os.path.getsize(SALIDA) / 1e6))


if __name__ == '__main__':
    main()
