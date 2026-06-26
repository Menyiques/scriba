#!/usr/bin/env python3
# Empaqueta el TAP para ZX Spectrum 48K:
#   python empaqueta48.py juego.bin [salida.tap] [org] [pantalla.scr]
# Orden del TAP: cargador BASIC, [pantalla de carga 6912 @ 16384], codigo.
# La pantalla de carga se busca en: argumento 4, img/screen.scr, screen.scr.
# El .bin se compila antes con:  zxbc --org 24000 ... juego.bas  (sin --tap).
import sys, struct, os

def bloque(data, flag):
    b = bytes([flag]) + data
    chk = 0
    for x in b:
        chk ^= x
    return struct.pack('<H', len(b) + 1) + b + bytes([chk])

def cab(tipo, nombre, lon, p1, p2=32768):
    n = (nombre + ' ' * 10)[:10].encode('ascii')
    return bloque(bytes([tipo]) + n + struct.pack('<HHH', lon, p1, p2), 0)

def num(n):
    return str(n).encode('ascii') + bytes([0x0E, 0, 0, n & 255, (n >> 8) & 255, 0])

def linea(nl, cuerpo):
    return struct.pack('>H', nl) + struct.pack('<H', len(cuerpo) + 1) + cuerpo + b'\r'

def buscar_scr(extra):
    cand = ([extra] if extra else []) + ['img/screen.scr', 'screen.scr',
                                         '../img/Spectrum/screen.scr',
                                         '../img/screen.scr',
                                         '../../img/Spectrum/screen.scr',
                                         '../../img/screen.scr']
    for p in cand:
        if p and os.path.isfile(p) and os.path.getsize(p) == 6912:
            return open(p, 'rb').read(), p
    return None, None

def leer_border():
    """Color de borde (0-7) del cargador, escrito por el editor en border.txt."""
    for p in ('border.txt', '../border.txt', '../../border.txt'):
        try:
            if os.path.isfile(p):
                return int(open(p).read().strip()) & 7
        except (ValueError, OSError):
            pass
    return 0

def main():
    if len(sys.argv) < 2:
        print('uso: python empaqueta48.py juego.bin [salida.tap] [org] [pantalla.scr]')
        sys.exit(1)
    code = open(sys.argv[1], 'rb').read()
    out = sys.argv[2] if len(sys.argv) > 2 else 'juego.tap'
    org = int(sys.argv[3]) if len(sys.argv) > 3 else 24000
    scr, scrnom = buscar_scr(sys.argv[4] if len(sys.argv) > 4 else None)
    CLEAR, LOAD, CODE_T, RND, USR, POKE = 0xFD, 0xEF, 0xAF, 0xF9, 0xC0, 0xF4
    BORDER = 0xE7
    cuerpo = (bytes([BORDER]) + num(leer_border()) + b':' +
              bytes([CLEAR]) + num(org - 1) + b':' +
              bytes([POKE]) + num(23739) + b',' + num(111) + b':' +
              bytes([LOAD]) + b'""' + bytes([CODE_T]))
    if scr:
        cuerpo += b':' + bytes([LOAD]) + b'""' + bytes([CODE_T])
    cuerpo += (b':' + bytes([POKE]) + num(23739) + b',' + num(244) +
               b':' + bytes([RND, USR]) + num(org))
    prog = linea(10, cuerpo)
    tap = cab(0, 'cargador', len(prog), 10, len(prog)) + bloque(prog, 0xFF)
    if scr:
        tap += cab(3, 'pantalla', len(scr), 16384) + bloque(scr, 0xFF)
    tap += cab(3, 'codigo', len(code), org) + bloque(code, 0xFF)
    open(out, 'wb').write(tap)
    print(out + ': ' + str(len(tap)) + ' bytes | codigo ' + str(len(code)) +
          ' @ ' + str(org) +
          (' | pantalla de carga: ' + scrnom if scr else ' | sin pantalla de carga'))
    fin = org + len(code)
    print('Binario 48K: $%04X-$%04X (%d bytes). Limite practico ~39.7 KB.' %
          (org, fin - 1, len(code)))

main()
