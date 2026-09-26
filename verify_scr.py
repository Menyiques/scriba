# -*- coding: utf-8 -*-
"""
verify_scr.py - El condact SCR en las maquinas de Spectrum.

Se inyectan en Tifon dos respuestas de prueba -una que pinta una tira de 8
filas reasignandola a una sala (SCR @playa), otra que pinta una pantalla
entera de 24 (SCR screen)- y se comprueba, en 48K, 128K y Next, que:

  * SCR de 8 filas deja la imagen arriba y el texto debajo (fila 8);
  * SCR @sala repinta en el acto si estas en esa sala, y la sala se sigue
    describiendo con esa pantalla en vez de con su imagen;
  * SCR de 24 filas tapa todo (scrfull=1) y se va con el siguiente CLS/DESC.

En 48K y 128K se compara la pantalla ULA byte a byte contra el flujo ZX0
descomprimido; en Next se mira el banco de Layer 2 y el clip, que es donde
vive la imagen. El CPC se juega entero en el simulador de probar_cpc (disco,
cargador y RAM de 128K) y se compara la pantalla con lo que convierte el export.

    python verify_scr.py [juego.yaml]
"""
import copy
import io
import os
import sys
import tempfile

import yaml

import spectrum_export as sx
import verify_next as vn

POR_DEFECTO = os.path.join('Games', 'Operacion Tifon Negro',
                           'Operacion Tifon Negro.yaml')

# Dos respuestas que no tocan nada del juego: EXAMINAR BOMBA reasigna a la playa
# la tira 'acantilado'; EXAMINAR CAJA pinta la pantalla entera 'screen'.
_RESP = ('ON EXAMI BOMBA _\n  SCR @playa acantilado.scr\n  PRINT "cambiada"\n  MATCH\nENDON\n'
         'ON EXAMI CAJA _\n  SCR screen\n  PRINT "cielo"\n  MATCH\nENDON\n')


def _juego(maquina, yaml_path):
    game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
    g = copy.deepcopy(game)
    g.setdefault('condacts', {})
    g['condacts']['responses'] = _RESP + (g['condacts'].get('responses') or '')
    raiz = os.path.dirname(os.path.abspath(yaml_path))
    import probar_juego as pj
    import spectrum_export as _sx
    c = _sx.recolecta(g)

    if maquina == 'next':
        import next_nativo as nn
        j = pj.Juego.__new__(pj.Juego)
        j.game = g
        j.nex = os.path.join(tempfile.gettempdir(), 'scriba_scr.nex')
        j.info = nn.export_nex(g, j.nex,
                               datadir=os.path.join(raiz, 'temp', 'Next', 'data'),
                               musicdir=os.path.join(raiz, 'music'))
        j.sym = j.info['simbolos']
    else:
        cls = __import__('probar_128' if maquina == '128' else 'probar_48')
        Juego = cls.Juego128 if maquina == '128' else cls.Juego48
        j = Juego.__new__(Juego)
        j.game = g
        import verify_next as _vn
        if maquina == '128':
            import spectrum128_nativo as s128
            (code, db, sym, spec, dbaddr, payload, avisos,
             npsg, psg_nom, ex) = s128.compila(g, raiz, ancho=_vn.ANCHO)
            j.code, j.db, j.dbaddr, j.sym, j.payload = code, db, dbaddr, sym, payload
        else:
            import spectrum48_nativo as s48
            code, db, sym, spec, dbaddr = s48.compila(g, ancho=_vn.ANCHO,
                                                      org=s48.ORG, game_dir=raiz)
            j.code, j.db, j.dbaddr, j.sym = code, db, dbaddr, sym
        j.info = {}
    j.vars = {k.upper(): i for i, k in enumerate(c.vars.keys())}
    j.locs = list(c.locids)
    j.objs = {n.upper(): i for i, n in enumerate(
        n for n, _ in sorted(c.objidx.items(), key=lambda kv: kv[1]))}
    j.cpu = j.mem = j.tec = None
    return j.arranca(), raiz


def _flujos_esperados(raiz, nombres):
    pant, _ = sx.pantallas_spectrum(os.path.join(raiz, 'img', 'Spectrum'), nombres)
    out = {}
    for nombre, filas, fl in pant:
        out[nombre] = (filas, b''.join(sx.dzx0_simula(f) for f in fl))
    return out


def _spectrum(maquina, yaml_path, res):
    def chk(n, ok):
        res.append(('%-4s %s' % (maquina, n), bool(ok)))

    vn.PILA_ARNES = 0xBFEE if maquina == '128' else 0xFFEE
    j, raiz = _juego(maquina, yaml_path)
    cpu, mem, sym = j.cpu, j.mem, j.sym
    esp = _flujos_esperados(raiz, ['acantilado', 'screen'])

    p = j.escribe('EXAMINAR BOMBA')            # SCR @playa acantilado (8 filas)
    filas, raw = esp['acantilado']
    chk('SCR @sala pinta la tira arriba y el texto debajo',
        bytes(mem[0x4000:0x4800]) == raw[:2048] and mem[sym['nxwt']] == 8)
    chk('SCR @sala deja el texto de la respuesta en pantalla',
        'cambiada' in ' '.join(p))
    j.escribe('MIRAR')                          # describe: repinta la reasignada
    chk('la sala se describe con la pantalla reasignada',
        bytes(mem[0x4000:0x4800]) == raw[:2048] and mem[sym['nxwt']] == 8)
    j.escribe('EXAMINAR CAJA')                  # SCR screen (24 filas)
    chk('SCR de 24 filas tapa todo (scrfull=1)', mem[sym['scrfull']] == 1)
    j.escribe('MIRAR')                          # DESC la quita
    chk('un DESC quita la pantalla entera y vuelve la de la sala',
        mem[sym['scrfull']] == 0 and mem[sym['nxwt']] == 8)


def _next(yaml_path, res):
    def chk(n, ok):
        res.append(('next %s' % n, bool(ok)))

    vn.PILA_ARNES = vn.__dict__.get('PILA_ARNES')   # verificar_nex la ajusta sola
    import next_nativo as nn
    j, raiz = _juego('next', yaml_path)
    cpu, mem, sym = j.cpu, j.mem, j.sym
    scrt = sym['scrt']

    def l2_banco():
        return cpu.nextreg.get(0x12)

    j.escribe('EXAMINAR BOMBA')                 # SCR @playa acantilado (8 filas)
    chk('SCR @sala apunta Layer 2 a su banco',
        l2_banco() == mem[scrt] and mem[sym['nxwt']] == 8)
    j.escribe('MIRAR')
    chk('la sala se describe con esa pantalla', l2_banco() == mem[scrt]
        and mem[sym['nxwt']] == 8)
    j.escribe('EXAMINAR CAJA')                  # SCR screen (24 filas)
    chk('SCR de 24 filas: Layer 2 a pantalla completa y scrfull=1',
        cpu.nextreg.get(0x18) == 191 and mem[sym['scrfull']] == 1)
    j.escribe('MIRAR')
    chk('un DESC apaga la pantalla entera (scrfull=0)', mem[sym['scrfull']] == 0)


def _cpc(yaml_path, res):
    """El CPC, en el simulador de probar_cpc: el .dsk entero, con su cargador,
    su CAS IN y su RAM de 128K. La tira de 8 filas tiene que quedar en las 64
    lineas de arriba tal cual la convierte el export (Modo 1, ZX0), y la de
    24, en Modo 0 y entera en la pantalla, hasta el siguiente DESC."""
    import cpc_nativo as cn
    import png2cpc
    import probar_cpc as pc
    game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
    g = copy.deepcopy(game)
    g.setdefault('condacts', {})
    g['condacts']['responses'] = _RESP + (g['condacts'].get('responses') or '')
    raiz = os.path.dirname(os.path.abspath(yaml_path))

    def chk(n, ok):
        res.append(('cpc  %s' % n, bool(ok)))

    # Tifon llena el disco, y la pantalla de 24 filas son 16K: con todas sus
    # salas no entraria. La prueba va con una carpeta de imagenes que solo
    # trae las dos que usa (la tira y la pantalla entera, que es tambien la
    # portada).
    import shutil
    img = os.path.join(tempfile.gettempdir(), 'scriba_scr_cpc', 'img')
    shutil.rmtree(os.path.dirname(img), ignore_errors=True)
    os.makedirs(os.path.join(img, 'Original'))
    import glob
    pantalla = sorted(glob.glob(os.path.join(raiz, 'img', 'Original', 'screen.*')))[0]
    for f in (os.path.join(raiz, 'img', 'Original', '@acantilado.png'), pantalla):
        shutil.copy(f, os.path.join(img, 'Original', os.path.basename(f)))
    j = pc.JuegoCPC(yaml_path, game=g, img_dir=img)
    metidas = sum(1 for k in j.ficheros if k.startswith('SCR'))
    aviso = any('pantalla' in a.lower() and 'no caben' in a.lower()
                for a in j.info['avisos'])
    chk('las pantallas del SCR entran en el .dsk o se avisa', metidas > 0 or aviso)
    if not metidas:
        return
    j.arranca()
    mem, sym = j.mem, j.sym
    tintas = cn._tintas_texto(g, 1)
    raw, t23 = cn._loc_image(os.path.join(img, 'AmstradCPC'),
                             os.path.join(img, 'Original'), '@acantilado', 1, tintas)

    def tira():
        return (png2cpc.lineal(mem[0xC000:0x10000], cn.IMG_LINEAS) == raw
                and tuple(j.tintas[2:4]) == tuple(t23) and j.pant.w[2] == 8)

    p = j.escribe('EXAMINAR BOMBA')             # SCR @playa acantilado (8 filas)
    chk('SCR @sala pinta la tira arriba, con sus tintas, y el texto debajo', tira())
    chk('SCR @sala deja el texto de la respuesta en pantalla',
        'cambiada' in ' '.join(p))
    j.escribe('MIRAR')                          # describe: repinta la reasignada
    chk('la sala se describe con la pantalla reasignada', tira())
    j.escribe('EXAMINAR CAJA')                  # SCR screen (24 filas)
    scr, _inks = png2cpc.convert_menu(pantalla, contrast=True)
    chk('SCR de 24 filas: Modo 0, la pantalla entera y scrfull=1',
        j.modo == 0 and mem[sym['scrfull']] == 1
        and bytes(mem[0xC000:0x10000]) == bytes(scr))
    j.escribe('MIRAR')                          # DESC la quita
    chk('un DESC vuelve al Modo 1 y a la sala (scrfull=0)',
        j.modo == 1 and mem[sym['scrfull']] == 0 and tira())


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    yaml_path = argv[0] if argv else POR_DEFECTO
    res = []
    for maquina in ('48', '128'):
        _spectrum(maquina, yaml_path, res)
    _next(yaml_path, res)
    _cpc(yaml_path, res)
    bien = sum(1 for _, ok in res if ok)
    for nombre, ok in res:
        print('  %s  %s' % ('OK  ' if ok else 'FALLA', nombre))
    print()
    print('%d/%d' % (bien, len(res)))
    return 0 if bien == len(res) else 1


if __name__ == '__main__':
    sys.exit(main())
