# -*- coding: utf-8 -*-
"""
verify_next.py - Arnes de validacion del motor nativo en ZX Spectrum Next.

Hace lo mismo que verify_cpc.py, con una diferencia importante: alli TODAS las
llamadas de plataforma se anulaban con stubs, asi que el camino de impresion y
el de teclado nunca se ejercitaban. Aqui no hay stubs de texto: corre el
impresor de verdad contra la pantalla ULA simulada (&4000-&57FF) y luego se
decodifican los pixeles de vuelta a texto comparando con la fuente. Lo mismo
con el teclado, que se lee por el puerto &FE como en la maquina real.

    python verify_next.py [juego.yaml]
"""
import os
import sys

import yaml

import cpc_nativo
import game_engine as ge
import nativecc as nc
import next_nativo as nn
import spectrum_export as sx
import z80

ORG = 0x6000
ANCHO = 32


# ---------------------------------------------------------------------------
# construccion
# ---------------------------------------------------------------------------
def construir(game):
    c = sx.recolecta(game)
    sysm, _sal = cpc_nativo._sys_msgs_y_salidas(game.get('metadata') or {})
    while len(sysm) < ge.NSYS:
        sysm.append('')
    spec, _ = nc.compile_game(c, sysm[:ge.NSYS], width=ANCHO)

    code, sym = nn.assemble_engine_next(org=ORG, db_base=ORG)
    dbaddr = ORG + len(code)
    code, sym = nn.assemble_engine_next(org=ORG, db_base=dbaddr)
    db, _ = ge.build_game_db(
        spec['messages'], spec['locations'], spec['vocab'], spec['objects'],
        spec['responses'], spec['startloc'], spec['sysverbs'], spec['width'],
        load=dbaddr, proc_before=spec['proc_before'], proc_after=spec['proc_after'],
        proc_onstart=spec['proc_onstart'], hdrbuf=0, imgbuf=0,
        loc_slot=bytes([255] * len(spec['locations'])), vall=spec['vall'],
        font_acc=spec['font_acc'], timers=spec['timers'],
        llevarmax=spec['llevarmax'])

    mem = bytearray(65536)
    mem[ORG:ORG + len(code)] = code
    mem[dbaddr:dbaddr + len(db)] = db
    cpu = z80.Z80(mem)
    cpu.sp = 0xFFF0
    tec = Teclado(cpu, mem, sym)
    cpu.run(start=sym['init'])
    return cpu, mem, sym, spec, tec, len(code), len(db)


# ---------------------------------------------------------------------------
# teclado simulado: responde al escaneo por el puerto &FE
# ---------------------------------------------------------------------------
class Teclado:
    def __init__(self, cpu, mem, sym):
        self.puertos = [mem[sym['nxkport'] + i] for i in range(8)]
        self.tabla = [mem[sym['nxktab'] + i] for i in range(40)]
        self.pulsada = None
        cpu.hook_in[0xFE] = self._leer

    def pulsa(self, ch):
        self.pulsada = ord(ch) if isinstance(ch, str) else ch

    def suelta(self):
        self.pulsada = None

    def _leer(self, cpu, port):
        if self.pulsada is None:
            return 0xFF
        try:
            idx = self.tabla.index(self.pulsada)
        except ValueError:
            return 0xFF
        fila, bit = divmod(idx, 5)
        if self.puertos[fila] != ((port >> 8) & 0xFF):
            return 0xFF
        return 0xFF & ~(1 << bit)


# ---------------------------------------------------------------------------
# decodificador de pantalla: pixeles -> texto
# ---------------------------------------------------------------------------
def tabla_glifos(mem, sym):
    t = {}
    base = sym['nxfont']
    for i in range(96):
        t[bytes(mem[base + i * 8:base + i * 8 + 8])] = chr(32 + i)
    facc = mem[sym['faccp']] | (mem[sym['faccp'] + 1] << 8)
    if facc:
        acc = sx._ACC_CODE_PT if sx._PT_LANG else sx._ACC_CODE
        por_codigo = {code: ch for ch, code in acc.items()}
        for i in range(16):
            g = bytes(mem[facc + i * 8:facc + i * 8 + 8])
            t.setdefault(g, por_codigo.get(144 + i, '?'))
    t[bytes(8)] = ' '
    return t


def leer_pantalla(mem, sym):
    glifos = tabla_glifos(mem, sym)
    lineas = []
    for fila in range(24):
        alto = 0x40 | (fila & 0x18)
        bajo = (fila & 7) << 5
        out = []
        for col in range(32):
            g = bytes(mem[((alto + l) << 8) | (bajo + col)] for l in range(8))
            out.append(glifos.get(g, '?'))
        lineas.append(''.join(out).rstrip())
    return lineas


def texto_pantalla(mem, sym):
    return chr(10).join(l for l in leer_pantalla(mem, sym) if l.strip())


# ---------------------------------------------------------------------------
# ejecucion acotada de una rutina
# ---------------------------------------------------------------------------
def ejecutar(cpu, mem, addr, pasos=800000):
    mem[0xFFFE] = 0xC9
    cpu.sp = 0xFFEE
    mem[0xFFEE] = 0xFE
    mem[0xFFEF] = 0xFF
    cpu.pc = addr
    cpu.halted = False
    n = 0
    while n < pasos and cpu.pc != 0xFFFE:
        n += 1
        cpu.step()
    if n >= pasos:
        raise RuntimeError('sin terminar en %d pasos desde %04X' % (pasos, addr))
    return n


# ---------------------------------------------------------------------------
# comprobaciones
# ---------------------------------------------------------------------------
def verificar(game):
    cpu, mem, sym, spec, tec, nco, ndb = construir(game)
    EOP, CX = ge.EOP, ge.COP_EXTRA
    SC = 0xD000
    OBJLOC, OBJLIT = sym['objloc'], sym['objlit']
    OBJOPEN, OBJIN = sym['objopen'], sym['objin']
    FLAGS = sym['flags']
    cur = mem[sym['curloc']]
    objw = mem[sym['objweightp']] | (mem[sym['objweightp'] + 1] << 8)
    locdarkp = mem[sym['locdarkp']] | (mem[sym['locdarkp'] + 1] << 8)
    objlightp = mem[sym['objlightp']] | (mem[sym['objlightp'] + 1] << 8)

    def ev(bc):
        mem[SC:SC + len(bc)] = bytes(bc)
        mem[sym['cptr']] = SC & 0xFF
        mem[sym['cptr'] + 1] = (SC >> 8) & 0xFF
        ejecutar(cpu, mem, sym['eval_expr'])
        return cpu.a

    def cond(bc):
        mem[SC:SC + len(bc)] = bytes(bc)
        cpu.hl = SC
        cpu.de = len(bc)
        ejecutar(cpu, mem, sym['run_condacts'])

    E = lambda n: EOP[n]
    res = []
    chk = lambda nombre, ok: res.append((nombre, bool(ok)))

    # ---- 1. camino de texto real: imprimir y releer la pantalla ----
    ejecutar(cpu, mem, sym['nxcls'])
    for ch in 'ABC abc 123':
        cpu.a = ord(ch)
        ejecutar(cpu, mem, sym['txto'])
    chk('TXTO imprime y se relee', leer_pantalla(mem, sym)[0] == 'ABC abc 123')

    # ---- 2. word-wrap del motor sobre 32 columnas ----
    ejecutar(cpu, mem, sym['nxcls'])
    cpu.de = ge.SDARK
    ejecutar(cpu, mem, sym['print_msg'])
    pant = [l for l in leer_pantalla(mem, sym) if l.strip()]
    chk('print_msg + word-wrap <= %d col' % ANCHO,
        len(pant) >= 1 and all(len(l) <= ANCHO for l in pant))

    # ---- 3. descripcion de la localizacion inicial ----
    ejecutar(cpu, mem, sym['nxcls'])
    ejecutar(cpu, mem, sym['describe'])
    desc = [l for l in leer_pantalla(mem, sym) if l.strip()]
    chk('describe pinta la sala inicial', len(desc) >= 1)

    # ---- 3b. desplazamiento de la ventana al llegar abajo ----
    ejecutar(cpu, mem, sym['nxcls'])
    mem[sym['nxrow']] = 22
    mem[sym['nxcol']] = 0
    for ch in 'PENULTIMA':
        cpu.a = ord(ch)
        ejecutar(cpu, mem, sym['txto'])
    cpu.a = 13
    ejecutar(cpu, mem, sym['txto'])
    cpu.a = 10
    ejecutar(cpu, mem, sym['txto'])
    for ch in 'ULTIMA':
        cpu.a = ord(ch)
        ejecutar(cpu, mem, sym['txto'])
    antes = leer_pantalla(mem, sym)
    cpu.a = 13
    ejecutar(cpu, mem, sym['txto'])
    cpu.a = 10
    ejecutar(cpu, mem, sym['txto'])   # fuerza el scroll
    desp = leer_pantalla(mem, sym)
    chk('scroll sube la ventana una linea',
        antes[22] == 'PENULTIMA' and antes[23] == 'ULTIMA'
        and desp[21] == 'PENULTIMA' and desp[22] == 'ULTIMA' and desp[23] == '')

    # ---- 4. teclado por el puerto &FE ----
    tec.suelta()
    ejecutar(cpu, mem, sym['kmread'])
    sin = (cpu.f & 1) == 0
    tec.pulsa('n')
    ejecutar(cpu, mem, sym['kmread'])
    hay = (cpu.f & 1) == 1 and cpu.a == ord('n')
    ejecutar(cpu, mem, sym['kmread'])
    rebote = (cpu.f & 1) == 0          # sigue pulsada: no repite
    tec.suelta()
    ejecutar(cpu, mem, sym['kmread'])
    tec.pulsa('s')
    ejecutar(cpu, mem, sym['kmread'])
    otra = (cpu.f & 1) == 1 and cpu.a == ord('s')
    tec.suelta()
    chk('KMREAD: sin tecla / tecla / antirrebote', sin and hay and rebote)
    chk('KMREAD: segunda tecla distinta', otra)

    # ---- 5. paridad de features con verify_cpc.py ----
    A, B = 5, 6
    cond([CX['WEAR'], A])
    chk('WEAR -> WORN', mem[OBJLOC + A] == ge.WORN and ev([E('WORN'), A, E('END')]) == 1
        and ev([E('CARRIED'), A, E('END')]) == 1)
    cond([CX['REMOVE'], A])
    chk('REMOVE -> CARRIED', mem[OBJLOC + A] == ge.CARRIED and ev([E('WORN'), A, E('END')]) == 0)
    mem[locdarkp + cur] = 1
    mem[objlightp + B] = 1
    mem[OBJLIT + B] = 0
    mem[OBJLOC + B] = cur
    chk('DARK (lampara apagada)', ev([E('DARK'), E('END')]) == 1)
    cond([CX['LIT'], B])
    chk('LIT -> hay luz', ev([E('DARK'), E('END')]) == 0)
    cond([CX['UNLIT'], B])
    chk('UNLIT -> oscuro', ev([E('DARK'), E('END')]) == 1)
    mem[locdarkp + cur] = 0
    mem[objlightp + B] = 0
    mem[OBJLOC + B] = cur
    cond([CX['PUTIN'], A, B])
    chk('PUTIN', mem[OBJLOC + A] == ge.CONTAINED and mem[OBJIN + A] == B + 1)
    chk('PRESENT cerrado=0', ev([E('PRESENT'), A, E('END')]) == 0)
    cond([CX['OPEN'], B])
    chk('OPEN -> HASOBJOPEN', ev([E('HASOBJOPEN'), B, E('END')]) == 1)
    chk('PRESENT abierto=1', ev([E('PRESENT'), A, E('END')]) == 1)
    cond([CX['CLOSE'], B])
    chk('CLOSE -> PRESENT=0', ev([E('PRESENT'), A, E('END')]) == 0)
    cond([CX['TAKEOUT'], A])
    chk('TAKEOUT', mem[OBJLOC + A] == ge.CARRIED and mem[OBJIN + A] == 0)
    mem[OBJLOC + A] = 3
    chk('ISAT', ev([E('ISAT'), A, 3, E('END')]) == 1 and ev([E('ISAT'), A, 4, E('END')]) == 0)
    chk('CHANCE 100/0', ev([E('CHANCE'), 100, E('END')]) == 1 and ev([E('CHANCE'), 0, E('END')]) == 0)
    mem[sym['verbid']] = 7
    mem[sym['nounid']] = 9
    chk('VERB', ev([E('VERB'), 7, E('END')]) == 1 and ev([E('VERB'), 8, E('END')]) == 0)
    chk('NOUN1', ev([E('NOUN1'), 9, E('END')]) == 1 and ev([E('NOUN1'), 254, E('END')]) == 0)
    mem[sym['nounid2']] = 12
    chk('NOUN2', ev([E('NOUN2'), 12, E('END')]) == 1 and ev([E('NOUN2'), 13, E('END')]) == 0)
    nt = len(spec['timers'])
    if nt:
        TCUR, TACT = sym['tcur'], sym['tact']
        cond([CX['TSTART'], 0])
        antes = mem[TCUR]
        ejecutar(cpu, mem, sym['tick_timers'])
        chk('TIMER tick decrementa', mem[TCUR] == antes - 1 and mem[TACT] == 1)
        cond([CX['TRESET'], 0])
        chk('TIMER_RESET', mem[TCUR] == antes)
        cond([CX['TSTOP'], 0])
        chk('TIMER_STOP', mem[TACT] == 0)
    lm = spec['llevarmax']
    if lm != 255:
        oi = 0
        mem[OBJLOC + oi] = cur
        mem[objw + oi] = 50
        mem[FLAGS + lm] = 10
        mem[sym['nounid']] = spec['objects'][oi]['noun']
        ejecutar(cpu, mem, sym['do_get'])
        chk('GET rechaza por peso', mem[OBJLOC + oi] == cur)
        mem[FLAGS + lm] = 200
        mem[OBJLOC + oi] = cur
        mem[sym['nounid']] = spec['objects'][oi]['noun']
        ejecutar(cpu, mem, sym['do_get'])
        chk('GET acepta si cabe', mem[OBJLOC + oi] == ge.CARRIED)

    # ---- 6. AY por los puertos del Next ----
    cpu.a = 8
    cpu.c = 15
    ejecutar(cpu, mem, sym['sndreg'])
    chk('SNDREG escribe en &FFFD/&BFFD',
        cpu.ports.get(0xFFFD) == 8 and cpu.ports.get(0xBFFD) == 15)

    return res, desc, nco, ndb


def teclea(cpu, sym, tec, texto, tope=6000000):
    """Escribe una orden en el juego. Va cambiando el estado del teclado justo
    antes de cada entrada en KMREAD: pulsa una tecla, la suelta en la siguiente
    lectura (que es lo que espera el antirrebote) y pasa a la siguiente."""
    pendientes = list(texto)
    soltar = False
    n = 0
    while n < tope:
        if cpu.pc == sym['kmread']:
            if soltar:
                tec.suelta()
                soltar = False
            elif pendientes:
                tec.pulsa(pendientes.pop(0))
                soltar = True
            else:
                tec.suelta()
                return True
        cpu.step()
        n += 1
    return False


def corre_hasta(cpu, addr, tope=6000000):
    n = 0
    while n < tope and cpu.pc != addr:
        cpu.step()
        n += 1
    return cpu.pc == addr


def verificar_nex(game, salida):
    """Empaqueta el .nex, lo vuelve a leer del disco como lo hace NextZXOS,
    arranca desde el PC de la cabecera y comprueba que llega a pedir orden con
    la sala inicial en pantalla. Prueba del empaquetado, no solo del motor."""
    info = nn.export_nex(game, salida)
    mem, pc, sp, bancos = nn.carga_nex(salida)
    sym = info['simbolos']
    cpu = z80.Z80(mem)
    cpu.sp = sp
    Teclado(cpu, mem, sym)          # sin teclas pulsadas
    cpu.pc = pc
    cpu.halted = False
    n = 0
    while n < 4000000 and cpu.pc != sym['read_line']:
        cpu.step()
        n += 1
    llego = cpu.pc == sym['read_line']
    pant = [l for l in leer_pantalla(mem, sym) if l.strip()]

    # ---- jugar: escribir una orden y ver la respuesta ----
    jugadas = []
    if llego:
        tec2 = Teclado(cpu, mem, sym)
        for orden in ('n', 'coger linterna', 'i'):
            # teclea() vuelve cuando el juego ya esta pidiendo la orden siguiente,
            # o sea con el turno anterior resuelto y pintado.
            if not teclea(cpu, sym, tec2, orden + chr(13)):
                break
            jugadas.append((orden, [l for l in leer_pantalla(mem, sym) if l.strip()]))
    return info, llego, n, pant, bancos, jugadas


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        base, 'Games', 'Operacion Tifon Negro', 'Operacion Tifon Negro.yaml')
    game = yaml.safe_load(open(path, encoding='utf-8'))
    res, desc, nco, ndb = verificar(game)
    ok = sum(1 for _, b in res if b)
    for nombre, b in res:
        print(('  OK  ' if b else ' FALLA') + '  ' + nombre)
    print()
    print('motor+plataforma: %d bytes   base de datos: %d bytes   total: %d' % (nco, ndb, nco + ndb))
    print()
    print('--- pantalla tras describe ---')
    for l in desc:
        print('|' + l)
    print()
    # ---- vuelta completa por el .nex ----
    import tempfile
    salida = os.path.join(tempfile.gettempdir(), 'scriba_prueba_nativo.nex')
    info, llego, pasos, pant, bancos, jugadas = verificar_nex(game, salida)
    print('--- .nex: %s' % os.path.basename(salida))
    print('    bancos %s   PC=&%04X   SP=&%04X   %d bytes (&%04X-&%04X)'
          % (bancos, info['pc'], info['sp'], info['total'], info['org'], info['fin']))
    print('    arranque -> %s en %d instrucciones'
          % ('pide orden' if llego else 'NO LLEGA a pedir orden', pasos))
    for l in pant:
        print('    |' + l)
    res.append(('.nex arranca y pide orden', llego))
    for orden, p in jugadas:
        print()
        print('    --- orden: "%s"' % orden)
        for l in p:
            print('    |' + l)
    res.append(('.nex responde a ordenes escritas', len(jugadas) == 3))
    ok = sum(1 for _, b in res if b)
    print()
    print('%d/%d comprobaciones correctas' % (ok, len(res)))
    sys.exit(0 if ok == len(res) else 1)


if __name__ == '__main__':
    main()
