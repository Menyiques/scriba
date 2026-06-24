#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
empaqueta_nextap.py - Empaqueta un .tap para ZX Spectrum Next con:
  - el MOTOR (codigo) en RAM principal (org 24576 por defecto),
  - el TEXTO comprimido en bancos BAJOS (1,3,4,6) paginados con $7FFD,
  - las IMAGENES Layer 2 (.nxi de 16K) en bancos ALTOS (16,17,18,...) con $DFFD.

La clave (validada en hardware): el cargador 128 mantiene BANKM ($5B5C / 23388)
sincronizado con $7FFD, y para los bancos >7 escribe ademas los bits altos en
$DFFD. Eso es lo que hace que la paginacion funcione en el Next desde un .tap
(un .nex pelado no monta ese entorno y por eso fallaba).

Uso:
  python empaqueta_nextap.py codigo.bin texto.bin salida.tap [--org 24576]
         [--img 16:data/playa.nxi] [--img 17:data/acantilado.nxi] ...
"""
import sys
import struct
import argparse

# ── formato de bloques TAP ─────────────────────────────────────────────────
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

# tokens BASIC
CLEAR, LOAD, CODE_T = 0xFD, 0xEF, 0xAF
POKE, OUT, RND, USR = 0xF4, 0xDF, 0xF9, 0xC0
BANKM, P7FFD, PDFFD = 23388, 32765, 57341   # sysvar BANKM, puertos $7FFD / $DFFD
TEXT_BANKS = [1, 3, 4, 6]                    # bancos bajos para el texto comprimido
# tokens BASIC para el mensaje de carga
PRINT, AT, INK, PAPER, FLASH, BORDER, CLS = 0xF5, 0xAC, 0xD9, 0xDA, 0xDB, 0xE7, 0xFB


def _msg_carga(texto='CARGANDO...'):
    """BORDER/PAPER negro, INK cian, CLS y el texto de carga (traducible, metadato
    'loading') parpadeando y centrado. El texto va por la fuente de la ROM (mayus.
    ASCII; sin tildes)."""
    t = (texto or 'CARGANDO...').strip()[:30]
    col = max(0, (32 - len(t)) // 2)
    lit = b'"' + t.encode('ascii', 'replace').replace(b'"', b"'") + b'"'
    return (bytes([BORDER]) + num(0) + b':' +
            bytes([PAPER]) + num(0) + b':' + bytes([INK]) + num(5) + b':' +
            bytes([CLS]) + b':' +
            bytes([PRINT, AT]) + num(9) + b',' + num(col) + b';' +
            bytes([FLASH]) + num(1) + b';' + lit)


def _pantalla_carga(border=0):
    """BORDER <n>, PAPER 0 e INK 0 + CLS. El papel/tinta en negro mantienen los
    mensajes de carga invisibles; el BORDE es configurable (metadata 'border')."""
    return (bytes([BORDER]) + num(border & 7) + b':' +
            bytes([PAPER]) + num(0) + b':' + bytes([INK]) + num(0) + b':' +
            bytes([CLS]))


def _carga_baja(nl, bank, suf=b''):
    """Pagina un banco 0-7 en $C000 (BANKM + $7FFD) y carga 16K alli."""
    val = (bank & 7) | 16                    # bits bajos + bit ROM (48K)
    return linea(nl,
                 bytes([POKE]) + num(BANKM) + b',' + num(val) + b':' +
                 bytes([OUT]) + num(P7FFD) + b',' + num(val) + b':' +
                 bytes([LOAD]) + b'""' + bytes([CODE_T]) + num(49152) + suf)


def _carga_alta(nl, bank, suf=b''):
    """Pagina un banco ALTO (>=8) en $C000 ($DFFD bits altos + $7FFD) y carga."""
    hi = (bank >> 3) & 7
    lo = (bank & 7) | 16
    return linea(nl,
                 bytes([OUT]) + num(PDFFD) + b',' + num(hi) + b':' +
                 bytes([POKE]) + num(BANKM) + b',' + num(lo) + b':' +
                 bytes([OUT]) + num(P7FFD) + b',' + num(lo) + b':' +
                 bytes([LOAD]) + b'""' + bytes([CODE_T]) + num(49152) + suf)


def construye_tap(code, texto, imgs, org=24576, deferidos=None,
                  cargando='CARGANDO...', border=0):
    """code: bytes del motor. texto: blob comprimido. imgs: lista (banco, bytes).
    deferidos: bancos que NO carga el cargador BASIC; se anexan al final como
    bloques de datos SIN cabecera para que el MOTOR los lea con la rutina ROM
    LD-BYTES en una 2ª fase (asi el titulo + musica salen antes de cargarlo todo).
    cargando: texto del mensaje de carga (metadato 'loading', traducible).
    Devuelve los bytes del .tap."""
    dif = set(deferidos or [])
    trozos = [texto[i:i + 16384] for i in range(0, len(texto), 16384)]
    if len(trozos) > len(TEXT_BANKS):
        raise ValueError('el texto (%d bytes) supera %d bancos de 16K'
                         % (len(texto), len(TEXT_BANKS)))

    # ── cargador BASIC: pantalla TODA en negro, SIN mensaje ni % ──
    # No tocamos el canal S (el viejo POKE 23739 no oculta los "Bytes:" y ademas
    # en el Next deja el papel en 7). En su lugar dejamos papel 0 / tinta 0 (CLS)
    # y la pantalla inferior tambien negra (BORDCR=23624): asi los mensajes de
    # carga de la ROM salen en negro sobre negro = invisibles.
    c10 = (bytes([CLEAR]) + num(org - 1) + b':' +
           _pantalla_carga(border) + b':' +
           bytes([POKE]) + num(23624) + b',' + num(0) + b':' +
           bytes([LOAD]) + b'""' + bytes([CODE_T]))
    prog = linea(10, c10)
    nl = 20
    for j in range(len(trozos)):                 # texto -> bancos bajos
        prog += _carga_baja(nl, TEXT_BANKS[j])
        nl += 10
    for bank, _ in imgs:                          # imagenes (fase 1) -> bancos altos
        if bank in dif:
            continue
        prog += _carga_alta(nl, bank)
        nl += 10
    # restaurar paginacion (banco 0 + ROM) y ejecutar
    cf = (bytes([OUT]) + num(PDFFD) + b',' + num(0) + b':' +
          bytes([POKE]) + num(BANKM) + b',' + num(16) + b':' +
          bytes([OUT]) + num(P7FFD) + b',' + num(16) + b':' +
          bytes([RND, USR]) + num(org))
    prog += linea(nl, cf)

    # ── ensamblado del .tap (el orden de bloques = orden de los LOAD) ──
    tap = cab(0, 'cargador', len(prog), 10, len(prog)) + bloque(prog, 0xFF)
    tap += cab(3, 'codigo', len(code), org) + bloque(code, 0xFF)
    for j, t in enumerate(trozos):
        tap += cab(3, 'texto' + str(j + 1), len(t), 49152) + bloque(t, 0xFF)
    # fase 1: bancos con cabecera (los carga el BASIC: blank, titulo, paletas)
    for bank, data in imgs:
        if bank in dif:
            continue
        d = (data + b'\x00' * 16384)[:16384]     # cada imagen = 16K exactos
        tap += cab(3, 'img%d' % bank, 16384, 49152) + bloque(d, 0xFF)
    # fase 2: bancos DIFERIDOS, SIN cabecera y en orden ascendente de banco;
    # el motor (cargaImgs/cargaBanco) los lee con LD-BYTES tras pulsar tecla.
    for bank, data in sorted((b, d) for b, d in imgs if b in dif):
        d = (data + b'\x00' * 16384)[:16384]
        tap += bloque(d, 0xFF)
    return tap


def main():
    ap = argparse.ArgumentParser(description='Empaqueta un .tap para Next (texto '
                                 'en bancos bajos + imagenes Layer 2 en altos).')
    ap.add_argument('code', help='binario del motor (zxbc)')
    ap.add_argument('texto', help='blob de texto comprimido (_texto.bin)')
    ap.add_argument('tap', help='salida .tap')
    ap.add_argument('--org', type=int, default=24576)
    ap.add_argument('--img', action='append', default=[],
                    help='banco:fichero.nxi (banco ALTO >=16, repetible)')
    a = ap.parse_args()
    code = open(a.code, 'rb').read()
    texto = open(a.texto, 'rb').read()
    imgs = []
    for spec in a.img:
        bk, _, fn = spec.partition(':')
        imgs.append((int(bk), open(fn, 'rb').read()))
    tap = construye_tap(code, texto, imgs, org=a.org)
    open(a.tap, 'wb').write(tap)
    print('%s: %d bytes | codigo %d @ %d | texto %d banco(s) | %d imagen(es) %s'
          % (a.tap, len(tap), len(code), a.org,
             (len(texto) + 16383) // 16384, len(imgs),
             [b for b, _ in imgs]))


if __name__ == '__main__':
    main()
