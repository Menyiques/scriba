#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cpcnative.py — Motor nativo Z80 para CPC (modelo PAW/DAAD) y el compilador que
genera la base de datos del juego. En construccion por fases:

  Fase 1-2 (esto): formato de la seccion de texto + nucleo de texto del motor
                   (expandir mensaje comprimido BPE + imprimir con word-wrap).

El motor se escribe en ensamblador (z80asm) y se verifica en el simulador
(z80.py) interceptando el firmware. Luego se ensambla a bytes fijos que van
dentro de Scriba: el usuario nunca necesita herramientas externas.

Mapa de memoria (provisional, se fija en la fase de integracion CPC):
  &4000  codigo del motor
  &8000  base de datos del juego
  &C000  pantalla
  &BB5A  TXT OUTPUT (firmware)
"""

import txtpack

# direcciones provisionales
ENGINE_ORG = 0x4000
DB_BASE = 0x8000
TXT_OUTPUT = 0xBB5A

# ---------------------------------------------------------------------------
# Formato de la base de datos (seccion de texto, fase 1):
#   Cabecera (8 bytes):
#     +0  dictidx  (word)  direccion de la tabla indice del diccionario
#     +2  msgidx   (word)  direccion de la tabla indice de mensajes
#     +4  width    (byte)  ancho de linea para el word-wrap
#     +5  ntok     (byte)  numero de tokens del diccionario (128..128+ntok-1)
#     +6  nmsg     (word)  numero de mensajes
#   dictidx: ntok words -> direccion de la cadena expandida de cada token
#   dict data: por token  [chars...][0]
#   msgidx:  nmsg words -> direccion de cada mensaje comprimido
#   msg data: por mensaje [bytes comprimidos...][0]   (literales 32-127, tokens 128+)
# ---------------------------------------------------------------------------

def build_text_db(messages, load=DB_BASE, width=40):
    """Compila una lista de mensajes a la seccion de texto de la base de datos.
    Devuelve (db_bytes, info)."""
    dic = txtpack.build_dict(''.join(messages), 128)
    exps = txtpack.expansions(dic)              # cadenas de cada token (solo literales)
    ntok = len(exps)
    toks = [txtpack.tokenize(m, dic) for m in messages]
    nmsg = len(messages)

    hdr = 8
    dictidx_addr = load + hdr
    dictdata_addr = dictidx_addr + ntok * 2
    dict_ptrs, dictdata = [], bytearray()
    for s in exps:
        dict_ptrs.append(dictdata_addr + len(dictdata))
        dictdata += s.encode('latin-1') + b'\x00'
    msgidx_addr = dictdata_addr + len(dictdata)
    msgdata_addr = msgidx_addr + nmsg * 2
    msg_ptrs, msgdata = [], bytearray()
    for t in toks:
        msg_ptrs.append(msgdata_addr + len(msgdata))
        msgdata += bytes(t) + b'\x00'

    out = bytearray()

    def w16(v):
        out.append(v & 0xFF); out.append((v >> 8) & 0xFF)

    w16(dictidx_addr); w16(msgidx_addr)
    out.append(width & 0xFF); out.append(ntok & 0xFF); w16(nmsg)
    for p in dict_ptrs:
        w16(p)
    out += dictdata
    for p in msg_ptrs:
        w16(p)
    out += msgdata
    return bytes(out), dict(load=load, ntok=ntok, nmsg=nmsg, size=len(out),
                            dictidx=dictidx_addr, msgidx=msgidx_addr)


# ---------------------------------------------------------------------------
# Motor — nucleo de texto (Fase 2)
# ---------------------------------------------------------------------------
ENGINE_ASM = r'''
        org   ENGINE_ORG

TXT     equ   TXT_OUTPUT
DBBASE  equ   DB_BASE

; ---- punto de entrada de prueba: imprime el mensaje cuyo indice esta en testidx
start:  call  init
        ld    a,(testidx)
        call  print_msg
        ret

; ---- init: lee los punteros de la cabecera de la base de datos
init:   ld    hl,(DBBASE+0)
        ld    (dictidx),hl
        ld    hl,(DBBASE+2)
        ld    (msgidx),hl
        ld    a,(DBBASE+4)
        ld    (width),a
        ret

; ---- print_msg: A = indice de mensaje. Expande y lo imprime con word-wrap.
print_msg:
        call  expand_msg          ; -> HL=BUF, BC=longitud
        xor   a
        ld    (col),a
        call  wrap_print
        ret

; ---- expand_msg: A=indice -> expande a BUF; devuelve HL=BUF, BC=longitud
expand_msg:
        ld    l,a
        ld    h,0
        add   hl,hl               ; A*2
        ld    de,(msgidx)
        add   hl,de
        ld    a,(hl)
        inc   hl
        ld    h,(hl)
        ld    l,a                 ; HL = direccion del mensaje comprimido
        ld    de,BUF
em_loop:
        ld    a,(hl)
        inc   hl
        or    a
        jr    z,em_done
        bit   7,a
        jr    z,em_lit
        ; --- token: copiar su cadena expandida ---
        push  hl
        sub   128
        ld    l,a
        ld    h,0
        add   hl,hl
        ld    bc,(dictidx)
        add   hl,bc
        ld    a,(hl)
        inc   hl
        ld    h,(hl)
        ld    l,a                 ; HL = cadena del token
em_tok: ld    a,(hl)
        inc   hl
        or    a
        jr    z,em_tokend
        ld    (de),a
        inc   de
        jr    em_tok
em_tokend:
        pop   hl
        jr    em_loop
em_lit: ld    (de),a
        inc   de
        jr    em_loop
em_done:
        ld    hl,BUF
        ld    a,e
        sub   l
        ld    c,a
        ld    a,d
        sbc   h
        ld    b,a                 ; BC = DE - BUF
        ld    hl,BUF
        ret

; ---- wrap_print: HL=texto, BC=longitud. Imprime con word-wrap (col,width).
wrap_print:
wp_main:
        ld    a,b
        or    c
        ret   z                   ; BC==0 -> fin
        ld    a,(hl)
        cp    32
        jp    z,wp_space
        ; --- medir longitud de la palabra en D ---
        push  hl
        push  bc
        ld    d,0
wp_meas:
        ld    a,b
        or    c
        jr    z,wp_md
        ld    a,(hl)
        cp    32
        jr    z,wp_md
        inc   d
        inc   hl
        dec   bc
        jr    wp_meas
wp_md:  pop   bc
        pop   hl
        ; --- cabe col+D en width? ---
        ld    a,(col)
        add   a,d
        ld    e,a
        ld    a,(width)
        cp    e
        jr    nc,wp_nonl          ; width >= col+D -> cabe
        call  newline
wp_nonl:
        ; --- imprimir D caracteres ---
wp_pw:  ld    a,d
        or    a
        jp    z,wp_main
        ld    a,(hl)
        call  char_raw
        inc   hl
        dec   bc
        dec   d
        jr    wp_pw

wp_space:
        ld    a,(col)
        ld    e,a
        ld    a,(width)
        cp    e
        jr    z,wp_spnl           ; col==width -> newline
        jr    c,wp_spnl           ; col>width  -> newline
        ld    a,32
        call  char_raw
        inc   hl
        dec   bc
        jp    wp_main
wp_spnl:
        call  newline
        inc   hl
        dec   bc
        jp    wp_main

; ---- char_raw: imprime A, col++ (preserva HL/DE/BC)
char_raw:
        push  hl
        push  de
        push  bc
        call  TXT
        ld    a,(col)
        inc   a
        ld    (col),a
        pop   bc
        pop   de
        pop   hl
        ret

; ---- newline: CR+LF, col=0 (preserva HL/DE/BC)
newline:
        push  hl
        push  de
        push  bc
        ld    a,13
        call  TXT
        ld    a,10
        call  TXT
        xor   a
        ld    (col),a
        pop   bc
        pop   de
        pop   hl
        ret

; ---- variables del motor ----
dictidx: defw 0
msgidx:  defw 0
width:   defb 40
col:     defb 0
testidx: defb 0
BUF:     defs 1024
'''


def assemble_engine(org=ENGINE_ORG, db_base=DB_BASE, txt=TXT_OUTPUT):
    import z80asm
    src = (ENGINE_ASM
           .replace('ENGINE_ORG', '&%04X' % org)
           .replace('TXT_OUTPUT', '&%04X' % txt)
           .replace('DB_BASE', '&%04X' % db_base))
    return z80asm.assemble(src, org=org)
