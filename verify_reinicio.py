# -*- coding: utf-8 -*-
"""
verify_reinicio.py - Que pasa cuando la partida se acaba.

Hasta la v2.53 el motor salia de mainloop con un RET y devolvia el control al
BASIC de la maquina: en el Next, el copyright de Sinclair Research; en cinta,
a recargar. Una aventura de los ochenta no hace eso: ofrece otra partida.

Aqui se comprueban las dos mitades de ese camino, en los tres binarios que lo
recorren (48K, 128K y Next):

  1. que la partida TERMINA de verdad -- el motor llega a la etiqueta
     'gameover', que es justo el retorno del 'call mainloop';
  2. que al pulsar tecla se vuelve a la PORTADA, con su musica (128K y Next;
     el 48K no tiene portada que repintar, solo la pantalla de carga), y de
     ahi a pedir ordenes con el juego reinicializado: quitf a cero, la sala
     inicial y la pantalla limpia, sin el texto de la partida anterior.

El final se fuerza levantando quitf a mano antes de un turno cualquiera: lo
que se prueba es el camino de vuelta, no como se llega al final (de eso ya se
encargan las baterias .pru, que acaban partidas de verdad).

    python verify_reinicio.py [juego.yaml]
"""
import os
import sys

import verify_next as vn

POR_DEFECTO = os.path.join('Games', 'Operacion Tifon Negro',
                           'Operacion Tifon Negro.yaml')

# maquina -> (clase del corredor, etiquetas de la portada que hay que pisar)
MAQUINAS = ('48', '128', 'next')
HITOS = {'48': (),                                   # sin portada propia
         '128': ('s128tit', 's128esp', 'psginit'),
         'next': ('nxtit', 'nxespera', 'psginit')}


def _juego(maquina, yaml_path):
    if maquina == '48':
        import probar_48 as p
        return p.Juego48(yaml_path)
    if maquina == '128':
        import probar_128 as p
        return p.Juego128(yaml_path)
    import probar_juego as p
    return p.Juego(yaml_path)


def comprueba(maquina, yaml_path, res):
    def chk(nombre, ok):
        res.append(('%-4s %s' % (maquina, nombre), bool(ok)))
        return ok

    j = _juego(maquina, yaml_path).arranca()
    cpu, mem, sym, tec = j.cpu, j.mem, j.sym, j.tec

    if 'gameover' not in sym:
        chk('el motor trae la etiqueta gameover', False)
        return
    fin = sym['gameover']
    hitos = {sym[h]: h for h in HITOS[maquina] if h in sym}
    chk('el motor trae las etiquetas de la portada',
        len(hitos) == len(HITOS[maquina]))

    mem[sym['quitf']] = 1              # se fuerza el fin de partida
    j.escribe('ESPERAR')
    if not chk('la partida sale de mainloop en vez de volver al BASIC',
               cpu.pc == fin):
        return

    # A partir de aqui: "pulsa una tecla", portada y otra vez a pedir orden.
    # Se teclea tanto en KMREAD como en el bucle de barrido de la portada, que
    # es donde espera mientras suena la musica.
    visto = []
    fr = sym.get('s128frm') or sym.get('nxframe')
    soltar = False
    n = 0
    while n < 20000000 and cpu.pc != sym['read_line']:
        if cpu.pc in hitos and hitos[cpu.pc] not in visto:
            visto.append(hitos[cpu.pc])
        if cpu.pc == sym['kmread'] or (fr is not None and cpu.pc == fr):
            if soltar:
                tec.suelta()
                soltar = False
            else:
                tec.pulsa(' ')
                soltar = True
        cpu.step()
        n += 1
    tec.suelta()

    if not chk('tras pulsar tecla vuelve a pedir ordenes',
               cpu.pc == sym['read_line']):
        return
    if HITOS[maquina]:
        chk('pasa por la portada y arranca la musica (%s)'
            % ', '.join(HITOS[maquina]), len(visto) == len(HITOS[maquina]))
    chk('la partida nueva empieza inicializada (quitf=0, sala inicial)',
        mem[sym['quitf']] == 0 and j.donde() == j.locs[0])
    pant = [l for l in vn.leer_pantalla(mem, sym) if l.strip()]
    texto = ' '.join(pant).lower()
    chk('la pantalla se limpia: no queda el turno anterior',
        'esperar' not in texto)
    chk('y describe la sala inicial', bool(pant))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    yaml_path = argv[0] if argv else POR_DEFECTO
    res = []
    for maquina in MAQUINAS:
        comprueba(maquina, yaml_path, res)
    bien = sum(1 for _, ok in res if ok)
    for nombre, ok in res:
        print('  %s  %s' % ('OK  ' if ok else 'FALLA', nombre))
    print()
    print('%d/%d' % (bien, len(res)))
    return 0 if bien == len(res) else 1


if __name__ == '__main__':
    sys.exit(main())
