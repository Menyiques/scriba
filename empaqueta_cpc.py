#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
empaqueta_cpc.py — Crea una imagen de disco .dsk (formato CPCEMU estandar,
AMSDOS DATA) en Python puro y empaqueta el .bas Locomotive de cpc_export.

Formato del disco:
  · DATA: 40 pistas, 9 sectores/pista (IDs &C1..&C9), 512 B/sector, 1 cara.
  · Bloque CP/M = 1024 B (2 sectores). Directorio = 64 entradas (bloques 0 y 1).
    Sin pistas reservadas. Layout 1:1 (sector ID &C(k+1) = sector logico k).
  · Ficheros ASCII SIN cabecera AMSDOS (como SAVE,A): el cargador de BASIC los
    re-tokeniza al hacer RUN"NOMBRE". El ultimo registro se rellena con &1A.

Uso:
  from empaqueta_cpc import export_dsk
  export_dsk(game, 'juego.dsk', modo=1)            # game = dict del YAML
  python empaqueta_cpc.py juego.yaml 1             # genera juego_cpc.dsk
"""

import sys

SECT_PER_TRACK = 9
SECT_SIZE      = 512
NTRACKS        = 40
BLOCK_SIZE     = 1024
SECT_PER_BLOCK = BLOCK_SIZE // SECT_SIZE          # 2
DIR_BLOCKS     = 2
DIR_ENTRIES    = 64
FIRST_DATA_BLOCK = DIR_BLOCKS
TOTAL_BLOCKS   = NTRACKS * SECT_PER_TRACK * SECT_SIZE // BLOCK_SIZE  # 180
SECTOR_IDS     = [0xC1 + i for i in range(SECT_PER_TRACK)]
FILLER         = 0xE5
EOF_CPM        = 0x1A


# ─── Construccion de la imagen .dsk ─────────────────────────────────────────
def _pad_name(name, ext):
    nm = (name.upper() + ' ' * 8)[:8].encode('ascii', 'replace')
    ex = (ext.upper() + ' ' * 3)[:3].encode('ascii', 'replace')
    return nm, ex


def make_dsk(files):
    """files: lista de (name<=8, ext<=3, data:bytes). Devuelve bytes del .dsk."""
    blocks = {}                                    # nº bloque -> bytearray(1024)
    dir_data = bytearray([FILLER]) * (DIR_ENTRIES * 32)
    next_block = FIRST_DATA_BLOCK
    dir_idx = 0

    for (name, ext, data) in files:
        n_records = (len(data) + 127) // 128
        padded = bytearray(data)
        if len(padded) % 128:                      # rellena el ultimo registro
            padded += bytes([EOF_CPM] * (128 - len(padded) % 128))
        n_blocks = (len(padded) + BLOCK_SIZE - 1) // BLOCK_SIZE or 1
        if next_block + n_blocks > TOTAL_BLOCKS:
            raise ValueError('el juego no cabe en el disco (180 bloques)')
        block_list = list(range(next_block, next_block + n_blocks))
        next_block += n_blocks
        for bi, bnum in enumerate(block_list):
            chunk = padded[bi * BLOCK_SIZE:(bi + 1) * BLOCK_SIZE]
            buf = bytearray([FILLER] * BLOCK_SIZE)
            buf[:len(chunk)] = chunk
            blocks[bnum] = buf

        # entradas de directorio: 16 bloques (16 KB / 128 registros) por extent
        nm, ex = _pad_name(name, ext)
        rem = n_records
        for ext_no, k in enumerate(range(0, n_blocks, 16)):
            al = block_list[k:k + 16]
            rc = min(128, rem); rem -= rc
            ent = bytearray(32)
            ent[0] = 0                              # usuario 0
            ent[1:9] = nm
            ent[9:12] = ex
            ent[12] = ext_no & 0x1F                 # EX (extent bajo)
            ent[13] = 0                             # S1
            ent[14] = (ext_no >> 5) & 0xFF          # S2 (extent alto)
            ent[15] = rc                            # RC (registros del extent)
            for j, b in enumerate(al):
                ent[16 + j] = b                     # bloques (8 bits, DSM<256)
            if dir_idx >= DIR_ENTRIES:
                raise ValueError('directorio lleno (64 entradas)')
            dir_data[dir_idx * 32:(dir_idx + 1) * 32] = ent
            dir_idx += 1

    blocks[0] = bytearray(dir_data[0:BLOCK_SIZE])
    blocks[1] = bytearray(dir_data[BLOCK_SIZE:2 * BLOCK_SIZE])

    def sector_bytes(track, k):
        L = track * SECT_PER_TRACK + k
        bnum, half = divmod(L, SECT_PER_BLOCK)
        blk = blocks.get(bnum)
        if blk is None:
            return bytes([FILLER] * SECT_SIZE)
        return bytes(blk[half * SECT_SIZE:(half + 1) * SECT_SIZE])

    out = bytearray()
    dib = bytearray(256)
    dib[0:34] = b"MV - CPCEMU Disk-File\r\nDisk-Info\r\n"
    dib[0x22:0x2E] = b"Scriba CPC  "
    dib[0x30] = NTRACKS
    dib[0x31] = 1
    tsize = 256 + SECT_PER_TRACK * SECT_SIZE        # 4864
    dib[0x32] = tsize & 0xFF
    dib[0x33] = (tsize >> 8) & 0xFF
    out += dib

    for t in range(NTRACKS):
        tib = bytearray(256)
        tib[0:12] = b"Track-Info\r\n"
        tib[0x10] = t
        tib[0x11] = 0                               # cara
        tib[0x14] = 2                               # tamano sector N=2 (512)
        tib[0x15] = SECT_PER_TRACK
        tib[0x16] = 0x4E                            # GAP#3
        tib[0x17] = FILLER
        for k in range(SECT_PER_TRACK):
            o = 0x18 + k * 8
            tib[o + 0] = t
            tib[o + 1] = 0
            tib[o + 2] = SECTOR_IDS[k]
            tib[o + 3] = 2
            tib[o + 6] = SECT_SIZE & 0xFF
            tib[o + 7] = (SECT_SIZE >> 8) & 0xFF
        out += tib
        for k in range(SECT_PER_TRACK):
            out += sector_bytes(t, k)
    return bytes(out)


# ─── Lectura de vuelta (autovalidacion, sin emulador) ───────────────────────
def read_dsk(dsk):
    """Parsea el .dsk y devuelve dict nombre.ext -> bytes (con relleno EOF)."""
    ntracks = dsk[0x30]
    tsize = dsk[0x32] | (dsk[0x33] << 8)
    sectors = {}                                    # (track, id) -> bytes
    for t in range(ntracks):
        base = 256 + t * tsize
        nsec = dsk[base + 0x15]
        off = base + 256
        for k in range(nsec):
            sid = dsk[base + 0x18 + k * 8 + 2]
            sectors[(t, sid)] = dsk[off:off + SECT_SIZE]
            off += SECT_SIZE

    def logical_sector(L):
        track, k = divmod(L, SECT_PER_TRACK)
        return sectors[(track, SECTOR_IDS[k])]

    def block(b):
        return (logical_sector(b * SECT_PER_BLOCK) +
                logical_sector(b * SECT_PER_BLOCK + 1))

    dir_bytes = block(0) + block(1)
    extents = {}                                    # name.ext -> {ex: (rc, [blk])}
    for i in range(DIR_ENTRIES):
        e = dir_bytes[i * 32:(i + 1) * 32]
        if e[0] == FILLER:
            continue
        name = e[1:9].decode('ascii', 'replace').rstrip()
        ext = bytes(b & 0x7F for b in e[9:12]).decode('ascii', 'replace').rstrip()
        exn = (e[12] & 0x1F) | (e[14] << 5)
        rc = e[15]
        al = [b for b in e[16:32] if b]
        extents.setdefault(f'{name}.{ext}', {})[exn] = (rc, al)

    files = {}
    for fn, exts in extents.items():
        data = bytearray()
        for exn in sorted(exts):
            rc, al = exts[exn]
            ext_bytes = bytearray()
            for b in al:
                ext_bytes += block(b)
            files[fn] = files.get(fn, b'')
            data += ext_bytes[:rc * 128]
        files[fn] = bytes(data)
    return files


# ─── API de alto nivel ──────────────────────────────────────────────────────
def basic_bytes(game, modo=1):
    """Genera el .bas Locomotive como bytes ASCII (CR/LF). Devuelve (bytes, avisos)."""
    import cpc_export as cx
    import spectrum_export as sx
    c = cx.cpc_prepare(sx.recolecta(game))
    lines = cx.genera_cpc(c, modo)
    text = '\r\n'.join(lines) + '\r\n'
    return text.encode('ascii', 'replace'), c.avisos


def export_dsk(game, dsk_path, modo=1, nombre='GAME'):
    """Genera el .bas y construye un .dsk arrancable (RUN\"GAME\" o RUN\"DISC\")."""
    bas, avisos = basic_bytes(game, modo)
    loader = (f'10 MODE {modo}:RUN"{nombre}.BAS"\r\n').encode('ascii')
    dsk = make_dsk([(nombre, 'BAS', bas), ('DISC', 'BAS', loader)])
    with open(dsk_path, 'wb') as f:
        f.write(dsk)
    return dsk, avisos


# ─── Ficheros binarios con cabecera AMSDOS (para pantallas .scr) ────────────
def amsdos_header(name, ext, length, load, exec_=None):
    h = bytearray(128)
    nm, ex = _pad_name(name, ext)
    h[1:9] = nm; h[9:12] = ex
    h[18] = 2                                   # tipo binario
    h[21] = load & 0xFF; h[22] = (load >> 8) & 0xFF
    h[24] = length & 0xFF; h[25] = (length >> 8) & 0xFF
    e = load if exec_ is None else exec_
    h[26] = e & 0xFF; h[27] = (e >> 8) & 0xFF
    h[64] = length & 0xFF; h[65] = (length >> 8) & 0xFF; h[66] = (length >> 16) & 0xFF
    chk = sum(h[0:67]) & 0xFFFF
    h[67] = chk & 0xFF; h[68] = (chk >> 8) & 0xFF
    return bytes(h)


def bin_file(name, ext, data, load):
    return amsdos_header(name, ext, len(data), load) + data


def export_dsk_img(game, dsk_path, img_base, modo=2, buffer=0x8B00, dither='bayer'):
    """Genera el .bas (Modo 2 con imagenes) + .dsk. Resolucion por localizacion:
      1) img/AmstradCPC/<id>.scr   -> pantalla CPC nativa, se usa TAL CUAL
      2) img/AmstradCPC/<id>.png|jpg -> ya adaptada al CPC (codifica sin re-contraste)
      3) img/Original/<id>.png|jpg -> master (conversion completa con contraste)
    Cada pantalla se comprime (RLE) si cabe en el buffer; si no, se guarda en
    crudo (16 KB) y se carga directa a &C000."""
    import os, math
    import cpc_export as cx
    import spectrum_export as sx
    import png2cpc
    cpcdir = os.path.join(img_base, 'AmstradCPC')
    origdir = os.path.join(img_base, 'Original')
    BUFMAX = 0xA600 - buffer

    def screen_for(name, dith):
        p = os.path.join(cpcdir, name + '.scr')
        if os.path.isfile(p):
            return (open(p, 'rb').read() + bytes(16384))[:16384]
        for ext in ('.png', '.jpg', '.jpeg'):
            p = os.path.join(cpcdir, name + ext)
            if os.path.isfile(p):                       # ya adaptada: no re-ditherizar
                return png2cpc.convert_m2(p, 64, contrast=False, dither='threshold')
        for ext in ('.png', '.jpg', '.jpeg'):
            p = os.path.join(origdir, name + ext)
            if os.path.isfile(p):
                return png2cpc.convert_m2(p, 64, contrast=True, dither=dith)
        return None

    # ── titulo (Modo 0) y musica: no dependen del dither, se calculan una vez ──
    menu_inks = menu_scr = None
    for nm in ('screen', 'menu', 'titulo', 'portada'):
        found = False
        for base, ctr in ((cpcdir, False), (origdir, True)):
            for ext in ('.png', '.jpg', '.jpeg'):
                mp = os.path.join(base, nm + ext)
                if os.path.isfile(mp):
                    menu_scr, menu_inks = png2cpc.convert_menu(mp, contrast=ctr)
                    found = True; break
            if found:
                break
        if found:
            break
    avisos_mus = []
    music_bin = None
    music_dir = os.path.join(os.path.dirname(img_base) or '.', 'music')
    if os.path.isdir(music_dir):
        _f = os.listdir(music_dir)
        _mid = sorted(f for f in _f if f.lower().endswith(('.mid', '.midi')))
        _bin = sorted(f for f in _f if f.lower().endswith('.bin'))
        if _bin:                                   # .bin de Arkos (hecho a mano) tiene prioridad
            music_bin = open(os.path.join(music_dir, _bin[0]), 'rb').read()
            if len(music_bin) > 128:
                _h = music_bin[:128]
                if (sum(_h[:67]) & 0xFFFF) == (_h[67] | (_h[68] << 8)):
                    music_bin = music_bin[128:]
        elif _mid:                                 # si no hay .bin, convierte el .mid (sin tools)
            import mid2psg
            try:
                music_bin, _ = mid2psg.cpc_music_bin(os.path.join(music_dir, _mid[0]))
            except Exception as ex:
                avisos_mus.append('musica: no pude convertir %s: %s' % (_mid[0], ex))
    if music_bin and len(music_bin) > BUFMAX:
        avisos_mus.append('musica demasiado larga; se omite')
        music_bin = None
    has_music = bool(music_bin) and menu_inks is not None
    blank = png2cpc.rle_pack(bytes(16384))

    def construir(dith):
        c = cx.cpc_prepare(sx.recolecta(game))
        image_locs, raw_locs, pic_files = set(), set(), []
        for lid in c.locids:
            scr = screen_for(lid, dith)
            if scr is None:
                continue
            idx = c.locidx[lid]
            image_locs.add(idx)
            comp = png2cpc.rle_pack(scr)
            if len(comp) <= BUFMAX:
                pic_files.append(('PIC%d' % idx, 'SCR', bin_file('PIC%d' % idx, 'SCR', comp, buffer)))
            else:
                raw_locs.add(idx)
                pic_files.append(('PIC%d' % idx, 'SCR', bin_file('PIC%d' % idx, 'SCR', scr, 0xC000)))
        lines = cx.genera_cpc(c, modo=2, image_locs=image_locs, menu_inks=menu_inks,
                              raw_locs=raw_locs, music=has_music, comprime_texto=True)
        bas = ('\r\n'.join(lines) + '\r\n').encode('latin-1', 'replace')
        files = [('GAME', 'BAS', bas),
                 ('DISC', 'BAS', b'10 MODE 2:RUN"GAME.BAS"\r\n')] + pic_files
        files.append(('BLANK', 'SCR', bin_file('BLANK', 'SCR', blank, buffer)))
        if has_music:
            files.append(('MUSIC', 'BIN', bin_file('MUSIC', 'BIN', music_bin, 0x8B00)))
        if menu_scr is not None:
            files.append(('MENU', 'SCR', bin_file('MENU', 'SCR', menu_scr, 0xC000)))
        nblk = sum(math.ceil(len(fdata) / 1024) for _, _, fdata in files) + 2  # +directorio
        return files, image_locs, c.avisos, nblk

    files, image_locs, avisos, nblk = construir(dither)
    if nblk > 180 and dither != 'threshold':       # no cabe -> reintenta con umbral
        files, image_locs, avisos, nblk = construir('threshold')
        avisos.append('imagenes a dither UMBRAL (con %s no cabian) para entrar en el disco' % dither)
    if nblk > 180:
        raise ValueError('No cabe en un disco: necesita %d bloques (178 utiles). '
                         'Reduce localizaciones/imagenes o reparte en varios discos.' % nblk)
    dsk = make_dsk(files)
    with open(dsk_path, 'wb') as f:
        f.write(dsk)
    return dsk, avisos + avisos_mus, image_locs


if __name__ == '__main__':
    import yaml, os
    path = sys.argv[1] if len(sys.argv) > 1 else 'tifon_demo.yaml'
    arg2 = sys.argv[2] if len(sys.argv) > 2 else '1'
    game = yaml.safe_load(open(path, encoding='utf-8'))
    if os.path.isdir(arg2):
        # build con imagenes (Modo 2, pantalla partida B/N): arg2 = carpeta de imagenes
        out = path.rsplit('.', 1)[0] + '_cpc_img.dsk'
        dsk, avisos, locs = export_dsk_img(game, out, arg2)
        print(f'[empaqueta_cpc] {out}: {len(dsk)} bytes | imagenes en localizaciones '
              f'{sorted(locs)} | {len(avisos)} avisos')
    else:
        modo = int(arg2)
        out = path.rsplit('.', 1)[0] + '_cpc.dsk'
        dsk, avisos = export_dsk(game, out, modo=modo)
        print(f'[empaqueta_cpc] {out}: {len(dsk)} bytes, modo {modo}, {len(avisos)} avisos')
        bas, _ = basic_bytes(game, modo)
        got = read_dsk(dsk).get('GAME.BAS', b'').rstrip(bytes([EOF_CPM]))
        print(f'  GAME.BAS ida-y-vuelta intacto: {got == bas.rstrip(bytes([EOF_CPM]))}')
