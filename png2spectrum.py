# -*- coding: utf-8 -*-
"""
png2spectrum.py — Conversor de PNG/JPG a pantalla ZX Spectrum (ULA, tercio
superior 256x64). Devuelve (bmp, att): 2048 bytes de bitmap + 256 de atributos,
exactamente el formato que consume imagenes_128k (= _carga_scr de un .scr 2304).

Hace dithering ordenado (Bayer 8x8) eligiendo 2 colores por bloque de 8x8 (un
INK y un PAPER, con el bit BRIGHT comun), como impone el hardware del Spectrum.
Sirve para dos cosas:

  - fallback de las localizaciones sin .scr propio: convierte el master de
    img/Original, igual que el export de Amstrad, con autocontraste;
  - y para los .jpg/.bmp/.png que se dejen en img/Spectrum, que son arte YA
    preparado para la maquina: esos se convierten tal cual, sin tocar niveles,
    y tienen que venir en 4:1 (la tira de 256x64 del tercio superior).
"""

RATIO_TIRA = 4.0        # 256x64: la franja de imagen de una localizacion
TOL_RATIO = 0.02        # 2% de margen, que recortar a mano nunca sale exacto


def comprueba_ratio(path, ratio=RATIO_TIRA, tol=TOL_RATIO):
    """Falla si la imagen no tiene la proporcion pedida. Se usa con lo que se
    deja en img/Spectrum: ahi la imagen es definitiva, y escalarla a la fuerza
    la achataria sin avisar."""
    from PIL import Image
    with Image.open(path) as im:
        an, al = im.size
    if not al:
        raise ValueError('imagen vacia')
    r = an / float(al)
    if abs(r - ratio) > ratio * tol:
        raise ValueError('mide %dx%d (%.2f:1) y hace falta %.0f:1 '
                         '(p. ej. %dx%d)' % (an, al, r, ratio,
                                             int(ratio * 64), 64))

# Paleta ZX Spectrum: 8 tonos x 2 brillos. Indice 0-7 (negro,azul,rojo,magenta,
# verde,cian,amarillo,blanco). Normal = 0xD7, brillo = 0xFF.
_HUE = [(0, 0, 0), (0, 0, 1), (1, 0, 0), (1, 0, 1),
        (0, 1, 0), (0, 1, 1), (1, 1, 0), (1, 1, 1)]


def _rgb(idx, bright):
    v = 0xFF if bright else 0xD7
    r, g, b = _HUE[idx]
    return (r * v, g * v, b * v)


# Bayer 8x8 (valores 0..63)
_BAYER8 = [
    [0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21],
]


def _dist(c1, c2):
    return (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2


def _pick2(block):
    """Elige (ink, paper, bright) para un bloque de 64 pixeles RGB."""
    best = None
    for bright in (False, True):
        pal = [_rgb(i, bright) for i in range(8)]
        cnt = [0] * 8
        for c in block:
            di = min(range(8), key=lambda i: _dist(c, pal[i]))
            cnt[di] += 1
        top = sorted(range(8), key=lambda i: -cnt[i])[:2]
        a, b = top[0], top[1]
        if cnt[b] == 0:
            b = 7 if a != 7 else 0
        e = sum(min(_dist(c, pal[a]), _dist(c, pal[b])) for c in block)
        if best is None or e < best[0]:
            best = (e, a, b, bright)
    _, a, b, bright = best

    def lum(i):
        r, g, bl = _rgb(i, bright)
        return r * 0.3 + g * 0.59 + bl * 0.11
    ink, paper = (a, b) if lum(a) >= lum(b) else (b, a)
    return ink, paper, bright


def to_scr_topthird(path, contrast=True, exigir_ratio=False):
    """PNG/JPG/BMP -> (bmp 2048, att 256) del tercio superior del Spectrum.

    contrast=True autocontrasta antes de convertir, que es lo que conviene a un
    master fotografico. Para arte ya preparado (img/Spectrum) se pasa False.
    exigir_ratio=True rechaza lo que no venga en 4:1 en vez de achatarlo."""
    from PIL import Image
    if exigir_ratio:
        comprueba_ratio(path)
    im = Image.open(path).convert('RGB')
    if contrast:
        try:
            from PIL import ImageOps
            im = ImageOps.autocontrast(im, cutoff=2)
        except Exception:
            pass
    im = im.resize((256, 64))
    px = im.load()
    bmp = bytearray(2048)
    att = bytearray(256)
    for crow in range(8):
        for cx in range(32):
            block = [px[cx * 8 + dx, crow * 8 + dy]
                     for dy in range(8) for dx in range(8)]
            ink, paper, bright = _pick2(block)
            att[crow * 32 + cx] = ink | (paper << 3) | (0x40 if bright else 0)
            inkrgb = _rgb(ink, bright)
            paprgb = _rgb(paper, bright)
            for dy in range(8):
                y = crow * 8 + dy
                bbyte = 0
                for dx in range(8):
                    c = px[cx * 8 + dx, y]
                    di = _dist(c, inkrgb)
                    dp = _dist(c, paprgb)
                    tot = di + dp
                    frac = (dp / tot) if tot else 0.5     # 1 = pegado a INK
                    th = (_BAYER8[dy & 7][dx & 7] + 0.5) / 64.0
                    if frac > th:
                        bbyte |= 1 << (7 - dx)             # pixel INK
                off = (y & 7) * 256 + (y >> 3) * 32 + cx
                bmp[off] = bbyte
    return bytes(bmp), bytes(att)


def to_scr_full(path, contrast=True):
    """PNG/JPG -> pantalla COMPLETA del Spectrum (6912 bytes = 6144 bitmap + 768
    atributos). Para la pantalla de carga/presentacion (screen.scr)."""
    from PIL import Image
    im = Image.open(path).convert('RGB')
    if contrast:
        try:
            from PIL import ImageOps
            im = ImageOps.autocontrast(im, cutoff=2)
        except Exception:
            pass
    im = im.resize((256, 192))
    px = im.load()
    bmp = bytearray(6144)
    att = bytearray(768)
    for crow in range(24):
        for cx in range(32):
            block = [px[cx * 8 + dx, crow * 8 + dy]
                     for dy in range(8) for dx in range(8)]
            ink, paper, bright = _pick2(block)
            att[crow * 32 + cx] = ink | (paper << 3) | (0x40 if bright else 0)
            inkrgb = _rgb(ink, bright)
            paprgb = _rgb(paper, bright)
            for dy in range(8):
                y = crow * 8 + dy
                bbyte = 0
                for dx in range(8):
                    c = px[cx * 8 + dx, y]
                    di = _dist(c, inkrgb)
                    dp = _dist(c, paprgb)
                    tot = di + dp
                    frac = (dp / tot) if tot else 0.5
                    th = (_BAYER8[dy & 7][dx & 7] + 0.5) / 64.0
                    if frac > th:
                        bbyte |= 1 << (7 - dx)
                # layout ZX pantalla completa: tercio | linea | fila-char | col
                off = ((y & 7) << 8) | ((y & 0x38) << 2) | ((y & 0xC0) << 5) | cx
                bmp[off] = bbyte
    return bytes(bmp) + bytes(att)
