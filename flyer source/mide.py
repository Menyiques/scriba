"""Mide, en el original y en una pagina generada, la primera palabra de cada
bloque de texto: su ancho (para calibrar el tamano de letra) y su borde de
arriba (para alinear en vertical). Todo en mm.

    python "flyer source/mide.py" flyer_es.png"""
import os, sys
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
PXMM = 2479 / 210.0
# nombre: (x0, y0, x1, y1) en mm, una banda con una linea de texto
BANDAS = {
    'cab PUBLICIDAD': (12, 13, 48, 18.3),
    'cab centro': (48, 13, 140, 18.3),
    'titular BASIC': (12, 21, 150, 37.5),
    'titular ASM': (12, 38, 150, 56.5),
    'entradilla Escribe': (12, 61, 160, 67.2),
    'pie ZX': (12, 117, 71, 121.6),
    'h2 ASM': (12, 124, 71, 132.5),
    'cuerpo Una': (139, 134, 198, 139.2),
    'cuerpo Tu': (12, 134, 71, 139.2),
    'vineta Musica': (15.5, 159.5, 71, 164.6),
    'codigo REM': (75, 154.5, 134, 159),
    'tabla ZX': (139, 155, 175, 160.5),
    'nov 3.0': (11, 192, 32.5, 206),
    'nov Novedades': (33, 194, 90, 201),
    'lista MSX2': (16.5, 208, 97, 213),
    'edpie El': (106, 241.7, 198, 245.6),
    'pie2 ZX': (75, 117, 134, 121.6),
    'pie3 Amstrad': (139, 117, 198, 121.6),
    'cuerpo Si': (75, 134, 134, 139.2),
    'pie Pruebalo': (12, 261, 120, 269.5, 0.45),
    'pie url': (12, 267.5, 120, 276.5),
    'pie Codigo': (12, 277, 120, 281.6),
    'pie programa': (122, 265, 170, 271),
}


def palabra(im, caja, umbral=110, hueco=0.75):
    """(x0, x1, y0, y1) de la primera palabra con tinta dentro de la caja."""
    x0, y0, x1, y1 = (int(v * PXMM) for v in caja)
    px = im.load()
    cols = []
    for x in range(x0, x1):
        cols.append(any(px[x, y] < umbral for y in range(y0, y1)))
    try:
        a = cols.index(True)
    except ValueError:
        return None
    b, vacio = a, 0
    for i in range(a, len(cols)):
        if cols[i]:
            b, vacio = i, 0
        else:
            vacio += 1
            if vacio > hueco * PXMM:
                break
    filas = [y for y in range(y0, y1) if any(px[x, y] < umbral for x in range(x0 + a, x0 + b + 1))]
    return ((x0 + a) / PXMM, (x0 + b + 1) / PXMM, filas[0] / PXMM, (filas[-1] + 1) / PXMM)


orig = Image.open(os.path.join(AQUI, 'img', 'original_es_2026-09.jpg')).convert('L')
nuevo = Image.open(os.path.join(AQUI, sys.argv[1])).convert('L').resize(orig.size)
print('%-20s %18s %18s   ancho  dx    dy(arriba)' % ('', 'original', 'nuevo'))
for n, caja in BANDAS.items():
    hueco = caja[4] if len(caja) > 4 else 0.75
    caja = caja[:4]
    o, v = palabra(orig, caja, hueco=hueco), palabra(nuevo, caja, hueco=hueco)
    if not o or not v:
        print('%-20s sin tinta (%s / %s)' % (n, o, v))
        continue
    print('%-20s x%6.2f w%6.2f   x%6.2f w%6.2f   %5.3f %+5.2f %+5.2f'
          % (n, o[0], o[1] - o[0], v[0], v[1] - v[0], (o[1] - o[0]) / (v[1] - v[0]),
             o[0] - v[0], o[2] - v[2]))
