# -*- coding: utf-8 -*-
"""
verify_click.py - El clic al teclear, en las maquinas que se pueden simular.

Cada tecla que acepta la linea de ordenes (letras, BORRAR y ENTER) tiene que
hacer un clic corto -- KCLICK, una rutina por maquina --, y solo esas: ni la
pausa de "pulsa una tecla" ni la portada. Aqui se teclea una orden y se cuentan
los clics por la salida de cada maquina:

  * 48K y 128K: el bit 4 del puerto &FE (el altavoz); ademas los tres bits
    bajos, el borde, tienen que seguir siendo los del borde puesto;
  * CPC: el canal A del AY por la SNDREG del firmware (volumen bajo y de
    vuelta a 0);
  * PCW: los comandos 11 (pitido puesto) y 12 (pitido quitado) del puerto &F8.

El Next comparte la rutina del Spectrum y el MSX2 usa el bit de clic del PPI
(&AB): de esos dos solo se comprueba que la rutina esta en el binario, porque
aqui no hay simulador de sus salidas.

    python verify_click.py [juego.yaml]
"""
import os
import sys

POR_DEFECTO = os.path.join('Games', 'Operacion Tifon Negro',
                           'Operacion Tifon Negro.yaml')
ORDEN = 'MIRAR'                       # cinco letras y un ENTER: seis teclas
TECLAS = len(ORDEN) + 1

res = []


def chk(nombre, ok):
    res.append((nombre, bool(ok)))


def _spectrum(maquina, yaml_path):
    if maquina == '48':
        import probar_48 as m
        j = m.Juego48(yaml_path)
    else:
        import probar_128 as m
        j = m.Juego128(yaml_path)
    j.arranca()
    fe = []
    j.cpu.hook_out[0xFE] = lambda c, p, v: fe.append(v)
    j.escribe(ORDEN)
    # el borde que hubiera antes del clic: la ultima escritura sin altavoz
    altavoz = [v for v in fe if v & 16]
    bordes = {v & 7 for v in fe}
    ciclos = sum(1 for a, b in zip([0] + fe, fe) if (b & 16) and not (a & 16))
    chk('%sK  un clic (dos ciclos de altavoz) por tecla: %d en %d teclas'
        % (maquina, ciclos, TECLAS), ciclos == 2 * TECLAS)
    chk('%sK  el altavoz acaba quitado (no se queda sonando)' % maquina,
        bool(fe) and not (fe[-1] & 16))
    chk('%sK  el borde no cambia: siempre el mismo color (%s)'
        % (maquina, sorted(bordes)), len(bordes) == 1 and bool(altavoz))
    j.cierra() if hasattr(j, 'cierra') else None


def _cpc(yaml_path):
    import probar_cpc as pc
    j = pc.JuegoCPC(yaml_path)
    seq = []
    fw = j.firmware

    def espia(cpu, pcx):
        if pcx == 0xBD34:                       # MC SOUND REGISTER
            seq.append((cpu.a, cpu.c))
        return fw(cpu, pcx)
    j.firmware = espia
    j.arranca()
    del seq[:]
    j.escribe(ORDEN)
    # cada clic: R6=12, R7=&37, R8=6 ... R8=0
    subidas = sum(1 for a, c in seq if a == 8 and c == 6)
    bajadas = sum(1 for a, c in seq if a == 8 and c == 0)
    chk('CPC  un clic por tecla: %d en %d teclas' % (subidas, TECLAS),
        subidas == TECLAS)
    chk('CPC  cada clic vuelve a volumen 0 (%d)' % bajadas, bajadas == subidas)
    chk('CPC  el mezclador del clic es solo ruido en A (&37)',
        all(c == 0x37 for a, c in seq if a == 7))


def _pcw(yaml_path):
    import probar_pcw as pw
    j = pw.JuegoPCW(yaml_path)
    j.arranca()
    f8 = []
    previo = j.cpu.hook_out.get(0xF8)

    def espia(cpu, port, v):
        f8.append(v)
        if previo:
            previo(cpu, port, v)
    j.cpu.hook_out[0xF8] = espia
    j.escribe(ORDEN)
    pit = [v for v in f8 if v in (11, 12)]
    chk('PCW  un pitido puesto (11) y quitado (12) por tecla: %d en %d teclas'
        % (pit.count(11), TECLAS),
        pit == [11, 12] * TECLAS)


def _estaticas():
    import game_engine as ge
    import msx2_nativo as mx
    import next_nativo as nx
    import pcw_nativo as pn
    _c, sym = ge.assemble_engine(modo=1, pantallas=[])
    chk('CPC  el binario lleva KCLICK', 'kclick' in sym)
    for nombre, src in (('Next', nx.PLAT_ASM), ('MSX2', mx.plat_asm()),
                        ('PCW', pn.plat_asm())):
        chk('%s  la capa de la maquina define KCLICK (una vez)' % nombre,
            src.count('\nKCLICK:') == 1)
    chk('MSX2  el clic es el bit 7 del PPI (&AB, &0F/&0E)',
        'out   (&AB),a' in mx.plat_asm() and '&0F' in mx.plat_asm())
    chk('todas  read_line llama a KCLICK con la tecla ya leida',
        'jr    nc,rl_idle      ; sin tecla -> precargar una contigua y reintentar\n'
        '        call  KCLICK' in ge.ENGINE_ASM)


def main():
    yaml_path = sys.argv[1] if len(sys.argv) > 1 else POR_DEFECTO
    _estaticas()
    _spectrum('48', yaml_path)
    _spectrum('128', yaml_path)
    _cpc(yaml_path)
    _pcw(yaml_path)
    bien = sum(1 for _, ok in res if ok)
    for nombre, ok in res:
        print('  %s  %s' % ('OK  ' if ok else 'FALLA', nombre))
    print()
    print('%d/%d' % (bien, len(res)))
    return 0 if bien == len(res) else 1


if __name__ == '__main__':
    sys.exit(main())
