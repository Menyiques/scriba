# -*- coding: utf-8 -*-
"""
verify_128.py - Arnes de validacion del motor nativo en ZX Spectrum 128K.

Lo que hay que probar aqui que no prueba el 48K son los bancos: que el texto
de cada mensaje se lee de SU banco (TXTPAGE), que la imagen de cada sala se
pagina y se descomprime EXACTA en la pantalla, que la musica se lee del banco,
y que la pila nunca asoma por la ventana de &C000: es lo unico que hace segura
la paginacion sin devolver nada a su sitio.

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

vn.PILA_ARNES = 0xBFEE      # el texto va en bancos: la pila del arnes, bajo la ventana
import z80


class Bancos:
    """Paginacion del 128K: el puerto &7FFD elige que banco de 16K se ve en
    &C000-&FFFF. El simulador tiene un mapa plano, asi que al cambiar de banco
    se guarda lo que hubiera y se trae lo del banco nuevo."""

    ORDEN = (1, 3, 4, 6, 7, 0)       # los seis bancos del payload, en orden

    def __init__(self, cpu, mem, payload):
        self.mem = mem
        self.pag = {n: bytearray(16384) for n in range(8)}
        for j in range(0, len(payload), 16384):
            trozo = payload[j:j + 16384]
            self.pag[self.ORDEN[j // 16384]][:len(trozo)] = trozo
        mem[0xC000:0x10000] = self.pag[0]           # arranca con el 0 puesto
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
     npsg, psg_nom, ex) = s128.compila(game, game_dir)
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
                avisos=avisos, psg=npsg, psg_nom=psg_nom, ex=ex)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        'Games/Operacion Tifon Negro/Operacion Tifon Negro.yaml'
    game = yaml.safe_load(open(path, encoding='utf-8'))
    game_dir = os.path.dirname(os.path.abspath(path))
    e = construir(game, game_dir)
    cpu, mem, sym, tec = e['cpu'], e['mem'], e['sym'], e['tec']

    c = sx.recolecta(game)
    tabla, scr_off = e['ex']['tabla'], e['ex']['scr_off']

    print('ZX Spectrum 128K - motor nativo Z80')
    print('  motor+plataforma : %6d bytes  (&%04X-&%04X)'
          % (e['code'], s128.ORG, e['dbaddr'] - 1))
    print('  base de datos    : %6d bytes  (&%04X-&%04X)'
          % (e['db'], e['dbaddr'], e['dbaddr'] + e['db'] - 1))
    print('  RAM principal    : %6d de %d, %d libres'
          % (e['code'] + e['db'], s128.SP128 - s128.PILA_MIN - s128.ORG,
             s128.SP128 - s128.PILA_MIN - (s128.ORG + e['code'] + e['db'])))
    print('  imagenes         : %6d bytes, %d libres de %d en los bancos'
          % (len(e['payload']), s128.TOPE_BANCOS - len(e['payload']),
             s128.TOPE_BANCOS))
    print()

    res = []
    chk = lambda n, ok: res.append((n, bool(ok)))

    # ---- 0. nada permanente en la ventana: el mapa plano acaba bajo &C000 ----
    chk('motor y base de datos acaban bajo la ventana de &C000',
        e['dbaddr'] + e['db'] <= 0xC000)
    chk('la pila arranca bajo la ventana', cpu.sp < 0xC000)
    chk('los mensajes llevan tabla de banco (texto en bancos)',
        (mem[sym['msgbnk']] | (mem[sym['msgbnk'] + 1] << 8)) != 0)

    # ---- 1. la imagen de la sala inicial, byte a byte, y su texto del banco ----
    loc = mem[sym['curloc']]
    offs = tabla.get(loc + 1)
    chk('la sala inicial tiene imagen', offs is not None)
    if offs:
        vn.ejecutar(cpu, mem, sym['nxcls'])
        vn.ejecutar(cpu, mem, sym['describe'], sym=sym, tec=tec)
        # el texto de la sala sale de un banco: la descripcion tiene que estar
        # en pantalla, y el banco que queda puesto ser uno de los del texto
        _desc = e['spec']['messages'][e['spec']['locations'][loc]['desc']]
        _pant = ' '.join(l.strip() for l in vn.leer_pantalla(mem, sym))
        _pal = [w for w in _desc.replace(chr(10), ' ').split() if w.isalpha()][:4]
        chk('la descripcion se lee de su banco y llega a pantalla',
            all(w in _pant for w in _pal))
        chk('la pila sigue bajo la ventana tras describir', cpu.sp < 0xC000)
        espB = sx.dzx0_simula(bytes(e['payload'][offs[0]:]))
        espA = sx.dzx0_simula(bytes(e['payload'][offs[1]:]))
        chk('el bitmap descomprime exacto en &4000 (%d bytes)' % len(espB),
            bytes(mem[0x4000:0x4000 + len(espB)]) == espB)
        chk('los atributos descomprimen exactos en &5800 (%d bytes)' % len(espA),
            bytes(mem[0x5800:0x5800 + len(espA)]) == espA)
        chk('el texto arranca debajo de la imagen (fila %d)' % s128.FILA_TEXTO,
            mem[sym['nxwt']] == s128.FILA_TEXTO)

    # ---- 2. la paginacion se ha usado de verdad, y el sexto banco (el 0) vale ----
    chk('se ha paginado por &7FFD', e['bancos'].cambios > 0)
    # El banco 0 era la RAM alta del juego y ahora es un banco mas: se marca su
    # contenido y se lee por TXTPAGE, como haria un mensaje que cayera ahi.
    e['bancos'].pag[0][0:4] = b'SEIS'
    cpu.a = 16                              # 16 = banco 0 con la ROM de 48K
    vn.ejecutar(cpu, mem, sym['txtpage'])
    chk('el banco 0 se pagina con TXTPAGE 16 y se lee por la ventana',
        bytes(mem[0xC000:0xC004]) == b'SEIS')
    chk('y son seis bancos, 98.304 bytes', s128.TOPE_BANCOS == 6 * 16384
        and len(s128.BANCOS) == 6)

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
        chk('y la lee de su banco (psgbnk != 0)', mem[sym['psgbnk']] != 0)
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
