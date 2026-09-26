# -*- coding: utf-8 -*-
"""
bateria_msx2.py - Bateria de pruebas sobre el cartucho MSX2 REAL, en openMSX.

Hermana de bateria_next.py, con el mismo formato de pruebas (.pru) y el mismo
juez (Relator); solo cambia el emulador. El juego se compila en MODO PRUEBA
(msx2_nativo._modo_prueba): el cartucho lleva el guion en sus ultimos bancos,
se teclea solo y copia cada caracter que imprime al "debugdevice" de openMSX
(puertos &2E/&2F), que lo escribe a un fichero. Lo que se prueba es lo que se
distribuye: la cabecera y el cargador de la ROM, el paso a RAM, el mapper
ASCII16, el VDP en SCREEN 5 y la BIOS de verdad (C-BIOS, que es libre y viene
con openMSX; con --maquina se puede usar cualquier otra que se tenga).

USO
    python bateria_msx2.py juego.yaml pruebas.pru [opciones]

    -v / -vv          como en bateria_next.py
    --openmsx RUTA    el emulador (si no, la variable OPENMSX o el PATH)
    --maquina M       maquina de openMSX (por defecto C-BIOS_MSX2_EU)
    --segundos N      tope de tiempo EMULADO (por defecto se estima)
    --traza FILE      guarda la traza cruda
    --png CARPETA     al acabar, vuelca la pantalla (la VRAM) a un PNG

openMSX se baja de https://openmsx.org (el instalador de Windows ya trae las
maquinas C-BIOS). El emulador corre sin ventana y a toda velocidad.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import yaml

import bateria_next as bn
import msx2_nativo as mx

MAQUINA = 'C-BIOS_MSX2_EU'


def busca_openmsx(ruta=None):
    cands = [ruta, os.environ.get('OPENMSX'), 'openmsx', 'openmsx.exe',
             r'C:\Program Files\openMSX\openmsx.exe',
             r'C:\Program Files (x86)\openMSX\openmsx.exe']
    for cand in cands:
        if not cand:
            continue
        if os.path.isfile(cand):
            return cand
        hallado = shutil.which(cand)
        if hallado:
            return hallado
    raise RuntimeError('no encuentro openMSX. Pasa --openmsx RUTA, pon la '
                       'variable de entorno OPENMSX o metelo en el PATH. Se '
                       'descarga de https://openmsx.org')


def _tcl(ruta):
    return ruta.replace('\\', '/')


def ejecuta(openmsx, rom, segundos, maquina=MAQUINA, png=None, paciencia=600):
    """Corre el cartucho y devuelve los bytes que salieron por el debugdevice."""
    tmp = tempfile.mkdtemp(prefix='scriba_msx_')
    traza = os.path.join(tmp, 'traza.txt')
    vram = os.path.join(tmp, 'vram.bin')
    script = os.path.join(tmp, 'bateria.tcl')
    volcado = ''
    if png:
        volcado = ('set f [open "%s" w]; fconfigure $f -translation binary; '
                   'puts -nonewline $f [debug read_block VRAM 0 27136]; '
                   'for {set i 0} {$i < 16} {incr i} '
                   '{puts -nonewline $f [getcolor $i]}; close $f; '
                   % _tcl(vram))
    with io.open(script, 'w', encoding='ascii') as f:
        f.write('set renderer none\n'
                'set throttle off\n'
                'set mute on\n'
                'set debugoutput "%s"\n'
                'debug set_watchpoint write_io 0x2D {} {%s exit}\n'
                'after time %d {%s exit}\n'
                % (_tcl(traza), volcado, segundos, volcado))
    env = dict(os.environ)
    env.setdefault('SDL_VIDEODRIVER', 'dummy')
    env.setdefault('SDL_AUDIODRIVER', 'dummy')
    try:
        p = subprocess.run([openmsx, '-machine', maquina, '-ext', 'debugdevice',
                            '-carta', rom, '-romtype', 'ASCII16',
                            '-script', script],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, env=env, timeout=paciencia)
        salida = p.stdout.decode('latin-1', 'replace')
    except subprocess.TimeoutExpired:
        salida = 'openMSX no termino en %ds' % paciencia
    try:
        datos = open(traza, 'rb').read() if os.path.isfile(traza) else b''
        if png and os.path.isfile(vram):
            vram_png(open(vram, 'rb').read(), png)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return datos, salida


def vram_png(datos, destino):
    """La VRAM de SCREEN 5 (27136 bytes + 16 colores 'RGB' de 0..7) -> PNG."""
    from PIL import Image
    v, pal = datos[:27136], datos[27136:]
    cols = [tuple(int(pal[3 * i + k:3 * i + k + 1] or b'0') * 255 // 7
                  for k in range(3)) for i in range(16)]
    im = Image.new('RGB', (256, 212))
    px = im.load()
    for y in range(212):
        for x in range(128):
            b = v[y * 128 + x]
            px[2 * x, y] = cols[b >> 4]
            px[2 * x + 1, y] = cols[b & 15]
    im.resize((512, 424), Image.NEAREST).save(destino)


def guion_de(pruebas):
    """El de bateria_next, mas (ENTER): pulsar ENTER sin escribir nada, como
    en probar_juego."""
    g = bytearray()
    for _nombre, pasos in pruebas:
        g += bn.RESET + bn.FOTO
        for tipo, dato in pasos:
            if tipo != 'orden':
                continue
            if str(dato).strip().upper() == '(ENTER)':
                g += b'\r' + bn.FOTO
                continue
            orden = bn._tecleable(dato)
            if not orden:
                raise ValueError('orden vacia o no tecleable: %r' % dato)
            g += orden.encode('ascii') + b'\r' + bn.FOTO
    return bytes(g)


class Relator(bn.Relator):
    """Tras un FIN DEL JUEGO la partida se queda parada (el cartucho de pruebas
    tira las teclas hasta la prueba siguiente), asi que las ordenes que queden
    no imprimen nada: se juzgan contra la ultima respuesta, que es lo que
    seguiria en pantalla. Una orden normal nunca sale vacia: lleva su eco."""

    ultimo = ''

    def _paso(self, texto, foto):
        if texto.strip():
            self.ultimo = texto
        elif self.k > 0:
            texto = self.ultimo
        return bn.Relator._paso(self, texto, foto)

    def _reset(self):
        self.ultimo = ''
        return bn.Relator._reset(self)


def main():
    argv = sys.argv[1:]
    conval = ('--openmsx', '--maquina', '--segundos', '--traza', '--png')
    sueltos, salta = [], False
    for a in argv:
        if salta:
            salta = False
            continue
        if a in conval:
            salta = True
        elif not a.startswith('-'):
            sueltos.append(a)
    if len(sueltos) < 2:
        print(__doc__)
        sys.exit(2)
    yaml_path, pru_path = sueltos[0], sueltos[1]
    nivel = 2 if '-vv' in argv else (1 if '-v' in argv else 0)
    openmsx = busca_openmsx(bn._opcion(argv, '--openmsx'))
    maquina = bn._opcion(argv, '--maquina', MAQUINA)
    raiz = os.path.dirname(os.path.abspath(yaml_path))
    game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
    pruebas, saltadas = [], 0
    for nombre, pasos in bn.lee_pru(pru_path):
        # "=== [128 next pc] nombre": solo en esas maquinas, como en probar_juego
        m = re.match(r'\[([^\]]+)\]\s*(.*)', nombre)
        if m and not set(m.group(1).lower().split()) & {'msx', 'msx2'}:
            saltadas += 1
            continue
        pruebas.append((nombre, pasos))
    guion = guion_de(pruebas)
    nordenes = sum(1 for _, p in pruebas for t, _d in p if t == 'orden')
    nchecks = sum(1 for _, p in pruebas for t, _d in p if t != 'orden')
    print('emulador   %s (%s)' % (openmsx, maquina))
    print('juego      %s' % os.path.basename(yaml_path))
    print('bateria    %s: %d prueba(s), %d orden(es), %d comprobacion(es)'
          % (os.path.basename(pru_path), len(pruebas), nordenes, nchecks)
          + ('; %d de otras maquinas, saltadas' % saltadas if saltadas else ''))
    sys.stdout.flush()

    t0 = time.time()
    import presupuesto
    presupuesto.empieza()
    rom, info = mx.compila(game, game_dir=raiz, guion=guion)
    rom_path = os.path.join(tempfile.gettempdir(), 'scriba_bateria_msx2.rom')
    with open(rom_path, 'wb') as f:
        f.write(rom)
    print('compilado  %d loc, %d obj, %d imagenes; %d bytes de motor + %d de '
          'datos; cartucho de %d KB; guion de %d bytes (%.1fs)'
          % (info['localizaciones'], info['objetos'], len(info['imagenes']),
             info['codigo'], info['datos'], len(rom) // 1024, len(guion),
             time.time() - t0))
    segundos = int(bn._opcion(argv, "--segundos", 0)) or (60 + 2 * nordenes +
                                                           10 * len(pruebas))
    print('jugando    %d segundos emulados como mucho\n' % segundos)
    sys.stdout.flush()

    ref = bn.Referencias(game)
    rel = Relator(bn.plan_de(pruebas), ref, nivel)
    acc = bn._mapa_acentos(ref.pt)
    t0 = time.time()
    datos, salida = ejecuta(openmsx, rom_path, segundos, maquina,
                            png=bn._opcion(argv, '--png'))
    texto = bn.descodifica(datos, acc)
    if bn._opcion(argv, '--traza'):
        io.open(bn._opcion(argv, '--traza'), 'w', encoding='utf-8').write(texto)
    rel.come(texto)
    tardado = time.time() - t0
    if rel.t < 0:
        print('Ninguna partida llego a empezar (%.0fs). El emulador dijo:\n' % tardado)
        print(salida.strip()[-2000:] or '(nada)')
        print('\nY por el puerto de traza:\n%s' % (texto.strip()[:2000] or '(nada)'))
        sys.exit(1)
    rel.cierra()
    print()
    if not nivel:
        anterior = None
        for nombre, detalle in rel.fallos:
            if nombre != anterior:
                print('=== %s' % nombre)
                anterior = nombre
            print('        FALLA %s' % detalle)
        if rel.fallos:
            print()
    if not bn.FIN_RE.search(texto):
        print('AVISO: el guion no llego al final en %d segundos emulados; '
              'reintenta con --segundos %d' % (segundos, segundos * 2))
    print('%d comprobacion(es) en %d prueba(s), %s  (%.0fs de emulador)'
          % (rel.hechas, len(pruebas),
             '%d fallo(s)' % len(rel.fallos) if rel.fallos else 'todo correcto',
             tardado))
    sys.exit(1 if rel.fallos else 0)


if __name__ == '__main__':
    main()
