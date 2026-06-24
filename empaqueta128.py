#!/usr/bin/env python3
# Empaqueta el TAP final para ZX Spectrum 128K (textos en bancos):
#   python empaqueta128.py juego.bin juego_texto.bin [salida.tap] [org] [pantalla.scr]
# Orden del TAP: cargador BASIC, [pantalla de carga 6912 @ 16384], codigo, bancos.
# La pantalla de carga se busca en: argumento 5, img/screen.scr, screen.scr.
# IMPORTANTE: org por defecto 24576. El cargador hace CLEAR org-1 y
# necesita ~600 bytes de holgura sobre el programa BASIC (23755+212):
# con org 24000 el Spectrum da 'M RAMTOP no good'.
# El cargador pagina los bancos 1/3/4/6 en $C000 y carga alli el texto.
import sys, struct, os

def buscar_scr(extra):
    # rutas relativas al cwd (carpeta del .bas). Con la estructura nueva el .bas
    # esta en <juego>/temp/<target>, asi que se prueban tambien ../img y ../../img.
    cand = ([extra] if extra else []) + ['img/Spectrum/screen.scr',
                                         'img/128/screen.scr',
                                         'img/screen.scr', 'screen.scr',
                                         '../img/Spectrum/screen.scr',
                                         '../img/128/screen.scr',
                                         '../img/screen.scr',
                                         '../../img/Spectrum/screen.scr',
                                         '../../img/128/screen.scr',
                                         '../../img/screen.scr']
    for p in cand:
        if p and os.path.isfile(p) and os.path.getsize(p) == 6912:
            return open(p, 'rb').read(), p
    return None, None

def leer_border():
    """Color de borde (0-7) del cargador, escrito por el editor en border.txt
    (metadata 'border'). El .bas compila en temp/<target>, asi que se prueba el
    cwd y los padres. Por defecto 0 (negro)."""
    for p in ('border.txt', '../border.txt', '../../border.txt'):
        try:
            if os.path.isfile(p):
                return int(open(p).read().strip()) & 7
        except (ValueError, OSError):
            pass
    return 0

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

def main():
    if len(sys.argv) < 3:
        print('uso: python empaqueta128.py juego.bin juego_texto.bin [salida.tap] [org]')
        sys.exit(1)
    code = open(sys.argv[1], 'rb').read()
    texto = open(sys.argv[2], 'rb').read()
    out = sys.argv[3] if len(sys.argv) > 3 else 'juego128.tap'
    org = int(sys.argv[4]) if len(sys.argv) > 4 else 24576
    scr, scrnom = buscar_scr(sys.argv[5] if len(sys.argv) > 5 else None)
    BANCOS = [17, 19, 20, 22, 23]   # 16 + banco RAM 1,3,4,6,7
    trozos = [texto[i:i + 16384] for i in range(0, len(texto), 16384)]
    if len(trozos) > 5:
        print('ERROR: texto.bin supera 80K (5 bancos)')
        sys.exit(1)
    CLEAR, LOAD, CODE_T = 0xFD, 0xEF, 0xAF
    POKE, OUT, RND, USR = 0xF4, 0xDF, 0xF9, 0xC0
    BORDER = 0xE7
    cuerpo10 = (bytes([BORDER]) + num(leer_border()) + b':' +
                bytes([CLEAR]) + num(org - 1) + b':' +
                bytes([POKE]) + num(23739) + b',' + num(111) + b':' +
                bytes([LOAD]) + b'""' + bytes([CODE_T]))
    if scr:
        cuerpo10 += b':' + bytes([LOAD]) + b'""' + bytes([CODE_T])
    prog = linea(10, cuerpo10)
    nl = 20
    for j in range(len(trozos)):
        prog += linea(nl, bytes([POKE]) + num(23388) + b',' + num(BANCOS[j]) + b':' +
                      bytes([OUT]) + num(32765) + b',' + num(BANCOS[j]) + b':' +
                      bytes([LOAD]) + b'""' + bytes([CODE_T]) + num(49152))
        nl += 10
    prog += linea(nl, bytes([POKE]) + num(23388) + b',' + num(16) + b':' +
                  bytes([OUT]) + num(32765) + b',' + num(16) + b':' +
                  bytes([POKE]) + num(23739) + b',' + num(244) + b':' +
                  bytes([RND, USR]) + num(org))
    tap = cab(0, 'cargador', len(prog), 10, len(prog)) + bloque(prog, 0xFF)
    if scr:
        tap += cab(3, 'pantalla', len(scr), 16384) + bloque(scr, 0xFF)
    tap += cab(3, 'codigo', len(code), org) + bloque(code, 0xFF)
    for j, t in enumerate(trozos):
        tap += cab(3, 'texto' + str(j + 1), len(t), 49152) + bloque(t, 0xFF)
    open(out, 'wb').write(tap)
    print(out + ': ' + str(len(tap)) + ' bytes | codigo ' + str(len(code)) +
          ' @ ' + str(org) + ' | ' + str(len(trozos)) + ' banco(s) de texto' +
          (' | pantalla de carga: ' + scrnom if scr else ' | sin pantalla de carga'))
    heap = 4096
    fin_code = org + len(code)
    tope = fin_code + heap
    libre_ram = 65536 - tope
    print()
    print('=== MEMORIA LIBRE ===')
    print('RAM principal: motor %d bytes ($%04X-$%04X) + heap %d -> libre %d bytes' %
          (len(code), org, fin_code - 1, heap, max(0, libre_ram)))
    if libre_ram < 0:
        print('  *** NO CABE: sobran %d bytes (motor+heap > 65536) ***' % -libre_ram)
    print('Bancos 128K (5 x 16384 = 81920):')
    for j in range(5):
        usado = len(trozos[j]) if j < len(trozos) else 0
        print('  banco %d: %5d usados | %5d libres' % (j, usado, 16384 - usado))
    print('  total bancos: %d usados | %d libres (texto+imagenes futuros)' %
          (len(texto), len(BANCOS) * 16384 - len(texto)))

main()
