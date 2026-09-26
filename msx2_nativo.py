# -*- coding: utf-8 -*-
"""
msx2_nativo.py - Capa de plataforma MSX2 para el motor nativo Z80.

El mismo motor (game_engine.ENGINE_ASM) y la misma base de datos que mueven el
Spectrum, el Next y el CPC; aqui solo se resuelven los ~20 simbolos de
plataforma, como hace next_nativo. La salida es un cartucho MegaROM ASCII16
(.rom), que arranca solo en cualquier MSX2 y en openMSX / WebMSX / blueMSX.

MAPA DE MEMORIA
    pagina 0  &0000-&3FFF   BIOS. Se queda puesta: la interrupcion IM1 de
                            &0038, el teclado (CHSNS/CHGET) y KILBUF.
    pagina 1  &4000-&7FFF   el cartucho. En el banco 0 va la cabecera "AB" y
                            el cargador; una vez arrancado el juego, esta
                            pagina es la VENTANA DE PAGINACION, como &C000 en
                            el 128K y el Next: por ella se leen, cada uno de su
                            banco de 16K, el texto (TXTPAGE, por mensaje), los
                            FX, la musica y las imagenes.
    pagina 2  &8000-&BFFF   RAM (la del mismo slot que la pagina 3)
    pagina 3  &C000-&FFFF   RAM; por encima de HIMEM (&F380 sin disquetera),
                            las variables del sistema, que no se tocan.

    &8000-....              motor + capa de plataforma + base de datos plana
                            (todo lo que no es texto). Es la "imagen RAM": el
                            cargador la copia desde la ROM al arrancar, porque
                            el motor lleva sus variables mezcladas con el
                            codigo y no puede correr desde ROM.
    ....-MSXSP              la pila (PILA_MIN bytes por encima de la imagen)

LA ROM (ASCII16: bancos de 16K; el registro de la pagina 1 esta en &6000)
    banco 0                 cabecera, cargador y el trocito que copia la imagen
    bancos 1..              texto del juego, FX y musica (ids = n de banco)
    detras                  paletas e imagenes de sala, portada
    detras                  la imagen RAM (motor + DB), en bancos seguidos
    (modo prueba)           el guion de la bateria, en los ultimos bancos

PANTALLA: SCREEN 5 (256x212, 16 colores de una paleta de 512), programada
directamente en el VDP V9938. La misma fuente de 6 pixeles del Spectrum, 42
columnas x 24 filas; cada glifo son exactamente 3 bytes por linea (2 pixeles
por byte), asi que no hay mascaras ni desplazamientos. El scroll y el borrado
los hace el VDP por hardware (YMMM y HMMV). La franja de imagen de sala son las
filas 0..7 (256x64), igual que en el Spectrum y el Next.

    Paleta: 0..7 son los ocho colores del Spectrum, fijos, que es con lo que
    trabajan INK/PAPER/BORDER. 8..15 son libres: cada imagen de sala trae los
    suyos, y se reduce a esos 8 mas los 8 fijos. La portada usa los 16.

TECLADO por la BIOS (CHSNS/CHGET): vale para el teclado espanol (la Ñ) y los
de cualquier otro pais sin tablas propias. SONIDO por el PSG (AY-3-8910), el
mismo chip que el del 128K: solo cambian los puertos (&A0/&A1) y que el bit 7
del registro 7 tiene que quedarse a 1 y el 6 a 0 (son las direcciones de los
puertos de E/S del PSG, donde estan los joysticks).

Uso:
    python msx2_nativo.py juego.yaml [salida.rom]
"""
import os

import game_engine as ge
import next_nativo as nx
import spectrum48_nativo as s48
import z80asm

ORG = 0x8000            # la imagen RAM empieza en la pagina 2
VENTANA = 0x4000        # la pagina 1: ventana de paginacion
BANCO = 16384
HIMEM_SIN_DISCO = 0xF380
PILA_MIN = 256          # la pila, por encima de la imagen (la BIOS mete la
                        # interrupcion encima de lo del motor)
COLS = nx.COLS          # 42
FILA_TEXTO = nx.FILA_TEXTO   # 8: la imagen ocupa las filas 0..7
YOFF = 10               # 24 filas x 8 = 192 lineas, centradas en las 212
XOFFB = 1               # 42 x 6 = 252 pixeles: 2 de margen a cada lado
MAX_BANCOS = 256        # ASCII16 de 4 MB; los registros son de 8 bits
ROM_MIN = 128 * 1024    # por debajo, los detectores de mapper dudan

# Paleta fija (3 bits por componente): los colores del Spectrum. El brillo
# normal del Spectrum es ~84%, o sea 6 de 7.
PALETA_FIJA = [(0, 0, 0), (0, 0, 6), (6, 0, 0), (6, 0, 6),
               (0, 6, 0), (0, 6, 6), (6, 6, 0), (6, 6, 6)]
PALETA_BRILLO = [(0, 0, 0), (0, 0, 7), (7, 0, 0), (7, 0, 7),
                 (0, 7, 0), (0, 7, 7), (7, 7, 0), (7, 7, 7)]


def _pal_bytes(rgbs):
    """[(r,g,b) de 0..7] -> los dos bytes por color que espera el puerto &9A."""
    out = bytearray()
    for r, g, b in rgbs:
        out += bytes([((r & 7) << 4) | (b & 7), g & 7])
    return bytes(out)


# ---------------------------------------------------------------------------
#  El cargador: banco 0 de la ROM
# ---------------------------------------------------------------------------
# Lo llama la BIOS al arrancar (la direccion INIT de la cabecera), con la
# pagina 1 en el cartucho y la pila en la pagina 3. Comprueba que la maquina
# es un MSX2 y que hay RAM de sobra por debajo de HIMEM, pone en la pagina 2 la
# RAM del mismo slot que la pagina 3 (la receta de siempre: en un MSX de 64K es
# toda la RAM, y en uno con mapper es un segmento del mismo mapper), copia a la
# RAM el trocito que copia (el cargador vive en la pagina 1 y va a paginar la
# pagina 1) y salta ahi.
CARGADOR_ASM = r'''
        org   &4000
        defb  "AB"
        defw  msxboot
        defw  0,0,0
        defs  6
; Firma de mapper en &4010 (fichero 0x0010): WebMSX no adivina el mapper de una
; ROM que no conoce (escoge ASCII8, que va antes en su lista, y el juego se
; reinicia al copiar la imagen); con "ASCII16X" escoge ASCII16-X, que con
; bancos de 8 bits es ASCII16 (registros en &6000 y &7000).
        defb  "ASCII16X"
msxboot:
        ld    a,(&002D)        ; MSXVER: 0 = MSX1
        or    a
        ld    hl,ldmsx1
        jr    z,ld_err
        ld    hl,(&FC4A)       ; HIMEM: por encima, lo del sistema
        ld    de,MSXTOP
        or    a
        sbc   hl,de
        ld    hl,ldmem
        jr    c,ld_err
        di
        in    a,(&A8)          ; slot primario de la pagina 3 -> bits 1-0
        rlca
        rlca
        and   3
        ld    c,a
        ld    b,0
        ld    hl,&FCC1         ; EXPTBL: bit 7 = slot expandido
        add   hl,bc
        ld    a,(hl)
        and   &80
        jr    z,ld_prim
        or    c
        ld    c,a
        inc   hl
        inc   hl
        inc   hl
        inc   hl               ; SLTTBL: copia del registro de subslot
        ld    a,(hl)
        rrca
        rrca
        rrca
        rrca
        and   &0C              ; subslot de la pagina 3 -> bits 3-2
        or    c
        ld    c,a
ld_prim:
        ld    a,c
        ld    h,&80
        call  &0024            ; ENASLT: la pagina 2, a esa RAM
        di
        ld    a,1
        ld    (&7000),a        ; (registro de la pagina 2: no se usa, pero
                               ; los detectores de ASCII16 lo buscan)
        ld    hl,ldstub
        ld    de,MSXSTUB
        ld    bc,LDSTUBN
        ldir
        jp    MSXSTUB
; mensaje y a dormir, con la BIOS (el juego no ha tocado la pantalla)
ld_err: ld    a,(hl)
        or    a
        jr    z,ld_fin
        call  &00A2            ; CHPUT
        inc   hl
        jr    ld_err
ld_fin: ei
        halt
        jr    ld_fin
ldmsx1: defb  "Este juego necesita un MSX2.",13,10,0
ldmem:  defb  "No hay memoria libre bastante.",13,10
        defb  "Arranca sin disquetera (manten",13,10
        defb  "pulsado CTRL, o SHIFT) y prueba",13,10
        defb  "otra vez.",13,10,0
ldstub:
'''

# El trocito que copia la imagen RAM desde sus bancos. Se ensambla aparte, en
# su direccion final (justo detras de la imagen, en el hueco de la pila, que
# todavia no se usa), y el cargador lo lleva dentro como datos.
STUB_ASM = r'''
        org   MSXSTUB
        ld    hl,IMGLEN
        ld    (stlen),hl
        ld    de,ORIGIN
        ld    a,IMGBANK
st_l:   ld    (&6000),a
        ld    (stbk),a
        ld    hl,(stlen)
        ld    bc,&4000
        or    a
        sbc   hl,bc
        jr    nc,st_ll         ; queda un banco entero o mas
        add   hl,bc
        ld    b,h
        ld    c,l              ; BC = lo que queda
        ld    hl,0
st_ll:  ld    (stlen),hl
        ld    a,b
        or    c
        jr    z,st_fin
        ld    hl,&4000
        ldir
        ld    a,(stbk)
        inc   a
        jr    st_l
st_fin: ld    sp,MSXSP
        jp    MSXSTART
stlen:  defw  0
stbk:   defb  0
'''


# ---------------------------------------------------------------------------
#  La capa de plataforma: PLAT_ASM del Next con sus rutinas de maquina
#  cambiadas por las del MSX2
# ---------------------------------------------------------------------------
NXGLYPH_MSX = r'''nxglyph:
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
        push  de
        ld    de,NXFONT
        add   hl,de
        pop   de
        ret

'''

NXPLOT_MSX = r'''; ---------------------------------------------------------------------------
; nxplot: pinta la matriz de HL en (nxrow,nxcol). SCREEN 5 son 4 bits por
; pixel y el glifo mide 6: tres bytes por linea, siempre alineados. Cada par de
; pixeles del glifo (bits 7-6, 5-4, 3-2) escoge uno de los cuatro bytes de
; msxpair, que mkpair rellena con la tinta y el papel de ahora.
; ---------------------------------------------------------------------------
nxplot:
        push  hl
        call  mkpair
        ld    a,(nxrow)
        add   a,a
        add   a,a
        add   a,a
        add   a,YOFF           ; linea de pixeles (<= 194)
        ld    l,0
        srl   a
        rr    l
        ld    h,a              ; HL = linea * 128
        ld    a,(nxcol)
        ld    b,a
        add   a,a
        add   a,b
        add   a,XOFFB          ; byte = columna * 3 + margen (<= 124)
        or    l
        ld    l,a
        ex    de,hl            ; DE = direccion en la VRAM
        pop   hl               ; HL = matriz
        ld    b,8
nxp_l:  push  bc
        ld    c,(hl)
        inc   hl
        ex    de,hl
        di
        call  vwaddr
        ex    de,hl
        ld    a,c
        rlca
        rlca
        call  pairout
        ld    a,c
        rrca
        rrca
        rrca
        rrca
        call  pairout
        ld    a,c
        rrca
        rrca
        call  pairout
        ei
        ex    de,hl
        ld    bc,128
        add   hl,bc            ; la linea de abajo
        ex    de,hl
        pop   bc
        djnz  nxp_l
        ret

; pairout: A (bits 1-0) = par de pixeles -> su byte al puerto de datos del VDP
pairout:
        push  hl
        and   3
        ld    hl,msxpair
        add   a,l
        ld    l,a
        jr    nc,po_nc
        inc   h
po_nc:  ld    a,(hl)
        out   (&98),a
        pop   hl
        ret

; mkpair: los cuatro bytes de color para papel/tinta (INVERSE los cambia)
mkpair:
        push  bc
        push  de
        push  hl
        ld    a,(nxattr)
        ld    b,a
        and   7
        ld    d,a              ; D = tinta
        ld    a,b
        rrca
        rrca
        rrca
        and   7
        ld    e,a              ; E = papel
        ld    a,(nxinv)
        or    a
        jr    z,mk_ok
        ld    a,d
        ld    d,e
        ld    e,a
mk_ok:  ld    hl,msxpair
        ld    a,e
        rlca
        rlca
        rlca
        rlca
        ld    b,a              ; B = papel en el nibble alto
        or    e
        ld    (hl),a           ; papel, papel
        inc   hl
        ld    a,b
        or    d
        ld    (hl),a           ; papel, tinta
        inc   hl
        ld    a,d
        rlca
        rlca
        rlca
        rlca
        ld    c,a              ; C = tinta en el nibble alto
        or    e
        ld    (hl),a           ; tinta, papel
        inc   hl
        ld    a,c
        or    d
        ld    (hl),a           ; tinta, tinta
        pop   hl
        pop   de
        pop   bc
        ret
msxpair: defb 0,0,0,0

; vwaddr: HL = direccion de la VRAM (0..&7FFF, la pagina 0 de SCREEN 5) ->
; el VDP, listo para escribir ahi. Con las interrupciones cortadas: la BIOS
; lee el registro de estado en cada barrido y eso rompe la pareja de bytes.
vwaddr:
        ld    a,h
        rlca
        rlca
        and   3
        out   (&99),a
        ld    a,14+128         ; R#14: bits 16-14 de la direccion
        out   (&99),a
        ld    a,l
        out   (&99),a
        ld    a,h
        and   &3F
        or    &40              ; escritura
        out   (&99),a
        ret

'''

NXCLS_MSX = r'''; ---------------------------------------------------------------------------
; nxcls: borra con el papel la ventana de texto (de la fila nxwt hasta abajo, a
; todo lo ancho) y sube el cursor. Si la ventana empieza arriba del todo, se
; borran tambien los margenes de arriba y abajo. Lo que haya por encima de
; nxwt -- la imagen de la sala -- se queda.
; ---------------------------------------------------------------------------
nxcls:
        call  mkpair
        ld    a,(nxwt)
        or    a
        jr    z,nxc_todo
        add   a,a
        add   a,a
        add   a,a
        add   a,YOFF
        jr    nxc_y
nxc_todo:
        xor   a
nxc_y:  ld    l,a
        ld    h,0
        ld    (vcb+6),hl       ; DY
        ld    a,212
        sub   l
        ld    l,a
        ld    (vcb+10),hl      ; NY: hasta la ultima linea
        call  vchmmv
        ld    a,(nxwt)
        ld    (nxrow),a
        ld    a,(nxwl)
        ld    (nxcol),a
        xor   a
        ld    (nxpcnt),a       ; pantalla limpia: la cuenta de pagina, a cero
        ret

; msxclsall: la pantalla entera, con el papel de ahora
msxclsall:
        call  mkpair
        ld    hl,0
        ld    (vcb+6),hl
        ld    hl,212
        ld    (vcb+10),hl
        jp    vchmmv

; vchmmv: rellena con msxpair[0] (papel,papel) las lineas DY..DY+NY-1 a todo
; lo ancho. DY y NY ya estan en vcb.
vchmmv:
        ld    hl,0
        ld    (vcb+4),hl       ; DX
        ld    hl,256
        ld    (vcb+8),hl       ; NX
        ld    a,(msxpair)
        ld    (vcb+12),a       ; CLR
        xor   a
        ld    (vcb+13),a       ; ARG
        ld    a,&C0            ; HMMV
        ld    (vcb+14),a
        jp    vdpcmd

; vdpcmd: manda los 15 registros de vcb (R#32..R#46) y espera a que acabe.
vdpcmd:
        call  vdpwait
        ld    hl,vcb
        di
        ld    a,32
        out   (&99),a
        ld    a,17+128         ; R#17: escritura indirecta desde R#32
        out   (&99),a
        ld    bc,15*256+&9B
vc_l:   ld    a,(hl)
        out   (c),a
        inc   hl
        djnz  vc_l
        ei
; vdpwait: espera a que el VDP acabe el comando en curso (S#2, bit CE)
vdpwait:
        di
        ld    a,2
        out   (&99),a
        ld    a,15+128
        out   (&99),a
vw_l:   in    a,(&99)
        rrca
        jr    c,vw_l
        xor   a                ; y R#15 de vuelta a S#0, que es el que lee
        out   (&99),a          ; la interrupcion de la BIOS
        ld    a,15+128
        out   (&99),a
        ei
        ret
; SX, SY, DX, DY, NX, NY, CLR, ARG, CMD
vcb:    defw  0,0,0,0,0,0
        defb  0,0,0

'''

NXSCROLL_MSX = r'''; ---------------------------------------------------------------------------
; nxscroll: sube una fila la ventana de texto (de nxwt a nxwb) con un YMMM del
; VDP, y borra la de abajo con un HMMV.
; ---------------------------------------------------------------------------
nxscroll:
        push  af
        push  bc
        push  de
        push  hl
        ld    a,(nxwb)
        ld    b,a
        ld    a,(nxwt)
        ld    c,a
        ld    a,b
        sub   c                ; filas que suben
        jr    z,nxs_fin        ; ventana de una sola fila
        add   a,a
        add   a,a
        add   a,a
        ld    l,a
        ld    h,0
        ld    (vcb+10),hl      ; NY
        ld    a,c
        add   a,a
        add   a,a
        add   a,a
        add   a,YOFF
        ld    l,a
        ld    (vcb+6),hl       ; DY = arriba de la ventana
        add   a,8
        ld    l,a
        ld    (vcb+2),hl       ; SY = una fila mas abajo
        ld    l,h
        ld    (vcb+4),hl       ; DX = 0: YMMM mueve de DX al borde derecho
        xor   a
        ld    (vcb+13),a       ; ARG: hacia abajo y a la derecha
        ld    a,&E0            ; YMMM
        ld    (vcb+14),a
        call  vdpcmd
nxs_fin:
        call  mkpair
        ld    a,(nxwb)
        add   a,a
        add   a,a
        add   a,a
        add   a,YOFF
        ld    l,a
        ld    h,0
        ld    (vcb+6),hl
        ld    l,8
        ld    (vcb+10),hl
        call  vchmmv
        pop   hl
        pop   de
        pop   bc
        pop   af
        ret

'''

SCRBORDER_MSX = r'''SCRBORDER:
        call  nxcolor
        and   7
        push  de
        ld    e,7
        call  vdpset           ; R#7: color del borde
        pop   de
        ret

'''

NXCOLOR_MSX = r'''nxcolor:
        push  hl
        push  de
        cp    27
        jr    c,nxc_ok
        ld    a,26             ; fuera de rango: blanco
nxc_ok: ld    l,a
        ld    h,0
        ld    de,NXCOLT
        add   hl,de
        ld    a,(hl)
        pop   de
        pop   hl
        ret

'''

NXINIT_MSX = r'''; ---------------------------------------------------------------------------
; NXINIT: SCREEN 5 a mano, en el VDP, sin pasar por la BIOS (el CHGMOD del
; MSX2 va a la SUB-ROM y en C-BIOS no esta entero). Se apuntan tambien las
; copias de los registros y SCRMOD, para que la BIOS sepa donde esta.
; ---------------------------------------------------------------------------
NXINIT:
        di
        xor   a
        ld    (&F3DB),a        ; CLIKSW: sin el clic de las teclas
        ld    a,5
        ld    (&FCAF),a        ; SCRMOD
        ld    hl,MSXREGS
mi_r:   ld    a,(hl)
        cp    255
        jr    z,mi_9
        ld    e,a
        inc   hl
        ld    a,(hl)
        inc   hl
        call  vdpset
        jr    mi_r
mi_9:   ld    a,(&FFE8)        ; RG9SAV: se respeta 50/60 Hz (bit NT)
        and   2
        or    &80              ; LN: 212 lineas
        ld    e,9
        call  vdpset
        ld    hl,PALFIJA
        call  msxpal16
        ld    a,NXBORDE
        call  nxcolor
        ld    e,7
        call  vdpset
        ld    a,56             ; papel 7, tinta 0
        ld    (nxattr),a
        call  msxclsall
        ld    a,&60            ; pantalla encendida, interrupcion de barrido
        ld    e,1
        call  vdpset
        ei
        jp    NXL2INIT

; vdpset: A = valor, E = registro. Apunta la copia que guarda la BIOS.
vdpset:
        push  af
        push  hl
        di
        out   (&99),a
        ld    h,a
        ld    a,e
        or    &80
        out   (&99),a
        ld    a,e
        cp    8
        jr    nc,vs_8
        ld    l,e
        ld    a,h
        ld    h,0
        push  de
        ld    de,&F3DF         ; RG0SAV..RG7SAV
        add   hl,de
        pop   de
        ld    (hl),a
        jr    vs_f
vs_8:   cp    24
        jr    nc,vs_f
        ld    l,e
        ld    a,h
        ld    h,0
        push  de
        ld    de,&FFDF         ; RG8SAV = &FFE7 = &FFDF + 8
        add   hl,de
        pop   de
        ld    (hl),a
vs_f:   pop   hl
        pop   af
        ret

; msxvcopy: HL = origen (RAM o ROM), DE = VRAM, BC = bytes
msxvcopy:
        ex    de,hl
        di
        call  vwaddr
        ex    de,hl
mvc_l:  ld    a,(hl)
        out   (&98),a
        inc   hl
        dec   bc
        ld    a,b
        or    c
        jr    nz,mvc_l
        ei
        ret

; msxpal16: HL = 32 bytes -> los 16 colores de la paleta
msxpal16:
        ld    b,32
        ld    c,0
; msxpal: HL = datos, C = primer color, B = bytes (2 por color)
msxpal:
        di
        ld    a,c
        out   (&99),a
        ld    a,16+128         ; R#16: puntero de paleta
        out   (&99),a
mp_l:   ld    a,(hl)
        out   (&9A),a
        inc   hl
        djnz  mp_l
        ei
        ret

; Registros de SCREEN 5 (el 1 va aparte, al final, con la pantalla ya borrada)
MSXREGS:
        defb  1,&20            ; pantalla apagada mientras se prepara
        defb  0,&06            ; G4 = SCREEN 5
        defb  2,&1F            ; tabla de nombres: pagina 0
        defb  5,&EF            ; atributos de sprites en &7600...
        defb  11,&00
        defb  6,&0F            ; ...y patrones en &7800 (apagados de todos modos)
        defb  8,&2A            ; TP (el color 0 es negro de verdad), VR, sin sprites
        defb  14,0
        defb  23,0             ; sin scroll vertical
        defb  255

'''

SNDREG_MSX = r'''; ---------------------------------------------------------------------------
; SNDREG: A = registro del PSG, C = valor. En el registro 7 los bits 7 y 6 son
; la direccion de los puertos de E/S del PSG (joysticks): 7 a 1 (salida) y 6 a
; 0 (entrada), pase lo que pase.
; ---------------------------------------------------------------------------
SNDREG:
        push  af
        push  bc
        cp    7
        jr    nz,sr_ok
        ld    b,a
        ld    a,c
        and   &3F
        or    &80
        ld    c,a
        ld    a,b
sr_ok:  di
        out   (&A0),a
        ld    a,c
        out   (&A1),a
        ei
        pop   bc
        pop   af
        ret

'''

KMREAD_MSX = r'''; ---------------------------------------------------------------------------
; KMREAD: lee el teclado SIN bloquear, por la BIOS.  CF=1 y A=tecla si hay una.
; KMW:    espera a que haya tecla (bloqueante).
; ---------------------------------------------------------------------------
KMREAD:
        push  bc
        push  de
        push  hl
        call  &009C            ; CHSNS: Z = no hay nada en el buffer
        jr    z,km_no
        call  &009F            ; CHGET
        call  kmmap
        or    a
        jr    z,km_no
        pop   hl
        pop   de
        pop   bc
        scf
        ret
km_no:  pop   hl
        pop   de
        pop   bc
        or    a                ; CF=0
        ret

KMW:    call  KMREAD
        jr    nc,KMW
        ret

; kmmap: codigo de la BIOS -> lo que espera el motor. BS y DEL borran (127);
; las letras con tilde, la Ñ y la Ç del juego de caracteres del MSX pasan a su
; letra sin nada, que es como esta el vocabulario.
kmmap:
        cp    8
        jr    z,kmm_del
        cp    127
        jr    z,kmm_del
        cp    128
        ret   c
        cp    166
        jr    nc,kmm_no
        push  hl
        push  de
        sub   128
        ld    e,a
        ld    d,0
        ld    hl,KMACC
        add   hl,de
        ld    a,(hl)
        pop   de
        pop   hl
        ret
kmm_del:
        ld    a,127
        ret
kmm_no: xor   a
        ret
;             128..143: C u e a a a a c e e e i i i A A
KMACC:  defb  'c','u','e','a','a','a','a','c','e','e','e','i','i','i','a','a'
;             144..159: E ae AE o o o u u y O U cent libra yen Pt f
        defb  'e',0,0,'o','o','o','u','u','y','o','u',0,0,0,0,0
;             160..165: a i o u n N
        defb  'a','i','o','u','n','n'

; nxscan: A <> 0 si hay alguna tecla pulsada ahora mismo (matriz, filas 0-8).
; Es para las esperas de la portada, que no deben gastar el buffer.
nxscan:
        push  bc
        ld    bc,0
ns_l:   di
        in    a,(&AA)
        and   &F0
        or    b
        out   (&AA),a
        in    a,(&A9)
        ei
        cpl
        or    c
        ld    c,a
        inc   b
        ld    a,b
        cp    9
        jr    c,ns_l
        ld    a,c
        pop   bc
        ret

'''

# TXTPAGE: A = banco -> la pagina 1. El registro de ASCII16 para &4000-&7FFF
# esta en &6000 (vale cualquier direccion de &6000-&67FF).
TXTPAGE_MSX = '''        ld    (&6000),a
        ret
'''


def _cambia_rutina(src, desde, hasta, nuevo):
    """Sustituye en PLAT_ASM desde la etiqueta `desde` (incluida) hasta la
    etiqueta `hasta` (excluida). Si alguna no esta, o esta dos veces, falla
    a voces: quiere decir que ha cambiado PLAT_ASM y hay que mirar esto."""
    a = '\n' + desde + ':'
    b = '\n' + hasta + ':'
    if src.count(a) != 1 or src.count(b) != 1:
        raise RuntimeError('msx2: no encuentro %s/%s en PLAT_ASM' % (desde, hasta))
    i = src.index(a) + 1
    j = src.index(b, i) + 1
    return src[:i] + nuevo + src[j:]


def plat_asm():
    """PLAT_ASM del Next con lo que depende de la maquina cambiado. Todo lo
    demas -- el cursor, la ventana, el salto de linea diferido, la pausa de
    pagina, el ritmo de escritura, INVERSE, los colores del guion -- es el
    mismo codigo que en Spectrum y Next."""
    src = nx.PLAT_ASM
    src = _cambia_rutina(src, 'nxglyph', 'nxplot', NXGLYPH_MSX)
    src = _cambia_rutina(src, 'nxplot', 'nxcls', NXPLOT_MSX)
    src = _cambia_rutina(src, 'nxcls', 'nxscroll', NXCLS_MSX)
    src = _cambia_rutina(src, 'nxscroll', 'TXTWIN', NXSCROLL_MSX)
    src = _cambia_rutina(src, 'SCRBORDER', 'nxcolor', SCRBORDER_MSX)
    # la tabla de colores se llama NXCOLT desde que se separo de nxcol (ver
    # abajo); con el PLAT_ASM de antes, NXCOL
    tabla = 'NXCOLT' if '\nNXCOLT:' in src else 'NXCOL'
    src = _cambia_rutina(src, 'nxcolor', tabla, NXCOLOR_MSX)
    src = _cambia_rutina(src, 'NXINIT', 'SCRMODE', NXINIT_MSX)
    src = _cambia_rutina(src, 'SNDREG', 'KMREAD', SNDREG_MSX)
    src = _cambia_rutina(src, 'KMREAD', 'CASOPEN', KMREAD_MSX)
    # La tabla de colores se llama NXCOL en PLAT_ASM, que para z80asm (no
    # distingue mayusculas) es la MISMA etiqueta que nxcol, la columna del
    # cursor: gana la ultima, la tabla, y el cursor escribe su columna encima
    # del color 0. Aqui la tabla va con otro nombre.
    if '\nNXCOLT:' not in src:
        if src.count('\nNXCOL:  defb') != 1:
            raise RuntimeError('msx2: no encuentro la tabla NXCOL en PLAT_ASM')
        src = src.replace('\nNXCOL:  defb', '\nNXCOLT: defb')
    # SCRMODE (el cambio de modo del CPC): aqui, la pantalla entera
    viejo = 'SCRMODE:\n        push  af\n        push  bc\n        push  de\n        push  hl\n        call  nxcls\n'
    if src.count(viejo) != 1:
        raise RuntimeError('msx2: no encuentro SCRMODE en PLAT_ASM')
    src = src.replace(viejo, viejo.replace('call  nxcls', 'call  msxcls0'))
    src += r'''
; msxcls0: borrado entero (SCRMODE): la ventana entera y el cursor arriba
msxcls0:
        call  msxclsall
        ld    a,(nxwt)
        ld    (nxrow),a
        ld    a,(nxwl)
        ld    (nxcol),a
        xor   a
        ld    (nxpcnt),a
        ret
'''
    src = nx.con_txtpage(src, TXTPAGE_MSX)
    # Nada de Z80N ni de puertos del Spectrum/Next
    import re
    sobra = re.search(r'(?mi)^[ \t]*(pixelad|pixeldn|nextreg|ldirx|mul)\b', src)
    if sobra:
        raise RuntimeError('msx2: queda Z80N: %r' % sobra.group(0).strip())
    sobra = re.search(r'(?mi)^[ \t]*add[ \t]+(hl|de|bc),[ \t]*(a\b|&|[0-9]|[A-Za-z_]+[ \t]*(;|$))', src)
    if sobra and not re.search(r'(?i),[ \t]*(bc|de|hl|sp)\b', sobra.group(0)):
        raise RuntimeError('msx2: queda ADD rr,A/nn: %r' % sobra.group(0).strip())
    codigo = '\n'.join(l.split(';', 1)[0] for l in src.split('\n'))
    if re.search(r'(?i)&(FFFD|BFFD|7FFD|243B|253B)\b', codigo) or re.search(r'(?i)out[ \t]*\(254\)', codigo):
        raise RuntimeError('msx2: queda un puerto del Spectrum en PLAT_ASM')
    return src


# ---------------------------------------------------------------------------
#  Imagenes de sala y portada
# ---------------------------------------------------------------------------
# MSXIT: por localizacion, 2 bytes: banco (0 = no tiene) y mitad (0 = &4000,
# 1 = &6000). Una imagen son 256x64 a 4 bits = 8192 bytes, dos por banco.
# MSXPALS: por localizacion, los colores 8..15 de su imagen (16 bytes).
IMG_ASM = r'''
; ===========================================================================
;  Imagenes de sala: la franja de arriba (filas 0..7 = 64 lineas)
; ===========================================================================
NXL2INIT:
        ret

; MSXPIC: A = localizacion. Si tiene imagen la pinta, pone sus 8 colores y
; vuelve con CF=1; si no, CF=0 y no toca nada.
MSXPIC:
        ld    c,a
        ld    b,0
        ld    hl,MSXIT
        add   hl,bc
        add   hl,bc
        ld    a,(hl)
        or    a
        ret   z                ; CF=0: sin imagen
        ld    (msxpbk),a
        inc   hl
        ld    a,(hl)
        ld    (msxpmi),a
        ld    a,(msxult)
        cp    c
        scf
        ret   z                ; ya esta puesta (la misma sala otra vez)
        ld    a,c
        ld    (msxult),a
        ld    l,c
        ld    h,0
        add   hl,hl
        add   hl,hl
        add   hl,hl
        add   hl,hl            ; 16 bytes de paleta por sala
        ld    de,MSXPALS
        add   hl,de
        ld    bc,16*256+8      ; 16 bytes desde el color 8
        call  msxpal
        ld    a,(msxpbk)
        ld    (&6000),a
        ld    hl,&4000
        ld    a,(msxpmi)
        or    a
        jr    z,mpi_0
        ld    h,&60
mpi_0:  ld    de,YOFF*128      ; la franja empieza en la linea YOFF
        ld    bc,8192
        call  msxvcopy
        scf
        ret
msxpbk: defb  0
msxpmi: defb  0
msxult: defb  255

; MSXNOPIC: la sala no tiene imagen (o esta a oscuras). La proxima que la
; tenga se tiene que pintar aunque sea la misma de antes.
MSXNOPIC:
        ld    a,255
        ld    (msxult),a
        ret

'''

SCR_ASM = r'''
; ===========================================================================
;  Pantallas sueltas del condact SCR (ver c_scr en el motor)
; ===========================================================================
; SCRT: 5 bytes por pantalla: filas (0 = no esta, 8 = tira, 24 = entera),
; banco y mitad del primer trozo, banco y mitad del segundo (solo las de 24:
; 16K + 8K). SCRPAL: los colores 8..15 de cada una (16 bytes). Las enteras
; usan tambien los 8 colores fijos, asi que el texto que se escriba encima
; sale con sus colores de siempre y no hay paleta que devolver en SCRREST.
SHOWSCR:
        cp    NSCR
        jp    nc,ss_no
        ld    (ss_i),a
        ld    b,c
        ld    l,a
        ld    h,0
        ld    e,l
        ld    d,h
        add   hl,hl
        add   hl,hl
        add   hl,de            ; 5 bytes por entrada
        ld    de,SCRT
        add   hl,de
        ld    a,(hl)
        or    a
        jp    z,ss_no          ; esta pantalla no esta en esta maquina
        ld    (ss_filas),a
        inc   hl
        ld    de,ss_b1
        push  bc
        ld    bc,4
        ldir
        pop   bc
        ld    a,b
        or    a
        jr    z,ss_pinta
        ld    h,0
        ld    l,0
        ld    d,41
        ld    e,23
        call  TXTWIN
        ld    a,12
        call  TXTO             ; como al describir una sala: todo limpio antes
ss_pinta:
        ld    a,255
        ld    (msxult),a       ; la imagen de la sala ya no esta puesta
        ld    a,(ss_i)
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl
        add   hl,hl
        add   hl,hl            ; 16 bytes de paleta por pantalla
        ld    de,SCRPAL
        add   hl,de
        ld    bc,16*256+8
        call  msxpal
        ld    a,(ss_b1)
        ld    (&6000),a
        ld    hl,&4000
        ld    a,(ss_h1)
        or    a
        jr    z,ss_h0
        ld    h,&60
ss_h0:  ld    de,YOFF*128
        ld    bc,8192
        ld    a,(ss_filas)
        cp    24
        jr    nz,ss_cp
        ld    bc,16384
ss_cp:  call  msxvcopy
        ld    a,(ss_filas)
        cp    24
        jr    z,ss_ent
        ; La ventana de texto pasa a empezar debajo de la tira, pero SIN mover
        ; el cursor si ya cae dentro (como en el 48K): al cambiar la imagen en
        ; mitad de una respuesta, el texto sigue donde iba.
        ld    a,FILATXT
        ld    (nxwt),a
        ld    a,(nxrow)
        cp    FILATXT
        jr    nc,ss_8
        ld    a,FILATXT
        ld    (nxrow),a
        xor   a
        ld    (nxcol),a
        ld    (col),a
ss_8:   xor   a
        ret                    ; A = 0: 8 filas
ss_ent: ld    a,(ss_b2)
        ld    (&6000),a
        ld    hl,&4000
        ld    a,(ss_h2)
        or    a
        jr    z,ss_e0
        ld    h,&60
ss_e0:  ld    de,YOFF*128+16384
        ld    bc,8192
        call  msxvcopy
        xor   a
        ld    (nxwt),a         ; ventana entera: lo que se imprima ira encima
        inc   a
        ret                    ; A = 1: 24 filas; se queda hasta CLS o DESC
ss_no:  ld    a,255
        ret
; La pantalla entera se va con el propio CLS: no hay modo ni paleta que
; devolver.
SCRREST:
        ret
ss_i:     defb 0
ss_filas: defb 0
ss_b1:    defb 0
ss_h1:    defb 0
ss_b2:    defb 0
ss_h2:    defb 0
'''

IMG_ASM_VACIO = r'''
NXL2INIT:
        ret
MSXNOPIC:
        ret
msxult: defb  255
'''

TITULO_ASM = r'''
; ===========================================================================
;  Portada: 256x212 a 16 colores (27136 bytes, dos bancos: 16384 + 10752)
;  y su paleta en MSXTPAL. Suena la musica mientras no toquen tecla.
; ===========================================================================
MSXTIT:
        ld    a,(&F3E6)        ; RG7SAV: el borde de ahora, para luego
        ld    (msxtbd),a
        xor   a
        ld    e,7
        call  vdpset           ; borde = color 0 (negro en la paleta de portada)
        ld    hl,MSXTPAL
        call  msxpal16
        ld    a,MSXTBK
        ld    (&6000),a
        ld    hl,&4000
        ld    de,0
        ld    bc,16384
        call  msxvcopy
        ld    a,MSXTBK+1
        ld    (&6000),a
        ld    hl,&4000
        ld    de,16384
        ld    bc,27136-16384
        call  msxvcopy
        call  msxespera
        ld    hl,PALFIJA       ; los colores del texto, de vuelta
        call  msxpal16
        ld    a,(msxtbd)
        ld    e,7
        call  vdpset
        ld    a,255
        ld    (msxult),a       ; la paleta de imagen se ha ido con la portada
        jp    SCRMODE
msxtbd: defb  0
'''

ESPERA_ASM = r'''
; msxespera: espera a que SUELTEN cualquier tecla y luego a que pulsen otra,
; con la musica sonando. Al final se vacia el buffer de la BIOS: la tecla de la
; portada no es la primera letra de la primera orden.
msxespera:
        call  psginit
mse_1:  ei
        halt
        call  psgframe
        call  nxscan
        or    a
        jr    nz,mse_1
mse_2:  ei
        halt
        call  psgframe
        call  nxscan
        or    a
        jr    z,mse_2
        call  psgoff
        jp    &0156            ; KILBUF
'''

PSG_ASM = r'''
; Musica del titulo: el mismo stream de registros del AY que en 128K y Next.
; Vive en un banco (psgbnk) y psgini es su direccion dentro de la ventana.
psginit:
        ld    a,(psgbnk)
        ld    (&6000),a
        ld    hl,(psgini)
        ld    (psgpos),hl
        ret

psgframe:
        ld    a,(psgbnk)
        ld    (&6000),a
        ld    hl,(psgpos)
        inc   hl               ; saltar el marcador de frame (&FF)
pf_rp:  ld    a,(hl)
        cp    &FF
        jr    z,pf_done
        cp    &FD
        jr    z,pf_loop        ; fin de la musica: rebobinar
        inc   hl
        ld    c,(hl)
        inc   hl
        call  SNDREG
        jr    pf_rp
pf_loop:
        ld    hl,(psgini)
        ld    (psgpos),hl
        ret
pf_done:
        ld    (psgpos),hl
        ret
psgpos: defw 0

psgoff:
        ld    a,7
        ld    c,&3F
        call  SNDREG           ; mezclador: los tres canales cerrados
        ld    a,8
        ld    c,0
        call  SNDREG
        ld    a,9
        call  SNDREG
        ld    a,10
        jp    SNDREG
'''


def _engine_msx(con_imagenes, con_titulo):
    """El motor con los parches del 48K (sin imagen, show_title -> ret, la
    pila al arrancar) y, si hace falta, las imagenes y la portada."""
    src = s48._engine_48()
    if con_imagenes:
        viejo = ('show_loc_image:\n'
                 '        ld    h,0\n'
                 '        ld    l,0\n'
                 '        ld    d,41\n'
                 '        ld    e,23\n'
                 '        call  TXTWIN\n')
        if src.count(viejo) != 1:
            raise RuntimeError('msx2: no encuentro show_loc_image en el motor')
        nuevo = ('show_loc_image:\n'
                 '        call  is_dark\n'
                 '        or    a\n'
                 '        jr    nz,msli_no       ; a oscuras no se ve nada\n'
                 '        ld    a,(curloc)\n'
                 '        call  MSXPIC\n'
                 '        jr    nc,msli_no\n'
                 '        ld    h,0\n'
                 '        ld    l,FILATXT        ; el texto, debajo de la imagen\n'
                 '        ld    d,41\n'
                 '        ld    e,23\n'
                 '        call  TXTWIN\n'
                 '        jr    msli_cls\n'
                 'msli_no:\n'
                 '        call  MSXNOPIC\n' + viejo[len('show_loc_image:\n'):] +
                 'msli_cls:\n')
        src = src.replace(viejo, nuevo)
    if con_titulo:
        viejo_t = 'show_title:\n        ret\n'
        if src.count(viejo_t) != 1:
            raise RuntimeError('msx2: no encuentro show_title en el motor')
        src = src.replace(viejo_t, 'show_title:\n        jp    MSXTIT\n')
    return src


def prefijo(org, db_base, sp, borde=7, nloc=256, titulo_bk=0, nscr=0):
    return (nx.prefijo(org, db_base, nimg=0, titulo=False, borde=borde,
                       nloc=nloc) +
            'S48SP equ &%04X\n' % sp +
            'MSXSP equ &%04X\n' % sp +
            'FILATXT equ %d\n' % FILA_TEXTO +
            'NSCR equ %d\n' % nscr +
            'YOFF equ %d\n' % YOFF +
            'XOFFB equ %d\n' % XOFFB +
            'MSXTBK equ %d\n' % titulo_bk)


def ensambla(org=ORG, db_base=None, sp=0xF000, idioma='es', borde=7,
             nloc=256, imagenes=None, titulo=None, psg_pos=None, guion_bk=None,
             pantallas=None):
    """Motor + capa MSX2. Devuelve (bytes, simbolos).
    imagenes: (tabla {loc: (banco, mitad)}, paletas {loc: 16 bytes}) o None.
    titulo:   (banco, paleta de 32 bytes) o None.
    psg_pos:  (direccion en la ventana, banco) de la musica, o None.
    guion_bk: banco del guion de la bateria (modo prueba) o None.
    pantallas: [(filas, banco1, mitad1, banco2, mitad2, 16 bytes de paleta)]
              de las pantallas del SCR, en el orden de spec['pantallas']."""
    if db_base is None:
        db_base = org
    plat = plat_asm()
    if pantallas:
        plat = nx.con_showscr(plat, SCR_ASM)
    partes = [plat]
    if pantallas:
        L = ['SCRT:']
        for e in pantallas:
            L.append('        defb %d,%d,%d,%d,%d' % tuple(e[:5]))
        L.append('SCRPAL:')
        for e in pantallas:
            L.append('        defb ' + ','.join(str(x) for x in e[5]))
        partes.append(chr(10).join(L))
    if imagenes:
        tabla, paletas = imagenes
        partes.append(IMG_ASM)
        L = ['MSXIT:']
        for i in range(max(1, nloc)):
            b, m = tabla.get(i, (0, 0))
            L.append('        defb %d,%d' % (b, m))
        L.append('MSXPALS:')
        for i in range(max(1, nloc)):
            p = paletas.get(i, b'\x00' * 16)
            L.append('        defb ' + ','.join(str(x) for x in p))
        partes.append('\n'.join(L))
    else:
        partes.append(IMG_ASM_VACIO)
    if titulo:
        partes.append(TITULO_ASM)
        partes.append(nx._datos_asm('MSXTPAL', titulo[1]))
        partes.append(ESPERA_ASM)
        if psg_pos:
            partes.append(PSG_ASM)
            partes.append('psgini: defw &%04X\npsgbnk: defb %d\n' % psg_pos)
        else:
            partes.append(nx.PSG_ASM_VACIO)
    partes.append(nx._datos_asm('PALFIJA', _pal_bytes(PALETA_FIJA + PALETA_BRILLO)))
    partes.append(nx.SMP_ASM_VACIO)
    fuente = (prefijo(org, db_base, sp, borde, nloc=nloc,
                      titulo_bk=titulo[0] if titulo else 0,
                      nscr=len(pantallas or ())) +
              _engine_msx(bool(imagenes), bool(titulo)) +
              chr(10).join(partes) + chr(10) +
              nx._font_asm(idioma) + chr(10))
    if guion_bk is not None:
        fuente = _modo_prueba(fuente, guion_bk)
    return z80asm.assemble(fuente, org=org)


# ---------------------------------------------------------------------------
#  Modo prueba: el cartucho se juega solo y cuenta lo que hace
# ---------------------------------------------------------------------------
# Lo mismo que next_nativo._modo_prueba, con el MSX: el guion va en bancos de
# la ROM y se lee por la ventana de &4000 (el motor pagina su texto antes de
# leerlo, asi que no hay que devolver nada a su sitio), y la traza sale por el
# "debugdevice" de openMSX (puertos &2E/&2F), que la escribe a un fichero. Al
# acabar, un OUT al puerto &2D, que la bateria vigila para cerrar el emulador.
PUERTO_TRAZA = 0x2F
PRUEBA_MSX_ASM = r'''
; --- modo prueba MSX2 --------------------------------------------------------
mgbk:   defb  MSXGUIONBK       ; banco del guion que toca leer
mgp:    defw  &4000            ; y por donde va

MSXPRINI:
        ld    a,&23            ; debugdevice: modo multibyte, ASCII
        out   (&2E),a
        ret

MSXFIN:
        di
        ld    hl,NXT_FIN
        call  nxtrs
        call  NXDUMP
        out   (&2D),a          ; la bateria cierra el emulador aqui
msxf_l: halt
        jr    msxf_l
'''


def _modo_prueba(src, guion_bk):
    def cambia(viejo, nuevo):
        if src.count(viejo) != 1:
            raise ValueError('msx2 modo prueba: %r aparece %d veces'
                             % (viejo[:40], src.count(viejo)))
        return src.replace(viejo, nuevo, 1)

    # 1. traza de cada caracter impreso
    src = cambia('TXTO:\n        push  af\n',
                 'TXTO:\n        out   (&2F),a       ; modo prueba: traza\n'
                 '        push  af\n')
    # 2. el teclado sale del guion
    i = src.index('\nKMREAD:\n')
    j = src.index('\nKMW:', i)
    src = src[:i + 1] + r'''KMREAD:
        push  hl
mg_l:   ld    a,(mgbk)
        ld    (&6000),a
        ld    hl,(mgp)
        ld    a,(hl)
        or    a
        jr    z,mg_fin
        inc   hl
        bit   7,h
        jr    z,mg_ok          ; sigue dentro de la ventana
        ld    hl,mgbk
        inc   (hl)
        ld    hl,&4000
mg_ok:  ld    (mgp),hl
        cp    1
        jr    z,mg_vol         ; 1 = foto del estado, no es tecla
        cp    2
        jr    z,mg_res         ; 2 = volver a empezar la partida
        pop   hl
        scf
        ret
mg_vol: call  NXDUMP
        jr    mg_l
mg_res: ld    hl,NXT_RES
        call  nxtrs
        ld    sp,MSXSP
        jp    start
mg_fin: pop   hl
        jp    MSXFIN
''' + src[j + 1:]
    # 3. la espera bloqueante no gasta guion
    src = cambia('KMW:    call  KMREAD\n        jr    nc,KMW\n        ret\n',
                 'KMW:    ld    a,32          ; modo prueba: ni espera ni gasta\n'
                 '        ret\n')
    # 3b. al acabar la partida, la partida se queda acabada hasta la prueba
    #     siguiente: las teclas que queden del guion se tiran, y las fotos ven
    #     el estado final (la puntuacion, la sala). Es lo que ve probar_juego,
    #     que se queda con la pantalla del final. Con KMW sin gastar guion, la
    #     partida volvia a empezar antes de la foto y PUNTOS salia a 0.
    src = cambia('        ld    de,SOTRA\n        call  print_msg\n        call  KMW\n',
                 '        ld    de,SOTRA\n        call  print_msg\n'
                 'mgo_l:  call  KMREAD         ; modo prueba: hasta el #RESET\n'
                 '        jr    mgo_l\n')
    # 4. el debugdevice, al arrancar
    src = cambia('\n        call  init\n',
                 '\n        call  MSXPRINI\n        call  init\n')
    # 5. fuera la espera de barrido del ritmo de escritura
    src = cambia('        ei\n        halt\n        xor   a\nnxr_g:',
                 '        xor   a\nnxr_g:')
    if '\nmsxespera:\n' in src:
        i = src.index('\nmsxespera:\n')
        j = src.index('        jp    &0156', i)
        j = src.index('\n', j) + 1
        src = src[:i + 1] + 'msxespera:\n        ret\n' + src[j:]
    return ('NXTRAZA equ &%04X\nNXGUION equ &4000\n'
            'MSXGUIONBK equ %d\n' % (PUERTO_TRAZA, guion_bk) +
            src + nx.PRUEBA_ASM + PRUEBA_MSX_ASM + '\n')


# ---------------------------------------------------------------------------
#  Conversion de imagenes a SCREEN 5
# ---------------------------------------------------------------------------
def _a3(v):
    return max(0, min(7, int(round(v * 7 / 255.0))))


def _de3(c):
    return int(round(c * 255 / 7.0))


def convierte(path, alto, fijos, auto=True, usables=None):
    """Imagen -> (bytes SCREEN 5 de 256 x alto, [(r,g,b) 0..7] de los colores
    libres, que van en los indices len(fijos)..15). `fijos` son los colores que
    no se pueden tocar (los 8 del texto en las imagenes de sala; el negro del
    fondo en la portada). `usables`: cuales de los fijos puede usar la imagen
    (None = todos); en las salas solo el negro y el blanco, que los demas son
    los colores puros del Spectrum y al difuminar salen como motas.
    `auto`: autocontraste, como hacen las demas maquinas con los masteres de
    img/Original; lo de img/MSX ya es la version definitiva y no se toca."""
    from PIL import Image, ImageOps
    im = Image.open(path).convert('RGB')
    im = im.resize((256, alto), Image.LANCZOS)
    if auto:
        im = ImageOps.autocontrast(im, cutoff=2)
    nlibres = 16 - len(fijos)
    q = im.quantize(colors=nlibres, method=Image.MEDIANCUT)
    pal = q.getpalette()[:nlibres * 3]
    libres = [tuple(_a3(pal[3 * k + t]) for t in range(3)) for k in range(nlibres)]
    if usables is None:
        usables = list(range(len(fijos)))
    # indice en la paleta de cuantizar -> indice de verdad en SCREEN 5
    indices = list(usables) + list(range(len(fijos), 16))
    colores = [fijos[i] for i in usables] + libres
    pim = Image.new('P', (1, 1))
    flat = []
    for r, g, b in colores:
        flat += [_de3(r), _de3(g), _de3(b)]
    pim.putpalette(flat + flat[:3] * (256 - len(colores)))
    idx = im.quantize(palette=pim, dither=Image.FLOYDSTEINBERG)
    px = [indices[p] for p in idx.tobytes()]
    out = bytearray(256 * alto // 2)
    for i in range(0, len(px), 2):
        out[i // 2] = ((px[i] & 15) << 4) | (px[i + 1] & 15)
    return bytes(out), libres


def _es_original(path):
    return os.path.basename(os.path.dirname(path)).lower() == 'original'


def busca_imagen(game_dir, nombre):
    """img/MSX/<id> manda (ya es la version definitiva); si no, el master de
    img/Original. El nombre vale con arroba y sin ella."""
    if not game_dir:
        return None
    cands = [nombre, nombre.lstrip('@'), '@' + nombre.lstrip('@')]
    for sub in ('MSX', 'Original'):
        d = os.path.join(game_dir, 'img', sub)
        if not os.path.isdir(d):
            continue
        ficheros = {f.lower(): f for f in os.listdir(d)}
        for c in cands:
            for ext in ('.png', '.jpg', '.jpeg', '.bmp', '.gif'):
                f = ficheros.get((c + ext).lower())
                if f:
                    return os.path.join(d, f)
    return None


# ---------------------------------------------------------------------------
#  Compilar y empaquetar
# ---------------------------------------------------------------------------
def compila(game, game_dir=None, ancho=COLS, guion=None, imagenes=True):
    """Devuelve (rom, info)."""
    import cpc_nativo
    import nativecc as nc
    import presupuesto
    import scriba_info
    import spectrum_export as sx

    c = sx.recolecta(game)
    sysm, _sal = cpc_nativo._sys_msgs_y_salidas(game.get('metadata') or {})
    while len(sysm) < ge.NSYS:
        sysm.append('')

    fx_blob = b''
    try:
        import capabilities
        import fx_engine
        usados = capabilities.used_fx(game)
        if usados:
            fx_blob = fx_engine.pack_ay_fx(game.get('fx', []) or [], usados)
    except Exception:
        fx_blob = b''

    avisos = []
    # imagenes de sala (por localizacion, en el orden de curloc) y portada
    salas = []
    if imagenes and game_dir:
        for i, lid in enumerate(c.locids):
            p = busca_imagen(game_dir, lid)
            if p:
                salas.append((i, lid, p))
    portada = busca_imagen(game_dir, 'screen') if (imagenes and game_dir) else None

    ficha = scriba_info.ficha(game, 'msx2', scriba_info.ahora())
    spec, _ = nc.compile_game(c, sysm[:ge.NSYS], width=ancho, filas=0,
                              ficha=ficha, imagen_intro=bool(salas))
    idioma = str((game.get('metadata') or {}).get('language', '') or 'es')
    borde = nx.borde_inicial(game)
    nlocs = len(spec['locations'])

    texto = dict(ventana=VENTANA, tam=BANCO, ids=list(range(1, MAX_BANCOS)))

    def _db(dbaddr):
        return ge.build_game_db(
            spec['messages'], spec['locations'], spec['vocab'], spec['objects'],
            spec['responses'], spec['startloc'], spec['sysverbs'], spec['width'],
            load=dbaddr, proc_before=spec['proc_before'],
            proc_after=spec['proc_after'], proc_onstart=spec['proc_onstart'],
            hdrbuf=0, imgbuf=0, loc_slot=b'', vall=spec['vall'],
            font_acc=spec['font_acc'], timers=spec['timers'],
            llevarmax=spec['llevarmax'], fx=fx_blob, texto=texto)

    bancos = [bytearray(b) for b in _db(ORG)[1]['bancos_texto']]
    ntxt = len(bancos)
    texto_bytes = sum(len(b) for b in bancos) - len(fx_blob)

    # musica del titulo, detras del texto (solo si hay portada)
    psg_pos = None
    psg = b''
    if portada:
        psg_bruto, _nom = nx._musica(os.path.join(game_dir, 'music'))
        if psg_bruto:
            psg = nx._trunca_psg(psg_bruto, BANCO)
            if len(psg) < len(psg_bruto):
                avisos.append('musica recortada de %d a %d bytes y en bucle'
                              % (len(psg_bruto), len(psg)))
            bancos, donde = ge.empaqueta_en_bancos([psg], bancos=bancos)
            psg_pos = (VENTANA + donde[0][1], 1 + donde[0][0])

    def _nuevo_banco():
        bancos.append(bytearray())
        return len(bancos)       # id = numero de banco (el 0 es el cargador)

    # Imagenes de 8K (una tira de 256x64): dos por banco, en &4000 o en &6000
    # de la ventana. Empiezan en un banco nuevo, detras del texto.
    lleno = [True]

    def coloca8k(raw):
        if lleno[0] or len(bancos[-1]) >= BANCO:
            _nuevo_banco()
            lleno[0] = False
        mitad = len(bancos[-1]) // 8192
        bancos[-1] += raw
        return len(bancos), mitad

    tabla, paletas = {}, {}
    img_bytes = 0
    for i, lid, p in salas:
        try:
            raw, libres = convierte(p, 64, PALETA_FIJA, _es_original(p), usables=(0, 7))
        except Exception as e:
            avisos.append('imagen de %s: %s' % (lid, e))
            continue
        tabla[i] = coloca8k(raw)
        paletas[i] = _pal_bytes(libres)
        img_bytes += len(raw)

    # Pantallas sueltas (SCR): 4:1 es una tira de 8 filas, como la de una
    # sala; lo demas, pantalla entera de 24 filas (256x192 = 16K + 8K). Las
    # dos con los 8 colores fijos delante, para que el texto se lea encima.
    pant = []
    for nombre in (spec.get('pantallas') or []):
        p = busca_imagen(game_dir, nombre) if (imagenes and game_dir) else None
        if not p:
            avisos.append('SCR %s: no hay imagen en img/MSX ni img/Original; '
                          'no pintara nada' % nombre)
            pant.append((0, 0, 0, 0, 0, bytes(16)))
            continue
        try:
            from PIL import Image
            w, h = Image.open(p).size
            filas = 8 if w >= 3 * h else 24
            raw, libres = convierte(p, filas * 8, PALETA_FIJA, _es_original(p),
                                    usables=(0, 7))
        except Exception as e:
            avisos.append('SCR %s: %s' % (nombre, e))
            pant.append((0, 0, 0, 0, 0, bytes(16)))
            continue
        if filas == 8:
            b1, h1 = coloca8k(raw)
            pant.append((8, b1, h1, 0, 0, _pal_bytes(libres)))
        else:
            b1 = _nuevo_banco()
            bancos[-1] += raw[:BANCO]
            lleno[0] = True
            b2, h2 = coloca8k(raw[BANCO:])
            pant.append((24, b1, 0, b2, h2, _pal_bytes(libres)))
        img_bytes += len(raw)

    titulo = None
    if portada:
        try:
            # 256x192 (la portada es 4:3), centrada en las 212 lineas con el
            # color 0 (negro) arriba y abajo
            raw, libres = convierte(portada, 192, [(0, 0, 0)], _es_original(portada))
            raw = bytes(YOFF * 128) + raw + bytes((212 - 192 - YOFF) * 128)
            libres = [(0, 0, 0)] + libres
            b1 = _nuevo_banco()
            bancos[-1] += raw[:BANCO]
            _nuevo_banco()
            bancos[-1] += raw[BANCO:]
            lleno[0] = True
            titulo = (b1, _pal_bytes(libres))
            img_bytes += len(raw)
        except Exception as e:
            avisos.append('portada: %s' % e)
            psg_pos = None
    elif psg:
        psg_pos = None

    # la imagen RAM: dos pasadas, como en las demas maquinas
    img_arg = (tabla, paletas) if tabla else None
    ntope = HIMEM_SIN_DISCO - PILA_MIN

    def _asm(base, sp, gbk=None):
        return ensambla(org=ORG, db_base=base, sp=sp, idioma=idioma, borde=borde,
                        nloc=nlocs, imagenes=img_arg, titulo=titulo,
                        psg_pos=psg_pos, guion_bk=gbk, pantallas=pant)

    img_banco0 = len(bancos) + 1
    nguion = (len(guion) + BANCO) // BANCO if guion is not None else 0
    gbk = None
    if guion is not None:
        # el guion va detras de la imagen RAM; su banco depende del tamano de
        # la imagen, asi que se estima con una primera pasada
        gbk = 1
    code, _s = _asm(ORG, 0xF000, gbk)
    dbaddr = ORG + len(code)
    db, info_db = _db(dbaddr)
    fin = dbaddr + len(db)
    sp = (fin + PILA_MIN + 15) & 0xFFF0
    if guion is not None:
        gbk = img_banco0 + (fin - ORG + BANCO - 1) // BANCO
    code, sym = _asm(dbaddr, sp, gbk)
    assert ORG + len(code) == dbaddr, 'el motor cambio de tamano entre pasadas'
    for j, b in enumerate(info_db['bancos_texto']):
        assert bytes(bancos[j][:len(b)]) == bytes(b), 'el texto se movio de banco'
    imagen_ram = code + db

    presupuesto.comprueba(
        'MSX2',
        [('motor + plataforma', len(code)),
         ('base de datos (sin el texto)', len(db))],
        ntope - ORG,
        'la RAM de &%04X a &%04X (HIMEM sin disquetera, menos la pila)'
        % (ORG, ntope),
        presupuesto.RECORTA_PLANO, primero=True)

    # banco 0: el cargador y el trocito que copia
    stub_src = ('ORIGIN equ &%04X\nIMGLEN equ %d\nIMGBANK equ %d\n'
                'MSXSP equ &%04X\nMSXSTART equ &%04X\nMSXSTUB equ &%04X\n'
                % (ORG, len(imagen_ram), img_banco0, sp, sym['start'], fin) +
                STUB_ASM)
    stub, _ = z80asm.assemble(stub_src, org=fin)
    assert fin + len(stub) <= sp - 32, 'el cargador no cabe en el hueco de la pila'
    car_src = ('MSXTOP equ &%04X\nMSXSTUB equ &%04X\nLDSTUBN equ %d\n'
               % (sp, fin, len(stub)) + CARGADOR_ASM)
    cargador, _ = z80asm.assemble(car_src, org=0x4000)
    banco0 = cargador + stub
    assert len(banco0) <= BANCO

    rom = bytearray(banco0.ljust(BANCO, b'\xFF'))
    for b in bancos:
        rom += bytes(b).ljust(BANCO, b'\xFF')
    assert len(rom) == img_banco0 * BANCO
    rom += imagen_ram
    rom += b'\xFF' * (-len(rom) % BANCO)
    if guion is not None:
        assert len(rom) // BANCO == gbk, 'el guion no cae en su banco'
        rom += (bytes(guion) + b'\x00').ljust(nguion * BANCO, b'\x00')
    tam = ROM_MIN
    while tam < len(rom):
        tam *= 2
    nb = tam // BANCO
    if nb > MAX_BANCOS:
        raise ValueError('el cartucho necesita %d bancos de 16K y el mapper '
                         'ASCII16 admite %d (4 MB)' % (len(rom) // BANCO, MAX_BANCOS))
    rom = bytes(rom.ljust(tam, b'\xFF'))
    presupuesto.comprueba(
        'MSX2',
        [('texto del juego', texto_bytes),
         ('efectos FX', len(fx_blob)),
         ('musica del titulo', len(psg)),
         ('imagenes y portada', img_bytes)],
        (MAX_BANCOS - 2) * BANCO, 'los bancos del cartucho ASCII16 (4 MB)',
        presupuesto.RECORTA_BANCOS)
    info = {'codigo': len(code), 'datos': len(db), 'org': ORG, 'db': dbaddr,
            'fin': fin, 'sp': sp, 'libre': ntope - fin,
            'rom': len(rom), 'bancos_texto': ntxt, 'imagenes': sorted(tabla),
            'portada': bool(titulo), 'musica': bool(psg_pos),
            'pantallas': [n for n, e in zip(spec.get('pantallas') or [], pant) if e[0]],
            'localizaciones': nlocs, 'objetos': len(spec['objects']),
            'avisos': avisos, 'sym': sym, 'img_banco0': img_banco0,
            'guion_bk': gbk}
    return rom, info


def export_rom(game, rom_path, game_dir=None, ancho=COLS, imagenes=True):
    import presupuesto
    presupuesto.empieza()
    rom, info = compila(game, game_dir=game_dir, ancho=ancho, imagenes=imagenes)
    with open(rom_path, 'wb') as f:
        f.write(rom)
    info['presupuesto'] = presupuesto.informe()
    return info


def main():
    import argparse
    import yaml
    ap = argparse.ArgumentParser(
        description='Compila un juego de Scriba a cartucho MSX2 (.rom, MegaROM ASCII16).')
    ap.add_argument('yaml')
    ap.add_argument('rom', nargs='?')
    ap.add_argument('--sin-imagenes', action='store_true')
    a = ap.parse_args()
    game = yaml.safe_load(open(a.yaml, encoding='utf-8'))
    salida = a.rom or (a.yaml.rsplit('.', 1)[0] + '_msx2.rom')
    info = export_rom(game, salida, game_dir=os.path.dirname(os.path.abspath(a.yaml)),
                      imagenes=not a.sin_imagenes)
    print('ROM MSX2 (MegaROM ASCII16): %s' % salida)
    print('  cartucho         : %6d KB, %d bancos de texto'
          % (info['rom'] // 1024, info['bancos_texto']))
    print('  motor+plataforma : %6d bytes  (&%04X-&%04X)'
          % (info['codigo'], info['org'], info['db'] - 1))
    print('  base de datos    : %6d bytes  (&%04X-&%04X)'
          % (info['datos'], info['db'], info['fin'] - 1))
    print('  pila en &%04X; libre hasta HIMEM: %d bytes' % (info['sp'], info['libre']))
    print('  %d localizaciones, %d objetos, %d imagenes%s%s'
          % (info['localizaciones'], info['objetos'], len(info['imagenes']),
             ', portada' if info['portada'] else '',
             ', musica' if info['musica'] else ''))
    if info['pantallas']:
        print('  pantallas SCR: %s' % ', '.join(info['pantallas']))
    for av in info['avisos']:
        print('  AVISO: %s' % av)


if __name__ == '__main__':
    main()
