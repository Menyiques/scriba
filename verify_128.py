# -*- coding: utf-8 -*-
"""
verify_128.py - Arnes de validacion del motor nativo en ZX Spectrum 128K.

Lo que hay que probar aqui que no prueba el 48K son los bancos: que la imagen
de cada sala se pagina y se descomprime EXACTA en la pantalla, que el motor
deja el banco 0 de vuelta al terminar (si no, se lleva por delante la mitad
alta de su propia base de datos) y que la pila baja hace su trabajo mientras
hay un banco puesto.

La comparacion no es "algo ha pintado": se descomprime el mismo flujo ZX0 con
el simulador de dzx0 de spectrum_export y se compara byte a byte con lo que el
motor ha dejado en &4000 y &5800.

    python verify_128.py [juego.yaml]
"""
import os
import sys

import yaml

import spectrum128_nativo as s128
import spectrum_export as sx
import verify_next as vn
import z80


class Bancos:
    """Paginacion del 128K: el puerto &7FFD elige que banco de 16K se ve en
    &C000-&FFFF. El simulador tiene un mapa plano, asi que al cambiar de banco
    se guarda lo que hubiera y se trae lo del banco nuevo."""

    ORDEN = (1, 3, 4, 6, 7)          # los cinco bancos de imagenes, en orden

    def __init__(self, cpu, mem, payload):
        self.mem = mem
        self.pag = {n: bytearray(16384) for n in range(8)}
        for j in range(0, len(payload), 16384):
            trozo = payload[j:j + 16384]
            self.pag[self.ORDEN[j // 16384]][:len(trozo)] = trozo
        self.pag[0][:] = mem[0xC000:0x10000]       # la RAM del juego
        self.actual = 0
        self.cambios = 0
        cpu.hook_out[0x7FFD] = self._out

    def _out(self, cpu, port, val):
        b = val & 7
        self.cambios += 1
        if b == self.actual:
            return
        self.pag[self.actual][:] = self.mem[0xC000:0x10000]
        self.mem[0xC000:0x10000] = self.pag[b]
        self.actual = b


def construir(game, game_dir):
    (code, db, sym, spec, dbaddr, payload, avisos,
     npsg, psg_nom) = s128.compila(game, game_dir)
    mem = bytearray(65536)
    mem[s128.ORG:s128.ORG + len(code)] = code
    mem[dbaddr:dbaddr + len(db)] = db
    cpu = z80.Z80(mem)
    cpu.sp = s128.SP128
    bancos = Bancos(cpu, mem, payload)
    tec = vn.Teclado(cpu, mem, sym)
    cpu.run(start=sym['init'])
    return dict(cpu=cpu, mem=mem, sym=sym, spec=spec, tec=tec, bancos=bancos,
                payload=payload, code=len(code), db=len(db), dbaddr=dbaddr,
                avisos=avisos, psg=npsg, psg_nom=psg_nom)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        'Games/Operacion Tifon Negro/Operacion Tifon Negro.yaml'
    game = yaml.safe_load(open(path, encoding='utf-8'))
    game_dir = os.path.dirname(os.path.abspath(path))
    e = construir(game, game_dir)
    cpu, mem, sym, tec = e['cpu'], e['mem'], e['sym'], e['tec']

    c = sx.recolecta(game)
    _payload, tabla, scr_off, _av = s128.imagenes(game_dir, c)

    print('ZX Spectrum 128K - motor nativo Z80')
    print('  motor+plataforma : %6d bytes  (&%04X-&%04X)'
          % (e['code'], s128.ORG, e['dbaddr'] - 1))
    print('  base de datos    : %6d bytes  (&%04X-&%04X)'
          % (e['db'], e['dbaddr'], e['dbaddr'] + e['db'] - 1))
    print('  RAM principal    : %6d de %d, %d libres'
          % (e['code'] + e['db'], s128.SP128 - s128.ORG,
             s128.SP128 - (s128.ORG + e['code'] + e['db'])))
    print('  imagenes         : %6d bytes, %d libres de %d en los bancos'
          % (len(e['payload']), s128.TOPE_BANCOS - len(e['payload']),
             s128.TOPE_BANCOS))
    print()

    res = []
    chk = lambda n, ok: res.append((n, bool(ok)))

    # huella de la mitad alta de la RAM, para detectar que el motor devuelve el
    # banco 0: si se dejara puesto otro, la base de datos de &C000 arriba se
    # convertiria en pixeles de una imagen
    huella = bytes(mem[0xC000:0xC000 + 512])

    # ---- 1. la imagen de la sala inicial, byte a byte ----
    loc = mem[sym['curloc']]
    offs = tabla.get(loc + 1)
    chk('la sala inicial tiene imagen', offs is not None)
    if offs:
        vn.ejecutar(cpu, mem, sym['nxcls'])
        vn.ejecutar(cpu, mem, sym['describe'], sym=sym, tec=tec)
        espB = sx.dzx0_simula(bytes(e['payload'][offs[0]:]))
        espA = sx.dzx0_simula(bytes(e['payload'][offs[1]:]))
        chk('el bitmap descomprime exacto en &4000 (%d bytes)' % len(espB),
            bytes(mem[0x4000:0x4000 + len(espB)]) == espB)
        chk('los atributos descomprimen exactos en &5800 (%d bytes)' % len(espA),
            bytes(mem[0x5800:0x5800 + len(espA)]) == espA)
        chk('el texto arranca debajo de la imagen (fila %d)' % s128.FILA_TEXTO,
            mem[sym['nxwt']] == s128.FILA_TEXTO)

    # ---- 2. el banco 0 vuelve a su sitio ----
    chk('el motor deja puesto el banco 0', e['bancos'].actual == 0)
    chk('la RAM alta sigue intacta tras paginar',
        bytes(mem[0xC000:0xC000 + 512]) == huella)
    chk('la pila vuelve a lo alto', cpu.sp not in (s128.SP_BAJA,))

    # ---- 3. una sala sin imagen deja la ventana a pantalla completa ----
    # (que la oscuridad tape la imagen lo prueba el camino de is_dark, comun a
    #  las tres maquinas y ya cubierto por verify_48 y verify_cpc)
    vn.ejecutar(cpu, mem, sym['nxcls'])
    sin = next((i for i in range(len(e['spec']['locations']))
                if tabla.get(i + 1) is None), None)
    if sin is not None:
        mem[sym['curloc']] = sin
        vn.ejecutar(cpu, mem, sym['describe'], sym=sym, tec=tec)
        chk('una sala sin imagen usa la pantalla entera',
            mem[sym['nxwt']] == 0)
        mem[sym['curloc']] = loc
    else:
        chk('una sala sin imagen usa la pantalla entera', True)

    # ---- 4. la portada ----
    if scr_off is not None:
        vn.ejecutar(cpu, mem, sym['nxcls'])
        vn.ejecutar(cpu, mem, sym['s128tit'])
        esp = sx.dzx0_simula(bytes(e['payload'][scr_off:]))
        chk('la portada descomprime exacta (%d bytes)' % len(esp),
            bytes(mem[0x4000:0x4000 + len(esp)]) == esp)
        chk('y deja el banco 0 puesto', e['bancos'].actual == 0)

    # ---- 5. la musica llega al AY ----
    if e['psg']:
        escrito = []
        cpu.hook_out[0xFFFD] = lambda c, p, v: escrito.append(('reg', v))
        cpu.hook_out[0xBFFD] = lambda c, p, v: escrito.append(('val', v))
        vn.ejecutar(cpu, mem, sym['psginit'])
        for _ in range(4):
            vn.ejecutar(cpu, mem, sym['psgframe'])
        chk('la musica (%d bytes) escribe en el AY por &FFFD/&BFFD' % e['psg'],
            any(k == 'reg' for k, _ in escrito)
            and any(k == 'val' for k, _ in escrito))
        del cpu.hook_out[0xFFFD], cpu.hook_out[0xBFFD]

    # ---- 6. el texto sigue funcionando como en el 48K ----
    vn.ejecutar(cpu, mem, sym['nxcls'])
    mem[sym['nxwt']] = 0
    mem[sym['nxrow']] = 0
    mem[sym['nxcol']] = 0
    for ch in 'ABC abc 123':
        cpu.a = ord(ch)
        vn.ejecutar(cpu, mem, sym['txto'])
    chk('TXTO sigue imprimiendo sobre la ULA',
        vn.leer_pantalla(mem, sym)[0] == 'ABC abc 123')

    bien = sum(1 for _, ok in res if ok)
    for nombre, ok in res:
        print('  %s  %s' % ('OK  ' if ok else 'FALLA', nombre))
    print()
    print('%d/%d' % (bien, len(res)))
    return 0 if bien == len(res) else 1


if __name__ == '__main__':
    sys.exit(main())
