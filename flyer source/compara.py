"""Compara una pagina generada con el flyer original: lado a lado y, encima, en
rojo/cian (rojo = solo en el original, cian = solo en el nuevo).

    python "flyer source/compara.py" flyer_es.png [zona x0 y0 x1 y1 en mm]"""
import os, sys
from PIL import Image, ImageChops, ImageOps

AQUI = os.path.dirname(os.path.abspath(__file__))
orig = Image.open(os.path.join(AQUI, 'img', 'original_es_2026-09.jpg')).convert('L')
nuevo = Image.open(os.path.join(AQUI, sys.argv[1])).convert('L').resize(orig.size)
if len(sys.argv) > 2:
    x0, y0, x1, y1 = (float(v) * orig.width / 210.0 for v in sys.argv[2:6])
    caja = tuple(int(v) for v in (x0, y0, x1, y1))
    orig, nuevo = orig.crop(caja), nuevo.crop(caja)
# lado a lado
w, h = orig.size
lado = Image.new('L', (w * 2 + 20, h), 255)
lado.paste(orig, (0, 0))
lado.paste(nuevo, (w + 20, 0))
esc = min(1.0, 1900.0 / lado.width, 1900.0 / lado.height)
lado.resize((int(lado.width * esc), int(lado.height * esc))).save(os.path.join(AQUI, '_lado.png'))
# encima: R = original, G y B = nuevo
o = ImageOps.invert(orig)
n = ImageOps.invert(nuevo)
encima = Image.merge('RGB', (ImageOps.invert(n), ImageOps.invert(o), ImageOps.invert(o)))
esc = min(1.0, 1900.0 / encima.width, 1900.0 / encima.height)
encima.resize((int(encima.width * esc), int(encima.height * esc))).save(os.path.join(AQUI, '_encima.png'))
print('ok')
