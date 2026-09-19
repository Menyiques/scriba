# -*- coding: utf-8 -*-
"""
next_nativo.py - Capa de plataforma ZX Spectrum Next para el motor nativo Z80.

El motor (game_engine.ENGINE_ASM) es codigo Z80 independiente de maquina: parser,
VM de condacts, evaluador de expresiones, tablas, temporizadores y word-wrap. Toda
su dependencia del CPC esta en ~20 simbolos externos que en el CPC se resuelven a
llamadas al firmware (&BBxx/&BCxx). Aqui esos mismos simbolos se resuelven a
rutinas propias escritas para el Next, y NO se toca game_engine.py: el export CPC
sigue funcionando igual.

No usa la ROM para nada (ni fuente ni teclado ni impresion), asi que el mapa de
memoria puede llevar RAM sobre &0000-&3FFF y dejar los 64 KB planos.

Simbolos de plataforma que consume el motor:
    TXTO TXTWIN SCRINK SCRBORDER SCRMODE KMREAD KMW SNDREG MCWAIT
    CASOPEN CASDIR CASCLOSE MTABLE TXTMATRIX TXTMTABLE
    KLINIT KLADDF KLDELF MUSINIT MUSPLAY MUSSTOP

Usa instrucciones Z80N (PIXELAD, ADD HL,A, ADD HL,nn).
Fase 1 (esto): texto 8x8 en 32 columnas sobre la pantalla ULA, teclado por
matriz, AY por &FFFD/&BFFD, sin imagenes ni musica. La geometria del impresor
esta aislada en NXPLOT/NXGLYPH: un impresor de 42 columnas entra ahi sin tocar
el resto.
"""
import re

import font42
import game_engine as ge
import z80asm

ORG = 0x6000        # motor: por encima de la pantalla ULA (&4000-&5AFF)
MTABLE = 0x5B00     # tabla de matrices de usuario (RAM libre bajo el motor)
PANT = 0x4000       # pantalla ULA
ATTR = 0x5800       # atributos
COLS = 42           # columnas de texto (fuente de 6 pixeles)
FILAS = 24


# ---------------------------------------------------------------------------
# Fuente de 6 pixeles: 112 glifos (codigos 32..127 y 224..239), con la tinta
# dentro de los 6 bits altos. La genera genera_font42.py a partir de la fuente
# de la ROM del Spectrum y de las tablas de print42_es/pt.bas, o sea que el
# motor nativo saca los mismos pixeles que los builds BASIC de 128K y Next.
# Los acentos van en la tabla, no en (faccp): la plataforma ya no depende de
# que el juego traiga sus bitmaps.
# ---------------------------------------------------------------------------
def _font_asm(idioma='es'):
    datos = font42.tabla(idioma)
    L = ['NXFONT:']
    for i in range(0, len(datos), 8):
        L.append('        defb ' + ','.join(str(b) for b in datos[i:i + 8]))
    return chr(10).join(L)


PLAT_ASM = r'''
; ===========================================================================
;  Capa de plataforma ZX Spectrum Next
; ===========================================================================

; --- estado del impresor ---
nxrow:   defb 0            ; fila del cursor
nxcol:   defb 0            ; columna del cursor
nxwl:    defb 0            ; ventana: izquierda
nxwt:    defb 0            ; ventana: arriba
nxwr:    defb 41           ; ventana: derecha
nxwb:    defb 23           ; ventana: abajo
nxattr:  defb 7            ; atributo actual (tinta 7, papel 0)
nxlast:  defb 0            ; ultima tecla devuelta (antirrebote)
nxsh:    defb 0            ; desplazamiento del glifo dentro del byte (0..7)
nxmh:    defb 0            ; mascara AND del primer byte de pantalla
nxml:    defb 0            ; mascara AND del segundo
nxfil:   defb 0            ; contador de lineas de pixeles
nxcaps:  defb 0            ; CAPS SHIFT pulsado en el ultimo escaneo

; ---------------------------------------------------------------------------
; TXTO: imprime el caracter de A. Equivale a TXT OUTPUT del CPC.
;   codigos de control:  8 = izquierda   10 = abajo   12 = borrar   13 = margen
; Preserva todos los registros (el motor cuenta con ello).
; ---------------------------------------------------------------------------
TXTO:
        push  af
        push  bc
        push  de
        push  hl
        call  nxchar
        pop   hl
        pop   de
        pop   bc
        pop   af
        ret

nxchar:
        cp    13
        jr    z,nx_cr
        cp    10
        jr    z,nx_lf
        cp    12
        jp    z,nxcls
        cp    8
        jr    z,nx_bs
        cp    32
        ret   c                ; otros codigos de control: se ignoran
        call  nxglyph          ; HL -> 8 bytes de la matriz del caracter
        call  nxplot
        ld    a,(nxcol)
        inc   a
        ld    (nxcol),a
        ld    b,a
        ld    a,(nxwr)
        cp    b
        ret   nc               ; aun cabe en la linea
        call  nx_cr            ; desborda: margen + siguiente linea
        jr    nx_lf

nx_cr:  ld    a,(nxwl)
        ld    (nxcol),a
        ret

nx_lf:  ld    a,(nxrow)
        inc   a
        ld    b,a
        ld    a,(nxwb)
        cp    b
        jr    c,nx_scr         ; se sale de la ventana: hay que desplazar
        ld    a,b
        ld    (nxrow),a
        ret
nx_scr: ld    a,(nxwb)
        ld    (nxrow),a
        jp    nxscroll

nx_bs:  ld    a,(nxcol)
        ld    b,a
        ld    a,(nxwl)
        cp    b
        ret   nc               ; ya esta en el margen izquierdo
        dec   b
        ld    a,b
        ld    (nxcol),a
        ret

; ---------------------------------------------------------------------------
; nxglyph: A = codigo -> HL = matriz de 8 bytes.
;   32..127  -> indices 0..95 de la tabla
;   224..239 -> indices 96..111 (acentos)
; ---------------------------------------------------------------------------
nxglyph:
        cp    224
        jr    nc,nxg_acc
        cp    128
        jr    nc,nxg_sp
        sub   32
        jr    nxg_tab
nxg_acc:
        cp    240
        jr    nc,nxg_sp
        sub   128              ; 224 -> 96
        jr    nxg_tab
nxg_sp: xor   a                ; desconocido -> espacio
nxg_tab:
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl
        add   hl,hl
        add   hl,NXFONT        ; Z80N: ADD HL,nn
        ret

; ---------------------------------------------------------------------------
; nxplot: pinta la matriz de HL en (nxrow,nxcol) con paso de 6 pixeles.
; El glifo lleva la tinta en los bits 7..2, o sea que al desplazarlo n bits a la
; derecha ocupa 6 pixeles a partir del pixel n del byte. Como puede caer a
; caballo de dos bytes, se escriben los dos, cada uno con su mascara.
; ---------------------------------------------------------------------------
nxplot:
        ld    (nxtmp),hl       ; guarda la matriz
        ld    a,(nxcol)
        ld    b,a
        add   a,a
        add   a,b
        add   a,a              ; X = col*6   (41*6 = 246, cabe en un byte)
        ld    e,a
        and   7
        ld    (nxsh),a
        add   a,a              ; *2: la tabla lleva dos bytes por entrada
        ld    c,a
        ld    b,0
        ld    hl,NXMASK
        add   hl,bc
        ld    a,(hl)
        ld    (nxmh),a
        inc   hl
        ld    a,(hl)
        ld    (nxml),a
        ld    a,(nxrow)
        add   a,a
        add   a,a
        add   a,a              ; Y = fila*8
        ld    d,a
        pixelad                ; Z80N: HL = direccion de pantalla de (D,E)
        ld    a,8
        ld    (nxfil),a
        ld    de,(nxtmp)       ; DE = matriz
nxp_l:  ld    a,(de)
        inc   de
        ld    c,0
        ld    b,a
        ld    a,(nxsh)
        or    a
        jr    z,nxp_ya
nxp_sh: srl   b                ; desplaza el glifo a su sitio; lo que sale
        rr    c                ; por la derecha cae en C (segundo byte)
        dec   a
        jr    nz,nxp_sh
nxp_ya: ld    a,(nxmh)
        and   (hl)
        or    b
        ld    (hl),a
        inc   l
        ld    a,(nxml)
        and   (hl)
        or    c
        ld    (hl),a
        dec   l
        pixeldn                ; Z80N: siguiente linea de pixeles
        ld    a,(nxfil)
        dec   a
        ld    (nxfil),a
        jr    nz,nxp_l
        ld    a,(nxrow)        ; atributo: &5800 + fila*32 + X/8
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl
        add   hl,hl
        add   hl,hl
        add   hl,hl
        ld    a,(nxcol)
        ld    b,a
        add   a,a
        add   a,b
        add   a,a
        srl   a
        srl   a
        srl   a                ; X/8
        add   hl,a             ; Z80N
        add   hl,&5800         ; Z80N
        ld    a,(nxattr)
        ld    (hl),a
        ld    a,(nxsh)
        cp    3
        ret   c                ; el glifo cabe entero en una celda de atributo
        inc   hl
        ld    a,(nxattr)
        ld    (hl),a
        ret
nxtmp:  defw 0

; mascaras AND por desplazamiento (byte alto, byte bajo): dejan a cero los 6
; pixeles que va a ocupar el glifo y conservan los vecinos.
NXMASK: defb &03,&FF
        defb &81,&FF
        defb &C0,&FF
        defb &E0,&7F
        defb &F0,&3F
        defb &F8,&1F
        defb &FC,&0F
        defb &FE,&07

; ---------------------------------------------------------------------------
; nxcls: borra la pantalla entera con el atributo actual y sube el cursor al
; margen de la ventana.
; ---------------------------------------------------------------------------
nxcls:
        ld    hl,&4000
        ld    de,&4001
        ld    bc,6143
        ld    (hl),0
        ldir
        ld    a,(nxattr)
        ld    hl,&5800
        ld    de,&5801
        ld    bc,767
        ld    (hl),a
        ldir
        ld    a,(nxwt)
        ld    (nxrow),a
        ld    a,(nxwl)
        ld    (nxcol),a
        ret

; ---------------------------------------------------------------------------
; nxscroll: sube una linea de caracteres toda la ventana de texto y deja la
; ultima fila en blanco. Fase 1: desplaza la pantalla completa.
; ---------------------------------------------------------------------------
nxscroll:
        push  af
        push  bc
        push  de
        push  hl
        ld    b,23             ; 23 filas de caracteres que suben
        ld    c,0              ; C = fila destino
nxs_f:  push  bc
        ld    a,c
        call  nxrowadr         ; HL = inicio de la fila destino
        push  hl
        ld    a,c
        inc   a
        call  nxrowadr         ; HL = inicio de la fila origen
        pop   de
        ex    de,hl            ; HL = destino, DE = origen
        push  bc
        ld    b,8              ; 8 lineas de pixeles por fila
nxs_pl: push  bc
        push  hl
        push  de
        ld    bc,32
        ex    de,hl
        ldir                   ; copia 32 bytes de origen a destino
        pop   de
        pop   hl
        inc   h                ; siguiente linea de pixeles (destino)
        inc   d                ; siguiente linea de pixeles (origen)
        pop   bc
        djnz  nxs_pl
        pop   bc
        pop   bc
        inc   c
        djnz  nxs_f
        ; ultima fila a blanco
        ld    a,23
        call  nxrowadr
        ld    b,8
nxs_bl: push  bc
        push  hl
        ld    d,h
        ld    e,l
        inc   de
        ld    bc,31
        ld    (hl),0
        ldir
        pop   hl
        inc   h
        pop   bc
        djnz  nxs_bl
        pop   hl
        pop   de
        pop   bc
        pop   af
        ret

; nxrowadr: A = fila (0..23) -> HL = direccion del primer byte de esa fila
nxrowadr:
        add   a,a
        add   a,a
        add   a,a
        ld    d,a
        ld    e,0
        pixelad                ; Z80N
        ret

; ---------------------------------------------------------------------------
; TXTWIN: H=izquierda L=arriba D=derecha E=abajo (convenio TXT WIN ENABLE).
; El motor pide ventanas de 80 columnas (CPC modo 2); aqui se recortan a 42.
; ---------------------------------------------------------------------------
TXTWIN:
        ld    a,h
        cp    42
        jr    c,nxw_l
        xor   a
nxw_l:  ld    (nxwl),a
        ld    a,l
        cp    24
        jr    c,nxw_t
        xor   a
nxw_t:  ld    (nxwt),a
        ld    a,d
        cp    42
        jr    c,nxw_r
        ld    a,41
nxw_r:  ld    (nxwr),a
        ld    a,e
        cp    24
        jr    c,nxw_b
        ld    a,23
nxw_b:  ld    (nxwb),a
        ld    a,(nxwt)
        ld    (nxrow),a
        ld    a,(nxwl)
        ld    (nxcol),a
        ret

; ---------------------------------------------------------------------------
; SCRINK: A = pluma (0 = papel, 1 = tinta), C = color. Ajusta el atributo.
; ---------------------------------------------------------------------------
SCRINK:
        or    a
        jr    nz,nxi_ink
        ld    a,(nxattr)
        and   &C7
        ld    b,a
        ld    a,c
        and   7
        rlca
        rlca
        rlca
        or    b
        ld    (nxattr),a
        ret
nxi_ink:
        ld    a,(nxattr)
        and   &F8
        ld    b,a
        ld    a,c
        and   7
        or    b
        ld    (nxattr),a
        ret

; SCRBORDER: A = color de borde
SCRBORDER:
        and   7
        out   (254),a
        ret

; SCRMODE: en el CPC cambia de modo y borra. Aqui solo borra.
SCRMODE:
        push  af
        push  bc
        push  de
        push  hl
        call  nxcls
        pop   hl
        pop   de
        pop   bc
        pop   af
        ret

; ---------------------------------------------------------------------------
; SNDREG: A = registro del AY, C = valor.  Puertos 128K/Next.
; ---------------------------------------------------------------------------
SNDREG:
        push  bc
        push  de
        ld    e,c
        ld    bc,&FFFD
        out   (c),a
        ld    bc,&BFFD
        out   (c),e
        pop   de
        pop   bc
        ret

; ---------------------------------------------------------------------------
; KMREAD: lee el teclado SIN bloquear.  CF=1 y A=tecla si hay una nueva.
; KMW:    espera a que haya tecla (bloqueante).
; ---------------------------------------------------------------------------
KMREAD:
        push  bc
        push  de
        push  hl
        call  nxscan
        ld    hl,nxlast
        or    a
        jr    nz,nxk_hay
        ld    (hl),0           ; nada pulsado: rearma el antirrebote
        pop   hl
        pop   de
        pop   bc
        or    a                ; CF=0
        ret
nxk_hay:
        cp    (hl)
        jr    z,nxk_rep
        ld    (hl),a
        pop   hl
        pop   de
        pop   bc
        scf
        ret
nxk_rep:
        pop   hl
        pop   de
        pop   bc
        or    a
        ret

KMW:    call  KMREAD
        jr    nc,KMW
        ret

; nxscan: recorre la matriz; A = tecla pulsada o 0.
nxscan:
        ld    bc,&FEFE
        in    a,(c)
        cpl
        and   1
        ld    (nxcaps),a       ; CAPS SHIFT
        ld    hl,NXKTAB
        ld    de,NXKPORT
        ld    b,8
nxs_row:
        push  bc
        ld    a,(de)
        ld    b,a
        ld    c,&FE
        in    a,(c)
        cpl
        and   &1F
        jr    z,nxs_nada
        ld    c,a
        ld    b,5
nxs_bit:
        srl   c
        jr    c,nxs_hall
        inc   hl
        djnz  nxs_bit
        jr    nxs_sig
nxs_hall:
        ld    a,(hl)
        or    a
        jr    z,nxs_cero       ; modificadora suelta: no cuenta
        cp    48
        jr    nz,nxs_ok
        ld    a,(nxcaps)
        or    a
        ld    a,48
        jr    z,nxs_ok
        ld    a,127            ; CAPS + 0 = borrar
nxs_ok: pop   bc
        ret
nxs_cero:
        pop   bc
        xor   a
        ret
nxs_nada:
        ld    bc,5
        add   hl,bc
nxs_sig:
        pop   bc
        inc   de
        djnz  nxs_row
        xor   a
        ret

NXKPORT: defb &FE,&FD,&FB,&F7,&EF,&DF,&BF,&7F
NXKTAB:
        defb 0,'z','x','c','v'
        defb 'a','s','d','f','g'
        defb 'q','w','e','r','t'
        defb '1','2','3','4','5'
        defb '0','9','8','7','6'
        defb 'p','o','i','u','y'
        defb 13,'l','k','j','h'
        defb ' ',0,'m','n','b'

; ---------------------------------------------------------------------------
; Sin equivalente util en fase 1.
;   CASOPEN/CASDIR/CASCLOSE devuelven CF=0 (no hay fichero) sin tocar A.
;   Los acentos no pasan por TXTMATRIX: NXGLYPH los lee de (faccp).
; ---------------------------------------------------------------------------
CASOPEN:
CASDIR:
CASCLOSE:
        scf
        ccf                    ; CF=0, A intacto
        ret

MCWAIT:
TXTMATRIX:
TXTMTABLE:
KLINIT:
KLADDF:
KLDELF:
MUSINIT:
MUSPLAY:
MUSSTOP:
        ret
'''


def _engine_next():
    """ENGINE_ASM con las rutinas irreproducibles del CPC neutralizadas.
    De momento solo detect128, que sondea los bancos del CPC escribiendo en
    &4000 (que en el Spectrum es la pantalla) por el puerto &7Fxx."""
    src = ge.ENGINE_ASM
    i = src.index(chr(10) + 'detect128:') + 1      # la etiqueta, no el comentario
    j = src.index('ret', src.index('ld    (has128),a', i)) + 3
    nuevo = ('detect128:\n'
             '        xor   a\n'
             '        ld    (has128),a      ; fase 1: sin bancos de imagen\n'
             '        ret')
    return src[:i] + nuevo + src[j:]


def prefijo(org, db_base):
    """Constantes que el motor espera resueltas. A diferencia del CPC, aqui NO
    se declaran TXTO/KMW/... como equ: son etiquetas de PLAT_ASM."""
    L = ['ORIGIN equ &%04X' % org,          # el motor lleva dentro 'org ORIGIN'
         'DBB equ &%04X' % db_base,
         'MTABLE equ &%04X' % MTABLE]
    for n in ('SCANTGO', 'SEXITS', 'SNOUND', 'SSEE', 'STAKE', 'SDROP',
              'SNOTHERE', 'SNOTCARR', 'SINVEN', 'SEMPTY', 'SNOTAKE', 'SDARK',
              'SSCORE', 'SHEAVY', 'SSCOREP', 'SSCORES',
              'CARRIED', 'NOWHERE', 'WORN', 'CONTAINED'):
        L.append('%s equ %d' % (n, getattr(ge, n)))
    return chr(10).join(L) + chr(10)


def assemble_engine_next(org=ORG, db_base=None, idioma='es'):
    """Ensambla motor + plataforma Next. Devuelve (bytes, tabla_de_simbolos)."""
    if db_base is None:
        db_base = org
    fuente = (prefijo(org, db_base) + _engine_next() + PLAT_ASM + chr(10) +
              _font_asm(idioma) + chr(10))
    return z80asm.assemble(fuente, org=org)


# ===========================================================================
#  Exportacion a .nex
# ===========================================================================
#
# Mapa de memoria (plano, sin paginar):
#
#   &0000-&3FFF   ROM de NextZXOS  (no la usamos, pero la dejamos puesta: asi
#                 la interrupcion IM1 sigue teniendo su gestor en &0038)
#   &4000-&5AFF   pantalla ULA + atributos
#   &5B00-&5FFF   libre
#   &6000-...     motor + capa de plataforma  (ORG)
#   ...           base de datos del juego, a continuacion
#   ...-&FFEF     libre
#   &FFF0         pila
#
# En bancos de 16K del .nex: &4000-&7FFF = banco 5, &8000-&BFFF = banco 2,
# &C000-&FFFF = banco 0. De repartirlo se encarga empaqueta_nex.bin_a_bancos.
#
# No mapeamos RAM sobre la ROM todavia. Se puede (la capa de plataforma no toca
# la ROM para nada), pero implica quedarse sin el gestor de interrupcion de
# &0038, o sea hacerse cargo del modo de interrupcion. Mientras quepa asi, no
# compensa. Cuando haga falta: nextreg &50 y &51 con dos paginas de 8K libres.

SP_NEX = 0xFFF0


def compila(game, ancho=COLS, org=ORG):
    """Ensambla motor+plataforma y construye la base de datos del juego.
    Devuelve (codigo, base_de_datos, simbolos, spec, dir_db)."""
    import cpc_nativo
    import nativecc as nc
    import spectrum_export as sx

    c = sx.recolecta(game)
    sysm, _sal = cpc_nativo._sys_msgs_y_salidas(game.get('metadata') or {})
    while len(sysm) < ge.NSYS:
        sysm.append('')
    spec, _ = nc.compile_game(c, sysm[:ge.NSYS], width=ancho)

    idioma = str((game.get('metadata') or {}).get('language', '') or 'es')
    code, sym = assemble_engine_next(org=org, db_base=org, idioma=idioma)
    dbaddr = org + len(code)
    code, sym = assemble_engine_next(org=org, db_base=dbaddr, idioma=idioma)
    db, _ = ge.build_game_db(
        spec['messages'], spec['locations'], spec['vocab'], spec['objects'],
        spec['responses'], spec['startloc'], spec['sysverbs'], spec['width'],
        load=dbaddr, proc_before=spec['proc_before'], proc_after=spec['proc_after'],
        proc_onstart=spec['proc_onstart'], hdrbuf=0, imgbuf=0,
        loc_slot=bytes([255] * len(spec['locations'])), vall=spec['vall'],
        font_acc=spec['font_acc'], timers=spec['timers'],
        llevarmax=spec['llevarmax'])
    return code, db, sym, spec, dbaddr


def export_nex(game, salida, ancho=COLS, org=ORG, borde=0):
    """Compila el juego al motor nativo y lo empaqueta en un .nex arrancable.
    Sin zxbc, sin Boriel, sin NextBuild: todo en Python."""
    import empaqueta_nex

    code, db, sym, spec, dbaddr = compila(game, ancho=ancho, org=org)
    plano = bytes(code) + bytes(db)
    fin = org + len(plano)
    if fin > SP_NEX - 256:
        raise ValueError(
            'no cabe en el mapa plano: motor+datos llegan a &%04X y la pila esta '
            'en &%04X. Hacen falta bancos para el texto.' % (fin, SP_NEX))

    bancos = {}
    for i, b in enumerate(plano):
        a = org + i
        slot = a & 0xC000
        bk = {0x4000: 5, 0x8000: 2, 0xC000: 0}[slot]
        bancos.setdefault(bk, bytearray(16384))
        bancos[bk][a - slot] = b
    bancos = {k: bytes(v) for k, v in bancos.items()}

    empaqueta_nex.build_nex(salida, bancos, pc=sym['start'], sp=SP_NEX,
                            border=borde)
    return {'codigo': len(code), 'datos': len(db), 'total': len(plano),
            'org': org, 'fin': fin, 'pc': sym['start'], 'sp': SP_NEX,
            'bancos': sorted(bancos), 'simbolos': sym,
            'localizaciones': len(spec['locations']),
            'objetos': len(spec['objects'])}


def carga_nex(path):
    """Reconstruye el mapa de 64K de un .nex como lo hace NextZXOS.
    Devuelve (memoria, pc, sp, bancos_presentes). Sirve para verificar el
    empaquetado sin emulador."""
    import struct
    datos = open(path, 'rb').read()
    if datos[:4] != b'Next':
        raise ValueError('no es un .nex')
    sp = struct.unpack_from('<H', datos, 12)[0]
    pc = struct.unpack_from('<H', datos, 14)[0]
    presentes = [b for b in range(112) if datos[18 + b]]
    orden = [b for b in ([5, 2, 0, 1, 3, 4] + list(range(6, 112))) if b in presentes]
    mem = bytearray(65536)
    ranura = {5: 0x4000, 2: 0x8000, 0: 0xC000}
    off = 512
    for b in orden:
        trozo = datos[off:off + 16384]
        off += 16384
        if b in ranura:
            mem[ranura[b]:ranura[b] + 16384] = trozo
    return mem, pc, sp, presentes


def main():
    import argparse
    import yaml
    ap = argparse.ArgumentParser(
        description='Compila un juego de Scriba a .nex con el motor nativo Z80.')
    ap.add_argument('yaml')
    ap.add_argument('nex', nargs='?')
    ap.add_argument('--ancho', type=int, default=COLS)
    ap.add_argument('--org', default=hex(ORG))
    a = ap.parse_args()
    game = yaml.safe_load(open(a.yaml, encoding='utf-8'))
    salida = a.nex or (a.yaml.rsplit('.', 1)[0] + '.nex')
    info = export_nex(game, salida, ancho=a.ancho, org=int(a.org, 0))
    print('NEX: %s' % salida)
    print('  motor+plataforma : %6d bytes' % info['codigo'])
    print('  base de datos    : %6d bytes' % info['datos'])
    print('  total            : %6d bytes  (&%04X-&%04X)'
          % (info['total'], info['org'], info['fin']))
    print('  bancos           : %s   PC=&%04X  SP=&%04X'
          % (info['bancos'], info['pc'], info['sp']))
    print('  %d localizaciones, %d objetos'
          % (info['localizaciones'], info['objetos']))


if __name__ == '__main__':
    main()
