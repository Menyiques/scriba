# -*- coding: utf-8 -*-
"""
pcw_nativo.py - Capa de plataforma Amstrad PCW 8256/8512 para el motor nativo Z80.

El mismo motor (game_engine.ENGINE_ASM) y la misma base de datos que las demas
maquinas; aqui se resuelven los simbolos de plataforma como en next_nativo y
msx2_nativo. La salida es un DISCO AUTOARRANCABLE (.dsk, formato CF2 de 180K,
una cara): se mete en la unidad A, se enciende la maquina y arranca el juego,
sin CP/M ni LocoScript.

EL ARRANQUE
    La "ROM" del PCW (que en realidad es un flujo de bytes del controlador de
    impresora) carga el sector 1 de la pista 0 en &F000, comprueba que sus 512
    bytes sumen &FF y salta a &F010, con los bloques 0-3 de 16K en &0000-&FFFF.
    Nuestro sector de arranque (CARGADOR_ASM) se copia a &0200 (bloque 0), lee
    del disco, pista a pista y a pelo por el uPD765, el resto del juego en los
    bloques 4 en adelante, copia el motor a su sitio (&8000, bloques 2 y 3) y
    salta a 'start'.

MAPA (bloques de 16K; ids de TXTPAGE = &80 + bloque, nunca 0)
    bloque 0  en &0000   pantalla S0: filas 0-21 (15840 bytes) y el roller-RAM
                         en &3E00. Se queda puesto siempre, salvo un instante
                         al descomprimir una imagen.
    bloque 1             pantalla S1: filas 22-31 en &0000, y detras un buffer
                         de 7920 bytes para descomprimir las imagenes.
    pagina 1  &4000      VENTANA DE PAGINACION, como &C000 en 128K/Next: por
                         ella se leen el texto, los FX y las imagenes, cada uno
                         de su bloque; y tambien S1 cuando se pinta una fila de
                         ahi. Nada permanente vive en ella.
    bloques 2-3 &8000    motor + base de datos plana; la pila en &FFF0, justo
                         bajo el teclado (que el PCW mapea en &3FF0-&3FFF del
                         bloque 3).
    bloques 4-15         texto, FX e imagenes, tal cual salen del disco.

PANTALLA: 720x256 monocromo, sin modo texto. Cada linea es una lista de 90
bytes separados 8 entre si, asi que una celda de caracter son 8 bytes seguidos
y un glifo se pinta con 8 LD (DE),A. Texto a 90 columnas x 32 filas con la
fuente de 6 pixeles del motor, centrada en celdas de 8 (los pixeles del PCW son
el doble de altos que de anchos: 8x8 se lee como el 8x16 de un PC). El scroll
no mueve la pantalla: rota el roller-RAM (256 punteros, uno por linea) y la
tabla ROWADR, y solo borra la fila que entra. INK/PAPER no tienen color: si el
papel es mas claro que la tinta, la pantalla entera pasa a video inverso.

SIN INTERRUPCIONES: el motor corre con DI de principio a fin. La pagina 0 es
pantalla, no hay nada en &0038 ni en &0066. MCWAIT cuenta los ticks del reloj
de 300 Hz por el puerto &F4 (que cuenta aunque nadie atienda la interrupcion);
el teclado se lee de su mapa en memoria; la controladora de disco, a sondeo.

SONIDO: el PCW solo tiene un pitido de encendido/apagado; PLAY, la musica y las
muestras quedan mudos (como en el 48K), pero PAUSE y los FX guardan su tiempo.

Uso:
    python pcw_nativo.py juego.yaml [salida.dsk]
"""
import os
import re

import game_engine as ge
import msx2_nativo as mx
import next_nativo as nx
import spectrum48_nativo as s48
import z80asm

ORG = 0x8000
SPPCW = 0xFFF0            # bajo el teclado mapeado en memoria
PILA_MIN = 256
TOPE = SPPCW - PILA_MIN   # donde tiene que acabar motor + DB
COLS = 90
FILAS = 32
FILA_TEXTO = 11           # la imagen: filas 0..10 = 88 lineas (4:1 en pixeles PCW)
FILA_BYTES = 720          # 90 celdas x 8 bytes
S0, S1 = 0, 1             # bloques de pantalla
BLK0 = 4                  # primer bloque de datos del disco
MAX_BLK = 16              # PCW 8256: 256K = 16 bloques
MAX_BLK_8512 = 32         # PCW 8512: 512K
BANCO = 16384
TMPBUF = 0x4000 + 10 * FILA_BYTES    # en S1, detras de las filas 22-31
ROLLER = 0x3E00           # en S0
PISTAS, SECTORES, SECTAM = 40, 9, 512
CAPACIDAD = (PISTAS * SECTORES - 1) * SECTAM    # sin el sector de arranque
# PCW 8512: la unidad B es de 720K (CF2DD: 80 pistas, dos caras). El PCW solo
# arranca de la A, asi que el modo 8512 son DOS discos: en la A, solo el sector
# de arranque; en la B, todo lo demas.
PISTAS_B, CARAS_B = 80, 2
CAPACIDAD_B = PISTAS_B * CARAS_B * SECTORES * SECTAM


# ---------------------------------------------------------------------------
#  El sector de arranque
# ---------------------------------------------------------------------------
# Especificacion de disco (los 16 primeros bytes): formato 0 (PCW/+3), una
# cara, 40 pistas, 9 sectores de 512, 1 pista reservada, bloques de 1K, 2 de
# directorio, huecos &2A/&52. El byte 15 cuadra la suma: &FF en el 8256/8512.
ESPEC = bytes([0, 0, 40, 9, 2, 1, 3, 2, 0x2A, 0x52, 0, 0, 0, 0, 0, 0])

# En &F010 (18 bytes): copia lo que le sigue a &0200 (bloque 0) y sigue ahi,
# porque la carga va a escribir encima de &F000.
ARRANQUE_ASM = r'''
        org   &F010
        di
        ld    sp,&0200
        ld    hl,&F022         ; lo que viene detras de estos 18 bytes
        ld    de,&0200
        ld    bc,&F200-&F022
        ldir
        jp    &0200
'''

CARGADOR_ASM = r'''
        org   &0200
        ld    a,4
        out   (&F8),a          ; interrupciones de la controladora: ignoradas
        ld    a,9
        out   (&F8),a          ; motores en marcha (el de la A ya lo esta)
        ld    a,RECAL
        or    a
        call  nz,ld_recal      ; unidad B: hay que llevar el cabezal a la 0
        ld    a,&80+BLK0
        ld    (ldblk),a
        out   (&F1),a
        ld    hl,&4000
        ld    e,S0INI          ; primer sector (en la A, el 1 es este)
; Una "unidad" es una cara de una pista: 9 sectores de un READ DATA.
ld_unid:
        ld    a,(ldrem)
        dec   a
        ld    a,9
        jr    nz,ld_eot
        ld    a,LEOT           ; la ultima, solo hasta donde hace falta
ld_eot: ld    (ld_cmd+6),a
        ld    a,(ldpis)
        ld    (ld_cmd+2),a
        ld    a,(ldcara)
        ld    (ld_cmd+3),a
        rlca
        rlca
        or    UNIT
        ld    (ld_cmd+1),a     ; cabeza (bit 2) y unidad
        ld    a,e
        ld    (ld_cmd+4),a
        ld    (ldhl),hl        ; por si hay que repetirla
        ld    a,(ldblk)
        ld    (ldb0),a
        ld    b,RETRY
ld_try: push  bc
        push  de
        ld    a,6
        out   (&F8),a          ; fuera el "terminal count"
        ld    hl,ld_cmd
        ld    b,9
        call  fdcout
        ld    hl,(ldhl)
        ld    c,1
ld_rd:  in    a,(0)            ; estado de la controladora
        add   a,a
        jr    nc,ld_rd         ; RQM: aun no
        add   a,a
        jp    p,ld_fin         ; EXM a 0: se acabo la ejecucion
        defb  &ED,&A2          ; INI: dato -> (HL)++ (z80asm no la conoce)
        ld    a,h
        cp    &80
        jr    nz,ld_rd
        ld    h,&40            ; bloque lleno: el siguiente, en la ventana
        ld    a,(ldblk)
        inc   a
        ld    (ldblk),a
        out   (&F1),a
        jr    ld_rd
ld_fin: ld    a,5
        out   (&F8),a          ; "terminal count": que acabe
        ld    (ldhl2),hl
        call  fdcin            ; 7 bytes de resultado en ldres
        pop   de
        pop   bc
        ld    a,(ldres)
        and   &C0
        jr    z,ld_ok          ; terminacion normal
        ld    a,(ldres+1)
        rla
        jr    c,ld_ok          ; "fin de cilindro": leimos hasta EOT, bien
        ld    hl,(ldhl)        ; mal: otra vez la misma
        ld    a,(ldb0)
        ld    (ldblk),a
        out   (&F1),a
        djnz  ld_try
        jp    ld_error
ld_ok:  ld    hl,(ldhl2)
        ld    a,(ldrem)
        dec   a
        ld    (ldrem),a
        jr    z,ld_todo
        ld    e,1
        ld    a,CARAS
        dec   a
        jr    z,ld_sig         ; una cara: pista siguiente
        ld    a,(ldcara)
        xor   1
        ld    (ldcara),a
        jp    nz,ld_unid       ; la otra cara de la misma pista, sin buscar
ld_sig: ld    a,(ldpis)
        inc   a
        ld    (ldpis),a
        push  hl
        call  ld_clr
        ld    a,(ldpis)
        ld    (ld_seek+2),a
        ld    hl,ld_seek
        ld    b,3
        call  fdcout
        call  ld_wint
        pop   hl
        jp    ld_unid
ld_todo:
        ld    a,10
        out   (&F8),a          ; motores parados
        ; el motor: de donde quedo en el flujo, a &8000
        ld    a,&80+IMGBLK
        ld    (ldblk),a
        out   (&F1),a
        ld    hl,&4000+IMGOFF
        ld    de,&8000
        ld    bc,IMGLEN
ld_cp:  ld    a,(hl)
        ld    (de),a
        inc   de
        inc   hl
        bit   7,h
        jr    z,ld_cp2
        ld    h,&40            ; se acabo el bloque: el siguiente
        ld    a,(ldblk)
        inc   a
        ld    (ldblk),a
        out   (&F1),a
ld_cp2: dec   bc
        ld    a,b
        or    c
        jr    nz,ld_cp
        ld    sp,SPPCW
        jp    PCWSTART
ld_error:
        ld    a,&C0            ; pantalla en inverso: algo fue mal al leer
        out   (&F7),a
ld_err: jr    ld_err

; ld_recal: la unidad B, a la pista 0. Dos veces: el 765 da como mucho 77
; pasos en un RECALIBRATE y la unidad tiene 80 pistas. Antes, medio segundo
; para que el motor coja velocidad (150 ticks del reloj de 300 Hz).
ld_recal:
        ld    b,150
ld_rw:  in    a,(&F4)
        and   &0F
        jr    z,ld_rw
        ld    c,a
        ld    a,b
        sub   c
        ld    b,a
        jr    z,ld_rc
        jr    nc,ld_rw
ld_rc:  ld    d,2
ld_rcl: call  ld_clr
        ld    hl,ld_rcmd
        ld    b,2
        call  fdcout
        call  ld_wint
        dec   d
        jr    nz,ld_rcl
        ret
; ld_wint: espera a que la controladora acabe (busqueda) y lee su estado
ld_wint:
        in    a,(&F8)
        and   &20
        jr    z,ld_wint
        ld    hl,ld_sns
        ld    b,1
        call  fdcout
        jp    fdcin
; ld_clr: fuera las interrupciones pendientes de la controladora
ld_clr: in    a,(&F8)
        and   &20
        ret   z
        ld    hl,ld_sns
        ld    b,1
        call  fdcout
        call  fdcin
        jr    ld_clr
; fdcout: B bytes desde HL a la controladora
fdcout: in    a,(0)
        add   a,a
        jr    nc,fdcout
        ld    a,(hl)
        out   (1),a
        inc   hl
        ex    (sp),hl
        ex    (sp),hl
        djnz  fdcout
        ret
; fdcin: el resultado de la controladora, a ldres
fdcin:  ld    hl,ldres
fi_l:   in    a,(0)
        add   a,a
        jr    nc,fi_l
        ret   p                ; DIO a 0: ya no hay mas que leer
        in    a,(1)
        ld    (hl),a
        inc   hl
        ex    (sp),hl
        ex    (sp),hl
        jr    fi_l

ld_cmd: defb  &66,0,0,0,1,2,9,&2A,&FF   ; READ DATA (MFM, sin borrados)
ld_seek: defb &0F,UNIT,0                ; SEEK
ld_rcmd: defb &07,UNIT                  ; RECALIBRATE
ld_sns: defb  &08                       ; SENSE INTERRUPT STATUS
ldrem:  defb  NUNID
ldpis:  defb  0
ldcara: defb  0
ldblk:  defb  0
ldb0:   defb  0
ldhl:   defw  0
ldhl2:  defw  0
ldres:  defs  8
'''


def sector_arranque(nsect, imgoff, imglen, start, unidad_b=False, retry=5):
    """Los 512 bytes del sector 1 de la pista 0 de la unidad A, con la suma
    cuadrada a &FF. `nsect`: sectores del flujo; `imgoff`: donde empieza el
    motor dentro de el. Con `unidad_b` el flujo se lee entero del disco de la
    unidad B (720K, dos caras, 80 pistas), desde su primer sector; si no, de
    este mismo disco, a partir del sector 2."""
    arr, _ = z80asm.assemble(ARRANQUE_ASM, org=0xF010)
    if unidad_b:
        nunid, leot, s0, unidad, caras, recal = ((nsect - 1) // SECTORES + 1,
                                                 (nsect - 1) % SECTORES + 1,
                                                 1, 1, 2, 1)
    else:
        nunid, leot, s0, unidad, caras, recal = (nsect // SECTORES + 1,
                                                 nsect % SECTORES + 1,
                                                 2, 0, 1, 0)
    if nunid > 255:
        raise ValueError('demasiadas pistas para el cargador')
    eq = ('BLK0 equ %d\nNUNID equ %d\nLEOT equ %d\nS0INI equ %d\nUNIT equ %d\n'
          'CARAS equ %d\nRECAL equ %d\nIMGBLK equ %d\n'
          'IMGOFF equ %d\nIMGLEN equ %d\nSPPCW equ &%04X\nPCWSTART equ &%04X\n'
          'RETRY equ %d\n'
          % (BLK0, nunid, leot, s0, unidad, caras, recal,
             imgoff // BANCO + BLK0, imgoff % BANCO, imglen,
             SPPCW, start, retry))
    car, _ = z80asm.assemble(eq + CARGADOR_ASM, org=0x0200)
    assert len(arr) == 18, len(arr)
    s = bytearray(ESPEC + arr + car)
    if len(s) > 512:
        raise ValueError('el cargador no cabe en el sector de arranque (%d bytes)'
                         % len(s))
    s = s.ljust(512, b'\x00')
    s[15] = (0xFF - (sum(s) - s[15])) & 0xFF
    assert sum(s) & 0xFF == 0xFF
    return bytes(s), nunid


def dsk(sectores, pistas=PISTAS, caras=1):
    """Imagen .dsk (CPCEMU, no extendida) de `pistas` x `caras` x 9 sectores
    de 512, ids 1-9. `sectores`: lista lineal de sectores de 512 bytes en el
    orden en que se leen (pista 0 cara 0, pista 0 cara 1, pista 1...)."""
    img = bytearray(256)
    img[0:34] = b'MV - CPCEMU Disk-File\r\nDisk-Info\r\n'
    img[34:48] = b'Scriba'.ljust(14, b'\x00')
    img[48] = pistas
    img[49] = caras
    ts = 256 + SECTORES * SECTAM
    img[50] = ts & 255
    img[51] = ts >> 8
    for t in range(pistas):
        for h in range(caras):
            tib = bytearray(256)
            tib[0:12] = b'Track-Info\r\n'
            tib[16] = t
            tib[17] = h
            tib[20] = 2
            tib[21] = SECTORES
            tib[22] = 0x2A
            tib[23] = 0xE5
            for s in range(SECTORES):
                o = 24 + s * 8
                tib[o] = t
                tib[o + 1] = h
                tib[o + 2] = s + 1
                tib[o + 3] = 2
            img += tib
            u = t * caras + h
            for s in range(SECTORES):
                k = u * SECTORES + s
                dato = sectores[k] if k < len(sectores) else b'\xE5' * SECTAM
                img += bytes(dato).ljust(SECTAM, b'\x00')
    return bytes(img)


# ---------------------------------------------------------------------------
#  La capa de plataforma
# ---------------------------------------------------------------------------
NXPLOT_PCW = r'''; ---------------------------------------------------------------------------
; nxplot: pinta la matriz de HL en (nxrow,nxcol). La celda son 8 bytes
; seguidos en la fila (ROWADR); el glifo, de 6 pixeles, va centrado.
; ---------------------------------------------------------------------------
nxplot:
        push  hl
        call  pcwcell          ; DE = la celda, con S1 puesto si hace falta
        pop   hl
        ld    b,8
np_l:   ld    a,(hl)
        rrca                   ; bits 7..2 -> 6..1 (el bit 0 del glifo es 0)
        ld    c,a
        ld    a,(nxinv)
        or    a
        ld    a,c
        jr    z,np_n
        cpl                    ; INVERSE: la celda entera al reves
np_n:   ld    (de),a
        inc   hl
        inc   de
        djnz  np_l
        ret

; pcwcell: (nxrow,nxcol) -> DE = direccion de la celda
pcwcell:
        ld    a,(nxrow)
        call  pcwrow           ; DE = principio de la fila
        ld    a,(nxcol)
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl
        add   hl,hl
        add   hl,de
        ex    de,hl
        ret

; pcwrow: A = fila -> DE = su principio (y S1 en la ventana si vive ahi)
pcwrow:
        push  hl
        add   a,a
        ld    e,a
        ld    d,0
        ld    hl,ROWADR
        add   hl,de
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        pop   hl
        ld    a,d
        cp    &40
        ret   c
        ld    a,&80+S1BLK
        out   (&F1),a
        ret

'''

NXCLS_PCW = r'''; ---------------------------------------------------------------------------
; nxcls: borra la ventana de texto (de nxwt hasta abajo). Si empieza arriba
; del todo, la pantalla vuelve a su orden de siempre (ROWADR y roller-RAM) y
; se borra entera. Decide tambien el video inverso: si el papel es mas claro
; que la tinta, la pantalla se ve en inverso.
; ---------------------------------------------------------------------------
nxcls:
        call  pcwinv
        ld    a,(nxwt)
        or    a
        jr    nz,nxc_ven
        call  pcwcanon
        call  pcwclsall
        jr    nxc_cur
nxc_ven:
        ld    b,a
nxc_f:  ld    a,b
        call  pcwclrow
        inc   b
        ld    a,b
        cp    FILAS
        jr    c,nxc_f
nxc_cur:
        ld    a,(nxwt)
        ld    (nxrow),a
        ld    a,(nxwl)
        ld    (nxcol),a
        xor   a
        ld    (nxpcnt),a       ; pantalla limpia: la cuenta de pagina, a cero
        ret

; pcwclrow: A = fila -> sus 720 bytes a cero
pcwclrow:
        push  bc
        call  pcwrow
        ld    h,d
        ld    l,e
        ld    (hl),0
        inc   de
        ld    bc,FILAB-1
        ldir
        pop   bc
        ret

; pcwclsall: las 32 filas en su sitio de siempre, a cero
pcwclsall:
        ld    hl,0
        ld    de,1
        ld    bc,22*FILAB-1
        ld    (hl),0
        ldir
        ld    a,&80+S1BLK
        out   (&F1),a
        ld    hl,&4000
        ld    de,&4001
        ld    bc,10*FILAB-1
        ld    (hl),0
        ldir
        ret

; pcwinv: video inverso si el papel es mas claro que la tinta
pcwinv:
        ld    a,(nxattr)
        ld    b,a
        and   7
        ld    c,a              ; C = tinta
        ld    a,b
        rrca
        rrca
        rrca
        and   7                ; A = papel
        cp    c
        ld    a,&40            ; pantalla visible
        jr    c,pci_n
        jr    z,pci_n
        ld    a,&C0            ; ... y en inverso
pci_n:  out   (&F7),a
        ret

; pcwcanon: ROWADR y roller-RAM en su orden de siempre. Filas 0-21 en S0
; desde &0000; 22-31 en S1 desde &0000 (&4000 en la ventana).
pcwcanon:
        ld    hl,ROWCAN
        ld    de,ROWADR
        ld    bc,FILAS*2
        ldir
        ld    hl,ROLLER
        ld    b,0              ; B = fila
pcn_f:  push  bc
        ld    a,b
        add   a,a
        ld    e,a
        ld    d,0
        push  hl
        ld    hl,ROWCAN
        add   hl,de
        ld    e,(hl)
        inc   hl
        ld    d,(hl)           ; DE = direccion de la fila (CPU)
        pop   hl
        call  pcwrol           ; 8 entradas del roller-RAM desde HL
        pop   bc
        inc   b
        ld    a,b
        cp    FILAS
        jr    c,pcn_f
        ret

; pcwrol: DE = direccion (CPU) del principio de una fila; HL = sus 8
; entradas en el roller-RAM. Bloque = S0 si DE < &4000, si no S1; la
; entrada es bloque<<13 | ((dir & &3FF0) >> 1) | (dir & 7).
pcwrol:
        ld    b,S0BLK*32
        ld    a,d
        cp    &40
        jr    c,prl_0
        ld    b,S1BLK*32
prl_0:  ld    a,d
        and   &3F
        ld    d,a
        srl   d
        rr    e                ; DE = (dir & &3FFF) >> 1  (el bit 3 era 0)
        ld    a,d
        or    b
        ld    d,a
        ld    c,8
prl_l:  ld    (hl),e
        inc   hl
        ld    (hl),d
        inc   hl
        inc   e                ; la linea siguiente, +1 (bits 0-2)
        dec   c
        jr    nz,prl_l
        ret

'''

NXSCROLL_PCW = r'''; ---------------------------------------------------------------------------
; nxscroll: sube una fila la ventana de texto (nxwt..nxwb) sin mover un solo
; byte de pantalla: se rotan sus entradas de ROWADR y del roller-RAM, y la
; fila de arriba, que da la vuelta, se borra y queda abajo.
; ---------------------------------------------------------------------------
nxscroll:
        push  af
        push  bc
        push  de
        push  hl
        ld    a,(nxwt)
        ld    c,a
        ld    a,(nxwb)
        sub   c
        jr    z,nxs_bl         ; ventana de una sola fila
        ld    b,a              ; B = filas que suben
        ; ROWADR: la de arriba se guarda, las demas suben
        ld    a,c
        add   a,a
        ld    e,a
        ld    d,0
        ld    hl,ROWADR
        add   hl,de
        push  hl
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        ld    (pcwtmp),de
        pop   de               ; DE = entrada de la fila de arriba
        ld    h,d
        ld    l,e
        inc   hl
        inc   hl
        push  bc
        ld    a,b
        add   a,a
        ld    c,a
        ld    b,0
        ldir                   ; sube B filas
        ld    hl,(pcwtmp)
        ex    de,hl
        ld    (hl),e
        inc   hl
        ld    (hl),d           ; la de arriba, abajo del todo
        pop   bc
        ; roller-RAM: lo mismo con sus 16 bytes por fila
        ld    a,c
        call  pcwrola          ; HL = entradas de la fila de arriba
        push  hl
        ld    de,pcwtr
        ld    bc,16
        ldir                   ; se guardan
        pop   de               ; DE = destino (la de arriba)
        ld    a,(nxwt)
        ld    c,a
        ld    a,(nxwb)
        sub   c
        ld    h,0
        ld    l,a
        add   hl,hl
        add   hl,hl
        add   hl,hl
        add   hl,hl
        ld    b,h
        ld    c,l              ; BC = 16 * filas que suben
        ld    h,d
        ld    l,e
        push  bc
        ld    bc,16
        add   hl,bc
        pop   bc
        ldir
        ld    hl,pcwtr
        ld    bc,16
        ldir                   ; la de arriba, abajo
nxs_bl: ld    a,(nxwb)
        call  pcwclrow
        pop   hl
        pop   de
        pop   bc
        pop   af
        ret

; pcwrola: A = fila -> HL = sus 8 entradas en el roller-RAM
pcwrola:
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl
        add   hl,hl
        add   hl,hl
        ld    de,ROLLER
        add   hl,de
        ret
pcwtmp: defw  0
pcwtr:  defs  16

; ---------------------------------------------------------------------------
; TXTWIN: H=izquierda L=arriba D=derecha E=abajo, recortado a 90x32.
; ---------------------------------------------------------------------------
TXTWIN:
        ld    a,h
        cp    COLS
        jr    c,nxw_l
        xor   a
nxw_l:  ld    (nxwl),a
        ld    a,l
        cp    FILAS
        jr    c,nxw_t
        xor   a
nxw_t:  ld    (nxwt),a
        ld    a,d
        cp    COLS
        jr    c,nxw_r
        ld    a,COLS-1
nxw_r:  ld    (nxwr),a
        ld    a,e
        cp    FILAS
        jr    c,nxw_b
        ld    a,FILAS-1
nxw_b:  ld    (nxwb),a
        ld    a,(nxwt)
        ld    (nxrow),a
        ld    a,(nxwl)
        ld    (nxcol),a
        ret

'''

SCRBORDER_PCW = r'''; SCRBORDER: el PCW no tiene borde de color
SCRBORDER:
        ret

'''

NXINIT_PCW = r'''; ---------------------------------------------------------------------------
; NXINIT: la pantalla. Roller-RAM en &3E00 del bloque 0 (puerto &F5 = bloque
; en los bits 7-5, direccion/512 en los 4-0), origen vertical 0, controlador
; de video en marcha, todo borrado.
; ---------------------------------------------------------------------------
NXINIT:
        ld    a,4
        out   (&F8),a          ; nada de interrupciones de la controladora
        ld    a,&80+S0BLK
        out   (&F0),a
        call  pcwcanon
        call  pcwclsall
        ld    a,S0BLK*32+ROLLER/512
        out   (&F5),a
        xor   a
        out   (&F6),a
        ld    a,7
        out   (&F8),a          ; controlador de video en marcha
        ld    a,56             ; papel 7, tinta 0... que en el PCW es verde
        ld    (nxattr),a       ; sobre negro: el inverso lo decide nxcls
        ld    a,&40
        out   (&F7),a
        call  pcwkbini
        ld    a,255            ; partida nueva (tambien tras un FIN): ninguna
        ld    (pcwult),a       ; imagen puesta, y la ventana a pantalla completa
        ld    h,0
        ld    l,0
        ld    d,COLS-1
        ld    e,FILAS-1
        call  TXTWIN
        jp    NXL2INIT

'''

SNDREG_PCW = r'''; SNDREG: el PCW no tiene AY. Los efectos guardan su tiempo (MCWAIT por
; frame) y no suenan.
SNDREG:
        ret

'''

KMREAD_PCW = r'''; ---------------------------------------------------------------------------
; KMREAD: lee el teclado SIN bloquear.  CF=1 y A=tecla si se acaba de pulsar
; una. El PCW mapea la matriz en &3FF0-&3FFF del bloque 3 (&FFF0 aqui); se
; comparan &FFF2-&FFFA con la ultima lectura y vale la primera tecla nueva.
; ---------------------------------------------------------------------------
KMREAD:
        push  bc
        push  de
        push  hl
        ld    hl,&FFF2
        ld    de,kbprev
        ld    c,0              ; numero de tecla del primer bit de este byte
km_b:   ld    a,(de)
        cpl
        and   (hl)             ; pulsadas ahora y no antes
        ld    b,a
        ld    a,(hl)
        ld    (de),a
        ld    a,b
        or    a
        jr    z,km_nb
        push  hl
        ld    a,c
km_bit: srl   b
        jr    nc,km_nx
        push  af
        push  bc
        ld    l,a
        ld    h,0
        ld    bc,KEYTAB
        add   hl,bc
        ld    a,(hl)
        pop   bc
        or    a
        jr    nz,km_si
        pop   af
km_nx:  inc   a
        inc   b
        dec   b
        jr    nz,km_bit
        pop   hl
km_nb:  inc   hl
        inc   de
        ld    a,c
        add   a,8
        ld    c,a
        cp    72
        jr    c,km_b
        pop   hl
        pop   de
        pop   bc
        or    a                ; CF=0
        ret
km_si:  pop   bc               ; (el AF guardado)
        pop   hl
        pop   hl
        pop   de
        pop   bc
        scf
        ret

KMW:    call  KMREAD
        jr    nc,KMW
        ret

; pcwkbini: lo que haya pulsado ahora no cuenta como tecla nueva
pcwkbini:
        ld    hl,&FFF2
        ld    de,kbprev
        ld    bc,9
        ldir
        ret

; nxscan: A <> 0 si hay alguna tecla pulsada ahora mismo
nxscan:
        push  bc
        push  hl
        ld    hl,&FFF0
        ld    b,11
        xor   a
ns_l:   or    (hl)
        inc   hl
        djnz  ns_l
        pop   hl
        pop   bc
        ret

kbprev: defs  9
; tecla -> caracter (0 = no es de escribir). Byte n = &FFF2+n, bit b = 8n+b.
; La tecla de ';' (a la derecha de la L) escribe 'n': en el teclado espanol es
; la Ñ, y el vocabulario la guarda sin tilde.
KEYTAB:
        defb  127,0,13,0,'7',0,0,0            ; &FFF2
        defb  '=','-',0,'p',0,'n',0,'.'        ; &FFF3
        defb  '0','9','o','i','l','k','m',','  ; &FFF4
        defb  '8','7','u','y','h','j','n',' '  ; &FFF5
        defb  '6','5','r','t','g','f','b','v'  ; &FFF6
        defb  '4','3','e','w','s','d','c','x'  ; &FFF7
        defb  '1','2',0,'q',0,'a',0,'z'        ; &FFF8
        defb  0,0,0,0,0,0,0,127                ; &FFF9 (el ultimo, <-DEL)
        defb  0,0,0,0,0,13,0,0                 ; &FFFA (ENTER del teclado numerico)

'''

MCWAIT_PCW = r'''MCWAIT:
        push  af
        push  bc
        ld    b,6              ; 6 ticks de 300 Hz = un barrido de 50 Hz
mcw_l:  in    a,(&F4)          ; ticks desde la ultima lectura (y a cero)
        and   &0F
        jr    z,mcw_l
        ld    c,a
        ld    a,b
        sub   c
        ld    b,a
        jr    z,mcw_f
        jr    nc,mcw_l
mcw_f:  pop   bc
        pop   af
        ret
'''

TXTPAGE_PCW = '''        out   (&F1),a
        ret
'''


def plat_asm():
    src = nx.PLAT_ASM
    cr = mx._cambia_rutina
    src = cr(src, 'nxglyph', 'nxplot', mx.NXGLYPH_MSX)
    src = cr(src, 'nxplot', 'nxcls', NXPLOT_PCW)
    src = cr(src, 'nxcls', 'nxscroll', NXCLS_PCW)
    src = cr(src, 'nxscroll', 'SCRATTR', NXSCROLL_PCW)     # con TXTWIN
    src = cr(src, 'SCRBORDER', 'nxcolor', SCRBORDER_PCW)
    tabla = 'NXCOLT' if '\nNXCOLT:' in src else 'NXCOL'
    src = cr(src, 'nxcolor', tabla, mx.NXCOLOR_MSX)
    if '\nNXCOLT:' not in src:
        src = src.replace('\nNXCOL:  defb', '\nNXCOLT: defb')
    src = cr(src, 'NXINIT', 'SCRMODE', NXINIT_PCW)
    src = cr(src, 'SNDREG', 'KMREAD', SNDREG_PCW)
    src = cr(src, 'KMREAD', 'CASOPEN', KMREAD_PCW)
    viejo = 'MCWAIT: ei\n        halt\n        ret\n'
    if src.count(viejo) != 1:
        raise RuntimeError('pcw: no encuentro MCWAIT en PLAT_ASM')
    src = src.replace(viejo, MCWAIT_PCW)
    # el ritmo de escritura esperaba un barrido con EI/HALT: aqui no hay
    # interrupciones
    viejo = '        ei\n        halt\n        xor   a\nnxr_g:'
    if src.count(viejo) != 1:
        raise RuntimeError('pcw: no encuentro char_lento en PLAT_ASM')
    src = src.replace(viejo, '        call  MCWAIT\n        xor   a\nnxr_g:')
    # SCRMODE: la pantalla entera
    viejo = ('SCRMODE:\n        push  af\n        push  bc\n        push  de\n'
             '        push  hl\n        call  nxcls\n')
    if src.count(viejo) != 1:
        raise RuntimeError('pcw: no encuentro SCRMODE en PLAT_ASM')
    src = src.replace(viejo, viejo.replace('call  nxcls', 'call  pcwcls0'))
    src += r'''
; pcwcls0: borrado entero (SCRMODE)
pcwcls0:
        ld    a,(nxwt)
        push  af
        xor   a
        ld    (nxwt),a
        call  nxcls
        pop   af
        ld    (nxwt),a
        ld    (nxrow),a
        ret
'''
    src = nx.con_txtpage(src, TXTPAGE_PCW)
    codigo = '\n'.join(l.split(';', 1)[0] for l in src.split('\n'))
    if re.search(r'(?mi)^[ \t]*(pixelad|pixeldn|nextreg|ldirx|mul|ei|halt)\b', codigo):
        raise RuntimeError('pcw: queda Z80N o EI/HALT en PLAT_ASM')
    if re.search(r'(?i)&(FFFD|BFFD|7FFD|243B|253B)\b', codigo) or \
            re.search(r'(?i)out[ \t]*\((254|&9[89AB]|&A[01])\)', codigo):
        raise RuntimeError('pcw: queda un puerto de otra maquina en PLAT_ASM')
    return src


# ---------------------------------------------------------------------------
#  Imagenes
# ---------------------------------------------------------------------------
IMG_ASM = r'''
; ===========================================================================
;  Imagenes: tira de 11 filas (720x88) de las salas y de SCR, y pantallas
;  enteras (portada y SCR de 32 filas). Todas en ZX0 en sus bloques.
; ===========================================================================
NXL2INIT:
        ret

; PCWPIC: A = localizacion. CF=1 si tiene imagen (y queda pintada).
PCWPIC:
        ld    c,a
        ld    b,0
        ld    hl,LOCIMG
        add   hl,bc
        add   hl,bc
        add   hl,bc            ; 3 bytes por sala: bloque, direccion
        ld    a,(hl)
        or    a
        ret   z                ; CF=0: sin imagen
        ld    a,(pcwult)
        cp    c
        scf
        ret   z                ; ya esta puesta
        ld    a,c
        ld    (pcwult),a
        jp    pcwtira

; PCWNOPIC: la proxima imagen se pinta aunque sea la misma
PCWNOPIC:
        ld    a,255
        ld    (pcwult),a
        ret

; pcwtira: HL -> (bloque, direccion en la ventana) de una tira de 11 filas.
; El bloque del flujo se pone un momento en &0000 (sin interrupciones no
; pasa nada), se descomprime al buffer de S1 y se copia fila a fila a donde
; esten ahora las 11 de arriba (el scroll las pudo mover).
pcwtira:
        ld    a,(hl)
        inc   hl
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        out   (&F0),a          ; el flujo, en &0000
        ld    a,&80+S1BLK
        out   (&F1),a          ; el buffer, en la ventana
        ex    de,hl
        res   6,h              ; &4000-&7FFF -> &0000-&3FFF
        ld    de,TMPBUF
        call  dzx0st
        ld    a,&80+S0BLK
        out   (&F0),a          ; la pantalla, de vuelta
        ld    hl,TMPBUF
        ld    b,0
pct_f:  push  bc
        ld    a,b
        push  hl
        call  pcwrow
        pop   hl
        ld    bc,FILAB
        ldir
        pop   bc
        inc   b
        ld    a,b
        cp    FILATXT
        jr    c,pct_f
        scf
        ret

; pcwentera: HL -> (bloqueA, dirA, bloqueB, dirB): pantalla entera en su
; orden de siempre. A = filas 0-21 en S0; B = filas 22-31 en S1.
pcwentera:
        push  hl
        call  pcwcanon
        pop   hl
        ld    a,(hl)
        inc   hl
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        inc   hl
        push  hl
        out   (&F1),a          ; flujo A en la ventana
        ex    de,hl
        ld    de,0             ; -> S0
        call  dzx0st
        pop   hl
        ld    a,(hl)
        inc   hl
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        out   (&F0),a          ; flujo B en &0000
        ld    a,&80+S1BLK
        out   (&F1),a
        ex    de,hl
        res   6,h
        ld    de,&4000         ; -> S1
        call  dzx0st
        ld    a,&80+S0BLK
        out   (&F0),a
        ld    a,255
        ld    (pcwult),a
        ret
pcwult: defb  255
'''

IMG_ASM_VACIO = r'''
NXL2INIT:
        ret
PCWNOPIC:
        ret
pcwult: defb  255
'''

TITULO_ASM = r'''
; La portada: pantalla entera, sin inverso, hasta que toquen una tecla
PCWTIT:
        ld    a,&40
        out   (&F7),a
        ld    hl,TITIMG
        call  pcwentera
pte_1:  call  MCWAIT
        call  nxscan
        or    a
        jr    nz,pte_1         ; que suelten la de arrancar
pte_2:  call  MCWAIT
        call  nxscan
        or    a
        jr    z,pte_2
        call  pcwkbini         ; esa tecla no es la primera de la orden
        jp    SCRMODE
'''

SCR_ASM = r'''
; ===========================================================================
;  Pantallas sueltas del condact SCR: 7 bytes por pantalla: filas (0, 11 o
;  32) y dos (bloque, direccion); las tiras usan solo el primero.
; ===========================================================================
SHOWSCR:
        cp    NSCR
        jp    nc,ss_no
        ld    b,c
        ld    l,a
        ld    h,0
        ld    e,l
        ld    d,h
        add   hl,hl
        add   hl,hl
        add   hl,hl
        or    a
        sbc   hl,de            ; 7 bytes por entrada
        ld    de,SCRT
        add   hl,de
        ld    a,(hl)
        or    a
        jp    z,ss_no
        ld    (ss_filas),a
        inc   hl
        push  hl
        ld    a,b
        or    a
        jr    z,ss_pinta
        ld    h,0
        ld    l,0
        ld    d,COLS-1
        ld    e,FILAS-1
        call  TXTWIN
        ld    a,12
        call  TXTO
ss_pinta:
        pop   hl
        ld    a,(ss_filas)
        cp    FILAS
        jr    z,ss_ent
        call  pcwtira
        ld    a,255
        ld    (pcwult),a
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
        ret                    ; A = 0: tira
ss_ent: call  pcwentera
        xor   a
        ld    (nxwt),a
        inc   a
        ret                    ; A = 1: pantalla entera
ss_no:  ld    a,255
        ret
SCRREST:
        ret
ss_filas: defb 0
'''


def _engine_pcw(con_imagenes, con_titulo):
    src = s48._engine_48()
    # la ventana a pantalla completa es de 90x32, no de 42x24
    v42 = ('show_loc_image:\n'
           '        ld    h,0\n'
           '        ld    l,0\n'
           '        ld    d,41\n'
           '        ld    e,23\n'
           '        call  TXTWIN\n')
    if src.count(v42) != 1:
        raise RuntimeError('pcw: no encuentro show_loc_image en el motor')
    src = src.replace(v42, v42.replace('d,41', 'd,COLS-1').replace('e,23', 'e,FILAS-1'))
    if con_imagenes:
        viejo = v42.replace('d,41', 'd,COLS-1').replace('e,23', 'e,FILAS-1')
        if False:
            pass
        if src.count(viejo) != 1:
            raise RuntimeError('pcw: no encuentro show_loc_image en el motor')
        nuevo = ('show_loc_image:\n'
                 '        call  is_dark\n'
                 '        or    a\n'
                 '        jr    nz,pcli_no       ; a oscuras no se ve nada\n'
                 '        ld    a,(curloc)\n'
                 '        call  PCWPIC\n'
                 '        jr    nc,pcli_no\n'
                 '        ld    h,0\n'
                 '        ld    l,FILATXT        ; el texto, debajo de la imagen\n'
                 '        ld    d,COLS-1\n'
                 '        ld    e,FILAS-1\n'
                 '        call  TXTWIN\n'
                 '        jr    pcli_cls\n'
                 'pcli_no:\n'
                 '        call  PCWNOPIC\n' + viejo[len('show_loc_image:\n'):] +
                 'pcli_cls:\n')
        src = src.replace(viejo, nuevo)
    if con_titulo:
        viejo_t = 'show_title:\n        ret\n'
        if src.count(viejo_t) != 1:
            raise RuntimeError('pcw: no encuentro show_title en el motor')
        src = src.replace(viejo_t, 'show_title:\n        jp    PCWTIT\n')
    return src


def _rowcan():
    """Direcciones (CPU) de las 32 filas en su orden de siempre."""
    return ([i * FILA_BYTES for i in range(22)] +
            [0x4000 + i * FILA_BYTES for i in range(10)])


def prefijo(org, db_base, borde=7, nloc=256, nscr=0):
    return (nx.prefijo(org, db_base, nimg=0, titulo=False, borde=borde, nloc=nloc) +
            'S48SP equ &%04X\n' % SPPCW +
            'FILATXT equ %d\n' % FILA_TEXTO +
            'NSCR equ %d\n' % nscr +
            'COLS equ %d\nFILAS equ %d\nFILAB equ %d\n' % (COLS, FILAS, FILA_BYTES) +
            'S0BLK equ %d\nS1BLK equ %d\n' % (S0, S1) +
            'ROLLER equ &%04X\nTMPBUF equ &%04X\n' % (ROLLER, TMPBUF))


def ensambla(org=ORG, db_base=None, idioma='es', nloc=256, locimg=None,
             titulo=None, pantallas=None, guion_bk=None):
    """locimg: {loc: (id, dir)}; titulo: (idA, dirA, idB, dirB);
    pantallas: [(filas, idA, dirA, idB, dirB)]."""
    if db_base is None:
        db_base = org
    plat = plat_asm()
    if pantallas:
        plat = nx.con_showscr(plat, SCR_ASM)
    partes = [plat]
    hay_img = bool(locimg) or bool(titulo) or bool(pantallas)
    if hay_img:
        partes.append(IMG_ASM)
        partes.append(s48.DZX0_ASM)
        L = ['LOCIMG:']
        for i in range(max(1, nloc)):
            b, d = (locimg or {}).get(i, (0, 0))
            L.append('        defb %d\n        defw &%04X' % (b, d))
        partes.append('\n'.join(L))
    else:
        partes.append(IMG_ASM_VACIO)
    if titulo:
        partes.append(TITULO_ASM)
        partes.append('TITIMG: defb %d\n        defw &%04X\n'
                      '        defb %d\n        defw &%04X' % titulo)
    if pantallas:
        L = ['SCRT:']
        for f, a, da, b, db in pantallas:
            L.append('        defb %d,%d\n        defw &%04X\n'
                     '        defb %d\n        defw &%04X' % (f, a, da, b, db))
        partes.append('\n'.join(L))
    partes.append('ROWADR: defs %d' % (FILAS * 2))
    partes.append('ROWCAN: defw ' + ','.join('&%04X' % a for a in _rowcan()))
    partes.append(nx.PSG_ASM_VACIO)
    partes.append(nx.SMP_ASM_VACIO)
    fuente = (prefijo(org, db_base, nloc=nloc, nscr=len(pantallas or ())) +
              _engine_pcw(bool(locimg), bool(titulo)) +
              chr(10).join(partes) + chr(10) +
              nx._font_asm(idioma) + chr(10))
    if guion_bk is not None:
        fuente = _modo_prueba(fuente, guion_bk)
    return z80asm.assemble(fuente, org=org)


# ---------------------------------------------------------------------------
#  Modo prueba (bateria_pcw.py): como el del MSX2
# ---------------------------------------------------------------------------
PRUEBA_PCW_ASM = r'''
; --- modo prueba PCW ------------------------------------------------------
mgbk:   defb  PCWGUIONBK
mgp:    defw  &4000
PCWFIN:
        ld    hl,NXT_FIN
        call  nxtrs
        call  NXDUMP
        out   (&2D),a          ; la bateria cierra el emulador aqui
pcwf_l: jr    pcwf_l
'''


def _modo_prueba(src, guion_bk):
    def cambia(viejo, nuevo):
        if src.count(viejo) != 1:
            raise ValueError('pcw modo prueba: %r aparece %d veces'
                             % (viejo[:40], src.count(viejo)))
        return src.replace(viejo, nuevo, 1)

    src = cambia('TXTO:\n        push  af\n',
                 'TXTO:\n        out   (&2F),a       ; modo prueba: traza\n'
                 '        push  af\n')
    i = src.index('\nKMREAD:\n')
    j = src.index('\nKMW:', i)
    src = src[:i + 1] + r'''KMREAD:
        push  hl
mg_l:   ld    a,(mgbk)
        out   (&F1),a
        ld    hl,(mgp)
        ld    a,(hl)
        or    a
        jr    z,mg_fin
        inc   hl
        bit   7,h
        jr    z,mg_ok
        ld    hl,mgbk
        inc   (hl)
        ld    hl,&4000
mg_ok:  ld    (mgp),hl
        cp    1
        jr    z,mg_vol
        cp    2
        jr    z,mg_res
        pop   hl
        scf
        ret
mg_vol: call  NXDUMP
        jr    mg_l
mg_res: ld    hl,NXT_RES
        call  nxtrs
        ld    sp,S48SP
        jp    start
mg_fin: pop   hl
        jp    PCWFIN
''' + src[j + 1:]
    src = cambia('KMW:    call  KMREAD\n        jr    nc,KMW\n        ret\n',
                 'KMW:    ld    a,32          ; modo prueba: ni espera ni gasta\n'
                 '        ret\n')
    src = cambia('        ld    de,SOTRA\n        call  print_msg\n        call  KMW\n',
                 '        ld    de,SOTRA\n        call  print_msg\n'
                 'mgo_l:  call  KMREAD         ; modo prueba: hasta el #RESET\n'
                 '        jr    mgo_l\n')
    src = cambia('        call  MCWAIT\n        xor   a\nnxr_g:',
                 '        xor   a\nnxr_g:')
    if '\nPCWTIT:\n' in src:
        src = cambia('PCWTIT:\n', 'PCWTIT:\n        ret\n')
    return ('NXTRAZA equ &002F\nNXGUION equ &4000\n'
            'PCWGUIONBK equ %d\n' % guion_bk +
            src + nx.PRUEBA_ASM + PRUEBA_PCW_ASM + '\n')


# ---------------------------------------------------------------------------
#  Conversion de imagenes: monocromo, 720 de ancho, en celdas de 8x8
# ---------------------------------------------------------------------------
# Bayer 8x8: mas ordenado que Floyd-Steinberg, y comprime casi el doble (unos
# 4 KB por tira en vez de 7), que en un disco de 180K es la diferencia entre
# que quepan las imagenes o no.
BAYER8 = [[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
          [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
          [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
          [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]]


def convierte(path, filas, auto=True):
    """Imagen -> bytes de pantalla del PCW de `filas` filas de caracteres
    (720 x filas*8), en el orden de la memoria: fila, celda, linea."""
    from PIL import Image, ImageOps
    im = Image.open(path).convert('L')
    im = im.resize((720, filas * 8), Image.LANCZOS)
    if auto:
        im = ImageOps.autocontrast(im, cutoff=2)
    px = im.load()
    out = bytearray(filas * FILA_BYTES)
    for r in range(filas):
        for c in range(90):
            for k in range(8):
                y = r * 8 + k
                fila_b = BAYER8[y & 7]
                v = 0
                for b in range(8):
                    x = c * 8 + b
                    if px[x, y] * 64 > (fila_b[x & 7] * 256 + 128):
                        v |= 0x80 >> b
                out[r * FILA_BYTES + c * 8 + k] = v
    return bytes(out)


def busca_imagen(game_dir, nombre):
    """img/PCW/<id> manda (ya es la version definitiva); si no, img/Original."""
    if not game_dir:
        return None
    cands = [nombre, nombre.lstrip('@'), '@' + nombre.lstrip('@')]
    for sub in ('PCW', 'Original'):
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


def _zx0(raw, cache_dir=None):
    import hashlib
    import spectrum_export as sx
    if cache_dir:
        h = hashlib.sha1(raw).hexdigest()
        p = os.path.join(cache_dir, h + '.zx0')
        if os.path.isfile(p):
            return open(p, 'rb').read()
    comp = bytes(sx.zx0_comprime(raw, offset_limit=1024))
    if cache_dir:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            open(p, 'wb').write(comp)
        except OSError:
            pass
    return comp


# ---------------------------------------------------------------------------
#  Compilar y empaquetar
# ---------------------------------------------------------------------------
def compila(game, game_dir=None, guion=None, imagenes=True, modelo='8256'):
    """Devuelve (discos, info). `modelo` '8256': un disco de 180K que
    arranca solo, discos = bytes. '8512': discos = (A, B), el de arranque y el
    de datos de 720K para la unidad B."""
    dos = str(modelo) == '8512'
    capacidad = CAPACIDAD_B if dos else CAPACIDAD
    max_blk = MAX_BLK_8512 if dos else MAX_BLK
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
    cache = os.path.join(game_dir, 'temp', 'PCW') if game_dir else None
    salas = []
    if imagenes and game_dir:
        for i, lid in enumerate(c.locids):
            p = busca_imagen(game_dir, lid)
            if p:
                salas.append((i, lid, p))
    portada = busca_imagen(game_dir, 'screen') if (imagenes and game_dir) else None

    ficha = scriba_info.ficha(game, 'pcw', scriba_info.ahora())
    spec, _ = nc.compile_game(c, sysm[:ge.NSYS], width=COLS, filas=0,
                              ficha=ficha, imagen_intro=bool(salas))
    idioma = str((game.get('metadata') or {}).get('language', '') or 'es')
    nlocs = len(spec['locations'])
    ids = [0x80 + b for b in range(BLK0, max_blk)]
    texto = dict(ventana=0x4000, tam=BANCO, ids=ids)

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
    texto_bytes = sum(len(b) for b in bancos) - len(fx_blob)

    # Imagenes en ZX0, detras del texto, sin cruzar de un bloque a otro. Lo
    # que no quepa en el disco se queda fuera, empezando por la portada y
    # siguiendo por las ultimas salas; se avisa.
    flujos = []                      # (clave, bytes)
    for i, lid, p in salas:
        try:
            flujos.append((('sala', i), _zx0(convierte(p, FILA_TEXTO,
                                                       _es_original(p)), cache)))
        except Exception as e:
            avisos.append('imagen de %s: %s' % (lid, e))
    pant = []
    for k, nombre in enumerate(spec.get('pantallas') or []):
        p = busca_imagen(game_dir, nombre) if (imagenes and game_dir) else None
        if not p:
            avisos.append('SCR %s: no hay imagen en img/PCW ni img/Original' % nombre)
            continue
        try:
            from PIL import Image
            w, h = Image.open(p).size
            if w >= 3 * h:
                flujos.append((('scr', k, 0), _zx0(convierte(p, FILA_TEXTO,
                                                             _es_original(p)), cache)))
                pant.append((k, FILA_TEXTO))
            else:
                raw = convierte(p, FILAS, _es_original(p))
                flujos.append((('scr', k, 0), _zx0(raw[:22 * FILA_BYTES], cache)))
                flujos.append((('scr', k, 1), _zx0(raw[22 * FILA_BYTES:], cache)))
                pant.append((k, FILAS))
        except Exception as e:
            avisos.append('SCR %s: %s' % (nombre, e))
    if portada:
        try:
            raw = convierte(portada, FILAS, _es_original(portada))
            flujos.append((('tit', 0), _zx0(raw[:22 * FILA_BYTES], cache)))
            flujos.append((('tit', 1), _zx0(raw[22 * FILA_BYTES:], cache)))
        except Exception as e:
            avisos.append('portada: %s' % e)

    def _coloca(flujos):
        bk = [bytearray(b) for b in bancos]
        donde = {}
        if flujos:
            bk2, pos = ge.empaqueta_en_bancos([f for _, f in flujos], bancos=bk)
            bk = bk2
            for (clave, _f), (bi, off) in zip(flujos, pos):
                donde[clave] = (ids[bi] if bi < len(ids) else 0, 0x4000 + off)
        return bk, donde

    code = db = None

    def _total(bk, codelen):
        return (len(bk) * BANCO + codelen)

    # dos pasadas para el motor: su tamano no depende de donde caigan las
    # imagenes, pero si de cuales hay
    fuera = []
    while True:
        bk, donde = _coloca(flujos)
        locimg = {k[1]: v for k, v in donde.items() if k[0] == 'sala'}
        titulo = ((donde[('tit', 0)] + donde[('tit', 1)])
                  if ('tit', 0) in donde else None)
        scrs = []
        for k, _n in enumerate(spec.get('pantallas') or []):
            filas = dict(pant).get(k, 0)
            if not filas or ('scr', k, 0) not in donde:
                scrs.append((0, 0, 0, 0, 0))
            elif filas == FILAS:
                scrs.append((FILAS,) + donde[('scr', k, 0)] + donde[('scr', k, 1)])
            else:
                scrs.append((FILA_TEXTO,) + donde[('scr', k, 0)] + (0, 0))

        def _asm(base, gbk=None):
            return ensambla(org=ORG, db_base=base, idioma=idioma, nloc=nlocs,
                            locimg=locimg, titulo=titulo, pantallas=scrs,
                            guion_bk=gbk)
        gbk = None if guion is None else 0x80 + BLK0 + len(bk)
        code, _s = _asm(ORG, gbk)
        dbaddr = ORG + len(code)
        db, info_db = _db(dbaddr)
        code, sym = _asm(dbaddr, gbk)
        assert ORG + len(code) == dbaddr
        imagen = code + db
        nguion = 0 if guion is None else (len(guion) + BANCO) // BANCO
        if guion is None:
            ocupa = (len(bk) - 1) * BANCO + len(bk[-1]) + len(imagen) if bk else len(imagen)
        else:
            ocupa = (len(bk) + nguion) * BANCO + len(imagen)
        nblk = (ocupa + BANCO - 1) // BANCO
        if (ocupa <= capacidad and BLK0 + nblk <= max_blk
                and all(v[0] for v in donde.values())):
            break
        if not flujos:
            raise ValueError('el juego no cabe en el disco de 180K (%d bytes)' % ocupa)
        # fuera la portada primero, luego la ultima imagen
        tit = [f for f in flujos if f[0][0] == 'tit']
        quita = tit if tit else [flujos[-1]]
        for f in quita:
            flujos.remove(f)
        fuera.append(quita[0][0])
    for j, b in enumerate(info_db['bancos_texto']):
        assert bytes(bk[j][:len(b)]) == bytes(b), 'el texto se movio de bloque'
    if fuera:
        avisos.append('no cabe todo en el disco de %s: fuera %s'
                      % ('720K' if dos else '180K',
                         ', '.join('portada' if k[0] == 'tit' else
                                   ('SCR %d' % k[1] if k[0] == 'scr' else
                                    'imagen de %s' % c.locids[k[1]])
                                   for k in fuera)))
    fin = ORG + len(imagen)
    presupuesto.comprueba(
        'Amstrad PCW',
        [('motor + plataforma', len(code)),
         ('base de datos (sin el texto)', len(db))],
        TOPE - ORG, 'la RAM de &%04X a &%04X (bajo la pila y el teclado)'
        % (ORG, TOPE), presupuesto.RECORTA_PLANO, primero=True)

    # El flujo del disco: los bloques de datos (cada uno en su sitio de 16K,
    # menos el ultimo, que no se rellena), el guion de la bateria si lo hay
    # (en bloques enteros) y la imagen del motor, pegada detras: el cargador
    # la copia de ahi a &8000 byte a byte, cruzando de bloque cuando toca.
    flujo = bytearray()
    for b in bk[:-1]:
        flujo += bytes(b).ljust(BANCO, b'\x00')
    if bk:
        flujo += bytes(bk[-1])
    if guion is not None:
        flujo = flujo.ljust(len(bk) * BANCO, b'\x00')
        flujo += (bytes(guion) + b'\x00').ljust(nguion * BANCO, b'\x00')
    imgoff = len(flujo)
    flujo += imagen
    nsect = (len(flujo) + SECTAM - 1) // SECTAM
    arranque, nunid = sector_arranque(nsect, imgoff, len(imagen), sym['start'],
                                      unidad_b=dos)
    datos = [bytes(flujo[i:i + SECTAM]).ljust(SECTAM, b'\x00')
             for i in range(0, len(flujo), SECTAM)]
    npis = (nunid + 1) // 2 if dos else nunid
    info = {'codigo': len(code), 'datos': len(db), 'org': ORG, 'db': dbaddr,
            'fin': fin, 'libre': TOPE - fin, 'bloques': len(bk),
            'disco': len(flujo) + (0 if dos else SECTAM), 'capacidad': capacidad,
            'modelo': '8512' if dos else '8256', 'imagenes': sorted(locimg),
            'portada': bool(titulo), 'pantallas': [n for k, n in
                                                   enumerate(spec.get('pantallas') or [])
                                                   if scrs[k][0]],
            'localizaciones': nlocs, 'objetos': len(spec['objects']),
            'texto': texto_bytes, 'avisos': avisos, 'sym': sym,
            'pistas': npis, 'flujo': bytes(flujo), 'imgoff': imgoff}
    presupuesto.comprueba(
        'Amstrad PCW',
        [('texto del juego', texto_bytes), ('efectos FX', len(fx_blob)),
         ('imagenes y portada', sum(len(f) for _, f in flujos)),
         ('motor + base de datos', len(imagen))],
        capacidad, 'el disco de 720K de la unidad B' if dos else
        'el disco de 180K (CF2, una cara)', presupuesto.RECORTA_BANCOS)
    if dos:
        return (dsk([arranque]), dsk(datos, PISTAS_B, CARAS_B)), info
    return dsk([arranque] + datos), info


def _es_original(path):
    return os.path.basename(os.path.dirname(path)).lower() == 'original'


def nombre_b(dsk_path):
    """El disco de datos del modo 8512: el mismo nombre con _B."""
    base, ext = os.path.splitext(dsk_path)
    return base + '_B' + (ext or '.dsk')


def export_dsk(game, dsk_path, game_dir=None, imagenes=True, modelo='8256'):
    """Escribe el disco (8256) o los dos discos (8512: `dsk_path` es el de
    arranque, para la unidad A, y el de datos va al lado con _B)."""
    import presupuesto
    presupuesto.empieza()
    discos, info = compila(game, game_dir=game_dir, imagenes=imagenes, modelo=modelo)
    if info['modelo'] == '8512':
        a, b = discos
        with open(dsk_path, 'wb') as f:
            f.write(a)
        info['disco_b'] = nombre_b(dsk_path)
        with open(info['disco_b'], 'wb') as f:
            f.write(b)
    else:
        with open(dsk_path, 'wb') as f:
            f.write(discos)
    info['presupuesto'] = presupuesto.informe()
    return info


def main():
    import argparse
    import yaml
    ap = argparse.ArgumentParser(
        description='Compila un juego de Scriba a disco autoarrancable de Amstrad PCW.')
    ap.add_argument('yaml')
    ap.add_argument('dsk', nargs='?')
    ap.add_argument('--sin-imagenes', action='store_true')
    ap.add_argument('--8512', dest='pcw8512', action='store_true',
                    help='dos discos: arranque (unidad A) y datos de 720K (unidad B)')
    a = ap.parse_args()
    game = yaml.safe_load(open(a.yaml, encoding='utf-8'))
    salida = a.dsk or (a.yaml.rsplit('.', 1)[0] + '_pcw.dsk')
    info = export_dsk(game, salida, game_dir=os.path.dirname(os.path.abspath(a.yaml)),
                      imagenes=not a.sin_imagenes,
                      modelo='8512' if a.pcw8512 else '8256')
    if info['modelo'] == '8512':
        print('PCW 8512: arranque (unidad A) %s + datos (unidad B) %s'
              % (salida, info['disco_b']))
    else:
        print('Disco PCW autoarrancable: %s' % salida)
    print('  en el disco      : %6d bytes de %d (%d pistas)'
          % (info['disco'], info['capacidad'], info['pistas']))
    print('  motor+plataforma : %6d bytes  (&%04X-&%04X)'
          % (info['codigo'], info['org'], info['db'] - 1))
    print('  base de datos    : %6d bytes  (&%04X-&%04X)'
          % (info['datos'], info['db'], info['fin'] - 1))
    print('  libre bajo la pila: %d bytes' % info['libre'])
    print('  %d localizaciones, %d objetos, %d imagenes%s'
          % (info['localizaciones'], info['objetos'], len(info['imagenes']),
             ', portada' if info['portada'] else ''))
    if info['pantallas']:
        print('  pantallas SCR: %s' % ', '.join(info['pantallas']))
    for av in info['avisos']:
        print('  AVISO: %s' % av)


if __name__ == '__main__':
    main()
