# -*- coding: utf-8 -*-
"""
genera_font42.py - Genera font42.py: la fuente de 6 pixeles (42 columnas) del
motor nativo del ZX Spectrum Next.

Fuentes de datos, todas ya en el repositorio:
  CSpect/CRoad/code/ROMFONT.FNT   fuente 8x8 de la ROM del Spectrum
  print42_es.bas, print42_pt.bas  tablas whichcolumn y characters de la rutina
                                  de 42 columnas de Britlion, con los glifos
                                  acentuados que ya usan los builds BASIC

La rutina de Britlion estrecha cada caracter EN TIEMPO DE EJECUCION: por cada
glifo, whichcolumn dice que columna quitar (mascara de 1s desde la izquierda; el
primer 0 marca la columna que se va), y los caracteres que no sobreviven a ese
recorte llevan un glifo redibujado en la tabla characters. Aqui ese trabajo se
hace UNA VEZ al generar, no en cada caracter impreso: el resultado son 8 bytes
por glifo con la tinta ya dentro de los 6 bits altos.

Dos glifos se corrigen respecto a lo que traen los .bas:

  '_' (95)  su entrada de whichcolumn vale 6, que es el indice de la 'a'
            acentuada en characters, asi que en los builds BASIC el subrayado
            se pinta como 'a con tilde'. Aqui lleva su propio glifo.

  'q' (113) su whichcolumn vale 255 (no se quita ninguna columna) y el remate
            de la cola cae en la columna 7, fuera de la celda de 6 pixeles, asi
            que invade el primer pixel del caracter siguiente. Aqui la cola va
            recta, alineada con el borde derecho del cuenco.

    python genera_font42.py
"""
import io
import re

ROMFONT = 'CSpect/CRoad/code/ROMFONT.FNT'

# glifos propios, ya en formato de 6 px (tinta en los bits 7..2)
PROPIOS = {
    95:  [0, 0, 0, 0, 0, 0, 0, 0x7C],                      # _
    113: [0, 0, 0x3C, 0x44, 0x44, 0x3C, 0x04, 0x04],       # q con cola recta
}


def _tablas(path):
    s = io.open(path, encoding='utf-8', errors='replace').read()
    wc = [int(m.group(1)) for m in re.finditer(
        r'defb\s+(\d+)', s[s.index('whichcolumn:'):s.index('LOCAL characters')])]
    ch = [int(m.group(1)) for m in re.finditer(
        r'defb\s+(\d+)', s[s.index('characters:'):])]
    return wc, ch


def _glifo(code, wc, ch, rom):
    if code in PROPIOS:
        return list(PROPIOS[code])
    v = wc[code - 32]
    if v < 128:                                  # glifo redibujado
        return list(ch[v * 8:v * 8 + 8])
    base = (code - 32) * 8                       # recorte de columna sobre la ROM
    if base + 8 > len(rom):
        return [0] * 8
    return [((b & v) | (((b << 1) & 0xFF) & (~v & 0xFF))) & 0xFF
            for b in rom[base:base + 8]]


def tabla(path, rom):
    """112 glifos x 8 bytes: codigos 32..127 y luego 224..239 (acentos)."""
    wc, ch = _tablas(path)
    out = []
    for code in list(range(32, 128)) + list(range(144, 160)):
        out += _glifo(code, wc, ch, rom)
    return out


def comprueba(nombre, t):
    """La tinta tiene que caber en los 6 bits altos: si toca los bits 1..0
    invade el primer pixel del caracter siguiente."""
    malos = []
    for i in range(0, len(t), 8):
        if any(b & 0x03 for b in t[i:i + 8]):
            j = i // 8
            malos.append(32 + j if j < 96 else 224 + j - 96)
    if malos:
        raise SystemExit('%s: tinta fuera de la celda de 6 px en %s' % (nombre, malos))


def _emite(nombre, t):
    L = ['%s = bytes([' % nombre]
    for i in range(0, len(t), 8):
        j = i // 8
        c = 32 + j if j < 96 else 224 + j - 96
        L.append('    ' + ','.join('%3d' % b for b in t[i:i + 8]) +
                 ',  # %s' % (chr(c) if 32 < c < 127 else c))
    L.append('])')
    return chr(10).join(L)


def main():
    rom = open(ROMFONT, 'rb').read()
    es = tabla('print42_es.bas', rom)
    pt = tabla('print42_pt.bas', rom)
    comprueba('ES', es)
    comprueba('PT', pt)
    cab = ('# -*- coding: utf-8 -*-\n'
           '"""\nfont42.py - Fuente de 6 pixeles (42 columnas) del motor nativo del Next.\n\n'
           'GENERADO por genera_font42.py. No editar a mano.\n\n'
           'Cada glifo son 8 bytes con la tinta en los 6 bits altos (7..2), listos para\n'
           'pintar con paso de 6 pixeles. Orden: codigos 32..127 y luego 224..239, que\n'
           'es como SCRIBA codifica los acentos.\n"""\n\n')
    io.open('font42.py', 'w', encoding='utf-8').write(
        cab + _emite('ES', es) + chr(10) * 2 + _emite('PT', pt) + chr(10) * 2 +
        'def tabla(idioma):\n'
        '    """Los 896 bytes de la fuente para el idioma dado."""\n'
        "    return PT if str(idioma or '').lower().startswith('pt') else ES\n")
    print('font42.py: ES %d bytes, PT %d bytes (%d glifos cada una)'
          % (len(es), len(pt), len(es) // 8))


if __name__ == '__main__':
    main()
