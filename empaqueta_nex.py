#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
empaqueta_nex.py - Empaquetador propio de ficheros .NEX (formato v1.2) para
Scriba, para no depender de NextBuild/NextLib. Junta el binario del motor
(compilado con zxbc pelado) + los bancos de imagen (.nxi) en un .nex
autocontenido que NextZXOS arranca solo.

Formato NEX v1.2 (wiki SpecNext):
  - 512 bytes de cabecera: "Next"+"V1.2", RAM, nº bancos, flags de pantalla,
    borde, SP, PC, array de 112 bancos presentes, version de core, entry bank...
  - (opcionales: paleta, pantallas de carga, copper) -> aqui no se usan.
  - bancos de 16K en ESTE orden fijo: 5,2,0,1,3,4,6,7,8,...,111 (solo presentes).

API:
  build_nex(out_path, banks, pc, sp, entry_bank=0, ram=1, border=0,
            core=(3,0,0))
    banks: dict {numero_banco_16k: bytes}  (cada valor se rellena/recorta a 16384)
"""

import os
import struct

ORDER = [5, 2, 0, 1, 3, 4] + list(range(6, 112))   # orden de bancos en el .nex


def _bank16(data):
    b = bytearray(data[:16384])
    if len(b) < 16384:
        b += b'\x00' * (16384 - len(b))
    return bytes(b)


def build_nex(out_path, banks, pc, sp, entry_bank=0, ram=1, border=0,
              core=(3, 0, 0)):
    """Construye un .nex. banks = {bank16k: bytes}. pc/sp 16-bit.
    ram: 0 = 768k, 1 = 1792k. core = (major, minor, subminor)."""
    present = sorted(banks.keys())
    if any(b < 0 or b > 111 for b in present):
        raise ValueError('numero de banco fuera de rango 0..111')

    h = bytearray(512)
    h[0:4] = b'Next'
    h[4:8] = b'V1.2'
    h[8] = ram & 0xFF                       # RAM requerida
    h[9] = len(present) & 0xFF              # nº de bancos de 16K a cargar
    h[10] = 128                             # flags pantalla: 128 = sin paleta, sin loading screen
    h[11] = border & 7                      # color de borde
    struct.pack_into('<H', h, 12, sp & 0xFFFF)    # SP
    struct.pack_into('<H', h, 14, pc & 0xFFFF)    # PC (0 = no ejecutar)
    struct.pack_into('<H', h, 16, 0)              # nº ficheros extra
    for b in present:                       # array de bancos presentes (orden 0..111)
        h[18 + b] = 1
    h[130] = 0                              # barra de carga Layer2 off
    h[131] = 0                              # color barra
    h[132] = 0                              # delay por banco
    h[133] = 0                              # delay inicial
    h[134] = 0                              # 0 = resetear estado de la maquina
    h[135] = core[0] & 0x0F                 # core major
    h[136] = core[1] & 0x0F                 # core minor
    h[137] = core[2] & 0xFF                 # core subminor
    h[138] = 0                              # Timex/HiRes color (no usado)
    h[139] = entry_bank & 0xFF              # banco a mapear en $C000 (slot 3)
    struct.pack_into('<H', h, 140, 0)       # file handle: 0 = cerrar el .nex

    with open(out_path, 'wb') as f:
        f.write(h)
        for b in ORDER:                     # bancos en el orden fijo del formato
            if b in banks:
                f.write(_bank16(banks[b]))
    return out_path


def bin_a_bancos(bin_path, org):
    """Reparte un binario crudo (cargado a 'org') en bancos de 16K segun la
    direccion. 16K bank n cubre absoluto n*0x4000 en el espacio de 64K mapeado.
    Devuelve {bank16k: bytes}. Asume el mapeo por defecto:
      $0000-$3FFF=ROM, $4000-$7FFF=bank5, $8000-$BFFF=bank2, $C000-$FFFF=bank0.
    Solo se soportan datos en $4000-$FFFF (RAM)."""
    data = open(bin_path, 'rb').read()
    addr_map = {0x4000: 5, 0x8000: 2, 0xC000: 0}   # inicio de slot -> banco 16K
    flat = 0x10000 - org                            # espacio plano disponible
    if len(data) > flat:
        raise ValueError(
            'JUEGO DEMASIADO GRANDE para Next plano: el motor + texto comprimido '
            'ocupa %d bytes (%.1f KB) desde org 0x%04X, y el limite plano es %d '
            'bytes (%.1f KB). El Z80 no puede direccionar mas de 64K y el texto '
            'en bancos no es viable en un .nex (NextZXOS no cede la paginacion). '
            'Para un juego de este tamano usa la exportacion 128K (.tap), que SI '
            'banca el texto. Reduce texto/imagenes o baja el org para games mas '
            'pequenos.' % (len(data), len(data) / 1024, org, flat, flat / 1024))
    banks = {}
    for i, byte in enumerate(data):
        a = org + i
        if a > 0xFFFF:
            raise ValueError('el binario excede 0xFFFF (no cabe en el mapa de 64K)')
        slot = a & 0xC000                          # inicio del slot de 16K
        bk = addr_map.get(slot)
        if bk is None:
            raise ValueError('byte en direccion ROM 0x%04X (org demasiado bajo)' % a)
        banks.setdefault(bk, bytearray(16384))
        banks[bk][a - slot] = byte
    return {k: bytes(v) for k, v in banks.items()}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Empaqueta un .nex (v1.2) propio.")
    ap.add_argument('bin', help='binario del motor (zxbc -f bin)')
    ap.add_argument('nex', help='salida .nex')
    ap.add_argument('--org', default='0x8000')
    ap.add_argument('--pc', default=None, help='PC (def = org)')
    ap.add_argument('--sp', default='0x7FFE')          # como NextBuild (.cfg)
    ap.add_argument('--entry-bank', type=int, default=0)
    ap.add_argument('--sysvars', default=None,
                    help='sysvars.bin -> banco 10, offset 0x1C00 (como NextBuild)')
    ap.add_argument('--img', action='append', default=[],
                    help='banco:fichero.nxi  (repetible, banco 16K completo)')
    a = ap.parse_args()
    org = int(a.org, 0)
    pc = int(a.pc, 0) if a.pc else org
    sp = int(a.sp, 0)
    banks = bin_a_bancos(a.bin, org)
    if a.sysvars:                                       # NextZXOS sysvars en banco 10
        sv = open(a.sysvars, 'rb').read()
        b10 = bytearray(banks.get(10, bytes(16384)))
        b10[0x1C00:0x1C00 + len(sv)] = sv
        banks[10] = bytes(b10)
    for spec in a.img:
        bk, _, fn = spec.partition(':')
        banks[int(bk)] = open(fn, 'rb').read()
    build_nex(a.nex, banks, pc, sp, entry_bank=a.entry_bank)
    print('NEX:', a.nex, '| bancos:', sorted(banks.keys()),
          '| PC=0x%04X SP=0x%04X' % (pc, sp))


if __name__ == '__main__':
    main()
