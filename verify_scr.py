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
vive la imagen. El CPC va por disco (CAS IN) y su prueba es el export, no el
simulador: se comprueba aparte que las pantallas entran en el .dsk.

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
    """El CPC va por disco: se comprueba que las pantallas del SCR se convierten
    y se meten en el .dsk (o se avisa si no caben)."""
    import cpc_nativo
    game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
    g = copy.deepcopy(game)
    g.setdefault('condacts', {})
    g['condacts']['responses'] = _RESP + (g['condacts'].get('responses') or '')
    raiz = os.path.dirname(os.path.abspath(yaml_path))
    tmp = os.path.join(tempfile.gettempdir(), 'scriba_scr.dsk')
    info = cpc_nativo.export_native(g, tmp, modo=2,
                                    img_dir=os.path.join(raiz, 'img'))
    d = open(tmp, 'rb').read()
    # o entran en el disco, o hay un aviso claro de que no caben (Tifon va lleno)
    metidas = sum(1 for k in range(8) if ('SCR%02d   SCR' % k).encode() in d)
    aviso = any('pantalla' in a.lower() and 'no caben' in a.lower()
                for a in info['avisos'])
    res.append(('cpc  las pantallas del SCR entran en el .dsk o se avisa',
                metidas > 0 or aviso))


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
