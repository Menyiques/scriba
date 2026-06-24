#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
png2next.py - Convierte PNG o JPG al formato crudo de Layer 2 del ZX Spectrum
Next que usa el motor de Scriba (incrustado con INCBIN, sin SD ni LoadBMP).

Por cada imagen genera dos ficheros:
  <nombre>.nxi  -> pixeles, 1 byte/pixel (indice de paleta), en orden de lectura.
                  256x64  = 16384 bytes (tira del tercio superior de Layer 2).
                  256x192 = 49152 bytes (pantalla completa, para el menu).
  <nombre>.nxp  -> paleta: 256 entradas x 2 bytes en formato 9-bit del Next:
                  byte1 = RRRGGGBB ; byte2 = bit0 = 9.o bit (LSB azul).
                  (El motor sube byte1 a la paleta de Layer 2 con NextRegA $41.)

La imagen se REDIMENSIONA (se estrecha) al tamano destino sin recortar, y se
busca la MEJOR paleta de hasta 256 colores por median-cut, cuantizada a la
rejilla de 9 bits del Next (512 colores posibles) para que se vea fiel.

Uso:
  python png2next.py muelle.png                 -> muelle.nxi + muelle.nxp (256x64)
  python png2next.py menu.jpg --menu            -> 256x192 (pantalla de menu)
  python png2next.py img/Next                   -> convierte toda la carpeta
  from png2next import convert

Requiere: Pillow (pip install pillow).
"""

import os
import sys
import argparse

try:
    from PIL import Image
except ImportError:
    sys.stderr.write("ERROR: falta Pillow. Instala con:  pip install pillow\n")
    raise

ANCHO = 256
ALTO_TIRA = 64        # tira del tercio superior (localizaciones)
ALTO_MENU = 192       # pantalla completa (menu / presentacion)


def _to3(v):
    return (v * 7 + 127) // 255

def _from3(c3):
    return (c3 * 255 + 3) // 7

def _snap9(rgb):
    """Ajusta un color de 24 bits al color Next de 9 bits mas cercano."""
    r, g, b = rgb
    return (_from3(_to3(r)), _from3(_to3(g)), _from3(_to3(b)))

def _nxp_bytes(rgb):
    """Color RGB -> 2 bytes del formato de paleta del Next."""
    r3, g3, b3 = _to3(rgb[0]), _to3(rgb[1]), _to3(rgb[2])
    byte1 = (r3 << 5) | (g3 << 2) | (b3 >> 1)   # RRRGGGBB
    byte2 = b3 & 0x01                            # 9.o bit (LSB azul)
    return bytes((byte1, byte2))


def convert(src_path, nxi_path=None, nxp_path=None, menu=False,
            dither=False, verbose=False):
    """Convierte src_path (PNG/JPG) a <nxi> + <nxp>.
    menu=True -> 256x192; si no, 256x64. Devuelve (nxi_path, nxp_path, info)."""
    if nxi_path is None:
        nxi_path = os.path.splitext(src_path)[0] + '.nxi'
    if nxp_path is None:
        nxp_path = os.path.splitext(nxi_path)[0] + '.nxp'
    alto = ALTO_MENU if menu else ALTO_TIRA

    im = Image.open(src_path).convert('RGB')
    w0, h0 = im.size
    # estrechar/redimensionar al tamano destino (sin recortar)
    if (w0, h0) != (ANCHO, alto):
        im = im.resize((ANCHO, alto), Image.LANCZOS)

    # 1) snap de todos los pixeles a 9 bits para que el cuantizador agrupe
    #    sobre colores que el Next puede mostrar
    px = im.load()
    for y in range(alto):
        for x in range(ANCHO):
            px[x, y] = _snap9(px[x, y])

    # 2) mejor paleta de <=256 colores (median-cut)
    dmode = Image.FLOYDSTEINBERG if dither else Image.NONE
    q = im.quantize(colors=256, method=Image.MEDIANCUT, dither=dmode)

    # 3) re-ajustar la paleta resultante a 9 bits (median-cut puede promediar)
    pal = q.getpalette()
    n_pal = len(pal) // 3
    pal_rgb = []
    for i in range(256):
        if i < n_pal:
            r, g, b = pal[3 * i], pal[3 * i + 1], pal[3 * i + 2]
            pal_rgb.append(_snap9((r, g, b)))
        else:
            pal_rgb.append((0, 0, 0))

    # 4) escribir .nxi (indices) y .nxp (paleta 9-bit, 256 entradas)
    idx = q.tobytes()                       # row-major = orden de lectura
    esperado = ANCHO * alto
    if len(idx) != esperado:
        raise ValueError("tamano de pixeles inesperado: %d (esperaba %d)"
                         % (len(idx), esperado))
    with open(nxi_path, 'wb') as f:
        f.write(idx)
    nxp = bytearray()
    for rgb in pal_rgb:
        nxp += _nxp_bytes(rgb)
    with open(nxp_path, 'wb') as f:
        f.write(nxp)

    n_col = len(set(idx))
    info = ['%s -> %s (%dx%d, %d B) + %s (paleta %d colores)'
            % (os.path.basename(src_path), os.path.basename(nxi_path),
               ANCHO, alto, esperado, os.path.basename(nxp_path), n_col)]
    if (w0, h0) != (ANCHO, alto):
        info.append('  redimensionada %dx%d -> %dx%d' % (w0, h0, ANCHO, alto))
    if verbose:
        for line in info:
            print(line)
    return nxi_path, nxp_path, info


def convert_dir(carpeta, verbose=False):
    """Convierte todos los PNG/JPG de una carpeta. screen.*/menu.* van a 256x192."""
    exts = ('.png', '.jpg', '.jpeg')
    n = 0
    for nombre in sorted(os.listdir(carpeta)):
        if nombre.lower().endswith(exts):
            base = os.path.splitext(nombre)[0]
            es_menu = base.lower() in ('screen', 'menu')
            convert(os.path.join(carpeta, nombre), menu=es_menu, verbose=verbose)
            if not verbose:
                print('  %s%s' % (nombre, ' (menu 256x192)' if es_menu else ''))
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(
        description="PNG/JPG -> Layer 2 del Next (.nxi + .nxp), para INCBIN.")
    ap.add_argument("entrada", help="PNG/JPG o carpeta")
    ap.add_argument("salida", nargs='?', help="ruta .nxi de salida")
    ap.add_argument("--menu", action="store_true", help="256x192 (pantalla completa)")
    ap.add_argument("-d", "--dither", action="store_true", help="difuminado")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if os.path.isdir(a.entrada):
        n = convert_dir(a.entrada, verbose=a.verbose)
        print("\n%d imagen(es) convertida(s)" % n)
    else:
        convert(a.entrada, a.salida, menu=a.menu, verbose=True)


if __name__ == "__main__":
    main()
