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

import cpc_font
import game_engine as ge
import z80asm

ORG = 0x6000        # motor: por encima de la pantalla ULA (&4000-&5AFF)
MTABLE = 0x5B00     # tabla de matrices de usuario (RAM libre bajo el motor)
PANT = 0x4000       # pantalla ULA
ATTR = 0x5800       # atributos
COLS = 32           # columnas de texto (fase 1: fuente 8x8)
FILAS = 24


# ---------------------------------------------------------------------------
# Fuente: 32..127 desde cpc_font.ASCII (8x8). Los acentos (codigos 224..239) NO
# van aqui: el motor los trae en la propia base de datos, en (faccp), y NXGLYPH
# los lee de alli. Asi el juego manda su propia tipografia acentuada.
# ---------------------------------------------------------------------------
def _font_asm():
    datos = bytearray(cpc_font.ASCII)
    if len(datos) < 96 * 8:
        datos += bytes(96 * 8 - len(datos))
    datos = datos[:96 * 8]
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
nxwr:    defb 31           ; ventana: derecha
nxwb:    defb 23           ; ventana: abajo
nxattr:  defb 7            ; atributo actual (tinta 7, papel 0)
nxlast:  defb 0            ; ultima tecla devuelta (antirrebote)
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
; nxglyph: A = codigo -> HL = direccion de la matriz de 8 bytes.
;   32..127  -> NXFONT
;   224..239 -> acentos del juego, en (faccp) dentro de la base de datos
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
        sub   224
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl
        add   hl,hl
        ld    de,(faccp)
        ld    a,d
        or    e
        jr    z,nxg_sp
        add   hl,de
        ret
nxg_tab:
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl
        add   hl,hl
        ld    de,NXFONT
        add   hl,de
        ret
nxg_sp: ld    hl,NXFONT       ; desconocido -> espacio
        ret

; ---------------------------------------------------------------------------
; nxplot: vuelca la matriz de HL en (nxrow,nxcol) y pone el atributo.
; Distribucion de la pantalla del Spectrum:
;   pixel:  alto = &40 + (fila AND &18) + linea ;  bajo = (fila AND 7)*32 + col
;   attr :  &5800 + fila*32 + col
; ---------------------------------------------------------------------------
nxplot:
        ld    (nxtmp),hl       ; guarda la matriz
        ld    a,(nxrow)
        add   a,a
        add   a,a
        add   a,a
        ld    d,a              ; Y en pixeles = fila*8
        ld    a,(nxcol)
        add   a,a
        add   a,a
        add   a,a
        ld    e,a              ; X en pixeles = col*8
        pixelad                ; Z80N: HL = direccion de pantalla de (D,E)
        ex    de,hl            ; DE = pantalla
        ld    hl,(nxtmp)       ; HL = matriz
        ld    b,8
nxp_l:  ld    a,(hl)
        ld    (de),a
        inc   hl
        inc   d                ; dentro de una fila de caracteres basta INC D
        djnz  nxp_l
        ld    a,(nxrow)        ; atributo: &5800 + fila*32 + col
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl
        add   hl,hl
        add   hl,hl
        add   hl,hl
        ld    a,(nxcol)
        add   hl,a             ; Z80N: ADD HL,A
        add   hl,&5800         ; Z80N: ADD HL,nn
        ld    a,(nxattr)
        ld    (hl),a
        ret
nxtmp:  defw 0

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
; El motor pide ventanas de 80 columnas (CPC modo 2); aqui se recortan.
; ---------------------------------------------------------------------------
TXTWIN:
        ld    a,h
        cp    32
        jr    c,nxw_l
        xor   a
nxw_l:  ld    (nxwl),a
        ld    a,l
        cp    24
        jr    c,nxw_t
        xor   a
nxw_t:  ld    (nxwt),a
        ld    a,d
        cp    32
        jr    c,nxw_r
        ld    a,31
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


def assemble_engine_next(org=ORG, db_base=None):
    """Ensambla motor + plataforma Next. Devuelve (bytes, tabla_de_simbolos)."""
    if db_base is None:
        db_base = org
    fuente = prefijo(org, db_base) + _engine_next() + PLAT_ASM + chr(10) + _font_asm() + chr(10)
    return z80asm.assemble(fuente, org=org)
