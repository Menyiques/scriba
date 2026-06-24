#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
png2cpc.py — Convierte una imagen (png/jpg) a una pantalla Amstrad CPC en
MODO 0 (160x200, 16 tintas de la paleta hardware de 27 colores).

Pipeline (clave para fotos oscuras como las nocturnas de DAS BOOT):
  1. Redimensiona a 160 x img_lines.
  2. AUTO-CONTRASTE: estira el rango tonal (si no, los tonos < 64 se aplastan
     a negro porque la paleta CPC solo tiene niveles 0/128/255 por canal).
  3. Elige 16 colores representativos (median cut) y los ancla a los 27 colores
     firmware del CPC -> 16 tintas.
  4. Re-cuantiza con DITHERING Floyd-Steinberg contra esas 16 tintas.
  5. Empaqueta a bytes Modo 0 (pixeles entrelazados) en el layout de memoria
     de pantalla del CPC (offset = (y%8)*0x800 + (y//8)*0x50 + xbyte), listo
     para cargar de un tiron en &C000.

Salida: (screen_bytes[16384], inks[16 numeros firmware 0-26]).
Para PANTALLA PARTIDA: la imagen ocupa las primeras `img_lines` lineas; el
resto se rellena con la tinta `paper` (la ventana de texto va debajo).

Verificacion: decode_preview() reconstruye un PNG desde los bytes CPC.
"""

from PIL import Image, ImageOps

# Paleta firmware del CPC: indice 0-26 -> RGB (niveles 0/128/255 por canal).
CPC_FW = [
    (0,0,0),(0,0,128),(0,0,255),(128,0,0),(128,0,128),(128,0,255),
    (255,0,0),(255,0,128),(255,0,255),(0,128,0),(0,128,128),(0,128,255),
    (128,128,0),(128,128,128),(128,128,255),(255,128,0),(255,128,128),
    (255,128,255),(0,255,0),(0,255,128),(0,255,255),(128,255,0),
    (128,255,128),(128,255,255),(255,255,0),(255,255,128),(255,255,255),
]

W = 160                    # ancho en pixeles Modo 0
H = 200                    # alto total de la pantalla
BYTES_PER_LINE = 80        # 2 pixeles por byte
SCREEN = 0x4000            # 16384


def _nearest_fw(rgb):
    r, g, b = rgb[:3]
    best, bi = 1 << 30, 0
    for i, (cr, cg, cb) in enumerate(CPC_FW):
        d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if d < best:
            best, bi = d, i
    return bi


def _mode0_byte(pa, pb):
    """Empaqueta dos pixeles (pen 0-15) en un byte Modo 0 (bits entrelazados)."""
    return (((pa & 1) << 7) | ((pb & 1) << 6) | ((pa & 4) << 3) | ((pb & 4) << 2)
            | ((pa & 2) << 2) | ((pb & 2) << 1) | ((pa & 8) >> 2) | ((pb & 8) >> 3))


def _unpack_mode0(byte):
    pa = ((byte >> 7) & 1) | (((byte >> 3) & 1) << 1) | (((byte >> 5) & 1) << 2) | (((byte >> 1) & 1) << 3)
    pb = ((byte >> 6) & 1) | (((byte >> 2) & 1) << 1) | (((byte >> 4) & 1) << 2) | (((byte >> 0) & 1) << 3)
    return pa, pb


def convert(path, img_lines=128, text_bg=0, text_fg=24, contrast=True):
    """Convierte `path` a (screen_bytes, inks). Para PANTALLA PARTIDA reserva
    pen 0 = fondo de texto y pen 1 = tinta de texto (colores fijos text_bg/
    text_fg); la imagen usa los pens 2-15 (14 colores). El area de texto
    (lineas >= img_lines) se rellena con pen 0, asi el texto siempre es legible."""
    im = Image.open(path).convert('RGB').resize((W, img_lines), Image.LANCZOS)
    if contrast:
        im = ImageOps.autocontrast(im, cutoff=2)

    # 14 colores representativos para la imagen -> anclados a CPC (pens 2-15)
    rep = im.quantize(colors=14, method=Image.MEDIANCUT)
    rp = rep.getpalette()[:14 * 3]
    img_inks = [_nearest_fw(tuple(rp[i * 3:i * 3 + 3])) for i in range(14)]
    while len(img_inks) < 14:
        img_inks.append(0)

    palimg = Image.new('P', (1, 1))
    flat = []
    for fw in img_inks:
        flat += list(CPC_FW[fw])
    flat += [0] * (768 - len(flat))
    palimg.putpalette(flat)
    q = im.quantize(palette=palimg, dither=Image.Dither.FLOYDSTEINBERG)
    idx = q.load()

    inks = [text_bg, text_fg] + img_inks      # 16 pens: 0=fondo,1=texto,2-15=img
    buf = bytearray([0] * SCREEN)
    for y in range(H):
        for xb in range(BYTES_PER_LINE):
            if y < img_lines:
                pa = idx[xb * 2, y] + 2       # la imagen empieza en pen 2
                pb = idx[xb * 2 + 1, y] + 2
            else:
                pa = pb = 0                   # area de texto -> pen 0
            off = (y % 8) * 0x800 + (y // 8) * 0x50 + xb
            buf[off] = _mode0_byte(pa, pb)
    return bytes(buf), inks


def decode_preview(screen, inks):
    """Reconstruye un PNG (PIL Image) desde los bytes CPC. Duplica en X para
    corregir el pixel ancho 2:1 del Modo 0."""
    im = Image.new('RGB', (W, H))
    px = im.load()
    for y in range(H):
        for xb in range(BYTES_PER_LINE):
            off = (y % 8) * 0x800 + (y // 8) * 0x50 + xb
            pa, pb = _unpack_mode0(screen[off])
            px[xb * 2, y] = CPC_FW[inks[pa]]
            px[xb * 2 + 1, y] = CPC_FW[inks[pb]]
    return im.resize((W * 2, H), Image.NEAREST)


# ─── MODO 2 (640x200, monocromo 1 bit) ──────────────────────────────────────
W2 = 640
B2 = 80                    # bytes por linea (8 px/byte)

# Matriz Bayer 8x8 (dither ordenado). Patron REGULAR -> comprime mucho mejor que
# el ruido del Floyd-Steinberg (clave para que el juego quepa en disco).
_BAYER8 = [[0,32,8,40,2,34,10,42],[48,16,56,24,50,18,58,26],
           [12,44,4,36,14,46,6,38],[60,28,52,20,62,30,54,22],
           [3,35,11,43,1,33,9,41],[51,19,59,27,49,17,57,25],
           [15,47,7,39,13,45,5,37],[63,31,55,23,61,29,53,21]]


def convert_m2(path, img_lines=144, contrast=True, dither='bayer'):
    """Imagen -> pantalla CPC Modo 2 (1 bit, B/N). dither:
      'bayer'     ordenado, patron regular, COMPRIME bien (por defecto)
      'floyd'     Floyd-Steinberg, mas detalle/suavidad pero comprime mal
      'threshold' umbral puro, maxima compresion, sin gradientes (alto contraste)
    La imagen ocupa las primeras img_lines lineas; el resto va a papel (pen 0)."""
    im = Image.open(path).convert('L').resize((W2, img_lines), Image.LANCZOS)
    if contrast:
        im = ImageOps.autocontrast(im, cutoff=2)
    if dither == 'floyd':
        px = im.convert('1').load()
        get = lambda x, y: px[x, y]
    elif dither == 'threshold':
        px = im.convert('1', dither=Image.Dither.NONE).load()
        get = lambda x, y: px[x, y]
    else:                                   # 'bayer' ordenado
        px = im.load()
        get = lambda x, y: 255 if px[x, y] > (_BAYER8[y % 8][x % 8] + 0.5) * 4 else 0
    buf = bytearray([0] * SCREEN)
    for y in range(H):
        if y >= img_lines:
            continue
        for xb in range(B2):
            b = 0
            for k in range(8):
                if get(xb * 8 + k, y):      # blanco -> bit 1 (PEN 1)
                    b |= (1 << (7 - k))
            buf[(y % 8) * 0x800 + (y // 8) * 0x50 + xb] = b
    return bytes(buf)


def decode_preview_m2(screen, ink=(255, 255, 255), paper=(0, 0, 0)):
    im = Image.new('RGB', (W2, H))
    px = im.load()
    for y in range(H):
        for xb in range(B2):
            b = screen[(y % 8) * 0x800 + (y // 8) * 0x50 + xb]
            for k in range(8):
                px[xb * 8 + k, y] = ink if (b >> (7 - k)) & 1 else paper
    return im


# ─── Compresion RLE (PackBits) ──────────────────────────────────────────────
def rle_pack(data):
    """PackBits: control 0..127 -> (n+1) literales; 129..255 -> (257-n) repes."""
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        run = 1
        while i + run < n and run < 128 and data[i + run] == data[i]:
            run += 1
        if run >= 2:
            out.append(257 - run)
            out.append(data[i])
            i += run
        else:
            j, lit = i, bytearray()
            while j < n and len(lit) < 128:
                r = 1
                while j + r < n and r < 2 and data[j + r] == data[j]:
                    r += 1
                if j + 1 < n and data[j + 1] == data[j]:
                    break
                lit.append(data[j]); j += 1
            out.append(len(lit) - 1)
            out += lit
            i = j
    return bytes(out)


def rle_unpack(data, outlen=SCREEN):
    out = bytearray()
    i = 0
    while i < len(data) and len(out) < outlen:
        c = data[i]; i += 1
        if c < 128:
            out += data[i:i + c + 1]; i += c + 1
        elif c > 128:
            out += bytes([data[i]]) * (257 - c); i += 1
    return bytes(out)


def convert_menu(path, contrast=True, sat=1.6):
    """Pantalla de TITULO Modo 0 (160x200, 16 colores). Pipeline orientado a
    EXPRIMIR color: realce de saturacion + dithering directo contra los 27
    colores hardware del CPC, eligiendo los 16 mas usados. (El median-cut previo
    colapsaba a grises en escenas oscuras.) Devuelve (screen_bytes, inks[16])."""
    from PIL import ImageEnhance
    from collections import Counter
    im = Image.open(path).convert('RGB').resize((W, H), Image.LANCZOS)
    if contrast:
        im = ImageOps.autocontrast(im, cutoff=2)
    if sat and sat != 1.0:
        im = ImageEnhance.Color(im).enhance(sat)
    # paleta P con los 27 colores CPC -> dithering directo
    pal27 = Image.new('P', (1, 1))
    flat = []
    for rgb in CPC_FW:
        flat += list(rgb)
    flat += [0] * (768 - len(flat))
    pal27.putpalette(flat)
    q27 = im.quantize(palette=pal27, dither=Image.Dither.FLOYDSTEINBERG)
    top = [c for c, _ in Counter(q27.getdata()).most_common(16)]
    pal16 = Image.new('P', (1, 1))
    f16 = []
    for ci in top:
        f16 += list(CPC_FW[ci])
    f16 += [0] * (768 - len(f16))
    pal16.putpalette(f16)
    q16 = im.quantize(palette=pal16, dither=Image.Dither.FLOYDSTEINBERG)
    idx = q16.load()
    inks = (top + [0] * 16)[:16]
    buf = bytearray(SCREEN)
    for y in range(H):
        for xb in range(BYTES_PER_LINE):
            buf[(y % 8) * 0x800 + (y // 8) * 0x50 + xb] = _mode0_byte(idx[xb * 2, y], idx[xb * 2 + 1, y])
    return bytes(buf), inks


if __name__ == '__main__':
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else 'img/Next/acantilado.png'
    lines = int(sys.argv[2]) if len(sys.argv) > 2 else 128
    screen, inks = convert(src, img_lines=lines)
    print(f'[png2cpc] {src} -> {len(screen)} bytes, img_lines={lines}')
    print(f'  inks (firmware 0-26): {inks}  (distintos: {sorted(set(inks))})')
    out = src.rsplit('/', 1)[-1].rsplit('.', 1)[0]
    with open(out + '.cpcs', 'wb') as f:
        f.write(screen)
    decode_preview(screen, inks).save(out + '_preview.png')
    print(f'  escrito {out}.cpcs y {out}_preview.png')
