#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
next_export.py - Exporta un juego Scriba a ZX BASIC para ZX Spectrum Next,
SELF-CONTAINED: sin NextLib, sin NextBuild, sin LoadSDBank.

  - Texto en la ULA (32/42/64 col), imagen en Layer 2 (tira del tercio superior).
  - NextReg se escribe por PUERTO ($243B=9275 selecciona reg, $253B=9531 dato).
  - Cada localizacion con imagen se muestra con $12-switch: NextReg $12 apunta
    el banco activo de Layer 2 al banco 16K donde el empaquetador colocara su
    <id>.nxi. El clip ($18) deja ver solo el tercio superior = la imagen.
  - La paleta de cada imagen va incrustada con incbin (<id>.nxp, 512 B) y se
    sube a la paleta de LAYER 2 ($43=$10, autoinc) escribiendo en $41 por puerto.

El .bas NO contiene las imagenes: las coloca empaqueta_nex.py en sus bancos a
partir del manifiesto "<salida>.banks" que escribe este modulo. Compilar el .bas
con zxbc pelado (--arch zxnext --org 32768 -o juego.bin) y luego empaquetar.

Reutiliza el MOTOR de spectrum_export (recolecta, genera_fuente..4, poda).

Uso:  from next_export import export_bas ; export_bas(game,'juego.bas',columnas=42)
"""

import os
import sys

import spectrum_export as sx

BANK_BASE = 16        # primer banco de 16K para imagenes (editable si colisiona)
REG_PORT = 9275       # $243B - selecciona el NextReg
VAL_PORT = 9531       # $253B - escribe el dato del NextReg
L2_PORT = 4667        # $123B - bit1 = Layer 2 visible


# --- Texto sin compresion (sustituye '@DICCIONARIO@') -----------------------

def _bloque_texto_plano(c):
    g = c.game
    L = ["' ---------- TEXTO SIN COMPRESION (Next) ----------",
         'FUNCTION pex(t$ AS STRING) AS STRING',
         '    RETURN t$',
         'END FUNCTION',
         '',
         'FUNCTION onomW$(i AS UBYTE) AS STRING']
    primero = True
    for oid in c.objids:
        nm = sx.translit_disp(g['objects'][oid].get('name', oid))
        kw = 'IF' if primero else 'ELSEIF'
        primero = False
        L.append(f'    {kw} i = {c.objidx[oid]} THEN')
        L.append(f'        RETURN {sx.q(nm)}')
    if not primero:
        L.append('    END IF')
    L.append('    RETURN ""')
    L.append('END FUNCTION')
    L.append('')
    L.append('SUB initDic()')
    L.append('END SUB')
    return '\n'.join(L)


# --- Asignacion de bancos (compartida con el empaquetador) ------------------

def asigna_bancos(locs_con_img):
    """Devuelve (mapa, blank): mapa = {lid: banco16k}, blank = banco del negro."""
    mapa = {lid: BANK_BASE + i for i, lid in enumerate(locs_con_img)}
    blank = BANK_BASE + len(locs_con_img)
    return mapa, blank


# --- Subsistema de imagen Layer 2 ($12-switch por puerto), self-contained ---

def _subepalup_asm(pal_bank):
    """FUNCTION asm que SUBE 256 colores de una paleta desde el BANCO de paletas.
    Pagina pal_bank en $C000 ($DFFD+$7FFD), con DI, sube los 256 bytes pares
    (color 8-bit) al registro de dato de paleta de Layer 2 ($41, autoinc) y
    restaura la paginacion (banco 0). Debe quedar POR DEBAJO de $C000 (como
    pk128): se inyecta junto a pk128 para que asi sea. Entrada FASTCALL: A=slot."""
    palhi = (pal_bank >> 3) & 7
    pallo = (pal_bank & 7) | 16
    return r'''
' Sube la paleta del 'slot' desde el BANCO de paletas (paginado). Bajo $C000.
FUNCTION FASTCALL subePalUp(slot AS UBYTE) AS UBYTE
    asm
        ; A = slot ; HL = $C000 + slot*512 (puntero dentro del banco de paletas)
        ld h, a
        ld l, 0
        add hl, hl
        ld bc, 0c000h
        add hl, bc
        ; seleccionar paleta de Layer 2 (reg $43=$10), indice 0 ($40=0) y
        ; dejar seleccionado el reg de DATO de paleta ($41). HL se conserva.
        ld bc, 243bh
        ld a, 43h
        out (c), a
        ld bc, 253bh
        ld a, 10h
        out (c), a
        ld bc, 243bh
        ld a, 40h
        out (c), a
        ld bc, 253bh
        xor a
        out (c), a
        ld bc, 243bh
        ld a, 41h
        out (c), a
        ; paginar el banco de paletas en $C000 (DI: el codigo $C000+ se va)
        di
        ld bc, 0dffdh
        ld a, ''' + str(palhi) + r'''
        out (c), a
        ld bc, 07ffdh
        ld a, ''' + str(pallo) + r'''
        out (c), a
        ld d, 0
subpu_lp:
        ld a, (hl)
        ld bc, 253bh
        out (c), a
        inc hl
        inc hl
        dec d
        jr nz, subpu_lp
        ; restaurar paginacion: banco 0 + ROM
        ld bc, 0dffdh
        xor a
        out (c), a
        ld bc, 07ffdh
        ld a, 16
        out (c), a
        ei
    end asm
END FUNCTION'''


def _cargabanco_asm():
    """FUNCTION asm: carga 16 KB de la CINTA en un banco (carga en 2 fases).
    Pagina 'bank' en $C000 ($DFFD+$7FFD, ROM 48K) y llama a la rutina de la ROM
    LD-BYTES ($0556) para leer el siguiente bloque del .tap (16384 B, flag $FF)
    directamente en $C000; luego restaura la paginacion. Debe quedar bajo $C000
    (se inyecta junto a pk128). FASTCALL: A = banco."""
    return r'''
' Carga 16K del siguiente bloque de cinta en 'bank' (ROM LD-BYTES). Bajo $C000.
FUNCTION FASTCALL cargaBanco(bank AS UBYTE) AS UBYTE
    asm
        ld e, a            ; E = banco
        srl a
        srl a
        srl a              ; A = banco >> 3  (bits altos -> $DFFD)
        di
        ld bc, 0dffdh
        out (c), a
        ld a, e
        and 7
        or 16              ; A = (banco&7)|16  (bits bajos + ROM 48K -> $7FFD)
        ld bc, 07ffdh
        out (c), a
        ld ix, 0c000h      ; destino
        ld de, 16384       ; longitud
        ld a, 255          ; flag de bloque de datos
        scf                ; carry = LOAD (no verify)
        call 0556h         ; ROM: LD-BYTES
        ld bc, 0dffdh      ; restaurar paginacion: banco 0 + ROM
        xor a
        out (c), a
        ld bc, 07ffdh
        ld a, 16
        out (c), a
        ei
    end asm
END FUNCTION'''


def _bloque_layer2(c, locs_con_img, scr_bank=None, pal_bank=None, scr_slot=0,
                   dos_fases=False):
    mapa, blank = asigna_bancos(locs_con_img)

    # tabla de paletas: incbin de cada .nxp (512 B) en orden de slot (data/).
    # Solo en modo PLANO (pal_bank=None, p.ej. .nex). En modo .tap las paletas
    # van en un BANCO (pal_bank) y se leen con subePalUp (bajo $C000).
    pal_incbin = []
    for lid in locs_con_img:
        pal_incbin.append(f'        incbin "data/{lid}.nxp"')
    pal_incbin = '\n'.join(pal_incbin) if pal_incbin else '        defb 0'

    # picBank(loc) -> banco 16K de su imagen (blank si no tiene)
    pbank = ['FUNCTION picBank(loc AS UBYTE) AS UBYTE']
    primero = True
    for lid in locs_con_img:
        kw = 'IF' if primero else 'ELSEIF'
        primero = False
        pbank.append(f'    {kw} loc = {c.locidx[lid]} THEN')
        pbank.append(f'        RETURN {mapa[lid]}')
    if not primero:
        pbank.append('    END IF')
    pbank.append(f'    RETURN {blank}')
    pbank.append('END FUNCTION')
    pbank = '\n'.join(pbank)

    # picPalIdx(loc) -> slot de paleta
    ppal = ['FUNCTION picPalIdx(loc AS UBYTE) AS UBYTE']
    primero = True
    for i, lid in enumerate(locs_con_img):
        kw = 'IF' if primero else 'ELSEIF'
        primero = False
        ppal.append(f'    {kw} loc = {c.locidx[lid]} THEN')
        ppal.append(f'        RETURN {i}')
    if not primero:
        ppal.append('    END IF')
    ppal.append('    RETURN 0')
    ppal.append('END FUNCTION')
    ppal = '\n'.join(ppal)

    # ── paletas: PLANO (incbin, pal_bank=None) vs BANCO (subePalUp) ──
    if pal_bank is None:
        pal_flat = (
            "' Direccion de la tabla de paletas (incrustadas, 512 B cada una).\n"
            'FUNCTION FASTCALL palAddr() AS UINTEGER\n'
            '    asm\n'
            '        ld hl, nx_paltab\n'
            '        ret\n'
            'nx_paltab:\n'
            + pal_incbin + '\n'
            '    end asm\n'
            'END FUNCTION')
        subepal_body = (
            '    DIM po AS UINTEGER\n'
            '    DIM k AS UINTEGER\n'
            '    po = palAddr() + slot * 512\n'
            '    nreg($43, $10)\n'
            '    nreg($40, 0)\n'
            '    OUT %d, $41\n'
            '    FOR k = 0 TO 255\n'
            '        OUT %d, PEEK(po + 2 * k)\n'
            '    NEXT k' % (REG_PORT, VAL_PORT))
        scrpal_func = (
            'FUNCTION FASTCALL palAddrScr() AS UINTEGER\n'
            '    asm\n'
            '        ld hl, scr_pal\n'
            '        ret\n'
            'scr_pal:\n'
            '        incbin "data/screen.nxp"\n'
            '    end asm\n'
            'END FUNCTION\n')
        showtitle_pal = (
            '    DIM po AS UINTEGER\n'
            '    DIM k AS UINTEGER\n'
            '    po = palAddrScr()\n'
            '    nreg($43, $10)\n'
            '    nreg($40, 0)\n'
            '    OUT %d, $41\n'
            '    FOR k = 0 TO 255\n'
            '        OUT %d, PEEK(po + 2 * k)\n'
            '    NEXT k' % (REG_PORT, VAL_PORT))
    else:
        pal_flat = ("' Paletas en el banco %d (se leen con subePalUp, bajo $C000)."
                    % pal_bank)
        subepal_body = ('    DIM rr AS UBYTE\n'
                        '    rr = subePalUp(slot)')
        scrpal_func = ''
        showtitle_pal = ('    DIM rr AS UBYTE\n'
                         '    rr = subePalUp(%d)' % scr_slot)

    cuerpo = r'''' ---------- LAYER 2 (Next, self-contained): un banco por loc ----------
' Cada imagen (256x64) vive en su banco de 16K (la coloca empaqueta_nex.py).
' showPic apunta NextReg $12 (banco activo de Layer 2) a ese banco; el clip
' muestra solo el tercio superior. NextReg por PUERTO ($243B/$253B). Sin NextLib.
DIM tw0 AS UBYTE
DIM pcnt AS UBYTE

' Escribe un NextReg por puerto (reg en $243B, dato en $253B).
SUB nreg(r AS UBYTE, v AS UBYTE)
    OUT ''' + str(REG_PORT) + r''', r
    OUT ''' + str(VAL_PORT) + r''', v
END SUB

''' + pal_flat + r'''

''' + pbank + r'''

''' + ppal + r'''

SUB initL2()
    tw0 = 8
    BORDER 7: PAPER 7: INK 0   ' colores por defecto (el autor los cambia en on_start)
    nreg($70, 0)             ' L2 256x192 8bpp
    nreg($12, ''' + str(blank) + r''')        ' banco activo de Layer 2 = blanco (negro)
    nreg($1C, 2)             ' reset clip index L2
    nreg($18, 0)
    nreg($18, 255)
    nreg($18, 0)
    nreg($18, 63)            ' clip = tercio superior (lineas 0-63)
    nreg($69, 128)           ' habilita Layer 2
    OUT ''' + str(L2_PORT) + r''', 2            ' $123B bit1: visible
    nreg($43, $10)           ' paleta de Layer 2
    nreg($40, 0)
    nreg($41, 0)             ' indice 0 = negro (para el banco blanco)
END SUB

' Sube la paleta del slot a la paleta de LAYER 2 ($43=$10, autoinc) por puerto.
SUB subePal(slot AS UBYTE)
''' + subepal_body + r'''
END SUB

' Muestra la imagen: apunta Layer 2 ($12) al banco de la localizacion + paleta.
SUB showPic(loc AS UBYTE)
    DIM bk AS UBYTE
    bk = picBank(loc)
    IF oscuro() = 1 THEN bk = ''' + str(blank) + r'''
    nreg($12, bk)
    IF bk = ''' + str(blank) + r''' THEN
        nreg($43, $10)
        nreg($40, 0)
        nreg($41, 0)         ' negro (banco blanco)
    ELSE
        subePal(picPalIdx(loc))
    END IF
END SUB

'''
    # ── pantalla de titulo Layer 2 (256x192 = 3 bancos) si hay data/screen.nxi ──
    if scr_bank is not None:
        cuerpo += (r'''
''' + scrpal_func + r'''
' Muestra la pantalla de titulo (256x192) a pantalla completa de Layer 2.
SUB showTitle()
    nreg($12, ''' + str(scr_bank) + r''')
    nreg($1C, 2)
    nreg($18, 0)
    nreg($18, 255)
    nreg($18, 0)
    nreg($18, 191)          ' clip = pantalla completa
    nreg($69, 128)
    OUT ''' + str(L2_PORT) + r''', 2
''' + showtitle_pal + r'''
END SUB

' Restaura el clip al tercio superior (lineas 0-63) para el juego.
SUB clipJuego()
    nreg($1C, 2)
    nreg($18, 0)
    nreg($18, 255)
    nreg($18, 0)
    nreg($18, 63)
END SUB
''')
    # carga en 2 fases: el motor carga los bancos de imagen (16..blank-1) desde
    # la cinta tras mostrar el titulo (se ejecuta despues de pulsar tecla).
    if dos_fases and locs_con_img:
        cuerpo += ('\nSUB cargaImgs()\n'
                   '    DIM b AS UBYTE\n'
                   '    DIM rr AS UBYTE\n'
                   '    FOR b = %d TO %d\n'
                   '        rr = cargaBanco(b)\n'
                   '    NEXT b\n'
                   'END SUB\n' % (BANK_BASE, blank - 1))
    return cuerpo


def _truncar_psg(stream, maxb):
    """Recorta un stream PSG estandar a <=maxb bytes en un limite de frame (0xFF)
    y lo cierra con 0xFD para que haga bucle. Asi una cancion larga que no cabe
    plana suena igualmente (su primer tramo, con el tempo correcto)."""
    cut = min(maxb, len(stream))
    while cut > 0 and stream[cut] != 0xFF:
        cut -= 1
    if cut <= 0:
        return stream
    return stream[:cut] + b'\xFD'


def _aplica_next(src, c, locs_con_img, scr_bank=None, psg_player=None,
                 pal_bank=None, scr_slot=0, dos_fases=False):
    bloque = _bloque_layer2(c, locs_con_img, scr_bank=scr_bank,
                            pal_bank=pal_bank, scr_slot=scr_slot,
                            dos_fases=dos_fases)
    if psg_player:
        bloque = psg_player + '\n' + bloque       # reproductor PSG (musica titulo)
    ancla = "' ---------- SALIDA 64 COLUMNAS CON SCROLL ----------"
    if ancla not in src:
        raise AssertionError('ancla de insercion de imagenes no encontrada')
    src = src.replace(ancla, bloque + ancla, 1)

    # subePalUp (paletas) y cargaBanco (carga 2 fases) DEBEN quedar bajo $C000:
    # se inyectan junto a pk128 (antes de entW$), que ya esta probado bajo $C000.
    iny = ''
    if pal_bank is not None:
        iny += _subepalup_asm(pal_bank).lstrip('\n') + '\n\n'
    if dos_fases:
        iny += _cargabanco_asm().lstrip('\n') + '\n\n'
    if iny:
        ancla_pk = 'FUNCTION entW$(k AS UINTEGER) AS STRING'
        if ancla_pk not in src:
            raise AssertionError('entW$ (bloque pk128) no encontrado')
        src = src.replace(ancla_pk, iny + ancla_pk, 1)

    # ventana de texto: filas 8-23
    viejo = 'SUB limpia()\n    CLS\n    crow = 0: ccol = 0\nEND SUB'
    nuevo = 'SUB limpia()\n    CLS\n    crow = 8: ccol = 0\nEND SUB'
    src = src.replace(viejo, nuevo, 1)
    src = src.replace('WinScrollUp(0, 0, 32, 24)',
                      'WinScrollUp(tw0, 0, 32, 24 - tw0)', 1)

    viejo = 'SUB descL()\n    DIM i AS UBYTE\n    pnl()'
    if viejo not in src:
        raise AssertionError('SUB descL() no encontrado')
    src = src.replace(viejo,
                      'SUB descL()\n    DIM i AS UBYTE\n'
                      '    showPic(l)\n'
                      '    limpiaTxt()', 1)

    if '\ninitDic()\n' not in src:
        raise AssertionError('initDic() no encontrado')
    src = src.replace('\ninitDic()\n', '\ninitDic()\ninitL2()\n', 1)

    if '\nlimpia()\n' not in src:
        raise AssertionError('limpia() no encontrado')
    if scr_bank is not None:
        # pantalla de titulo (Layer 2 256x192) + espera (con musica si hay) antes
        # del juego; luego clip al tercio superior y primera localizacion.
        if psg_player:
            # primero esperar a SOLTAR cualquier tecla residual (la de cargar) y
            # luego a una pulsacion NUEVA; si no, el bucle saldria al instante.
            espera = ('psginit()\n'
                      'DO\n    PAUSE 1\n    psgframe()\nLOOP UNTIL INKEY$ = ""\n'
                      'DO\n    PAUSE 1\n    psgframe()\nLOOP UNTIL INKEY$ <> ""\n'
                      'psgoff()\n')
        else:
            espera = 'PAUSE 0\n'
        # carga en 2 fases: tras el titulo+musica (y la tecla) el motor carga las
        # imagenes desde la cinta; antes de eso solo se cargo motor+texto+titulo.
        carga = 'cargaImgs()\n' if dos_fases else ''
        inicio = ('\nshowTitle()\n' + espera + carga +
                  'clipJuego()\nlimpia()\nshowPic(l)\ncrow = tw0\n')
    else:
        inicio = '\nlimpia()\nshowPic(l)\ncrow = tw0\n'
    src = src.replace('\nlimpia()\n', inicio, 1)

    src = src.replace('    crow = 8: ccol = 0\n',
                      '    crow = tw0: ccol = 0: pcnt = 0\n', 1)
    viejo_pg = ('        WinScrollUp(tw0, 0, 32, 24 - tw0)\n'
                '        crow = crow - 1\n    LOOP\nEND SUB')
    if viejo_pg not in src:
        raise AssertionError('pgchk no encontrado')
    pmas = viejo_pg + ('\n\nSUB pmas()\n'
                       '    pgchk()\n'
                       '    PAUSE 0\n'
                       '    pcnt = 0\n'
                       'END SUB\n\n'
                       'SUB limpiaTxt()\n'
                       '    asm\n'
                       '        ld hl, 4800h\n'
                       '        ld de, 4801h\n'
                       '        ld bc, 4095\n'
                       '        ld (hl), 0\n'
                       '        ldir\n'
                       '    end asm\n'
                       '    crow = tw0: ccol = 0: pcnt = 0\n'
                       'END SUB')
    src = src.replace(viejo_pg, pmas, 1)
    viejo_pnl = 'SUB pnl()\n    crow = crow + 1\n    ccol = 0\nEND SUB'
    src = src.replace(viejo_pnl,
                      'SUB pnl()\n    crow = crow + 1\n    ccol = 0\n'
                      '    pcnt = pcnt + 1\n'
                      '    IF pcnt >= 23 - tw0 THEN pmas()\nEND SUB', 1)
    src = src.replace('    li$ = leeLinea$()\n',
                      '    li$ = leeLinea$()\n    pcnt = 0\n', 1)
    return src


def _aplica_columnas(src, columnas, here, outdir):
    import shutil

    def _copylib(name):
        s = os.path.join(here, name)
        d = os.path.join(outdir, name)
        if os.path.isfile(s) and os.path.abspath(s) != os.path.abspath(d):
            shutil.copy(s, d)

    _fsuf = '_pt' if sx._PT_LANG else '_es'
    if columnas == 64:
        src = src.replace('#include <print64.bas>', '#include "print64%s.bas"' % _fsuf)
        _copylib('print64%s.bas' % _fsuf)
    elif columnas == 42:
        src = (src.replace('#include <print64.bas>', '#include "print42%s.bas"' % _fsuf)
                  .replace('printat64(', 'printat42(')
                  .replace('print64(', 'print42(')
                  .replace('avail = 64 - ccol', 'avail = 42 - ccol')
                  .replace('LEN(s$) < 60', 'LEN(s$) < 38'))
        _copylib('print42%s.bas' % _fsuf)
    elif columnas == 32:
        udgdata = ','.join(str(b) for b in
                           (sx._UDG_BYTES_PT if sx._PT_LANG else sx._UDG_BYTES))
        shim = ('DIM p32y AS UBYTE\n'
                'DIM p32x AS UBYTE\n'
                'SUB printat64(y AS UBYTE, x AS UBYTE)\n'
                '    p32y = y: p32x = x\n'
                'END SUB\n'
                'SUB print64(t$ AS STRING)\n'
                '    PRINT AT p32y, p32x; t$;\n'
                'END SUB\n'
                'SUB initUDG()\n'
                '    DIM iu AS UINTEGER\n'
                '    DIM adu AS UINTEGER\n'
                '    DIM bu AS UBYTE\n'
                '    adu = PEEK(23675) + 256 * PEEK(23676)\n'
                '    RESTORE udgdata\n'
                '    FOR iu = 0 TO 127\n'
                '        READ bu\n'
                '        POKE adu + iu, bu\n'
                '    NEXT iu\n'
                'END SUB\n'
                'udgdata:\n'
                'DATA ' + udgdata)
        src = (src.replace('#include <print64.bas>', shim)
                  .replace('avail = 64 - ccol', 'avail = 32 - ccol')
                  .replace('LEN(s$) < 60', 'LEN(s$) < 28'))
        src = src.replace('\ninitDic()\n', '\ninitDic()\ninitUDG()\n', 1)
    return src


def _locs_con_imagen(c, outdir):
    """Localizaciones con <id>.nxi en data/ (lo genera el editor)."""
    datadir = os.path.join(outdir, 'data')
    locs = []
    for lid in c.locids:
        if os.path.isfile(os.path.join(datadir, lid + '.nxi')):
            locs.append(lid)
    return locs


def _escribe_manifiesto(out_path, locs_con_img, extra=None, deferidos=None):
    """Escribe '<salida>.banks' = lineas 'banco<TAB>fichero[<TAB>D]' (relativos a
    data/) para que el empaquetador coloque cada imagen en su banco. Incluye blank
    y, si los hay, bancos extra (p.ej. los 3 de la pantalla de titulo). Los bancos
    en 'deferidos' se marcan con 'D': el cargador BASIC NO los carga; los carga el
    motor desde cinta (LD-BYTES) en la 2ª fase (titulo+musica primero)."""
    mapa, blank = asigna_bancos(locs_con_img)
    dif = set(deferidos or [])

    def _ln(bank, fn):
        return '%d\t%s\tD' % (bank, fn) if bank in dif else '%d\t%s' % (bank, fn)

    lines = []
    for lid in locs_con_img:
        lines.append(_ln(mapa[lid], lid + '.nxi'))
    lines.append(_ln(blank, 'blank.nxi'))
    for bank, fn in (extra or []):
        lines.append(_ln(bank, fn))
    man = out_path + '.banks'
    with open(man, 'w', encoding='ascii') as f:
        f.write('\n'.join(lines) + '\n')
    return man


def export_bas(game, out_path, progreso=None, columnas=42, modo='tap'):
    """modo='tap': texto comprimido en BANCOS (128K, pk128/$7FFD) + imagenes
    Layer 2 en bancos altos ($DFFD) -> empaqueta_nextap.py -> .tap (juegos
    grandes, sin limite, valido en Next por el entorno de paginacion del .tap).
    modo='nex': texto comprimido PLANO (incbin/PEEK) -> empaqueta_nex.py -> .nex
    autocontenido (solo juegos que caben en ~32K). En ambos las imagenes Layer 2
    se muestran con $12-switch (NextReg por puerto)."""
    def _p(pct, msg):
        if progreso:
            progreso(pct, msg)

    _p(56, 'Recolectando datos del juego (Next)...')
    _lang = (game.get('metadata', {}).get('language') or 'es').strip().lower()
    sx._PT_LANG = _lang.startswith('pt') or _lang.startswith('por')
    c = sx.recolecta(game)
    c.fx_enabled = True      # FX por AY en Next (prueba con heap reducido a 2 KB)
    _p(62, 'Generando motor ZX BASIC...')
    L = sx.genera_fuente(c)
    sx.genera_fuente2(c, L)
    _p(70, 'Transpilando condacts...')
    sx.genera_fuente3(c, L)
    sx.genera_fuente4(c, L)
    src = '\n'.join(L) + '\n'
    # mensajes del sistema personalizados (metadata['mensajes']) antes de comprimir
    try:
        import mensajes
        src, _ = mensajes.aplica(src, c.meta.get('mensajes'),
                                 int(c.meta.get('max_score', 0) or 0),
                                 sx.translit_disp)
    except Exception:
        pass

    src = src.replace('- ZX Spectrum 48K',
                      '- ZX Spectrum Next (texto comprimido + Layer 2)')
    src = src.replace('Generado por Scriba (motor + juego + compresion)',
                      'Generado por Scriba (motor + juego, Next)')

    _p(74, 'Podando codigo muerto...')
    src = sx.poda(src)

    outdir = os.path.dirname(os.path.abspath(out_path)) or '.'
    # raiz del juego: los intermedios (data/, _texto.bin, .banks) van en outdir
    # (temp/<target>/), pero los assets (img/, music/) viven en la raiz del juego.
    if os.path.basename(os.path.dirname(outdir)).lower() == 'temp':   # temp/<target>
        raiz = os.path.dirname(os.path.dirname(outdir))
    elif os.path.basename(outdir).lower() == 'temp':                  # temp
        raiz = os.path.dirname(outdir)
    else:
        raiz = outdir
    base = os.path.splitext(os.path.basename(out_path))[0]
    bin_name = base + '_texto.bin'

    # compresion de textos: 'tap' -> 128K (texto en bancos, pk128/$7FFD);
    # 'nex' -> 48K (texto plano, incbin + PEEK).
    cmode = '128k' if modo == 'tap' else '48k'
    _p(78, 'Comprimiendo textos (diccionario, %s)...' % cmode)
    nombres = [sx.translit_disp(c.game['objects'][oid].get('name', oid))
               for oid in c.objids]
    src, rep, bin_blob = sx.comprime(src, nombres, c.avisos, bin_name,
                                     progreso=progreso, modo=cmode)

    # FX por AY (Next siempre tiene AY): embebe los efectos referenciados por PLAY.
    src = sx.aplica_fx(src, game, clock=1773400, embed=True, enabled=True)

    locs_con_img = _locs_con_imagen(c, outdir)
    # banco "negro" (blank.nxi = 16K de ceros): locs sin imagen / oscuridad
    datadir = os.path.join(outdir, 'data')
    os.makedirs(datadir, exist_ok=True)
    with open(os.path.join(datadir, 'blank.nxi'), 'wb') as f:
        f.write(b'\x00' * 16384)

    # ── pantalla de titulo (data/screen.nxi 256x192 = 3 bancos) + musica ──
    _, blank0 = asigna_bancos(locs_con_img)
    scr_bank = None
    screen_banks = []
    scr_nxi = os.path.join(datadir, 'screen.nxi')
    scr_nxp = os.path.join(datadir, 'screen.nxp')
    if (os.path.isfile(scr_nxi) and os.path.getsize(scr_nxi) == 49152
            and os.path.isfile(scr_nxp)):
        data = open(scr_nxi, 'rb').read()
        scr_bank = blank0 + 1               # 3 bancos consecutivos para 256x192
        for i in range(3):
            fn = 'screen%d.nxi' % i
            with open(os.path.join(datadir, fn), 'wb') as f:
                f.write(data[i * 16384:(i + 1) * 16384])
            screen_banks.append((scr_bank + i, fn))

    # ── banco de PALETAS (solo .tap): saca las .nxp (512 B c/u) del binario
    # plano a un banco propio, que subePalUp lee paginando bajo $C000. Evita que
    # el .bin del motor + 12 KB de paletas se salga de $FFFF con muchas imagenes.
    pal_bank = None
    scr_slot = 0
    if modo == 'tap' and (locs_con_img or scr_bank is not None):
        scr_slot = len(locs_con_img)
        highest = blank0 if scr_bank is None else (scr_bank + 2)
        pal_bank = highest + 1
        pal = bytearray()
        for lid in locs_con_img:
            p = os.path.join(datadir, lid + '.nxp')
            pal += (open(p, 'rb').read() if os.path.isfile(p) else b'\x00' * 512)
        if scr_bank is not None:
            p = os.path.join(datadir, 'screen.nxp')
            pal += (open(p, 'rb').read() if os.path.isfile(p) else b'\x00' * 512)
        pal = (bytes(pal) + b'\x00' * 16384)[:16384]   # un banco de 16K exacto
        with open(os.path.join(datadir, 'paletas.nxi'), 'wb') as f:
            f.write(pal)
        screen_banks.append((pal_bank, 'paletas.nxi'))

    psg_player = None
    psg_info = None
    try:
        psg_stream, psg_nom = sx._leer_psg(os.path.join(raiz, 'music'))
    except Exception:
        psg_stream, psg_nom = None, None
    if psg_stream is not None:
        if scr_bank is None:
            c.avisos.append('musica: hay musica en music/ pero falta la pantalla de '
                            'titulo (img/Next/screen.*); se omite')
        else:
            if len(psg_stream) > 4500:
                orig = len(psg_stream)
                psg_stream = _truncar_psg(psg_stream, 4480)
                c.avisos.append(
                    'musica %s: %d bytes no caben planos; recortada a %d bytes '
                    '(~%d s) y en bucle. La cancion completa necesitaria musica '
                    'en banco.' % (psg_nom, orig, len(psg_stream),
                                   psg_stream.count(0xFF) // 50))
            psg_player = sx._PSG_PLAYER.replace('@PSGDATA@',
                                                sx._psg_defb(psg_stream))
            psg_info = '%s (%d bytes)' % (psg_nom, len(psg_stream))

    # carga en 2 fases (titulo+musica primero): DESACTIVADA. El Next, al cargar un
    # .tap desde SD, detiene la "cinta" tras el cargador BASIC, asi que la rutina
    # ROM LD-BYTES con la que el motor leia los bancos de imagen tras pulsar tecla
    # se cuelga esperando el tono guia. Volvemos a la carga monofasica (todos los
    # bancos en el cargador BASIC), que es fiable; el titulo sale tras cargar todo.
    mapa0, _ = asigna_bancos(locs_con_img)
    dos_fases = False
    deferidos = list(mapa0.values()) if dos_fases else None

    _p(84, 'Insertando Layer 2 ($12-switch por puerto)...')
    src = _aplica_next(src, c, locs_con_img, scr_bank=scr_bank,
                       psg_player=psg_player, pal_bank=pal_bank, scr_slot=scr_slot,
                       dos_fases=dos_fases)

    here = os.path.dirname(os.path.abspath(__file__))
    src = _aplica_columnas(src, columnas, here, outdir)

    _p(90, 'Escribiendo .bas + blob de texto...')
    # utf-8-sig (con BOM): zxbc lo lee como UTF-8 y emite cada char con ord(c),
    # asi los codigos UDG de acentos (0x80-0x9F, p.ej. 0x90 del portugues) que
    # queden como literal en el .bas sobreviven. cp1252 no define 5 de esos codigos
    # y fallaba; el grueso del texto viaja comprimido en el blob.
    with open(out_path, 'w', encoding='utf-8-sig') as f:
        f.write(src)
    with open(os.path.join(outdir, bin_name), 'wb') as f:
        f.write(bin_blob)

    man = _escribe_manifiesto(out_path, locs_con_img, extra=screen_banks,
                              deferidos=deferidos)
    # texto de la pantalla de carga: mensaje del sistema 'cargando' (editable y
    # traducible como el resto). Va por la fuente de la ROM en el cargador BASIC
    # -> ASCII en mayusculas. El empaquetador lo lee de '<salida>.loading'.
    try:
        import mensajes as _msgs
        _ov = c.meta.get('mensajes') or {}
        _txt = _ov.get('cargando') or _msgs.defaults().get('cargando') or 'CARGANDO...'
    except Exception:
        _txt = 'CARGANDO...'
    cargando = sx.translit(str(_txt)).upper()[:30]
    with open(out_path + '.loading', 'w', encoding='ascii', errors='replace') as f:
        f.write(cargando)
    mapa, blank = asigna_bancos(locs_con_img)
    org = 24576 if modo == 'tap' else 32768

    informe = ['Exportado (Next %s): %s (+ %s)'
               % ('.tap / texto en bancos' if modo == 'tap'
                  else '.nex / texto plano', out_path, bin_name)]
    informe.append(rep)
    informe.append('Columnas: %d. Org: %d. $12-switch imagenes, sin NextLib.'
                   % (columnas, org))
    if modo == 'tap':
        informe.append('Texto comprimido en bancos bajos (pk128/$7FFD); imagenes '
                       'Layer 2 en bancos altos ($DFFD). Empaqueta empaqueta_nextap.py.')
    else:
        informe.append('Texto comprimido plano (incbin); empaqueta empaqueta_nex.py.')
    if locs_con_img:
        informe.append('Imagenes en %d localizacion(es): %s'
                       % (len(locs_con_img), ', '.join(locs_con_img)))
        informe.append('Bancos imagen: ' + ', '.join('%s=%d' % (l, mapa[l])
                                                      for l in locs_con_img)
                       + ', blank=%d' % blank)
    if scr_bank is not None:
        informe.append('Pantalla de titulo (256x192) en bancos %d-%d.'
                       % (scr_bank, scr_bank + 2))
    if psg_info:
        informe.append('Musica del titulo: %s.' % psg_info)
    informe.append('Manifiesto de bancos: %s' % man)
    _p(100, 'Completado.')
    if c.avisos:
        informe.append('AVISOS (%d):' % len(c.avisos))
        vistos = set()
        for a in c.avisos:
            if a not in vistos:
                vistos.add(a)
                informe.append('  - ' + a)
    return '\n'.join(informe)


def main():
    import yaml
    if len(sys.argv) < 3:
        print('uso: python next_export.py juego.yaml salida.bas [columnas] [tap|nex]')
        return
    columnas = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    modo = sys.argv[4] if len(sys.argv) > 4 else 'tap'
    with open(sys.argv[1], encoding='utf-8') as f:
        game = yaml.safe_load(f)
    game.pop('_editor', None)
    print(export_bas(game, sys.argv[2], columnas=columnas, modo=modo))


if __name__ == '__main__':
    main()
