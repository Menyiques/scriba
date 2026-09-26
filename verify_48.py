# -*- coding: utf-8 -*-
"""
verify_48.py - Arnes de validacion del motor nativo en ZX Spectrum 48K.

Monta el binario que produce spectrum48_nativo (motor + capa de plataforma sin
una sola instruccion Z80N) en los 64K simulados de z80.py y comprueba que el
camino de verdad funciona: imprime sobre la pantalla ULA, vuelve a leer los
pixeles y los compara con la fuente. El decodificador de pantalla y el teclado
simulado son los mismos de verify_next.py, porque la pantalla y el teclado de
un 48K y de un Next son el mismo hierro.

    python verify_48.py [juego.yaml]
"""
import sys

import yaml

import game_engine as ge
import spectrum48_nativo as s48
import verify_next as vn
import z80


def construir(game):
    code, db, sym, spec, dbaddr = s48.compila(game, ancho=vn.ANCHO, org=s48.ORG)
    mem = bytearray(65536)
    mem[s48.ORG:s48.ORG + len(code)] = code
    mem[dbaddr:dbaddr + len(db)] = db
    cpu = z80.Z80(mem)
    cpu.sp = s48.SP48
    tec = vn.Teclado(cpu, mem, sym)
    cpu.run(start=sym['init'])
    return cpu, mem, sym, spec, tec, len(code), len(db), dbaddr


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        'Games/Operacion Tifon Negro/Operacion Tifon Negro.yaml'
    game = yaml.safe_load(open(path, encoding='utf-8'))
    cpu, mem, sym, spec, tec, nco, ndb, dbaddr = construir(game)

    print('ZX Spectrum 48K - motor nativo Z80 (sin Boriel)')
    print('  motor+plataforma : %6d bytes  (&%04X-&%04X)'
          % (nco, s48.ORG, dbaddr - 1))
    print('  base de datos    : %6d bytes  (&%04X-&%04X)'
          % (ndb, dbaddr, dbaddr + ndb - 1))
    print('  total            : %6d de %d bytes del mapa plano (&%04X-&%04X)'
          % (nco + ndb, s48.TOPE48 - s48.ORG, s48.ORG, s48.TOPE48 - 1))
    print('  libre            : %6d bytes (y %d de pila)' % (s48.TOPE48 - (s48.ORG + nco + ndb), s48.PILA48))
    print('  %d localizaciones, %d objetos, %d mensajes'
          % (len(spec['locations']), len(spec['objects']), len(spec['messages'])))
    print()

    res = []

    def chk(nombre, ok):
        res.append((nombre, bool(ok)))

    # --- 1. el impresor ULA: imprimir y releer los pixeles ---
    vn.ejecutar(cpu, mem, sym['nxcls'])
    for ch in 'ABC abc 123 ,.;':
        cpu.a = ord(ch)
        vn.ejecutar(cpu, mem, sym['txto'])
    linea = vn.leer_pantalla(mem, sym)[0]
    chk('TXTO imprime sobre la ULA y se relee', linea == 'ABC abc 123 ,.;')
    if linea != 'ABC abc 123 ,.;':
        print('    lei: %r' % linea)

    # --- 2. las 42 columnas, de la 0 a la 41 ---
    vn.ejecutar(cpu, mem, sym['nxcls'])
    patron = ''.join('0123456789'[i % 10] for i in range(42))
    for ch in patron:
        cpu.a = ord(ch)
        vn.ejecutar(cpu, mem, sym['txto'])
    chk('42 columnas completas', vn.leer_pantalla(mem, sym)[0] == patron)

    # --- 3. word-wrap del motor ---
    vn.ejecutar(cpu, mem, sym['nxcls'])
    cpu.de = ge.SDARK
    vn.ejecutar(cpu, mem, sym['print_msg'])
    pant = [l for l in vn.leer_pantalla(mem, sym) if l.strip()]
    chk('print_msg con word-wrap <= 42 col',
        len(pant) >= 1 and all(len(l) <= vn.ANCHO for l in pant))

    # --- 4. la partida entera desde start: init + on_start + describe ---
    mem[0xFFFE] = 0xC9
    cpu.sp = s48.SP48
    vn.ejecutar(cpu, mem, sym['nxcls'])
    vn.ejecutar(cpu, mem, sym['init'])
    hl = mem[sym['onstartp']] | (mem[sym['onstartp'] + 1] << 8)
    if hl:
        cpu.hl = hl
        vn.ejecutar(cpu, mem, sym['run_proc'], sym=sym, tec=tec)
    vn.ejecutar(cpu, mem, sym['describe'], sym=sym, tec=tec)
    pantalla = [l for l in vn.leer_pantalla(mem, sym) if l.strip()]
    chk('describe pinta la sala inicial', len(pantalla) >= 1)
    chk('sin caracteres ilegibles', not any('?' in l for l in pantalla))

    # --- 5. desplazamiento de la ventana ---
    vn.ejecutar(cpu, mem, sym['nxcls'])
    mem[sym['nxrow']] = 23
    mem[sym['nxcol']] = 0
    for ch in 'ULTIMA':
        cpu.a = ord(ch)
        vn.ejecutar(cpu, mem, sym['txto'])
    cpu.a = 13
    vn.ejecutar(cpu, mem, sym['txto'])
    cpu.a = 10
    vn.ejecutar(cpu, mem, sym['txto'], sym=sym, tec=tec)
    chk('la ventana sube al llegar abajo',
        vn.leer_pantalla(mem, sym)[22] == 'ULTIMA')

    # --- 6. BRIGHT / FLASH / INVERSE ---
    CX = ge.COP_EXTRA
    SC = 0xE000            # scratch por encima de la base de datos

    def condact(*bc):
        mem[SC:SC + len(bc)] = bytes(bc)
        cpu.hl = SC
        cpu.de = len(bc)
        vn.ejecutar(cpu, mem, sym['run_condacts'])

    condact(CX['BRIGHT'], 1)
    chk('BRIGHT 1 enciende el bit 6 del atributo', mem[sym['nxattr']] & 0x40)
    condact(CX['FLASH'], 1)
    chk('FLASH 1 enciende el bit 7', mem[sym['nxattr']] & 0x80)
    condact(CX['BRIGHT'], 0)
    chk('BRIGHT 0 lo apaga y no toca el resto',
        not (mem[sym['nxattr']] & 0x40) and (mem[sym['nxattr']] & 0x80))
    condact(CX['FLASH'], 0)

    # INVERSE no es un bit del atributo: invierte los PIXELES del caracter
    vn.ejecutar(cpu, mem, sym['nxcls'])
    mem[sym['nxrow']] = 0
    mem[sym['nxcol']] = 0
    cpu.a = ord('A')
    vn.ejecutar(cpu, mem, sym['txto'])
    normal = bytes(mem[0x4000 + (i << 8)] for i in range(8))
    vn.ejecutar(cpu, mem, sym['nxcls'])
    mem[sym['nxrow']] = 0
    mem[sym['nxcol']] = 0
    condact(CX['INVERSE'], 1)
    cpu.a = ord('A')
    vn.ejecutar(cpu, mem, sym['txto'])
    inverso = bytes(mem[0x4000 + (i << 8)] for i in range(8))
    esperado = bytes((~b) & 0xFC for b in normal)
    chk('INVERSE 1 complementa los 6 pixeles del glifo', inverso == esperado)
    condact(CX['INVERSE'], 0)
    vn.ejecutar(cpu, mem, sym['nxcls'])
    mem[sym['nxrow']] = 0
    mem[sym['nxcol']] = 0
    cpu.a = ord('A')
    vn.ejecutar(cpu, mem, sym['txto'])
    chk('INVERSE 0 lo deja como estaba',
        bytes(mem[0x4000 + (i << 8)] for i in range(8)) == normal)

    # --- 7. MCWAIT espera de verdad (PAUSE y los FX dependen de ello) ---
    mc = sym['mcwait']
    base = s48.ORG
    chk('MCWAIT es EI+HALT, no un RET pelado',
        mem[mc] == 0xFB and mem[mc + 1] == 0x76)

    # PAUSE 3 tiene que pasar por MCWAIT tres veces
    mem[SC:SC + 2] = bytes([CX['PAUSE'], 3])
    cpu.hl = SC
    cpu.de = 2
    mem[0xFFFE] = 0xC9
    cpu.sp = 0xFFEE
    mem[0xFFEE] = 0xFE
    mem[0xFFEF] = 0xFF
    cpu.pc = sym['run_condacts']
    cpu.halted = False
    vueltas = 0
    pasos = 0
    while pasos < 400000 and cpu.pc != 0xFFFE:
        if cpu.pc == mc:
            vueltas += 1
        cpu.step()
        pasos += 1
    chk('PAUSE 3 espera tres barridos', vueltas == 3)

    print('--- pantalla tras describe ---')
    for l in pantalla:
        print('  |' + l)
    print()
    bien = sum(1 for _, ok in res if ok)
    for nombre, ok in res:
        print('  %s  %s' % ('OK  ' if ok else 'FALLA', nombre))
    print()
    print('%d/%d' % (bien, len(res)))
    return 0 if bien == len(res) else 1


if __name__ == '__main__':
    sys.exit(main())
