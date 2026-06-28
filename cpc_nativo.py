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
    salidas = {1: t('dir_n').strip(), 2: t('dir_s').strip(), 3: t('dir_e').strip(),
               4: t('dir_o').strip(), 5: t('dir_u').strip(), 6: t('dir_d').strip()}
    return msgs, salidas
ENGINE_ORG = 0x1200          # direccion de carga del motor + DB

# Musica del titulo: el reproductor se engancha a la interrupcion de frame con
# KL_ADD_FRAME_FLY (game_engine.show_title). Toda la E/S del AY queda dentro de la
# interrupcion (sin chocar con el escaneo de teclado del firmware) y el primer
# plano solo espera la tecla. Activada.
MUSICA_TITULO = True


def export_native(game, dsk_path, modo=2, img_dir=None):
    """Compila el juego y escribe un .dsk arrancable. Devuelve un dict de info.
    modo: 1 (40 col, Modo 1) o 2 (80 col, Modo 2)."""
    import spectrum_export as sx
    import nativecc as nc
    import game_engine as ge
    import dsk

    c = sx.recolecta(game)
    # Ancho de wrap = columnas - 1: el firmware del CPC auto-salta de linea al
    # llegar al borde de la ventana (80/40 col). Si wrap_print usara el ancho
    # completo, su salto chocaria con el del firmware (lineas en blanco y texto
    # revuelto). Dejando 1 columna de margen, el firmware nunca auto-salta.
    width = 79 if modo == 2 else 39
    # Mensajes de sistema y nombres de salida localizados (metadata['mensajes']).
    sys_msgs, exit_names = _sys_msgs_y_salidas(game.get('metadata'))
    spec, info = nc.compile_game(c, sys_msgs, width=width)

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
    # cambiar a Modo 0). Al pulsar tecla, el motor vuelve a Modo 2 para el juego.
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
        import os as _os
        music_dir = _os.path.join(_os.path.dirname(img_dir), 'music')   # <raiz>/music
        musbin = _music_bin(music_dir)
        if musbin:
            info['music'] = True

    # Imagenes de localizacion (PIC<n>.SCR, n = indice 0-based de la localizacion).
    # Se cargan del disco al entrar en cada sitio, se descomprimen al tercio
    # superior y el texto va en una ventana debajo (pantalla partida Modo 2).
    import os as _os
    loc_pics = []
    info['nimg'] = 0
    if img_dir:
        import png2cpc
        cpcdir = _os.path.join(img_dir, 'AmstradCPC')
        origdir = _os.path.join(img_dir, 'Original')
        for name, lid in c.locidx.items():
            pic = _loc_image(cpcdir, origdir, name)
            if pic is not None:
                loc_pics.append((lid - 1, png2cpc.rle_pack(pic)))
        info['nimg'] = len(loc_pics)

    # Plan de cache en RAM de 128K (CPC 6128). Asigna slots a las imagenes que
    # quepan, por orden de localizacion. loc_slot[lid0] = slot (0..NSLOT-1) o 255.
    # SLOT_SIZE/SPB/NSLOT deben coincidir con las constantes del motor (slottab).
    SLOT_SIZE = 5120          # &1400; 3 por banco (3*5120=15360 <= 16384)
    NSLOT = 12                # 4 bancos extra x 3 slots
    nloc_total = len(spec['locations'])
    loc_slot = bytearray([255] * nloc_total)
    _nxt = 0
    for lid0, comp in loc_pics:
        if _nxt < NSLOT and len(comp) <= SLOT_SIZE and 0 <= lid0 < nloc_total:
            loc_slot[lid0] = _nxt
            _nxt += 1
    info['ncache'] = _nxt

    # dos pasadas: la 1a da la longitud del motor para colocar la DB justo detras
    code0, _ = ge.assemble_engine(org=org, db_base=org)
    dbaddr = org + len(code0)
    code, _ = ge.assemble_engine(org=org, db_base=dbaddr)

    def _mkdb(hb, ib):
        return ge.build_game_db(
            spec['messages'], spec['locations'], spec['vocab'], spec['objects'],
            spec['responses'], spec['startloc'], spec['sysverbs'], spec['width'],
            load=dbaddr, proc_before=spec['proc_before'],
            proc_after=spec['proc_after'], proc_onstart=spec['proc_onstart'],
            title_pal=title_pal, has_music=info['music'],
            has_title=(title is not None), hdrbuf=hb, imgbuf=ib,
            loc_slot=bytes(loc_slot), vall=spec.get('vall', 0),
            font_acc=spec.get('font_acc', b''),
            timers=spec.get('timers', ()),
            llevarmax=spec.get('llevarmax', 255), fx=fx_blob,
            exit_names=exit_names)[0]
    # 1a pasada: longitud de la DB; el buffer de cabecera CAS IN va detras de la DB.
    # imgbuf se fija en &8B00 (zona de la musica, libre durante el juego) porque
    # esta FUERA de la ventana de banca &4000-&7FFF: asi sirve de buffer de
    # transferencia con los bancos extra sin que se pagine.
    db0 = _mkdb(0, 0)
    db_end = dbaddr + len(db0)
    hdrbuf = (db_end + 0xFF) & ~0xFF       # buffer de cabecera CAS IN (2 KB)
    imgbuf = 0x8B00                        # buffer de imagen (base RAM, fuera de banca)
    db = _mkdb(hdrbuf, imgbuf)
    blob = code + db
    info['imgbuf'] = imgbuf

    # El cargador BASIC carga TODO (musica, titulo, juego). El motor no toca el
    # disco: solo pone paleta/musica/modo. Asi se evita corromper la base de datos.
    mode_cmd = 'MODE 2' if modo == 2 else 'MODE 1'
    parts = ['MEMORY &11FF']
    if info['music']:
        parts.append('LOAD"MUSIC.BIN"')
    if title is not None:
        parts.append('MODE 0')            # titulo en Modo 0; el motor vuelve a 2
        # Pantalla en negro durante la carga: las 16 tintas a 0 para no mostrar la
        # portada con la paleta por defecto (erronea) mientras carga GAME.BIN. El
        # motor pone la paleta real (set_title_pal) al arrancar y la portada aparece.
        parts.append('FOR p=0 TO 15:INK p,0:NEXT')
        parts.append('LOAD"TITLE.SCR"')
    else:
        parts.append(mode_cmd)
    parts.append('LOAD"GAME.BIN"')
    parts.append('CALL &%04X' % org)
    loader = ('10 ' + ':'.join(parts) + '\r\n').encode('ascii')
    files = [('DISC', 'BAS', loader),
             ('GAME', 'BIN', dsk.bin_file('GAME', 'BIN', blob, org))]
    if title is not None:
        files.append(('TITLE', 'SCR',
                      dsk.bin_file('TITLE', 'SCR', title, 0xC000)))
    if musbin:
        files.append(('MUSIC', 'BIN',
                      dsk.bin_file('MUSIC', 'BIN', musbin, 0x8B00)))
    for n, comp in loc_pics:
        nm = 'PIC%02d' % n
        files.append((nm, 'SCR', dsk.bin_file(nm, 'SCR', comp, imgbuf)))

    img = dsk.make_dsk(files)
    with open(dsk_path, 'wb') as f:
        f.write(img)

    info = dict(info)
    info['engine_org'] = org
    info['db_addr'] = dbaddr
    info['blob_size'] = len(blob)
    info['end_addr'] = org + len(blob)
    info['dsk_size'] = len(img)
    info['modo'] = modo
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


def _loc_image(cpcdir, origdir, name):
    """Imagen de una localizacion -> pantalla Modo 2 (tercio superior, 16 KB).
    Prioridad: img/AmstradCPC/<id>.scr (nativo, tal cual) -> <id>.png|jpg
    en AmstradCPC u Original (convertida a Modo 2, 64 lineas arriba)."""
    import os
    p = os.path.join(cpcdir, name + '.scr')
    if os.path.isfile(p):
        return (open(p, 'rb').read() + bytes(16384))[:16384]
    for base in (cpcdir, origdir):
        for ext in ('.png', '.jpg', '.jpeg'):
            pp = os.path.join(base, name + ext)
            if os.path.isfile(pp):
                import png2cpc
                scr = png2cpc.convert_m2(pp, 64, contrast=True, dither='bayer')
                return (bytes(scr) + bytes(16384))[:16384]
    return None


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
