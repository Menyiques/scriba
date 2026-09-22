# -*- coding: utf-8 -*-
"""
spectrum128_nativo.py - Capa de plataforma ZX Spectrum 128K para el motor Z80.

Es el 48K nativo (spectrum48_nativo) mas los bancos: el juego entero -- motor,
capa de plataforma y base de datos -- sigue viviendo en el mapa plano
&6000-&FF00, y los cinco bancos conmutables (1, 3, 4, 6 y 7) quedan ENTEROS
para las imagenes. En el export de BASIC esos mismos bancos los comparten el
texto y las imagenes, y el texto se lleva la mayor parte; aqui el texto va
comprimido dentro de la base de datos, en RAM principal, y no compite.

La trampa del mapa es la pila. Mientras hay un banco paginado, &C000-&FFFF NO
es la RAM de siempre, y ahi es justo donde vive la pila del juego (&FF00): un
push durante el paginado escribiria sobre los datos de la imagen. Por eso, el
rato que dura descomprimir, se cambia a una pila baja en &5C00 -- el buffer de
impresora, que no usa nadie -- y se restaura al acabar. Igual de importante:
toda la rutina de paginado vive por debajo de &C000, o desapareceria a mitad.

Las imagenes son dos flujos ZX0 por sala (bitmap y atributos), los mismos que
produce spectrum_export.imagenes_128k para el export de BASIC, con su misma
verificacion: ningun flujo cruza un limite de banco y todos se comprueban
descomprimiendolos con el simulador de dzx0. El descompresor es el
dzx0_standard de Einar Saukas y Urusergi, el mismo que ya usaba el export.

    python spectrum128_nativo.py juego.yaml [salida.tap]
"""
import os
import re

import game_engine as ge
import sample_ay
import next_nativo as nx
import spectrum48_nativo as s48
import spectrum_export as sx
import z80asm

ORG = s48.ORG             # &6000, igual que el 48K
SP128 = s48.SP48          # &FF00
SP_BAJA = 0x5C00          # pila de emergencia mientras hay un banco puesto
COLS = s48.COLS
BANCOS = (17, 19, 20, 22, 23)    # 16 + bancos de RAM 1, 3, 4, 6 y 7
TOPE_BANCOS = 5 * 16384
FILA_TEXTO = nx.FILA_TEXTO       # la imagen ocupa las filas 0..7


IMG128_ASM = r'''
; ===========================================================================
;  Imagenes en los bancos conmutables del 128K
; ===========================================================================
; S128T lleva, por localizacion (indice de curloc, 0..n-1), cuatro bytes:
; el desplazamiento del flujo del bitmap y el de los atributos, los dos
; DIVIDIDOS POR DOS -- por eso el empaquetador los alinea a par. Asi un
; desplazamiento de hasta 80 KB entra en 16 bits y el bit que sobra sale del
; acarreo al volver a doblarlo. El "no hay imagen" es &FFFF, no cero: cero es
; un desplazamiento perfectamente valido -- el del primer flujo del payload --
; y usarlo de centinela dejaba sin portada a los juegos que no traen imagenes
; de sala.
;
;   banco     = desplazamiento / 16384
;   direccion = &C000 + desplazamiento mod 16384

; s128adr: A = localizacion -> HL = su entrada de S128T
s128adr:
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl            ; 4 bytes por entrada
        ld    de,S128T
        add   hl,de
        ret

; S128PIC: A = localizacion. Pinta su imagen en el tercio superior y vuelve con
; CF=1; si esa sala no tiene, vuelve con CF=0 y sin tocar la pantalla.
S128PIC:
        call  s128adr
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        inc   hl
        ld    a,d
        and   e
        inc   a
        jr    z,s128no         ; &FFFF -> esta sala no tiene imagen
        ld    (s128ob),de
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        ld    (s128oa),de
        di                     ; ni interrupciones ni pila alta con banco puesto
        ld    (s128sp),sp
        ld    sp,SP128BAJA
        ld    de,&4000
        ld    hl,(s128ob)
        call  s128un           ; bitmap
        ld    de,&5800
        ld    hl,(s128oa)
        call  s128un           ; atributos
        call  s128ban0
        ld    sp,(s128sp)
        ei
        scf
        ret
s128no: or    a
        ret

; S128TIT: la pantalla de presentacion, si el juego la trae. Es un unico flujo
; de 6912 bytes que cubre bitmap y atributos de una vez.
S128TIT:
        ld    hl,(S128SCR)
        ld    a,h
        and   l
        inc   a
        ret   z                ; &FFFF -> este juego no trae portada
        di
        ld    (s128sp),sp
        ld    sp,SP128BAJA
        ld    de,&4000
        call  s128un
        call  s128ban0
        ld    sp,(s128sp)
        ei
        ret

; S128ESP: lo que dura la portada. Suena la musica del AY -- el 128K lleva el
; mismo chip y los mismos puertos que el Next, asi que el reproductor de
; next_nativo vale tal cual -- y se espera a que SUELTEN la tecla con la que se
; arranco antes de esperar a la siguiente; si no, la portada se iria al instante.
; Sin musica, psginit/psgframe/psgoff son RET y esto queda en una espera limpia
; sincronizada con el barrido.
S128ESP:
        call  psginit
s128e1: call  s128frm
        call  psgframe
        call  nxscan
        or    a
        jr    nz,s128e1
s128e2: call  s128frm
        call  psgframe
        call  nxscan
        or    a
        jr    z,s128e2
        jp    psgoff

; s128frm: un barrido. La ROM sigue paginada y el cargador deja IM1, asi que
; HALT da los 50 Hz sin montar nada.
s128frm:
        ei
        halt
        ret

; s128ban0: banco 0 de vuelta en &C000, que es donde el juego tiene su RAM.
; El 16 lleva ademas la ROM de 48K seleccionada, igual que deja el cargador.
s128ban0:
        ld    bc,&7FFD
        ld    a,16
        out   (c),a
        ret

; s128un: HL = desplazamiento/2 del flujo, DE = destino. Pagina el banco que le
; toca y lo descomprime. Deja el banco puesto: lo quita el que llama.
s128un: push  de
        call  s128pag
        pop   de
        jp    dzx0st

; s128pag: HL = desplazamiento/2 -> pagina su banco y deja HL apuntando dentro
; de la ventana de &C000. Lo usan el descompresor de imagenes y el reproductor
; de muestras, que solo se diferencian en que hacen con los bytes.
s128pag:
        add   hl,hl            ; el bit 16 se va al acarreo
        ld    a,0
        adc   a,a
        rlca
        rlca
        ld    c,a
        ld    a,h
        rlca
        rlca
        and   3
        add   a,c              ; A = banco 0..4
        ld    e,a
        ld    d,0
        ex    de,hl
        ld    bc,S128BK
        add   hl,bc
        ld    b,(hl)           ; B = lo que va al puerto &7FFD
        ex    de,hl
        ld    a,h
        and   &3F
        or    &C0
        ld    h,a              ; HL = &C000 + desplazamiento mod 16384
        ld    a,b
        ld    bc,&7FFD
        out   (c),a
        ret

S128BK: defb  17,19,20,22,23
s128ob: defw  0
s128oa: defw  0
s128sp: defw  0

; ---------------------------------------------------------------------------
;  dzx0_standard (Einar Saukas & Urusergi), con las etiquetas renombradas.
;  Es el mismo descompresor que ya usaba el export de BASIC, byte por byte.
;  HL = flujo comprimido, DE = destino.
; ---------------------------------------------------------------------------
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


SMP128_ASM = r'''
; ===========================================================================
;  Muestras digitalizadas (SAMPLE n)
; ===========================================================================
; Viven en los mismos bancos que las imagenes, detras de ellas, y se leen por la
; misma ventana de &C000. SMPT lleva por muestra el desplazamiento /2 y la
; longitud en bytes; &FFFF = esa ranura no existe.
;
; Igual que al pintar una imagen: mientras hay banco puesto la pila se muda
; abajo, porque la de siempre esta en &FF00 y eso es justo lo que se pagina.
SMPPLAY:
        or    a
        ret   z
        dec   a
        ld    l,a
        ld    h,0
        add   hl,hl
        add   hl,hl            ; 4 bytes por entrada
        ld    de,SMPT
        add   hl,de
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        inc   hl
        ld    a,d
        and   e
        inc   a
        ret   z                ; &FFFF -> no hay muestra ahi
        ld    (smpoff),de
        ld    e,(hl)
        inc   hl
        ld    d,(hl)
        ld    (smplen),de
        di
        ld    (s128sp),sp
        ld    sp,SP128BAJA
        ld    hl,(smpoff)
        call  s128pag
        ld    de,(smplen)
        call  SMPLAY
        call  s128ban0
        ld    sp,(s128sp)
        ei
        ret
smpoff: defw 0
smplen: defw 0
'''


IMG128_ASM_VACIO = r'''
S128PIC:
        or    a
        ret
S128TIT:
        ret
'''




def _tabla_smp_asm(tabla, nsmp):
    L = ['SMPT:']
    for i in range(1, nsmp + 1):
        e = tabla.get(i)
        L.append('        defw %d,%d' % (e[0] // 2, e[1]) if e
                 else '        defw &FFFF,0')
    return chr(10).join(L)


def _tabla_asm(tabla, scr_off, nlocs):
    """S128T (cuatro bytes por localizacion) y S128SCR, con los desplazamientos
    ya divididos por dos, que es como los lee s128un."""
    L = ['S128T:']
    for i in range(nlocs):
        offs = tabla.get(i + 1)          # imagenes_128k indexa en base 1
        if offs:
            L.append('        defw %d,%d' % (offs[0] // 2, offs[1] // 2))
        else:
            L.append('        defw &FFFF,&FFFF')
    L.append('S128SCR: defw %s'
             % ('&FFFF' if scr_off is None else str(scr_off // 2)))
    return chr(10).join(L)


def _engine_128(con_imagenes, con_titulo):
    """El motor con el parche del 48K y, encima, las imagenes por banco."""
    src = s48._engine_48()
    # _engine_next deja show_loc_image poniendo la ventana a pantalla completa;
    # aqui hay que preguntar primero si la sala tiene imagen.
    viejo = '''show_loc_image:
        ld    h,0
        ld    l,0
        ld    d,41
        ld    e,23
        call  TXTWIN
        ld    a,12
        call  TXTO
        xor   a
        ld    (col),a
        ret
'''
    if src.count(viejo) != 1:
        raise RuntimeError('no encuentro el show_loc_image del 48K en el motor')
    if con_imagenes:
        # Ojo al ORDEN: primero se borra y luego se pinta. En el Next la
        # imagen vive en Layer 2, una capa aparte, y daba igual borrar despues;
        # aqui esta en la propia pantalla ULA y un borrado posterior se la
        # lleva por delante. TXTWIN ya deja el cursor en la esquina de la
        # ventana nueva, asi que no hace falta un segundo borrado.
        nuevo = '''show_loc_image:
        ld    h,0
        ld    l,0
        ld    d,41
        ld    e,23
        call  TXTWIN           ; ventana entera...
        ld    a,12
        call  TXTO             ; ...y a limpiar, ANTES de pintar nada
        call  is_dark
        or    a
        jr    nz,sli_fin       ; a oscuras no se ve la imagen
        ld    a,(curloc)
        call  S128PIC
        jr    nc,sli_fin       ; esta sala no tiene
        ld    h,0
        ld    l,FILATXT        ; el texto, debajo de la imagen
        ld    d,41
        ld    e,23
        call  TXTWIN
sli_fin:
        xor   a
        ld    (col),a
        ret
'''
    else:
        nuevo = viejo
    src = src.replace(viejo, nuevo)

    if con_titulo:
        i = src.index(chr(10) + 'show_title:') + 1
        j = src.index(chr(10), src.index('show_title:', i)) + 1
        # el 48K dejo 'show_title:\n        ret\n'; se cambia por la portada
        viejo_t = 'show_title:\n        ret\n'
        if src.count(viejo_t) != 1:
            raise RuntimeError('no encuentro el show_title del 48K en el motor')
        src = src.replace(viejo_t,
                          'show_title:\n'
                          '        call  S128TIT      ; pinta la portada\n'
                          '        call  S128ESP      ; suena hasta que toquen tecla\n'
                          '        jp    SCRMODE      ; y se limpia para empezar\n')
    return src


def prefijo(org, db_base, borde=7):
    return (s48.prefijo(org, db_base, borde) +
            'SP128BAJA equ &%04X\n' % SP_BAJA +
            'FILATXT equ %d\n' % FILA_TEXTO)


def ensambla(org=ORG, db_base=None, idioma='es', borde=7,
             tabla=None, scr_off=None, nlocs=0, psg=b'', guion=None,
             smptab=None, nsmp=0, smphz=11025):
    """Ensambla motor + plataforma 48K + bancos de imagenes y musica del 128K."""
    if db_base is None:
        db_base = org
    hay_img = bool(tabla)
    hay_tit = scr_off is not None
    partes = [s48.sin_z80n(nx.PLAT_ASM), s48.Z80N_ASM, nx.IMG_ASM_VACIO]
    if hay_img or hay_tit:
        partes.append(IMG128_ASM)
        partes.append(_tabla_asm(tabla or {}, scr_off, nlocs))
    elif not smptab:
        partes.append(IMG128_ASM_VACIO)
    else:
        partes.append(IMG128_ASM)          # las muestras usan su paginado
        partes.append(_tabla_asm({}, None, nlocs))
    if smptab:
        import sample_ay
        partes.append(SMP128_ASM)
        partes.append(_tabla_smp_asm(smptab, nsmp))
        partes.append(sample_ay.asm(smphz, con_di=False))
    else:
        partes.append(nx.SMP_ASM_VACIO)
    # El reproductor de PSG del Next, sin tocar: el AY del 128K son los mismos
    # puertos (&FFFD para elegir registro, &BFFD para el dato).
    partes.append(nx.PSG_ASM + chr(10) + nx._datos_asm('NXPSG', psg)
                  if psg else nx.PSG_ASM_VACIO)
    fuente = (prefijo(org, db_base, borde) +
              _engine_128(hay_img, hay_tit) +
              chr(10).join(partes) + chr(10) +
              nx._font_asm(idioma) + chr(10))
    if guion is not None:
        fuente = nx._modo_prueba(fuente, guion, maquina='128', sp=SP128)
    return z80asm.assemble(fuente, org=org)


def imagenes(game_dir, c):
    """Los flujos ZX0 de las imagenes, con el mismo empaquetador (y la misma
    verificacion con dzx0) que usa el export de BASIC. texto_len=0 porque aqui
    los bancos son solo para imagenes: el texto va en la base de datos."""
    img = os.path.join(game_dir, 'img', 'Spectrum')
    if not os.path.isdir(img):
        return b'', {}, None, ['imagenes: no hay carpeta img/Spectrum']
    return sx.imagenes_128k(img, list(c.locids), c.locidx, 0)


def compila(game, game_dir, ancho=COLS, org=ORG, guion=None):
    """Devuelve (codigo, db, simbolos, spec, dir_db, payload, avisos)."""
    import cpc_nativo
    import nativecc as nc
    import scriba_info

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

    payload, tabla, scr_off, avisos = imagenes(game_dir, c)
    # las muestras van detras de las imagenes, en los mismos bancos
    smp_blob, smptab = sample_ay.muestras(game, len(payload))
    nsmp = len(game.get('samples') or [])
    smphz = int(((game.get('samples') or [{}])[0] or {}).get('hz', 11025))
    payload = payload + smp_blob
    # La musica solo tiene sentido con portada: es lo que suena mientras se
    # mira, igual que en el Next y en el export de BASIC.
    psg_bruto, psg_nom = ((b'', None) if scr_off is None
                          else nx._musica(os.path.join(game_dir, 'music')))
    import presupuesto
    presupuesto.comprueba(
        'ZX Spectrum 128K',
        [('imagenes y portada', len(payload) - len(smp_blob)),
         ('muestras digitalizadas', len(smp_blob))],
        TOPE_BANCOS, 'los 5 bancos conmutables: 1, 3, 4, 6 y 7',
        presupuesto.RECORTA_BANCOS)

    ficha = scriba_info.ficha(game, 'spectrum128', scriba_info.ahora())
    spec, _ = nc.compile_game(c, sysm[:ge.NSYS], width=ancho, filas=0,
                              ficha=ficha, imagen_intro=bool(tabla))
    idioma = str((game.get('metadata') or {}).get('language', '') or 'es')
    borde = nx.borde_inicial(game)
    nlocs = len(spec['locations'])

    def _db(dbaddr):
        return ge.build_game_db(
            spec['messages'], spec['locations'], spec['vocab'], spec['objects'],
            spec['responses'], spec['startloc'], spec['sysverbs'], spec['width'],
            load=dbaddr, proc_before=spec['proc_before'],
            proc_after=spec['proc_after'], proc_onstart=spec['proc_onstart'],
            hdrbuf=0, imgbuf=0, loc_slot=b'', vall=spec['vall'],
            font_acc=spec['font_acc'], timers=spec['timers'],
            llevarmax=spec['llevarmax'], fx=fx_blob)[0]

    def _asm(base, psg=b''):
        return ensambla(org=org, db_base=base, idioma=idioma, borde=borde,
                        tabla=tabla, scr_off=scr_off, nlocs=nlocs, psg=psg,
                        guion=guion, smptab=smptab, nsmp=nsmp, smphz=smphz)

    # La musica es lo unico elastico del binario, asi que se mide primero todo
    # lo demas y se le da el hueco que quede, en vez de asumir un tope y
    # reventar. Un juego con una base de datos enorme se queda con menos
    # cancion, pero se queda con cancion.
    psg = b''
    if psg_bruto:
        code0, _ = _asm(org)
        libre = (SP128 - nx.PILA_MIN
                 - (org + len(code0) + len(_db(org + len(code0)))))
        tope = min(nx.PSG_MAX, max(0, libre))
        if tope >= 64:
            psg = nx._trunca_psg(psg_bruto, tope)
            if len(psg) < len(psg_bruto):
                avisos = list(avisos) + [
                    'musica recortada de %d a %d bytes y en bucle'
                    % (len(psg_bruto), len(psg))]
        else:
            avisos = list(avisos) + [
                'no queda sitio para la musica (%d bytes libres); se omite'
                % max(0, libre)]

    code, _sym = _asm(org, psg)
    dbaddr = org + len(code)
    code, sym = _asm(dbaddr, psg)
    assert org + len(code) == dbaddr, 'el motor cambio de tamano entre pasadas'
    import presupuesto
    presupuesto.comprueba(
        'ZX Spectrum 128K',
        [('motor + plataforma', len(code) - len(psg)), ('musica del titulo', len(psg)),
         ('base de datos', len(_db(dbaddr)))],
        SP128 - org, 'el mapa plano &%04X-&%04X' % (org, SP128),
        presupuesto.RECORTA_PLANO, primero=True)
    return (code, _db(dbaddr), sym, spec, dbaddr, payload, avisos,
            len(psg), psg_nom)


# ---------------------------------------------------------------------------
#  Empaquetado .tap
# ---------------------------------------------------------------------------
def tap(blob, payload, org=ORG, nombre='juego', borde=7):
    """Cargador BASIC + codigo + un bloque por banco de imagenes.

    El cargador hace lo mismo que el del export de BASIC: por cada banco, POKE
    a la variable de sistema BANKM y OUT al puerto &7FFD antes de cargar en
    &C000, y al final deja el banco 0 puesto y salta al motor."""
    CLEAR, LOAD, CODE_T = 0xFD, 0xEF, 0xAF
    POKE, OUT, RND, USR, BORDER = 0xF4, 0xDF, 0xF9, 0xC0, 0xE7
    N = s48._num
    trozos = [payload[i:i + 16384] for i in range(0, len(payload), 16384)]
    if len(trozos) > len(BANCOS):
        raise ValueError('las imagenes ocupan %d bancos y solo hay %d'
                         % (len(trozos), len(BANCOS)))
    cuerpo = (bytes([BORDER]) + N(borde) + b':' +
              bytes([CLEAR]) + N(org - 1) + b':' +
              bytes([POKE]) + N(23739) + b',' + N(111))   # sin "Bytes:" al cargar
    prog = s48._linea(10, cuerpo)
    nl = 20
    for j in range(len(trozos)):
        prog += s48._linea(nl,
                           bytes([POKE]) + N(23388) + b',' + N(BANCOS[j]) + b':' +
                           bytes([OUT]) + N(32765) + b',' + N(BANCOS[j]) + b':' +
                           bytes([LOAD]) + b'""' + bytes([CODE_T]) + N(49152))
        nl += 10
    prog += s48._linea(nl,
                       bytes([POKE]) + N(23388) + b',' + N(16) + b':' +
                       bytes([OUT]) + N(32765) + b',' + N(16) + b':' +
                       bytes([LOAD]) + b'""' + bytes([CODE_T]) + b':' +
                       bytes([POKE]) + N(23739) + b',' + N(244) + b':' +
                       bytes([RND, USR]) + N(org))
    out = (s48._cab(0, nombre, len(prog), 10, len(prog)) + s48._bloque(prog, 255))
    for j, t in enumerate(trozos):
        out += (s48._cab(3, 'img%d' % (j + 1), len(t), 49152) +
                s48._bloque(t, 255))
    out += s48._cab(3, nombre, len(blob), org) + s48._bloque(blob, 255)
    return out


def export_tap(game, tap_path, game_dir=None, ancho=COLS, org=ORG):
    import presupuesto
    presupuesto.empieza()
    game_dir = game_dir or os.getcwd()
    (code, db, sym, spec, dbaddr, payload, avisos,
     npsg, psg_nom) = compila(game, game_dir, ancho=ancho, org=org)
    _smpblob, _smptab = sample_ay.muestras(game, 0)   # solo para el informe
    blob = code + db
    meta = game.get('metadata') or {}
    with open(tap_path, 'wb') as f:
        f.write(tap(blob, payload, org=org,
                    nombre=str(meta.get('title', 'juego'))[:10],
                    borde=nx.borde_inicial(game)))
    return {'codigo': len(code), 'datos': len(db), 'total': len(blob),
            'org': org, 'db': dbaddr, 'fin': org + len(blob),
            'libre': SP128 - (org + len(blob)),
            'mapa': SP128 - org,
            'payload': len(payload),
            'bancos': (len(payload) + 16383) // 16384,
            'banco_libre': TOPE_BANCOS - len(payload),
            'localizaciones': len(spec['locations']),
            'objetos': len(spec['objects']),
            'psg': npsg, 'psg_nom': psg_nom,
            'muestras': len(_smptab), 'muestras_bytes': len(_smpblob),
            'avisos': avisos, 'presupuesto': presupuesto.informe(),
            'sym': sym}


def export_nex_prueba(game, salida, guion, game_dir=None, ancho=COLS, org=ORG):
    """El 128K en MODO PRUEBA, envuelto en un .nex para que lo arranque jnext.

    Lleva las imagenes en sus bancos de siempre (1, 3, 4, 6 y 7, que es donde
    las pone el cargador del .tap) y el guion de la bateria en el 17, o sea que
    la bateria ejercita tambien la paginacion por &7FFD y el descompresor.
    El artefacto que se distribuye sigue siendo el .tap."""
    import empaqueta_nex
    game_dir = game_dir or os.getcwd()
    (code, db, sym, spec, dbaddr, payload, avisos,
     npsg, psg_nom) = compila(game, game_dir, ancho=ancho, org=org, guion=guion)
    plano = code + db
    bancos = s48.bancos_planos(plano, org)
    for j in range(0, len(payload), 16384):
        bancos[BANCOS[j // 16384] - 16] = payload[j:j + 16384].ljust(16384, b'\x00')
    bancos.update(s48.bancos_guion(guion))
    empaqueta_nex.build_nex(salida, bancos, pc=sym['start'], sp=SP128,
                            border=nx.borde_inicial(game))
    return {'codigo': len(code), 'datos': len(db), 'total': len(plano),
            'org': org, 'fin': org + len(plano), 'simbolos': sym,
            'guion': len(guion), 'bancos': sorted(bancos),
            'payload': len(payload), 'psg': npsg,
            'localizaciones': len(spec['locations']),
            'objetos': len(spec['objects']), 'imagenes': []}


def main():
    import argparse
    import yaml
    ap = argparse.ArgumentParser(
        description='Compila un juego de Scriba a .tap de 128K con el motor nativo.')
    ap.add_argument('yaml')
    ap.add_argument('tap', nargs='?')
    ap.add_argument('--ancho', type=int, default=COLS)
    ap.add_argument('--org', default=hex(ORG))
    a = ap.parse_args()
    game = yaml.safe_load(open(a.yaml, encoding='utf-8'))
    salida = a.tap or (a.yaml.rsplit('.', 1)[0] + '_128.tap')
    info = export_tap(game, salida, game_dir=os.path.dirname(os.path.abspath(a.yaml)),
                      ancho=a.ancho, org=int(a.org, 0))
    print('TAP 128K: %s' % salida)
    print('  motor+plataforma : %6d bytes  (&%04X-&%04X)'
          % (info['codigo'], info['org'], info['db'] - 1))
    print('  base de datos    : %6d bytes  (&%04X-&%04X)'
          % (info['datos'], info['db'], info['fin'] - 1))
    print('  RAM principal    : %6d de %d bytes, %d libres'
          % (info['total'], info['mapa'], info['libre']))
    print('  imagenes         : %6d bytes en %d banco(s), %d libres de %d'
          % (info['payload'], info['bancos'], info['banco_libre'], TOPE_BANCOS))
    print('  musica           : %s'
          % ('%s, %d bytes' % (info['psg_nom'], info['psg']) if info['psg']
             else 'no'))
    print('  %d localizaciones, %d objetos'
          % (info['localizaciones'], info['objetos']))
    for a_ in (info['avisos'] or [])[:1]:
        print('  ' + a_)


if __name__ == '__main__':
    main()
