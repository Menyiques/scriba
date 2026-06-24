#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
png2bmp.py - Convierte PNG al BMP de 8 bits que espera LoadBMP de NextBuild,
para la tira del tercio superior de Layer 2 (256x64, paleta de 256 colores).

SIN dependencias externas: decodifica el PNG con zlib (stdlib), por lo que
funciona dentro del .exe de Scriba (PyInstaller) sin Pillow.

Salida: <nombre>.bmp  -> BMP indexado de 8 bits (256 colores), 256x64.
La paleta se cuantiza a la rejilla de 9 bits del Next. Si la imagen tiene
<=256 colores (tras el ajuste a 9 bits) se usan exactos; si tiene mas, se
cuantiza a 3-3-2 (256 colores fijos) como respaldo.

Dimensiones: 256x64 directo; 256x192 -> recorta el tercio superior; otros
tamanos -> reescala (vecino mas cercano) con aviso.

Uso:
  python png2bmp.py muelle.png                 -> muelle.bmp
  python png2bmp.py img/Next                    -> convierte todos los PNG
  from png2bmp import convert
"""

import os
import sys
import struct
import zlib
import argparse

ANCHO, ALTO = 256, 64        # tira util (tercio superior de Layer 2)
ALTO_BMP = 192               # LoadBMP exige un BMP de pantalla completa 256x192


# ─── Decodificador PNG minimo (zlib stdlib) ─────────────────────────────────

def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(raw, height, bpp, stride):
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        ft = raw[pos]; pos += 1
        line = bytearray(raw[pos:pos + stride]); pos += stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                c = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(a, prev[i], c)) & 255
        elif ft != 0:
            raise ValueError('filtro PNG desconocido: %d' % ft)
        out += line
        prev = line
    return out


def _decode_png(path):
    """Devuelve (ancho, alto, pixeles) con pixeles = bytearray RGB (3/pixel),
    en orden de lectura. Soporta no entrelazado, profundidad 1/2/4/8/16 y
    tipos gris(0)/RGB(2)/paleta(3)/gris+alfa(4)/RGBA(6)."""
    data = open(path, 'rb').read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('no es un PNG valido')
    pos = 8
    w = h = depth = ctype = interlace = None
    plte = b''
    idat = bytearray()
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b'IHDR':
            w, h, depth, ctype, _comp, _filt, interlace = struct.unpack('>IIBBBBB', chunk)
        elif typ == b'PLTE':
            plte = chunk
        elif typ == b'IDAT':
            idat += chunk
        elif typ == b'IEND':
            break
    if interlace:
        raise ValueError('PNG entrelazado (Adam7) no soportado; reexporta sin entrelazado')
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, (depth * ch + 7) // 8)
    stride = (w * ch * depth + 7) // 8
    raw = _unfilter(zlib.decompress(bytes(idat)), h, bpp, stride)

    px = bytearray(w * h * 3)
    o = 0

    def samples_row(y):
        """Genera las muestras (por canal) de la fila y, expandiendo bits."""
        base = y * stride
        if depth == 8:
            for i in range(w * ch):
                yield raw[base + i]
        elif depth == 16:
            for i in range(w * ch):
                yield raw[base + i * 2]          # byte alto
        else:  # 1,2,4 bits (gris o paleta)
            mask = (1 << depth) - 1
            per = 8 // depth
            scale = 255 // mask if ctype != 3 else 1
            n = w * ch
            cnt = 0
            for byte_i in range(stride):
                b = raw[base + byte_i]
                for k in range(per):
                    if cnt >= n:
                        break
                    shift = 8 - depth * (k + 1)
                    v = (b >> shift) & mask
                    yield v * scale
                    cnt += 1

    for y in range(h):
        it = samples_row(y)
        for _x in range(w):
            if ctype == 2:          # RGB
                r = next(it); g = next(it); b = next(it)
            elif ctype == 6:        # RGBA
                r = next(it); g = next(it); b = next(it); next(it)
            elif ctype == 0:        # gris
                r = next(it); g = b = r
            elif ctype == 4:        # gris + alfa
                r = next(it); next(it); g = b = r
            elif ctype == 3:        # paleta
                idx = next(it)
                r = plte[idx * 3]; g = plte[idx * 3 + 1]; b = plte[idx * 3 + 2]
            px[o] = r; px[o + 1] = g; px[o + 2] = b
            o += 3
    return w, h, px


# ─── Ajuste de tamaño (puro) ────────────────────────────────────────────────

def _crop_o_reescala(w, h, px):
    info = None
    if (w, h) == (ANCHO, ALTO):
        return px, None
    if w == ANCHO and h >= ALTO:
        out = px[:ANCHO * ALTO * 3]            # tercio superior
        return out, 'recortado %dx%d -> %dx%d (tercio superior)' % (w, h, ANCHO, ALTO)
    # vecino mas cercano
    out = bytearray(ANCHO * ALTO * 3)
    for ny in range(ALTO):
        sy = ny * h // ALTO
        for nx in range(ANCHO):
            sx = nx * w // ANCHO
            s = (sy * w + sx) * 3
            d = (ny * ANCHO + nx) * 3
            out[d] = px[s]; out[d + 1] = px[s + 1]; out[d + 2] = px[s + 2]
    return out, 'AVISO: reescalado %dx%d -> %dx%d' % (w, h, ANCHO, ALTO)


# ─── Cuantización a 9 bits + paleta ─────────────────────────────────────────

def _to3(v):
    return (v * 7 + 127) // 255

def _from3(c3):
    return (c3 * 255 + 3) // 7


def _indexa(px):
    """px = RGB (cualquier nº de pixeles). Devuelve (indices, paleta_rgb,
    modo): exacto si <=256 colores; si no, 3-3-2. Paleta SIEMPRE de 256
    entradas (LoadBMP exige 1024 bytes de paleta)."""
    n = len(px) // 3
    # snap a 9 bits y cuenta colores
    snapped = bytearray(n * 3)
    uniq = {}
    for i in range(n):
        r = _from3(_to3(px[i * 3])); g = _from3(_to3(px[i * 3 + 1])); b = _from3(_to3(px[i * 3 + 2]))
        snapped[i * 3] = r; snapped[i * 3 + 1] = g; snapped[i * 3 + 2] = b
        c = (r, g, b)
        if c not in uniq:
            uniq[c] = len(uniq)
    if len(uniq) <= 256:
        pal = [(0, 0, 0)] * 256
        for c, k in uniq.items():
            pal[k] = c
        idx = bytearray(n)
        for i in range(n):
            idx[i] = uniq[(snapped[i * 3], snapped[i * 3 + 1], snapped[i * 3 + 2])]
        return idx, pal, 'exacta %d colores' % len(uniq)
    # respaldo 3-3-2 (paleta fija de 256)
    pal = []
    for k in range(256):
        r3 = (k >> 5) & 7; g3 = (k >> 2) & 7; b2 = k & 3
        pal.append((_from3(r3), _from3(g3), (b2 * 255 + 1) // 3))
    idx = bytearray(n)
    for i in range(n):
        r3 = _to3(px[i * 3]); g3 = _to3(px[i * 3 + 1]); b2 = _to3(px[i * 3 + 2]) >> 1
        idx[i] = (r3 << 5) | (g3 << 2) | b2
    return idx, pal, '3-3-2 (>256 colores)'


# ─── Escritura de BMP de 8 bits ─────────────────────────────────────────────

def _escribe_bmp(path, idx, pal, alto=ALTO_BMP):
    # filas de abajo a arriba; ancho 256 ya es multiplo de 4 (sin padding)
    pix = bytearray()
    for y in range(alto - 1, -1, -1):
        pix += idx[y * ANCHO:(y + 1) * ANCHO]
    paleta = bytearray()
    for (r, g, b) in pal:
        paleta += bytes((b, g, r, 0))          # BGRA (256 entradas = 1024 bytes)
    off = 14 + 40 + len(paleta)
    size = off + len(pix)
    fh = b'BM' + struct.pack('<IHHI', size, 0, 0, off)
    ih = struct.pack('<IiiHHIIiiII', 40, ANCHO, alto, 1, 8, 0, len(pix), 2835, 2835, 256, 0)
    with open(path, 'wb') as f:
        f.write(fh); f.write(ih); f.write(paleta); f.write(pix)


# ─── API ────────────────────────────────────────────────────────────────────

def convert(png_path, bmp_path=None, dither=False, verbose=False):
    if bmp_path is None:
        bmp_path = os.path.splitext(png_path)[0] + '.bmp'
    w, h, px = _decode_png(png_path)
    strip, aviso = _crop_o_reescala(w, h, px)     # 256x64 (tercio superior)
    # LoadBMP carga la pantalla Layer 2 completa, asi que se compone un lienzo
    # 256x192: la tira en las 64 lineas de arriba, negro debajo (lo de abajo
    # queda fuera del clip, no se ve).
    full = bytearray(ANCHO * ALTO_BMP * 3)        # todo 0 = negro
    full[0:ANCHO * ALTO * 3] = strip              # filas 0-63 (arriba)
    idx, pal, modo = _indexa(full)
    _escribe_bmp(bmp_path, idx, pal, ALTO_BMP)
    info = ['%s -> %s (BMP 8-bit, %dx%d, paleta %s)'
            % (os.path.basename(png_path), os.path.basename(bmp_path),
               ANCHO, ALTO_BMP, modo)]
    if aviso:
        info.append(aviso)
    if verbose:
        for line in info:
            print(line)
    return bmp_path, info


def convert_dir(carpeta, verbose=False):
    n = 0
    for nombre in sorted(os.listdir(carpeta)):
        if nombre.lower().endswith('.png'):
            _, info = convert(os.path.join(carpeta, nombre), verbose=verbose)
            if not verbose:
                print(info[0])
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description="PNG -> BMP 8-bit para LoadBMP (NextBuild), sin PIL.")
    ap.add_argument("entrada", help="PNG o carpeta con PNGs")
    ap.add_argument("salida", nargs='?', help="ruta .bmp de salida")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if os.path.isdir(a.entrada):
        n = convert_dir(a.entrada, verbose=a.verbose)
        print("\n%d imagen(es) convertida(s)" % n)
    else:
        convert(a.entrada, a.salida, verbose=True)


if __name__ == "__main__":
    main()
