# -*- coding: utf-8 -*-
"""
cpc_nativo.py — Exportador CPC NATIVO.

Compila el juego de Scriba al motor Z80 (modelo PAW/DAAD) + base de datos
compacta y lo empaqueta en un .dsk arrancable. Todo en Python puro, sin
compiladores externos: el motor se ensambla con el ensamblador Z80 propio
(z80asm) y la base de datos la genera el compilador (nativecc).

Frente al export BASIC: mucho más pequeño y rápido, y entra de sobra en RAM
(no da "Memory full"). El juego completo cabe en ~20 KB.

    info = export_native(game, "juego.dsk", modo=2)
"""

# Mensajes de sistema (indices 0..10 de la tabla de mensajes del motor)
SYS_MSGS = [
    "No puedes ir por ahi.", "Salidas: ", "No entiendo.", "Aqui ves: ",
    "Coges ", "Dejas ", "No ves eso aqui.", "No llevas eso.",
    "Llevas: ", "No llevas nada.", "No puedes coger eso.",
    "Esta completamente oscuro. No puedes ver nada.", "Puntuacion: ",
    "Llevas demasiado peso.",
]


def _sys_msgs_y_salidas(meta):
    """Construye los mensajes de sistema y los nombres de salida del motor CPC
    desde metadata['mensajes'] (el MISMO catálogo que Spectrum/Next, mensajes.py),
    para que las traducciones del editor valgan también en CPC. El CPC imprime
    prefijo + valor (p. ej. "Coges " + objeto), así que de las plantillas con
    placeholder se toma solo el prefijo. Devuelve (lista SYS_MSGS, dict salidas)."""
    import re
    try:
        import mensajes
        defs = mensajes.defaults()
    except Exception:
        return list(SYS_MSGS), None
    ov = (meta or {}).get('mensajes') or {}

    def t(mid):
        return str(ov.get(mid) or defs.get(mid) or '')

    def prefix(mid):
        s = t(mid)
        m = re.search(r'\{[a-z]+\}', s)
        if m:                         # plantilla "Coges {o}." -> "Coges "
            return s[:m.start()]
        s = s.rstrip()                # etiqueta "Salidas:" -> "Salidas: "
        if not s.endswith(':'):
            s += ':'
        return s + ' '

    msgs = [
        t('no_direccion'), prefix('salidas'), t('no_entiendo'), prefix('aqui_hay'),
        prefix('coges'), prefix('dejas'), t('no_ves_eso'), t('no_llevas_eso'),
        prefix('llevas_cab'), t('no_llevas_nada'), t('no_coger'),
        t('oscuro_total'), prefix('puntuacion'), t('peso_max'),
    ]
    # SSCOREP / SSCORES: "[+{n} puntos]" partido en prefijo y sufijo (ADDSCORE).
    pm = t('puntos_mas') or '[+{n} puntos]'
    mm = re.search(r'\{[a-z]+\}', pm)
    if mm:
        msgs += [pm[:mm.start()], pm[mm.end():]]
    else:
        msgs += [pm, '']
    # SFIN: el remate de END. El motor imprime prefijo + puntuacion, asi que de
    # "== FIN DEL JUEGO - Puntuacion: {p}/{max} ==" se toma solo el prefijo.
    msgs.append(prefix('fin_juego'))
    # SOTRA: lo que se ofrece al acabar. No esta en el catalogo historico,
    # asi que se admite override del autor y si no, texto por defecto.
    msgs.append(t('otra_partida') or 'Pulsa una tecla para jugar otra vez.')
    # SNADAC / SNADAD / SOSCHAY: COGER TODO y DEJAR TODO sin nada, y COGER
    # TODO a oscuras (v2.13; antes daban "No ves eso aqui" / "No llevas eso").
    msgs += [t('nada_coger'), t('nada_dejar'), t('oscuro_hay')]
    # SVACIO: ENTER sin nada (v2.16). Sin texto propio, el de "No entiendo".
    msgs.append(t('linea_vacia') or t('no_entiendo'))
    salidas = {1: t('dir_n').strip(), 2: t('dir_s').strip(), 3: t('dir_e').strip(),
               4: t('dir_o').strip(), 5: t('dir_u').strip(), 6: t('dir_d').strip()}
    return msgs, salidas
ENGINE_ORG = 0x1200          # direccion de carga del motor + DB

# Musica del titulo: el reproductor se engancha a la interrupcion de frame con
# KL_ADD_FRAME_FLY (game_engine.show_title). Toda la E/S del AY queda dentro de la
# interrupcion (sin chocar con el escaneo de teclado del firmware) y el primer
# plano solo espera la tecla. Activada.
MUSICA_TITULO = True

# Mapa de la RAM base del CPC para el motor nativo:
#   &1200 (o algo    motor (codigo, variables y TBUF: todo bajo &4000, porque
#   mas: BASIC_BUFFER)
#                    es lo que se ejecuta mientras un banco tapa &4000-&7FFF)
#   detras           la DB
#   detras (>=&4000) hdrbuf, el buffer de 2K de CAS IN (y la rutina de la
#                    musica del titulo: el firmware la quiere en los 32K
#                    centrales), y MTABLE, las matrices de los acentos
#   &8B00-&A67B      imgbuf: la musica del titulo mientras suena, y luego el
#                    buffer de las imagenes (cargar, descomprimir)
#   &C000            la pantalla
# En un 6128 lo que no quepa del texto va a los bancos 4-7 (TEXTn.BIN, los
# carga el BASIC) y lo que dejen libre, a la cache de imagenes.
IMGBUF = 0x8B00
IMGTOP = 0xA67C              # HIMEM con AMSDOS
HDRBUF_TAM = 2048
MTABLE_TAM = 256             # TXT SET M TABLE desde el 224: 32 caracteres x 8
IMG_LINEAS = 64              # la imagen: las 8 filas de arriba
IMG_RAW = 80 * IMG_LINEAS    # lineal, 80 bytes por linea en los dos modos
BANCOS = (0xC4, 0xC5, 0xC6, 0xC7)
ZX0_VENTANA = 640            # 8 lineas hacia atras: casi lo mismo que sin
                             # limite y cuatro veces mas rapido de comprimir
MAX_RANURAS = 64             # el mapa de bits 'populated' del motor

_ZX2CPC = (0, 2, 6, 8, 18, 20, 24, 26)   # como nativecc: color ZX -> firmware

# El cargador BASIC y la memoria que le queda. El programa empieza en &0170 y,
# para LOAD, BASIC aparta 4K de buffer de disco justo debajo de HIMEM; con
# MEMORY &11FF (el motor en &1200) quedan unos 4,1K para programa, variables
# y buffer. El cargador de una linea de siempre cabe con 52 bytes de sobra; el
# del 6128 (comprueba la RAM extra y carga los TEXTn) no, y daba "Memory full
# in 20". Por eso, con el texto en bancos, el motor sube lo que haga falta.
BASIC_PROG = 0x0170
BASIC_BUFFER = 4096
_BAS_KW = ('MEMORY', 'LOAD', 'MODE', 'FOR', 'TO', 'INK', 'NEXT', 'OUT', 'POKE',
           'IF', 'THEN', 'ELSE', 'PRINT', 'END', 'CALL', 'RUN')
_BAS_FN = ('PEEK',)


def tamano_basic(prog):
    """(bytes, variables) de un programa BASIC en ASCII una vez tokenizado por
    Locomotive BASIC: palabras clave de 1 byte (funciones, 2), numeros de 1 a
    3, &hex de 3, variables con 3 bytes de cabecera + el nombre, 5 por linea y
    2 del final. Es una cuenta por arriba, que es lo que hace falta."""
    import re
    total, variables = 2, set()
    if isinstance(prog, bytes):
        prog = prog.decode('ascii')
    for linea in prog.replace('\r', '').split('\n'):
        m = re.match(r'\s*\d+\s*(.*)', linea)
        if not m:
            continue
        s, i, n = m.group(1), 0, 5
        while i < len(s):
            if s[i] == '"':
                j = s.find('"', i + 1)
                j = len(s) - 1 if j < 0 else j
                n += j - i + 1
                i = j + 1
                continue
            m = re.match(r'&[0-9A-Fa-f]+|\d+|[A-Za-z]+|<>', s[i:])
            if not m:
                n += 1
                i += 1
                continue
            w = m.group(0)
            if w[0] == '&':
                n += 3
            elif w.isdigit():
                n += 1 if int(w) < 10 else (2 if int(w) < 256 else 3)
            elif w == '<>':
                n += 1
            elif w.upper() in _BAS_KW:
                n += 1
            elif w.upper() in _BAS_FN:
                n += 2
            else:
                n += 3 + len(w)
                variables.add(w.upper())
            i += len(w)
        total += n
    return total, len(variables)


def libre_basic(prog, org):
    """Lo que le queda a BASIC debajo de HIMEM (org - 1) para el buffer de LOAD."""
    n, nv = tamano_basic(prog)
    return org - (BASIC_PROG + n + 7 * nv)


def _cargador(org, nbancos, modo, titulo, musica, aviso, tintas_titulo=None):
    """DISC.BAS: carga portada, musica, texto (en los bancos) y juego, y lo
    arranca. Con texto en bancos, antes mira que haya RAM extra. La portada va
    LO PRIMERO y con su paleta ya puesta: se ve dibujarse y se queda a la
    vista mientras carga el resto (el motor, al arrancar, pone la misma paleta
    y la musica y espera una tecla)."""
    lineas = []
    if nbancos:
        # sin RAM extra no hay juego: se dice antes de cargar nada
        lineas.append('MEMORY &%04X:OUT &7F00,&C4:POKE &4000,170:OUT &7F00,&C5:'
                      'POKE &4000,85:OUT &7F00,&C4:a=PEEK(&4000):OUT &7F00,&C0:'
                      'IF a<>170 THEN PRINT"%s":END' % (org - 1, aviso))
        parts = []
    else:
        parts = ['MEMORY &%04X' % (org - 1)]
    if titulo:
        parts.append('MODE 0')            # titulo en Modo 0; el motor vuelve al suyo
        if tintas_titulo:
            # su paleta ANTES de cargarla (un .scr nativo sin paleta se queda
            # con la del firmware), y el borde del color del fondo
            t = list(tintas_titulo)[:16]
            parts.append('BORDER %d' % (t[0] & 31))
            parts.append(':'.join('INK %d,%d' % (k, c & 31) for k, c in enumerate(t)))
        parts.append('LOAD"TITLE.SCR"')
    else:
        parts.append('MODE %d' % modo)
    if musica:
        parts.append('LOAD"MUSIC.BIN"')
    for k in range(nbancos):
        parts.append('OUT &7F00,&%02X:LOAD"TEXT%d.BIN"' % (BANCOS[k], k))
    if nbancos:
        parts.append('OUT &7F00,&C0')
    parts.append('LOAD"GAME.BIN"')
    parts.append('CALL &%04X' % org)
    lineas.append(':'.join(parts))
    return ''.join('%d %s\r\n' % (10 * (k + 1), l)
                   for k, l in enumerate(lineas)).encode('ascii')


def _tintas_texto(game, modo):
    """(papel, pluma) del texto, colores del firmware. En Modo 1 son tambien
    dos de los cuatro colores de cada imagen, asi que se miran las primeras
    PAPER/INK sueltas del on_start (las que se ponen siempre al empezar)."""
    if modo != 1:
        return (1, 24)
    papel, pluma = 0, 26
    import re
    code = (game.get('code') or {}).get('on_start') or ''
    for ln in str(code).split('\n'):
        up = ln.strip().upper()
        if up.startswith(('IF ', 'ELSE', 'ENDIF', 'WHILE', 'DO')):
            break                      # lo condicional ya no es "siempre"
        m = re.match(r'(PAPER|INK)\s+(\d+)\s*$', up)
        if m:
            c = _ZX2CPC[int(m.group(2)) & 7]
            if m.group(1) == 'PAPER':
                papel = c
            else:
                pluma = c
    return (papel, pluma)


def _zx0_decode(comp):
    """Descompresor ZX0 v2 (el de dzx0_standard). Devuelve (datos, holgura):
    holgura = lo mas que la escritura llega a ir por delante de la lectura,
    para comprobar que se puede descomprimir en el sitio."""
    comp = bytes(comp)
    out = bytearray()
    st = {'i': 0, 'mask': 0, 'val': 0, 'back': False, 'hol': 0}

    def rbyte():
        b = comp[st['i']]
        st['i'] += 1
        return b

    def rbit():
        if st['back']:
            st['back'] = False
            return comp[st['i'] - 1] & 1
        st['mask'] >>= 1
        if not st['mask']:
            st['mask'] = 128
            st['val'] = rbyte()
        return 1 if st['val'] & st['mask'] else 0

    def gamma(inv=False):
        v = 1
        while not rbit():
            v = (v << 1) | (rbit() ^ (1 if inv else 0))
        return v

    def pon(b):
        st['hol'] = max(st['hol'], len(out) - st['i'] + 1)
        out.append(b)

    last = 1
    estado = 'lit'
    while True:
        if estado == 'lit':
            for _ in range(gamma()):
                b = rbyte()
                pon(b)
            estado = 'nuevo' if rbit() else 'ultimo'
        elif estado == 'ultimo':
            for _ in range(gamma()):
                pon(out[-last])
            estado = 'nuevo' if rbit() else 'lit'
        else:
            msb = gamma(True)
            if msb == 256:
                return bytes(out), st['hol']
            last = msb * 128 - (rbyte() >> 1)
            st['back'] = True
            for _ in range(gamma() + 1):
                pon(out[-last])
            estado = 'nuevo' if rbit() else 'lit'


def _zx0(raw, cache_dir=None):
    """ZX0 de una imagen, con cache en disco: comprimir en Python cuesta un
    par de segundos por imagen, y el juego se exporta muchas veces."""
    import hashlib
    import os
    import spectrum_export as sx
    f = None
    if cache_dir:
        clave = hashlib.sha1(b'zx0-%d:' % ZX0_VENTANA + bytes(raw)).hexdigest()
        f = os.path.join(cache_dir, clave + '.zx0')
        if os.path.isfile(f):
            try:
                comp = open(f, 'rb').read()
                if _zx0_decode(comp)[0] == bytes(raw):
                    return comp
            except Exception:
                pass
    comp = sx.zx0_comprime(raw, offset_limit=ZX0_VENTANA)
    if f:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(f, 'wb') as fh:
                fh.write(comp)
        except OSError:
            pass
    return comp


def _pic(raw, tintas, cache_dir=None):
    """Fichero de imagen: [tinta 2][tinta 3][ZX0 de las lineas seguidas], o
    None si no se pudiera descomprimir en su sitio (no pasa con 5120 bytes en
    un buffer de 7036, pero se comprueba)."""
    comp = _zx0(raw, cache_dir)
    datos, hol = _zx0_decode(comp)
    assert datos == bytes(raw)
    fichero = bytes([tintas[0] & 31, tintas[1] & 31]) + comp
    # cargado pegado a IMGTOP (y 2 bytes de longitud delante, para la cache);
    # la salida, desde IMGBUF, no puede alcanzar lo que queda por leer
    if len(fichero) + 2 > IMGTOP - IMGBUF or hol > (IMGTOP - IMGBUF) - len(comp):
        return None
    return fichero


def _aviso_6128(meta):
    """El aviso de maquina sin RAM extra, en ASCII (lo escribe el BASIC)."""
    import unicodedata
    try:
        import mensajes
        defs = mensajes.defaults()
    except Exception:
        defs = {}
    ov = (meta or {}).get('mensajes') or {}
    t = str(ov.get('necesita_6128') or defs.get('necesita_6128')
            or 'Este juego necesita un Amstrad CPC 6128.')
    t = unicodedata.normalize('NFD', t)
    t = ''.join(ch for ch in t if unicodedata.category(ch) != 'Mn')
    return ''.join(ch for ch in t if 32 <= ord(ch) < 127 and ch != '"')


def _reparte_ranuras(loc_pics, libres):
    """Coloca las imagenes de sala en los huecos de los bancos, a medida
    (longitud + 2 bytes), por orden de sala. libres = [(config, desde, hasta)].
    Devuelve ({sala0: ranura}, [(config, direccion)])."""
    huecos = [list(h) for h in libres]
    donde, slots = {}, []
    for lid0, fich in loc_pics:
        if len(slots) >= MAX_RANURAS:
            break
        n = len(fich) + 2
        for h in huecos:
            if h[2] - h[1] >= n:
                donde[lid0] = len(slots)
                slots.append((h[0], h[1]))
                h[1] += n
                break
    return donde, slots


def export_native(game, dsk_path, modo=1, img_dir=None):
    """Compila el juego y escribe un .dsk arrancable. Devuelve un dict de info.
    modo: 1 (40 columnas, imagenes de 4 colores) o 2 (80 columnas, 2 colores).
    Si el juego no cabe en la RAM base, el texto que sobra va a los bancos
    del 6128 (y el disco ya no arranca en un 464: lo dice el cargador)."""
    import os
    import spectrum_export as sx
    import nativecc as nc
    import game_engine as ge
    import dsk
    import presupuesto
    presupuesto.empieza()

    c = sx.recolecta(game)
    # Ancho de wrap = columnas - 1: el firmware del CPC auto-salta de linea al
    # llegar al borde de la ventana (80/40 col). Si wrap_print usara el ancho
    # completo, su salto chocaria con el del firmware (lineas en blanco y texto
    # revuelto). Dejando 1 columna de margen, el firmware nunca auto-salta.
    width = 79 if modo == 2 else 39
    # Mensajes de sistema y nombres de salida localizados (metadata['mensajes']).
    sys_msgs, exit_names = _sys_msgs_y_salidas(game.get('metadata'))
    # la ficha de VERSION, como en las demas maquinas; y la imagen de la sala
    # de salida antes de la presentacion (asi la presentacion sale debajo)
    import scriba_info
    ficha = scriba_info.ficha(game, 'cpc', scriba_info.ahora())
    spec, info = nc.compile_game(c, sys_msgs, width=width, ficha=ficha,
                                 imagen_intro=True)
    tintas = _tintas_texto(game, modo)

    # Efectos de sonido FX (AY): se embeben SOLO los referenciados por PLAY. El
    # reloj del AY del CPC es 1,0 MHz (los AYFX, hechos a 1,77 MHz del Spectrum,
    # se reescalan en effect_to_ayframes para conservar el tono).
    fx_blob = b''
    try:
        import capabilities
        import fx_engine
        _used = capabilities.used_fx(game)
        if _used:
            fx_blob = fx_engine.pack_ay_fx(game.get('fx', []) or [], _used,
                                           clock=1000000)
    except Exception:
        fx_blob = b''

    org = ENGINE_ORG
    # Pantalla de titulo (Modo 0, 16 colores). Se convierte ANTES de la base de
    # datos porque su paleta de 16 tintas va DENTRO de la DB (el motor la pone al
    # cambiar a Modo 0). Al pulsar tecla, el motor vuelve al modo del juego.
    info['title'] = False
    title = None
    title_pal = b''
    if img_dir:
        res = _title_screen(img_dir)
        if res is not None:
            title, inks = res
            if inks:
                title_pal = bytes(list(inks)[:16])
            info['title'] = True

    # Musica del titulo: se decide ANTES de la DB (lleva un flag en la cabecera).
    # La carga el cargador BASIC (LOAD"MUSIC.BIN" -> &8B00, fiable); el motor solo
    # la reproduce mientras se ve la portada.
    info['music'] = False
    musbin = None
    if img_dir and MUSICA_TITULO:
        music_dir = os.path.join(os.path.dirname(img_dir), 'music')   # <raiz>/music
        musbin = _music_bin(music_dir)
        if musbin:
            info['music'] = True

    # Imagenes de localizacion (PIC<n>.SCR, n = indice 0-based de la localizacion).
    # Se cargan del disco al entrar en cada sitio (o de la cache de los bancos),
    # se descomprimen al tercio superior y el texto va en una ventana debajo.
    cache_dir = (os.path.join(os.path.dirname(img_dir), 'temp', 'CPC')
                 if img_dir else None)
    loc_pics = []
    info['nimg'] = 0
    info['img_fuera'] = []
    if img_dir:
        cpcdir = os.path.join(img_dir, 'AmstradCPC')
        origdir = os.path.join(img_dir, 'Original')
        for name, lid in c.locidx.items():
            res = _loc_image(cpcdir, origdir, name, modo, tintas)
            if res is not None:
                fich = _pic(res[0], res[1], cache_dir)
                if fich is None:
                    info['img_fuera'].append(name)
                else:
                    loc_pics.append((lid - 1, fich))
        info['nimg'] = len(loc_pics)

    # Pantallas sueltas del condact SCR (SCRnn.SCR, nn = su indice): las de 8
    # filas se convierten como las de sala (mismo modo, 64 lineas, ZX0 a imgbuf);
    # las de 24, como la portada (Modo 0 de 16K con sus 16 tintas). Un .scr
    # nativo en img/AmstradCPC cuenta como de 8 filas, igual que en las salas;
    # las 24 solo salen de un png/jpg en proporcion 4:3.
    pant_files = []           # (nombre de fichero, bytes, direccion de carga)
    pant_tabla = []           # (filas, tintas) por pantalla, en orden
    if img_dir:
        import png2cpc
        cpcdir = os.path.join(img_dir, 'AmstradCPC')
        origdir = os.path.join(img_dir, 'Original')
    for i, nombre in enumerate(spec.get('pantallas') or []):
        filas, tintas_scr, datos, dire = 0, [], b'', 0
        if img_dir:
            # con y sin la arroba, como las de sala: busca_img prueba las dos
            # si el nombre la lleva, y aqui se prueba tambien a ponersela (los
            # masteres de img/Original suelen llevarla: @morfina.jpg)
            def _busca(carpeta, exts):
                if not os.path.isdir(carpeta):
                    return None
                return (sx.busca_img(carpeta, nombre, exts) or
                        sx.busca_img(carpeta, '@' + nombre.lstrip('@'), exts))
            p8 = _busca(cpcdir, ('.scr',))
            pp = (_busca(cpcdir, ('.png', '.jpg', '.jpeg')) or
                  _busca(origdir, ('.png', '.jpg', '.jpeg')))
            try:
                if p8 or (pp and sx._clase_pantalla(pp) == 8):
                    res = _convierte_8(p8, pp, modo, tintas)
                    datos = _pic(res[0], res[1], cache_dir) or b''
                    filas = 8 if datos else 0
                elif pp:
                    scr, inks = png2cpc.convert_menu(pp, contrast=True)
                    datos, filas, tintas_scr = bytes(scr), 24, list(inks or [])
                    dire = 0xC000
            except Exception as e:
                info.setdefault('notas_scr', []).append('SCR %s: %s' % (nombre, e))
        pant_tabla.append((filas, tintas_scr))
        if filas:
            pant_files.append(('SCR%02d' % i, datos, dire))
    info['pantallas'] = len([1 for f, _t in pant_tabla if f])

    # El motor: su tamano no depende de nada de lo que falta por decidir (la
    # tabla de ranuras va siempre con una entrada por imagen de sala), asi que
    # se ensambla una vez para saber donde empieza la DB.
    nranuras = max(1, len(loc_pics))
    aviso = _aviso_6128(game.get('metadata'))

    def _motor(dbaddr, slots, tbufn, mtable):
        slots = list(slots) + [(0xC0, 0x4000)] * (nranuras - len(slots))
        return ge.assemble_engine(org=org, db_base=dbaddr, nloc=len(spec['locations']),
                                  pantallas=pant_tabla, modo=modo, tintas=tintas,
                                  slots=slots, tbufn=tbufn, mtable=mtable,
                                  imgtop=IMGTOP, aviso128=aviso)

    def _mkdb(dbaddr, hb=0, texto=None, loc_slot=b''):
        return ge.build_game_db(
            spec['messages'], spec['locations'], spec['vocab'], spec['objects'],
            spec['responses'], spec['startloc'], spec['sysverbs'], spec['width'],
            load=dbaddr, proc_before=spec['proc_before'],
            proc_after=spec['proc_after'], proc_onstart=spec['proc_onstart'],
            title_pal=title_pal, has_music=info['music'],
            has_title=(title is not None), hdrbuf=hb, imgbuf=IMGBUF,
            loc_slot=loc_slot or bytes([255] * len(spec['locations'])),
            vall=spec.get('vall', 0),
            font_acc=spec.get('font_acc', b''),
            timers=spec.get('timers', ()),
            llevarmax=spec.get('llevarmax', 255), fx=fx_blob,
            exit_names=exit_names, texto=texto)

    # El cargador BASIC (con la paleta de la portada) decide donde empieza el
    # motor: a BASIC le tienen que quedar 4K debajo de HIMEM (BASIC_BUFFER)
    tintas_tit = list(title_pal) if title_pal else None

    def _org_para(nbancos, margen):
        car = _cargador(ENGINE_ORG, nbancos, modo, title is not None,
                        bool(musbin), aviso, tintas_tit)
        n, nv = tamano_basic(car)
        return max(ENGINE_ORG, (BASIC_PROG + n + 7 * nv + BASIC_BUFFER + margen
                                + 0xFF) & ~0xFF)
    org = _org_para(0, 64)
    _db, _inf = _mkdb(org)
    msg_tam = _inf['msg_tam']
    tbufn = max(msg_tam)
    code0, _ = _motor(org, [], tbufn, 0x8000)
    dbaddr = org + len(code0)

    def _tope(db_len):
        """Donde acaba la DB, el hdrbuf y MTABLE detras; y si cabe."""
        fin = dbaddr + db_len
        hb = max(0x4000, (fin + 0xFF) & ~0xFF)
        mt = hb + HDRBUF_TAM
        return hb, mt, mt + MTABLE_TAM <= IMGBUF

    def _banca(plano):
        return dict(ventana=0x4000, tam=16384, ids=list(BANCOS),
                    plano=plano, fx_plano=True)

    # 1) todo plano, como siempre: si cabe, el disco vale tambien para un 464
    # 2) si no, el texto que sobra a los bancos del 6128: se quedan planos los
    #    primeros mensajes (los del sistema, los nombres...) hasta llenar la RAM
    # 3) si ni con todo el texto en bancos, fuera FX y descripciones de objeto
    texto = None
    db, dbi = _mkdb(dbaddr)
    hb, mt, cabe = _tope(len(db))
    fx_fuera = []
    if not cabe:
        # el cargador del 6128 es mas largo: el motor sube lo que haga falta
        # para que a BASIC le quede su buffer (con 256 bytes de margen)
        org = _org_para(len(BANCOS), 256)
        code0, _ = _motor(org, [], tbufn, 0x8000)
        dbaddr = org + len(code0)
        todo_banco, _i = _mkdb(dbaddr, texto=_banca(()))
        if not _tope(len(todo_banco))[2]:
            # ni asi: los recortes de antes, sobre la DB con el texto en bancos
            if any(o.get('desc') for o in spec['objects']):
                _con = len(todo_banco)
                spec, _info2 = nc.compile_game(c, sys_msgs, width=width, ficha=ficha,
                                               imagen_intro=True, obj_desc=False)
                todo_banco, _i = _mkdb(dbaddr, texto=_banca(()))
                presupuesto.apunta(
                    'CPC: las descripciones de los objetos no caben (%s bytes) y se '
                    'quedan fuera: EXAMINAR imprime solo el nombre.'
                    % presupuesto._miles(_con - len(todo_banco)))
            if fx_blob and not _tope(len(todo_banco))[2]:
                import capabilities
                import fx_engine as _fe
                _usados = sorted(capabilities.used_fx(game))
                fx_blob = b''
                sin = len(_mkdb(dbaddr, texto=_banca(()))[0])
                hueco = IMGBUF - MTABLE_TAM - HDRBUF_TAM - 0xFF - (dbaddr + sin)
                dentro, mejor = set(), b''
                for i in _usados:
                    cand = _fe.pack_ay_fx(game.get('fx', []) or [], dentro | {i},
                                          clock=1000000)
                    if len(cand) <= hueco:
                        dentro.add(i)
                        mejor = cand
                fx_blob = mejor
                fx_fuera = [i for i in _usados if i not in dentro]
                todo_banco, _i = _mkdb(dbaddr, texto=_banca(()))
        # cuanto texto cabe plano: lo que queda libre con todo en bancos (si
        # se ha vuelto a compilar sin descripciones, los mensajes son otros)
        msg_tam = _i['msg_tam']
        libre = IMGBUF - MTABLE_TAM - HDRBUF_TAM - 0xFF - (dbaddr + len(todo_banco))
        plano, usado = [], 0
        for i, t in enumerate(msg_tam):
            if usado + t > libre:
                break
            plano.append(i)
            usado += t
        texto = _banca(plano)
        db, dbi = _mkdb(dbaddr, texto=texto)
        hb, mt, cabe = _tope(len(db))
        while not cabe and plano:          # por si el redondeo de hdrbuf
            plano.pop()
            texto = _banca(plano)
            db, dbi = _mkdb(dbaddr, texto=texto)
            hb, mt, cabe = _tope(len(db))
    info['fx_fuera'] = fx_fuera
    bancos_texto = dbi['bancos_texto'] if texto else []
    info['bancos_texto'] = [len(b) for b in bancos_texto]
    info['solo_6128'] = bool(bancos_texto)

    # La cache de imagenes: lo que el texto deja libre en los cuatro bancos
    nbt = len(bancos_texto)
    libres = []
    if nbt:
        libres.append((BANCOS[nbt - 1], 0x4000 + len(bancos_texto[-1]), 0x8000))
    libres += [(b, 0x4000, 0x8000) for b in BANCOS[nbt:]]
    donde, slots = _reparte_ranuras(loc_pics, libres)
    loc_slot = bytearray([255] * len(spec['locations']))
    for lid0, k in donde.items():
        if 0 <= lid0 < len(loc_slot):
            loc_slot[lid0] = k
    info['ncache'] = len(donde)

    db, dbi = _mkdb(dbaddr, hb, texto=texto, loc_slot=bytes(loc_slot))
    code, sym = _motor(dbaddr, slots, tbufn, mt)
    if len(code) != len(code0):
        raise RuntimeError('CPC: el motor ha cambiado de tamano entre pasadas')
    if org + len(code) > 0x4000:
        raise RuntimeError('CPC: el motor pasa de &4000 (&%04X)' % (org + len(code)))
    blob = code + db
    info['imgbuf'] = IMGBUF

    # El cargador BASIC carga TODO (musica, titulo, texto, juego). El motor no
    # toca el disco al arrancar: solo pone paleta/musica/modo.
    loader = _cargador(org, len(bancos_texto), modo, title is not None,
                       bool(musbin), aviso, tintas_tit)
    if libre_basic(loader, org) < BASIC_BUFFER:
        raise RuntimeError('CPC: al cargador BASIC no le queda sitio para el '
                           'buffer de disco (%d bytes de %d)'
                           % (libre_basic(loader, org), BASIC_BUFFER))
    files = [('DISC', 'BAS', loader),
             ('GAME', 'BIN', dsk.bin_file('GAME', 'BIN', blob, org))]
    for k, b in enumerate(bancos_texto):
        files.append(('TEXT%d' % k, 'BIN',
                      dsk.bin_file('TEXT%d' % k, 'BIN', bytes(b), 0x4000)))
    if title is not None:
        files.append(('TITLE', 'SCR',
                      dsk.bin_file('TITLE', 'SCR', title, 0xC000)))
    if musbin:
        files.append(('MUSIC', 'BIN',
                      dsk.bin_file('MUSIC', 'BIN', musbin, IMGBUF)))
    for n, comp in loc_pics:
        nm = 'PIC%02d' % n
        files.append((nm, 'SCR', dsk.bin_file(nm, 'SCR', comp, IMGTOP - len(comp))))
    # Las pantallas del SCR entran hasta donde haya disco: si no caben todas,
    # se quedan fuera las ultimas (el condact existe igual y no pinta) y se
    # avisa. Sin esto, un juego que llenara el disco no exportaria.
    def _scr_files():
        return [(nm, 'SCR', dsk.bin_file(nm, 'SCR', datos, dire or (IMGTOP - len(datos))))
                for nm, datos, dire in pant_files]
    scr_fuera = []
    base_files = list(files)
    while True:
        files = base_files + _scr_files()
        nb, ne = dsk.bloques(files)
        if (nb <= dsk.BLOQUES_DATOS and ne <= dsk.ENTRADAS_DIR) or not pant_files:
            break
        nm, _d, _a = pant_files.pop()
        k = int(nm[3:])
        scr_fuera.append(spec['pantallas'][k])
        pant_tabla[k] = (0, [])
    if scr_fuera:
        # el motor lleva SCRT dentro: hay que volver a ensamblar sin ellas
        code, sym = _motor(dbaddr, slots, tbufn, mt)
        blob = code + db
        base_files[1] = ('GAME', 'BIN', dsk.bin_file('GAME', 'BIN', blob, org))
        files = base_files + _scr_files()
    info['pantallas'] = len(pant_files)
    nb, ne = dsk.bloques(files)
    if nb > dsk.BLOQUES_DATOS or ne > dsk.ENTRADAS_DIR:
        raise ValueError(
            'CPC: el disco no da para tanto: %d bloques de 1K de %d (y %d '
            'ficheros de %d). Quita imagenes de sala o acorta texto.'
            % (nb, dsk.BLOQUES_DATOS, ne, dsk.ENTRADAS_DIR))

    # La cache es una OPTIMIZACION, no un requisito: una sala sin ranura se lee
    # del disco cada vez que entras (sli_disc en el motor), y la imagen sale
    # igual. Asi que esto NO es un aviso, es informacion.
    info['sin_cache'] = max(0, len(loc_pics) - info['ncache'])
    info['avisos'] = []
    if fx_fuera:
        _nom = [(game.get('fx') or [])[i - 1].get('name', str(i))
                for i in fx_fuera if i - 1 < len(game.get('fx') or [])]
        info['avisos'].append(
            'CPC: %d efecto(s) FX no caben y quedan mudos: %s. Los demas entran '
            'por orden de la pestana FX.' % (len(fx_fuera), ', '.join(_nom)))
    if scr_fuera:
        info['avisos'].append(
            'CPC: %d pantalla(s) del SCR no caben en el disco y no se pintan: %s. '
            'El .dsk son 178 bloques de 1K; las demas entran por orden de uso.'
            % (len(scr_fuera), ', '.join(scr_fuera)))
    if info['img_fuera']:
        info['avisos'].append('CPC: imagen(es) que no se pueden descomprimir en '
                              'el buffer: %s.' % ', '.join(info['img_fuera']))
    info['notas'] = []
    if bancos_texto:
        info['notas'].append(
            'CPC: el texto no cabe entero en la RAM base y %s bytes van a los '
            'bancos del 6128 (TEXT0..%d.BIN): este disco no arranca en un 464 '
            'sin ampliar (el cargador lo dice).'
            % (presupuesto._miles(sum(info['bancos_texto'])), len(bancos_texto) - 1))
    if info['sin_cache']:
        info['notas'].append(
            'CPC: %d de %d imagenes se leeran del disco cada vez (no caben en '
            'lo que el texto deja libre en los bancos). Se ven igual; solo '
            'tardan un instante al entrar en la sala.'
            % (info['sin_cache'], len(loc_pics)))
    partidas = [('motor + plataforma', len(code)),
                ('base de datos (con los FX)', len(db)),
                ('buffer de disco y acentos', HDRBUF_TAM + MTABLE_TAM)]
    if hb > dbaddr + len(db):
        partidas.append(('hueco hasta el buffer', hb - (dbaddr + len(db))))
    presupuesto.comprueba(
        'Amstrad CPC', partidas,
        IMGBUF - org, 'la RAM libre bajo el buffer de imagen, &%04X-&%04X' % (org, IMGBUF),
        presupuesto.RECORTA_PLANO)
    img = dsk.make_dsk(files)
    _extra = []
    if bancos_texto:
        _extra.append('   texto en los bancos del 6128: %s bytes en %d banco(s)'
                      % (presupuesto._miles(sum(info['bancos_texto'])), len(bancos_texto)))
    if loc_pics:
        _extra.append(
            '   cache de imagenes: %d de %d salas en los bancos del 6128'
            % (info['ncache'], len(loc_pics)))
    _extra.append('   disco: %d de %d bloques de 1K, %d ficheros'
                  % (nb, dsk.BLOQUES_DATOS, len(files)))
    presupuesto.apunta(chr(10).join(_extra))
    with open(dsk_path, 'wb') as f:
        f.write(img)

    info = dict(info)
    info['engine_org'] = org
    info['db_addr'] = dbaddr
    info['blob_size'] = len(blob)
    info['end_addr'] = org + len(blob)
    info['hdrbuf'] = hb
    info['mtable'] = mt
    info['dsk_size'] = len(img)
    info['dsk_bloques'] = nb
    info['modo'] = modo
    info['simbolos'] = sym
    info['presupuesto'] = presupuesto.informe()
    return info


def _music_bin(music_dir):
    """Binario de musica del titulo para cargar en &8B00 (reproductor Z80 + PSG).
    Un .bin de Arkos se usa tal cual; si no, convierte un .mid con mid2psg al
    reloj del AY del CPC. Se recorta si excede el buffer (&8B00..&A67B)."""
    import os
    import glob
    if not os.path.isdir(music_dir):
        return None
    bufmax = 0xA67B - 0x8B00
    bins = sorted(glob.glob(os.path.join(music_dir, '*.bin')))
    mids = sorted(glob.glob(os.path.join(music_dir, '*.mid'))
                  + glob.glob(os.path.join(music_dir, '*.midi')))
    if bins:
        b = open(bins[0], 'rb').read()
        if len(b) > 128:                       # quita cabecera AMSDOS si la trae
            h = b[:128]
            if (sum(h[:67]) & 0xFFFF) == (h[67] | (h[68] << 8)):
                b = b[128:]
        return b[:bufmax]
    if mids:
        import mid2psg
        binb, _ = mid2psg.cpc_music_bin(mids[0], clock=mid2psg.CLOCK_CPC)
        if len(binb) > bufmax:                 # recortar a un limite de frame
            cut = bufmax
            while cut > 71 and binb[cut] != 0xFF:
                cut -= 1
            binb = (binb[:cut] + b'\xFE') if cut > 71 else binb[:bufmax]
        return binb
    return None


def _loc_image(cpcdir, origdir, name, modo=1, tintas=(0, 26)):
    """Imagen de una localizacion -> (64 lineas seguidas de 80 bytes, (tinta 2,
    tinta 3)), o None. Prioridad: img/AmstradCPC/<id>.scr (una pantalla nativa
    del modo del juego: se toman sus 64 lineas de arriba) -> <id>.png|jpg en
    AmstradCPC u Original, convertida al modo del juego."""
    import os
    # con y sin la arroba: los masteres de img/Original la llevan (@playa.png)
    # y los ids de una traduccion pueden no llevarla (playa)
    nombres = [name] + [n for n in (name.lstrip('@'), '@' + name.lstrip('@'))
                        if n != name]

    def busca(base, exts):
        for n in nombres:
            for ext in exts:
                c = os.path.join(base, n + ext)
                if os.path.isfile(c):
                    return c
        return None
    p8 = busca(cpcdir, ('.scr',))
    pp = None
    if not p8:
        pp = busca(cpcdir, ('.png', '.jpg', '.jpeg')) or \
            busca(origdir, ('.png', '.jpg', '.jpeg'))
    if not p8 and not pp:
        return None
    return _convierte_8(p8, pp, modo, tintas)


def _convierte_8(p8, pp, modo, tintas):
    """Una imagen de 8 filas (sala o SCR) en el formato del motor: las lineas
    seguidas y las dos tintas propias (en Modo 2 no hay: van a 0). Un .scr
    nativo en Modo 1 no trae paleta: se le ponen las tintas 2 y 3 que tiene
    el firmware al arrancar."""
    import png2cpc
    if p8:
        scr = (open(p8, 'rb').read() + bytes(16384))[:16384]
        return png2cpc.lineal(scr, IMG_LINEAS), ((20, 6) if modo == 1 else (0, 0))
    if modo == 1:
        return png2cpc.convert_m1(pp, IMG_LINEAS, fijas=tintas)
    return png2cpc.convert_m2_lineal(pp, IMG_LINEAS), (0, 0)


def _title_screen(img_dir):
    """Busca la pantalla de titulo y la devuelve como (pantalla_modo0_16k, inks).
    Prioridad: img/AmstradCPC/screen.scr (nativo, sin paleta -> usa la del firmware)
    -> screen.png|jpg en img/AmstradCPC o img/Original (Modo 0 + 16 tintas)."""
    import os
    cpcdir = os.path.join(img_dir, 'AmstradCPC')
    origdir = os.path.join(img_dir, 'Original')
    for nm in ('screen', 'titulo', 'portada', 'menu'):
        p = os.path.join(cpcdir, nm + '.scr')
        if os.path.isfile(p):
            return (open(p, 'rb').read() + bytes(16384))[:16384], None
        for base in (cpcdir, origdir):
            for ext in ('.png', '.jpg', '.jpeg'):
                pp = os.path.join(base, nm + ext)
                if os.path.isfile(pp):
                    import png2cpc
                    scr, inks = png2cpc.convert_menu(pp, contrast=True)
                    return scr, inks
    return None
