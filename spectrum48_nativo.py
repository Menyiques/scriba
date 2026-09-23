# -*- coding: utf-8 -*-
"""
spectrum48_nativo.py - Capa de plataforma ZX Spectrum 48K para el motor nativo Z80.

Sondeo (spike): comprobar si el motor nativo Z80 -- el mismo que ya mueve el
Amstrad CPC y el ZX Spectrum Next -- puede correr en un 48K de verdad, sin
Boriel BASIC por medio, y cuanto ocupa.

La respuesta corta es que la capa de plataforma del Next YA es un 48K: imprime
sobre la pantalla ULA de &4000, lee el teclado por la matriz del puerto &FE y
no toca la ROM para nada. Lo unico que la ata al Next son SIETE instrucciones
Z80N (PIXELAD, PIXELDN, ADD HL,A y ADD HL,nn) y la parte de Layer 2, que aqui
no se usa. Asi que este modulo NO reescribe el impresor: coge
next_nativo.PLAT_ASM tal cual y le cambia esas siete lineas por Z80 normal.

Mapa de memoria (identico al del Next sin imagenes):
    &0000-&3FFF   ROM (no se usa; solo la RST 38 de la interrupcion)
    &4000-&5AFF   pantalla ULA
    &5B00-&5BFF   libre (MTABLE, sin uso en esta plataforma)
    &5C00-&5CB5   variables del sistema (intactas: la interrupcion IM1 sigue viva)
    &6000-....    motor + capa de plataforma + base de datos
    ....-&FF00    libre
    &FF00         pila

Uso:
    python spectrum48_nativo.py juego.yaml [salida.tap]
"""
import os
import re

import game_engine as ge
import next_nativo as nx
import z80asm

ORG = 0x6000          # igual que el Next: justo encima de la pantalla ULA
SP48 = 0xFF00         # pila del juego (por debajo de la zona de UDG de la ROM)
COLS = nx.COLS        # 42 columnas, la misma fuente de 6 pixeles


# ---------------------------------------------------------------------------
#  Las siete instrucciones Z80N de la capa de plataforma, en Z80 normal
# ---------------------------------------------------------------------------
Z80N_ASM = r'''
; ===========================================================================
;  Sustitutos Z80 de las instrucciones Z80N que usa la capa de plataforma
; ===========================================================================
; El Next trae PIXELAD y PIXELDN en silicio. En un 48K hay que hacerlas a mano,
; que es lo que lleva haciendose desde 1982. Las dos respetan todos los
; registros menos A y los flags, que es justo lo que los dos sitios donde se
; llaman pueden permitirse.

; p48ad: D = linea de pixeles (0..191), E = columna en pixeles -> HL = byte de
; pantalla que la contiene. Es el PIXELAD del Next.
;   H = &40 | ((Y & &C0) >> 3) | (Y & 7)
;   L = ((Y & &38) << 2) | (X >> 3)
p48ad:  ld    a,d
        and   &07
        ld    h,a              ; H = Y & 7  (linea dentro del caracter)
        ld    a,d
        rrca
        rrca
        rrca
        and   &18              ; tercio de pantalla
        or    &40
        or    h
        ld    h,a
        ld    a,d
        rlca
        rlca
        and   &E0              ; fila de caracteres dentro del tercio
        ld    l,a
        ld    a,e
        rrca
        rrca
        rrca
        and   &1F              ; columna / 8
        or    l
        ld    l,a
        ret

; p48dn: HL = la MISMA columna, una linea de pixeles mas abajo. Es el PIXELDN
; del Next. Sube la linea dentro del caracter; si desborda, baja una fila de
; caracteres; si tambien desborda, baja de tercio.
p48dn:  inc   h
        ld    a,h
        and   7
        ret   nz               ; seguimos dentro del mismo caracter
        ld    a,h
        sub   8
        ld    h,a
        ld    a,l
        add   a,32
        ld    l,a
        ret   nc               ; seguimos dentro del mismo tercio
        ld    a,h
        add   a,8
        ld    h,a
        ret
'''


def sin_z80n(src):
    """PLAT_ASM del Next -> el mismo codigo sin instrucciones Z80N.

    Son siete lineas contadas y ninguna esta en un sitio comprometido:
      - los dos PIXELAD y el PIXELDN pasan a CALL (solo gastan A, que en ambos
        sitios se recarga en la instruccion siguiente);
      - los dos ADD HL,nn (tablas NXFONT y NXCOL) pasan a LD DE,nn + ADD HL,DE
        con DE guardado, que no cuesta nada y no hay que auditar al llamador;
      - el par ADD HL,A + ADD HL,&5800 del calculo de la direccion de atributo
        pasa a DE, que ahi esta libre (lo unico vivo es HL).
    """
    n = [0]

    def cuenta(txt):
        n[0] += 1
        return txt

    # ADD HL,A seguido de ADD HL,&5800 -> direccion del atributo, via DE.
    src = re.sub(
        r'(?m)^([ \t]*)add[ \t]+hl,a[ \t]*;[^\n]*\n[ \t]*add[ \t]+hl,&5800[^\n]*$',
        lambda m: cuenta(
            m.group(1) + 'ld    e,a\n' +
            m.group(1) + 'ld    d,0\n' +
            m.group(1) + 'add   hl,de           ; + X/8\n' +
            m.group(1) + 'ld    de,&5800\n' +
            m.group(1) + 'add   hl,de           ; + base de atributos'),
        src)

    # ADD HL,nn sobre una tabla con nombre.
    src = re.sub(
        r'(?m)^([ \t]*)add[ \t]+hl,'
        r'(?!(?:af|bc|de|hl|sp|ix|iy|[abcdehl])\b)'
        r'([A-Za-z_][A-Za-z0-9_]*)[ \t]*;[^\n]*$',
        lambda m: cuenta(
            m.group(1) + 'push  de\n' +
            m.group(1) + 'ld    de,' + m.group(2) + '\n' +
            m.group(1) + 'add   hl,de\n' +
            m.group(1) + 'pop   de'),
        src)

    src = re.sub(r'(?m)^([ \t]*)pixelad\b[^\n]*$',
                 lambda m: cuenta(m.group(1) + 'call  p48ad'), src)
    src = re.sub(r'(?m)^([ \t]*)pixeldn\b[^\n]*$',
                 lambda m: cuenta(m.group(1) + 'call  p48dn'), src)

    if n[0] != 6:            # 6 sustituciones = 7 instrucciones (una es un par)
        raise RuntimeError('sin_z80n: esperaba 6 sustituciones, hice %d. '
                           'Ha cambiado PLAT_ASM.' % n[0])
    sobra = re.search(r'(?mi)^[ \t]*(pixelad|pixeldn|swapnib|mul|ldirx|ldix|'
                      r'nextreg|outinb|mirror|bsla|bsrl|bsrf|brlc|test)\b', src)
    if sobra:
        raise RuntimeError('sin_z80n: queda Z80N sin traducir: %r'
                           % sobra.group(0).strip())
    sobra = re.search(r'(?mi)^[ \t]*add[ \t]+(hl|de|bc),[ \t]*(a|&|[0-9])', src)
    if sobra:
        raise RuntimeError('sin_z80n: queda ADD rr,A/nn sin traducir: %r'
                           % sobra.group(0).strip())
    return src


# ---------------------------------------------------------------------------
#  El motor
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
#  dzx0_standard (Einar Saukas & Urusergi), con las etiquetas renombradas.
#  Es el mismo descompresor que usaba el export de BASIC, byte por byte.
#  HL = flujo comprimido, DE = destino. Lo comparten el 48K (pantallas SCR en
#  el mapa plano) y el 128K (imagenes, portada y pantallas en los bancos).
# ---------------------------------------------------------------------------
DZX0_ASM = r'''
dzx0st: ld    bc,&FFFF
        push  bc
        inc   bc
        ld    a,&80
dzx0li: call  dzx0el
        ldir
        add   a,a
        jr    c,dzx0no
        call  dzx0el
dzx0cp: ex    (sp),hl
        push  hl
        add   hl,de
        ldir
        pop   hl
        ex    (sp),hl
        add   a,a
        jr    nc,dzx0li
dzx0no: pop   bc
        ld    c,&FE
        call  dzx0lo
        inc   c
        ret   z
        ld    b,c
        ld    c,(hl)
        inc   hl
        rr    b
        rr    c
        push  bc
        ld    bc,1
        call  nc,dzx0bt
        inc   bc
        jr    dzx0cp
dzx0el: inc   c
dzx0lo: add   a,a
        jr    nz,dzx0sk
        ld    a,(hl)
        inc   hl
        rla
dzx0sk: ret   c
dzx0bt: add   a,a
        rl    c
        rl    b
        jr    dzx0lo
'''

# ---------------------------------------------------------------------------
#  Pantallas sueltas (condact SCR) en Spectrum: 48K y 128K
# ---------------------------------------------------------------------------
# SCRT lleva 5 bytes por pantalla: el flujo del bitmap, el de los atributos y
# las filas. Los flujos van como los lee SCRUN en cada maquina: en el 48K es
# dzx0st y son direcciones del mapa plano; en el 128K es s128un y son
# desplazamientos/2 dentro de los bancos. SCRUN es una etiqueta que cada
# maquina pone delante de su rutina (un equ a una etiqueta posterior no
# resuelve en z80asm). Filas: 8 (tira arriba, texto
# debajo, dos flujos como una imagen de sala), 24 (pantalla entera, un solo
# flujo de 6912 como la portada) o 0 (no esta en esta maquina: no pinta).
SCR_ASM = r'''
SHOWSCR:
        cp    NSCR
        jr    nc,ss_no
        ld    b,c              ; B = 1: borrar toda la pantalla antes
        ld    e,a
        ld    d,0
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl
        add   hl,de            ; 5 bytes por entrada
        ld    de,SCRT
        add   hl,de
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        inc   hl
        ld    (ss_ob),de
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        inc   hl
        ld    (ss_oa),de
        ld    a,(hl)
        or    a
        jr    z,ss_no          ; esta pantalla no esta en esta maquina
        ld    (ss_filas),a
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
        di
        ld    de,&4000
        ld    hl,(ss_ob)
        call  SCRUN
        ld    a,(ss_filas)
        cp    24
        jr    z,ss_ent
        ld    de,&5800
        ld    hl,(ss_oa)
        call  SCRUN            ; atributos de la tira
        ei
        ; La ventana de texto pasa a empezar debajo de la tira, pero SIN mover
        ; el cursor si ya cae dentro: al cambiar la imagen de la sala en mitad
        ; de una respuesta, el texto tiene que seguir donde iba. TXTWIN lo
        ; mandaria a la esquina y la respuesta se escribiria encima de lo de
        ; antes.
        ld    a,FILATXT
        ld    (nxwt),a
        ld    a,(nxrow)
        cp    FILATXT
        jr    nc,ss_8          ; el cursor ya esta debajo de la tira
        ld    a,FILATXT
        ld    (nxrow),a
        xor   a
        ld    (nxcol),a
        ld    (col),a
ss_8:   xor   a
        ret                    ; A = 0: 8 filas
ss_ent: ei
        xor   a
        ld    (nxwt),a         ; ventana entera: lo que se imprima ira encima
        inc   a
        ret                    ; A = 1: 24 filas; se queda hasta CLS o DESC
ss_no:  ld    a,255
        ret
; En Spectrum la pantalla entera se va con el propio CLS (la ventana de texto
; quedo a pantalla completa): no hay modo que restaurar.
SCRREST:
        ret
ss_ob:  defw 0
ss_oa:  defw 0
ss_filas: defb 0
'''


def tabla_scr_asm(entradas):
    """SCRT a partir de [(bitmap, atributos, filas)], con los flujos ya en la
    unidad de la maquina (direccion o desplazamiento/2): texto de ensamblador."""
    L = ['SCRT:']
    for b, a, filas in entradas:
        L.append('        defw %s,%s' % (b, a))
        L.append('        defb %d' % filas)
    return chr(10).join(L)


def pantallas_asm_48(pant):
    """Las pantallas del 48K, como datos del propio binario: cada flujo con su
    etiqueta, y la tabla SCRT apuntandolos. `pant` es lo que devuelve
    spectrum_export.pantallas_spectrum."""
    partes, entradas = [], []
    for i, (nombre, filas, flujos) in enumerate(pant):
        if not flujos:
            entradas.append(('0', '0', 0))
            continue
        etq = ['scr%db' % i, 'scr%da' % i][:len(flujos)]
        for e, f in zip(etq, flujos):
            partes.append(nx._datos_asm(e, f))
        entradas.append((etq[0], etq[1] if len(etq) > 1 else '0', filas))
    return chr(10).join(partes) + chr(10) + tabla_scr_asm(entradas)


def _engine_48():
    """ENGINE_ASM adaptado. Se parte del parche que ya hace el Next sin imagenes
    ni portada (detect128 -> NXINIT, show_title -> ret, show_loc_image -> ventana
    a pantalla completa, wrap_print -> char_lento) y solo se le anade la pila:
    en el CPC la pone el firmware y en el Next la cabecera del .nex, pero aqui
    entramos desde un RANDOMIZE USR con la pila de BASIC, que es de juguete."""
    src = nx._engine_next(False, False)
    i = src.index('start:  call  init')
    return (src[:i] +
            'start:  ld    sp,S48SP      ; la pila de BASIC no da para el motor\n'
            '        call  init' +
            src[i + len('start:  call  init'):])


def prefijo(org, db_base, borde=7, sp=SP48, ntxt=0, nscr=0, nloc=256):
    return (nx.prefijo(org, db_base, nimg=0, titulo=False, borde=borde, ntxt=ntxt,
                       nloc=nloc) +
            'S48SP equ &%04X\n' % sp +
            'FILATXT equ %d\n' % nx.FILA_TEXTO +
            'NSCR equ %d\n' % nscr)


def ensambla(org=ORG, db_base=None, idioma='es', borde=7, guion=None,
             pantallas=None, nloc=256):
    """Ensambla motor + capa de plataforma 48K. Devuelve (bytes, simbolos).
    Con `guion`, sale en MODO PRUEBA: el binario lleva dentro la partida, se
    teclea solo y copia lo que imprime a un puerto (ver bateria_next).
    `pantallas`: lo de spectrum_export.pantallas_spectrum; van como datos del
    binario y se pintan con el dzx0 desde el mapa plano."""
    if db_base is None:
        db_base = org
    plat = sin_z80n(nx.PLAT_ASM)
    extra = ''
    if pantallas:
        plat = nx.con_showscr(plat, SCR_ASM)
        # SCRUN es una ETIQUETA, no un equ: z80asm no resuelve un equ a una
        # etiqueta que viene despues (ya nos paso con el CPC).
        extra = ('SCRUN:' + DZX0_ASM + chr(10) +
                 pantallas_asm_48(pantallas) + chr(10))
    fuente = (prefijo(org, db_base, borde, nscr=len(pantallas or ()), nloc=nloc) +
              _engine_48() +
              plat + chr(10) +
              Z80N_ASM + chr(10) +
              nx.IMG_ASM_VACIO + chr(10) +
              nx.SMP_ASM_VACIO + chr(10) +   # el 48K no lleva AY
              extra +
              nx._font_asm(idioma) + chr(10))
    if guion is not None:
        fuente = nx._modo_prueba(fuente, guion, maquina='48', sp=SP48)
    return z80asm.assemble(fuente, org=org)


# ---------------------------------------------------------------------------
#  Empaquetado .nex para la bateria de emulador
# ---------------------------------------------------------------------------
BANCO_GUION = 17          # el guion del modo prueba, lejos de los bancos 0-7


def bancos_planos(plano, org):
    """El mapa plano repartido en los bancos de 16K que ve un 128K/Next:
    &4000-&7FFF = banco 5, &8000-&BFFF = banco 2, &C000-&FFFF = banco 0."""
    bancos = {}
    for slot, bk in ((0x4000, 5), (0x8000, 2), (0xC000, 0)):
        trozo = bytearray(16384)
        hay = False
        for i, b in enumerate(plano):
            a = org + i
            if a & 0xC000 == slot:
                trozo[a - slot] = b
                hay = True
        if hay:
            bancos[bk] = bytes(trozo)
    return bancos


def bancos_guion(guion, base=BANCO_GUION):
    """El guion troceado en paginas de 8K consecutivas, dos por banco: es como
    lo lee el motor, por una ventana sobre la ROM que va pasando de pagina."""
    pags = [guion[i:i + 8192].ljust(8192, b'\x00')
            for i in range(0, max(1, len(guion)), 8192)]
    return {base + k // 2: pags[k] + (pags[k + 1] if k + 1 < len(pags)
                                      else b'\x00' * 8192)
            for k in range(0, len(pags), 2)}


def export_nex_prueba(game, salida, guion, ancho=COLS, org=ORG, game_dir=None):
    """El 48K en MODO PRUEBA, envuelto en un .nex para que lo arranque jnext.

    El artefacto que se distribuye sigue siendo el .tap; esto es el mismo
    binario metido en el contenedor que el emulador sabe cargar, mas el guion
    de la bateria en sus bancos. Lo que se prueba es el motor y la base de
    datos de 48K reales, no el cargador BASIC de la cinta."""
    import empaqueta_nex
    code, db, sym, spec, dbaddr = compila(game, ancho=ancho, org=org, guion=guion,
                                          game_dir=game_dir)
    plano = code + db
    bancos = bancos_planos(plano, org)
    bancos.update(bancos_guion(guion))
    empaqueta_nex.build_nex(salida, bancos, pc=sym['start'], sp=SP48,
                            border=nx.borde_inicial(game))
    return {'codigo': len(code), 'datos': len(db), 'total': len(plano),
            'org': org, 'fin': org + len(plano), 'simbolos': sym,
            'guion': len(guion), 'bancos': sorted(bancos),
            'localizaciones': len(spec['locations']),
            'objetos': len(spec['objects']), 'imagenes': []}


def compila(game, ancho=COLS, org=ORG, guion=None, game_dir=None):
    """Ensambla motor y base de datos. Devuelve (codigo, db, simbolos, spec, dir_db).
    `game_dir` es la carpeta del juego, para buscar las pantallas del SCR en
    img/Spectrum e img/Original; sin ella, el condact existe y no pinta."""
    import cpc_nativo
    import nativecc as nc
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

    ficha = scriba_info.ficha(game, 'spectrum48', scriba_info.ahora())
    spec, _ = nc.compile_game(c, sysm[:ge.NSYS], width=ancho, filas=0,
                              ficha=ficha, imagen_intro=False)
    idioma = str((game.get('metadata') or {}).get('language', '') or 'es')
    borde = nx.borde_inicial(game)
    import presupuesto

    def _db(dbaddr):
        return ge.build_game_db(
            spec['messages'], spec['locations'], spec['vocab'], spec['objects'],
            spec['responses'], spec['startloc'], spec['sysverbs'], spec['width'],
            load=dbaddr, proc_before=spec['proc_before'],
            proc_after=spec['proc_after'], proc_onstart=spec['proc_onstart'],
            hdrbuf=0, imgbuf=0, loc_slot=b'', vall=spec['vall'],
            font_acc=spec['font_acc'], timers=spec['timers'],
            llevarmax=spec['llevarmax'], fx=fx_blob)[0]

    # pantallas sueltas (SCR): comprimidas, dentro del binario
    pant = []
    if spec.get('pantallas') and game_dir:
        pant, _av = sx.pantallas_spectrum(os.path.join(game_dir, 'img', 'Spectrum'),
                                          spec['pantallas'])
    pant_bytes = sum(len(f) for _, _, fl in pant for f in fl)

    # dos pasadas: la 1a da la longitud del motor, para saber donde cae la DB
    nloc = len(spec['locations'])
    code, _sym = ensambla(org=org, db_base=org, idioma=idioma, borde=borde,
                          guion=guion, pantallas=pant, nloc=nloc)
    dbaddr = org + len(code)
    code, sym = ensambla(org=org, db_base=dbaddr, idioma=idioma, borde=borde,
                         guion=guion, pantallas=pant, nloc=nloc)
    assert org + len(code) == dbaddr, 'el motor cambio de tamano entre pasadas'
    db = _db(dbaddr)
    # Las descripciones de los objetos (EXAMINAR) van dentro de la base de
    # datos desde v2.11. Si con ellas no cabe, se quedan fuera y se avisa:
    # EXAMINAR imprime solo el nombre, como hasta ahora. Es lo ultimo que se
    # sacrifica, antes de pedirle al autor que recorte.
    if org + len(code) + len(db) > SP48 and any(o.get('desc') for o in spec['objects']):
        _con = len(db)
        spec, _ = nc.compile_game(c, sysm[:ge.NSYS], width=ancho, filas=0,
                                  ficha=ficha, imagen_intro=False, obj_desc=False)
        db = _db(dbaddr)
        presupuesto.apunta(
            '48K: las descripciones de los objetos no caben (%s bytes) y se quedan '
            'fuera: EXAMINAR imprime solo el nombre. Sin ellas sobran %s bytes.'
            % (presupuesto._miles(_con - len(db)),
               presupuesto._miles(SP48 - org - len(code) - len(db))))
    presupuesto.comprueba(
        'ZX Spectrum 48K',
        [('motor + plataforma', len(code) - pant_bytes),
         ('pantallas SCR', pant_bytes),
         ('base de datos', len(db))],
        SP48 - org, 'el mapa plano &%04X-&%04X' % (org, SP48),
        presupuesto.RECORTA_PLANO)
    return code, db, sym, spec, dbaddr


# ---------------------------------------------------------------------------
#  Empaquetado .tap
# ---------------------------------------------------------------------------
def _bloque(datos, flag):
    import struct
    b = bytes([flag]) + datos
    chk = 0
    for x in b:
        chk ^= x
    return struct.pack('<H', len(b) + 1) + b + bytes([chk])


def _cab(tipo, nombre, lon, p1, p2=32768):
    import struct
    n = (nombre + ' ' * 10)[:10].encode('ascii', 'replace')
    return _bloque(bytes([tipo]) + n + struct.pack('<HHH', lon, p1, p2), 0)


def _num(n):
    return str(n).encode('ascii') + bytes([0x0E, 0, 0, n & 255, (n >> 8) & 255, 0])


def _linea(nl, cuerpo):
    import struct
    return (struct.pack('>H', nl) + struct.pack('<H', len(cuerpo) + 1) +
            cuerpo + b'\r')


def tap(blob, org=ORG, nombre='juego'):
    """Cinta de dos bloques: cargador BASIC + codigo. Sin pantalla de carga.
    (Las rutinas venian del viejo empaqueta48.py, copiadas porque aquel modulo corria
    su main() al importarlo.)"""
    cuerpo = (b'\xFD' + _num(org - 1) +                 # CLEAR org-1
              b':\xEF\x22\x22\xAF' +                   # : LOAD "" CODE
              b':\xF9\xC0' + _num(org))                 # : RANDOMIZE USR org
    bas = _linea(10, cuerpo)
    return (_cab(0, nombre, len(bas), 10, len(bas)) + _bloque(bas, 255) +
            _cab(3, nombre, len(blob), org) + _bloque(blob, 255))


def export_tap(game, tap_path, ancho=COLS, org=ORG, game_dir=None):
    import presupuesto
    presupuesto.empieza()
    code, db, sym, spec, dbaddr = compila(game, ancho=ancho, org=org,
                                          game_dir=game_dir)
    blob = code + db
    with open(tap_path, 'wb') as f:
        f.write(tap(blob, org=org,
                    nombre=str((game.get('metadata') or {}).get('title', 'juego'))[:10]))
    return {'codigo': len(code), 'datos': len(db), 'total': len(blob),
            'org': org, 'db': dbaddr, 'fin': org + len(blob),
            'libre': SP48 - (org + len(blob)),
            'mapa': SP48 - org,
            'localizaciones': len(spec['locations']),
            'objetos': len(spec['objects']),
            'presupuesto': presupuesto.informe(),
            'sym': sym}


def main():
    import argparse
    import yaml
    ap = argparse.ArgumentParser(
        description='Compila un juego de Scriba a .tap de 48K con el motor nativo Z80.')
    ap.add_argument('yaml')
    ap.add_argument('tap', nargs='?')
    ap.add_argument('--ancho', type=int, default=COLS)
    ap.add_argument('--org', default=hex(ORG))
    a = ap.parse_args()
    game = yaml.safe_load(open(a.yaml, encoding='utf-8'))
    salida = a.tap or (a.yaml.rsplit('.', 1)[0] + '_48.tap')
    info = export_tap(game, salida, ancho=a.ancho, org=int(a.org, 0))
    print('TAP 48K: %s' % salida)
    print('  motor+plataforma : %6d bytes  (&%04X-&%04X)'
          % (info['codigo'], info['org'], info['db'] - 1))
    print('  base de datos    : %6d bytes  (&%04X-&%04X)'
          % (info['datos'], info['db'], info['fin'] - 1))
    print('  total            : %6d bytes de %d del mapa plano'
          % (info['total'], info['mapa']))
    print('  libre            : %6d bytes  (%.1f%%)'
          % (info['libre'], 100.0 * info['libre'] / info['mapa']))
    print('  %d localizaciones, %d objetos'
          % (info['localizaciones'], info['objetos']))
    if info['libre'] < 0:
        print('  NO CABE: se pasa de &%04X' % SP48)


if __name__ == '__main__':
    main()
