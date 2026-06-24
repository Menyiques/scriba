# -*- coding: utf-8 -*-
"""
verify_cpc.py — Arnés de validación del motor nativo CPC (paridad de features).

Ensambla el motor, construye la base de datos de un juego y, con el emulador Z80
(z80.py), ejercita cada característica para comprobar que se comporta como la
referencia (intérprete de PC): objetos fijos, vestibles, luz/oscuridad,
temporizadores, contenedores, peso y los predicados nuevos.

Uso:
    python verify_cpc.py [juego.yaml]
Sin argumento usa Operacion Tifon Negro. Devuelve código 0 si todo pasa.
"""
import os
import sys

import yaml
import spectrum_export as sx
import nativecc as nc
import game_engine as ge
import z80

_FW = (0xBB5A, 0xBB09, 0xBB06, 0xBC0E, 0xBC32, 0xBC38, 0xBB90, 0xBB96, 0xBD19,
       0xBB66, 0xBBA8, 0xBBAB, 0xBCEF, 0xBCD7, 0xBCDD, 0x8B00, 0x8B03, 0x8B06,
       0xBC77, 0xBC83, 0xBC7A)


def _build(game):
    c = sx.recolecta(game)
    spec, _ = nc.compile_game(c, ['x'] * 14, width=79)
    org = 0x1200
    code, sym = ge.assemble_engine(org=org, db_base=org)
    dbaddr = org + len(code)
    code, sym = ge.assemble_engine(org=org, db_base=dbaddr)
    db, _ = ge.build_game_db(
        spec['messages'], spec['locations'], spec['vocab'], spec['objects'],
        spec['responses'], spec['startloc'], spec['sysverbs'], spec['width'],
        load=dbaddr, proc_before=spec['proc_before'], proc_after=spec['proc_after'],
        proc_onstart=spec['proc_onstart'], hdrbuf=0x6700, imgbuf=0x8B00,
        loc_slot=bytes([255] * len(spec['locations'])), vall=spec['vall'],
        font_acc=spec['font_acc'], timers=spec['timers'],
        llevarmax=spec['llevarmax'])
    mem = bytearray(65536)
    mem[org:org + len(code)] = code
    mem[dbaddr:dbaddr + len(db)] = db
    cpu = z80.Z80(mem)
    cpu.hook_call = {a: (lambda c: None) for a in _FW}
    cpu.hook_call[sym['detect128']] = lambda c: None
    cpu.sp = 0xBFF0
    cpu.run(start=sym['init'])
    return cpu, mem, sym, spec


def _run(cpu, mem, addr):
    mem[0xBFFE] = 0xC9
    cpu.sp = 0xBFEE
    mem[0xBFEE] = 0xFE
    mem[0xBFEF] = 0xBF
    cpu.pc = addr
    cpu.halted = False
    n = 0
    while n < 400000 and cpu.pc != 0xBFFE:
        n += 1
        cpu.step()


def verify(game):
    cpu, mem, sym, spec = _build(game)
    EOP, CX = ge.EOP, ge.COP_EXTRA
    SC = 0xA000
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
        _run(cpu, mem, sym['eval_expr'])
        return cpu.a

    def cond(bc):
        mem[SC:SC + len(bc)] = bytes(bc)
        cpu.hl = SC
        cpu.de = len(bc)
        _run(cpu, mem, sym['run_condacts'])

    E = lambda n: EOP[n]
    res = []

    def chk(name, ok):
        res.append((name, ok))

    A, B = 5, 6
    # vestibles
    cond([CX['WEAR'], A])
    chk('WEAR -> WORN', mem[OBJLOC + A] == ge.WORN and ev([E('WORN'), A, E('END')]) == 1
        and ev([E('CARRIED'), A, E('END')]) == 1)
    cond([CX['REMOVE'], A])
    chk('REMOVE -> CARRIED', mem[OBJLOC + A] == ge.CARRIED and ev([E('WORN'), A, E('END')]) == 0)
    # luz
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
    # contenedores
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
    # predicados
    mem[OBJLOC + A] = 3
    chk('ISAT', ev([E('ISAT'), A, 3, E('END')]) == 1 and ev([E('ISAT'), A, 4, E('END')]) == 0)
    chk('CHANCE 100/0', ev([E('CHANCE'), 100, E('END')]) == 1 and ev([E('CHANCE'), 0, E('END')]) == 0)
    mem[sym['verbid']] = 7
    mem[sym['nounid']] = 9
    chk('VERB', ev([E('VERB'), 7, E('END')]) == 1 and ev([E('VERB'), 8, E('END')]) == 0)
    chk('NOUN1', ev([E('NOUN1'), 9, E('END')]) == 1 and ev([E('NOUN1'), 254, E('END')]) == 0)
    mem[sym['nounid2']] = 12
    chk('NOUN2', ev([E('NOUN2'), 12, E('END')]) == 1 and ev([E('NOUN2'), 13, E('END')]) == 0)
    # temporizadores
    nt = len(spec['timers'])
    if nt:
        TCUR, TACT = sym['tcur'], sym['tact']
        cond([CX['TSTART'], 0])
        before = mem[TCUR]
        _run(cpu, mem, sym['tick_timers'])
        chk('TIMER tick decrementa', mem[TCUR] == before - 1 and mem[TACT] == 1)
        cond([CX['TRESET'], 0])
        chk('TIMER_RESET', mem[TCUR] == before)
        cond([CX['TSTOP'], 0])
        chk('TIMER_STOP', mem[TACT] == 0)
    # peso
    lm = spec['llevarmax']
    if lm != 255:
        oi = 0
        mem[OBJLOC + oi] = cur
        mem[objw + oi] = 50
        mem[FLAGS + lm] = 10
        mem[sym['nounid']] = spec['objects'][oi]['noun']
        _run(cpu, mem, sym['do_get'])
        chk('GET rechaza por peso', mem[OBJLOC + oi] == cur)
        mem[FLAGS + lm] = 200
        mem[OBJLOC + oi] = cur
        mem[sym['nounid']] = spec['objects'][oi]['noun']
        _run(cpu, mem, sym['do_get'])
        chk('GET acepta si cabe', mem[OBJLOC + oi] == ge.CARRIED)
    return res


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        base, 'Games', 'Operacion Tifon Negro', 'Operacion Tifon Negro.yaml')
    game = yaml.safe_load(open(path, encoding='utf-8'))
    res = verify(game)
    ok = sum(1 for _, b in res if b)
    for name, b in res:
        print(('  OK  ' if b else ' FALLA') + '  ' + name)
    print('\n%d/%d comprobaciones correctas' % (ok, len(res)))
    sys.exit(0 if ok == len(res) else 1)


if __name__ == '__main__':
    main()
