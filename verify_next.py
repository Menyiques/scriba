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
ANCHO = 42
FRAMES_TITULO = 60      # frames de portada antes de que el arnes pulse tecla


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
        self.pulsadas = []
        cpu.hook_in[0xFE] = self._leer

    def _pos(self, ch):
        cod = ord(ch) if isinstance(ch, str) else ch
        return divmod(self.tabla.index(cod), 5)

    def pulsa(self, ch):
        self.pulsadas = [self._pos(ch)]

    def pulsa_con_caps(self, ch):
        """CAPS SHIFT (fila 0, bit 0) mas otra tecla: asi se escribe el borrado."""
        self.pulsadas = [(0, 0), self._pos(ch)]

    def suelta(self):
        self.pulsadas = []

    def _leer(self, cpu, port):
        alto = (port >> 8) & 0xFF
        mask = 0xFF
        for fila, bit in self.pulsadas:
            if self.puertos[fila] == alto:
                mask &= ~(1 << bit) & 0xFF
        return mask


# ---------------------------------------------------------------------------
# decodificador de pantalla: pixeles -> texto
# ---------------------------------------------------------------------------
def tabla_glifos(mem, sym):
    """Indice inverso: los 6 bits de tinta de cada glifo -> su caracter."""
    t = {}
    base = sym['nxfont']
    acc = sx._ACC_CODE_PT if sx._PT_LANG else sx._ACC_CODE
    por_codigo = {code: ch for ch, code in acc.items()}
    for i in range(112):
        g = bytes(b & 0xFC for b in mem[base + i * 8:base + i * 8 + 8])
        ch = chr(32 + i) if i < 96 else por_codigo.get(144 + i - 96, '?')
        t.setdefault(g, ch)
    t[bytes(8)] = ' '
    return t


def leer_pantalla(mem, sym, ancho=ANCHO):
    """Decodifica la pantalla a texto. Cada caracter ocupa 6 pixeles, asi que
    hay que recortar la rodaja de 6 bits de los dos bytes que lo contienen."""
    glifos = tabla_glifos(mem, sym)
    lineas = []
    for fila in range(24):
        alto = 0x40 | (fila & 0x18)
        bajo = (fila & 7) << 5
        out = []
        for col in range(ancho):
            x = col * 6
            byte, n = x // 8, x % 8
            g = []
            for l in range(8):
                dirn = ((alto + l) << 8) | (bajo + byte)
                par = (mem[dirn] << 8) | (mem[dirn + 1] if byte < 31 else 0)
                g.append(((par << n) >> 8) & 0xFC)
            out.append(glifos.get(bytes(g), '?'))
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
    tec.suelta()
    ejecutar(cpu, mem, sym['kmread'])
    tec.pulsa_con_caps('0')
    ejecutar(cpu, mem, sym['kmread'])
    chk('KMREAD: CAPS+0 devuelve borrar (127)', (cpu.f & 1) == 1 and cpu.a == 127)
    tec.suelta()
    ejecutar(cpu, mem, sym['kmread'])
    tec.pulsa_con_caps('a')
    ejecutar(cpu, mem, sym['kmread'])
    chk('KMREAD: con CAPS pulsada las demas teclas siguen saliendo',
        (cpu.f & 1) == 1 and cpu.a == ord('a'))
    tec.suelta()

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


class EspiaNextReg:
    """Anota lo que se escribe por los puertos de NextReg ($243B selecciona el
    registro, $253B manda el dato) para poder comprobar la subida de paletas,
    que es un chorro de 256 bytes al mismo registro con autoincremento."""

    def __init__(self, cpu):
        self.reg = None
        self.flujo = []                 # lista de (registro, valor)
        cpu.hook_out[0x243B] = self._sel
        cpu.hook_out[0x253B] = self._dato

    def _sel(self, cpu, port, val):
        self.reg = val
        cpu.ports[port] = val

    def _dato(self, cpu, port, val):
        cpu.ports[port] = val
        if self.reg is not None:
            cpu.nextreg[self.reg] = val
            self.flujo.append((self.reg, val))

    def paleta(self):
        """La ultima tirada de 256 valores seguidos escritos en $41. No tiene por
        que estar al final del flujo: despues de subir la paleta se escriben otros
        registros (el de encendido de Layer 2, por ejemplo)."""
        fin = None
        for i in range(len(self.flujo) - 1, -1, -1):
            if self.flujo[i][0] == 0x41:
                fin = i
                break
        if fin is None:
            return b''
        out = []
        while fin >= 0 and self.flujo[fin][0] == 0x41 and len(out) < 256:
            out.append(self.flujo[fin][1])
            fin -= 1
        return bytes(reversed(out))


def verificar_nex(game, salida, datadir=None, musicdir=None):
    """Empaqueta el .nex, lo vuelve a leer del disco como lo hace NextZXOS,
    arranca desde el PC de la cabecera y comprueba que llega a pedir orden con
    la sala inicial en pantalla. Prueba del empaquetado, no solo del motor."""
    info = nn.export_nex(game, salida, datadir=datadir, musicdir=musicdir)
    mem, pc, sp, bancos = nn.carga_nex(salida)
    sym = info['simbolos']
    cpu = z80.Z80(mem)
    cpu.sp = sp
    espia = EspiaNextReg(cpu)
    Teclado(cpu, mem, sym)          # sin teclas pulsadas
    cpu.pc = pc
    cpu.halted = False

    # Arranque. Hay hasta dos esperas de tecla antes de que pida orden: la de la
    # pantalla de titulo (bucle propio, un frame por vuelta en nxframe) y la del
    # mensaje inicial (PAUSE 0, que va por KMW/KMREAD). Se captura el estado la
    # primera vez que se llega a cada una y luego se teclea para pasarla.
    tec0 = Teclado(cpu, mem, sym)
    ay = []
    cpu.hook_out[0xFFFD] = lambda c, pt, v: ay.append(('sel', v))
    cpu.hook_out[0xBFFD] = lambda c, pt, v: ay.append(('val', v))
    presentacion = []
    titulo = None
    l2_en_intro = l2_banco_intro = fila_intro = None
    vista_intro = False
    soltar = False
    n = 0
    frame = sym.get('nxframe')
    while n < 10000000 and cpu.pc != sym['read_line']:
        toca = False
        if frame is not None and cpu.pc == frame:
            if titulo is None:
                titulo = {'l2': cpu.nextreg.get(0x69),
                          'banco': cpu.nextreg.get(0x12),
                          'clip': cpu.nextreg.get(0x18),
                          'ay': 0, 'frames': 0}
            titulo['frames'] += 1
            # dejar correr unos segundos de portada antes de tocar tecla: si se
            # pulsa al primer frame no se comprueba que la musica avance
            toca = titulo['frames'] > FRAMES_TITULO
        elif cpu.pc == sym['kmread']:
            if not vista_intro:
                vista_intro = True
                if titulo is not None:
                    titulo['ay'] = len(ay)
                    titulo['psgpos'] = (mem[sym['psgpos']] |
                                        (mem[sym['psgpos'] + 1] << 8)) - sym['nxpsg'] \
                        if 'psgpos' in sym else None
                presentacion = [l for l in leer_pantalla(mem, sym) if l.strip()]
                l2_en_intro = cpu.nextreg.get(0x69)
                l2_banco_intro = cpu.nextreg.get(0x12)
                fila_intro = mem[sym['nxwt']]
            toca = True
        if toca:
            if soltar:
                tec0.suelta()
                soltar = False
            else:
                tec0.pulsa(' ')
                soltar = True
        cpu.step()
        n += 1
    tec0.suelta()
    if titulo is not None:
        titulo['clip_final'] = cpu.nextreg.get(0x18)
    llego = cpu.pc == sym['read_line']
    pant = [l for l in leer_pantalla(mem, sym) if l.strip()]

    # ---- jugar: escribir una orden y ver la respuesta ----
    jugadas = []
    if llego:
        tec2 = Teclado(cpu, mem, sym)
        for orden in ('n', 'coger linterna', 'i', 'version'):
            # teclea() vuelve cuando el juego ya esta pidiendo la orden siguiente,
            # o sea con el turno anterior resuelto y pintado.
            if not teclea(cpu, sym, tec2, orden + chr(13)):
                break
            jugadas.append((orden, [l for l in leer_pantalla(mem, sym) if l.strip()]))

    # ---- Layer 2: comprobar el banco activo y la paleta de la sala actual ----
    img = None
    if info['imagenes'] and llego:
        slotp = mem[sym['locslotp']] | (mem[sym['locslotp'] + 1] << 8)
        slot = mem[slotp + mem[sym['curloc']]] if slotp else 255
        esperado = None if slot == 255 else nn.BANK_IMG + slot
        # la presentacion sale en la sala INICIAL, que a estas alturas ya no es
        # la actual: hay que mirar su slot aparte
        slot0 = mem[slotp + info['inicio']] if slotp else 255
        esp0 = None if slot0 == 255 else nn.BANK_IMG + slot0
        pal_ok = True
        if slot != 255:
            lid = info['imagenes'][slot]
            pal_ok = espia.paleta() == nn._paleta256(
                os.path.join(datadir, lid + '.nxp'))
        img = {
            'n': len(info['imagenes']),
            'slot': slot,
            'banco': cpu.nextreg.get(0x12),
            'esperado': esperado,
            'modo': cpu.nextreg.get(0x70),
            'activa': cpu.nextreg.get(0x69),
            'clip': cpu.nextreg.get(0x18),
            'paleta_ok': pal_ok,
            'bancos_img': [b for b in bancos if b >= nn.BANK_IMG],
            'l2_intro': l2_en_intro,
            'banco_intro': l2_banco_intro,
            'fila_intro': fila_intro,
            'esp0': esp0,
        }
    return info, llego, n, pant, bancos, jugadas, img, presentacion, titulo


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
    info, llego, pasos, pant, bancos, jugadas, img, presentacion, titulo = verificar_nex(
        game, salida, datadir=nn.datadir_por_defecto(path),
        musicdir=nn.musicdir_por_defecto(path))
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
    res.append(('.nex responde a ordenes escritas', len(jugadas) == 4))

    if titulo:
        print()
        print('    --- pantalla de titulo')
        print('        Layer 2 $69=%s  banco $12=%s  clip $18=%s -> tras la tecla %s'
              % (titulo['l2'], titulo['banco'], titulo['clip'], titulo['clip_final']))
        print('        %d frames mostrados, %d escrituras al AY'
              % (titulo['frames'], titulo['ay']))
        res.append(('portada a pantalla completa en Layer 2',
                    titulo['l2'] == 128 and titulo['clip'] == 191))
        res.append(('...en el banco de la portada',
                    titulo['banco'] == nn.BANK_IMG + len(info['imagenes'])))
        res.append(('...y el clip vuelve al tercio superior al salir',
                    titulo['clip_final'] == 63))
        if info['psg'] and titulo.get('psgpos') is not None:
            # Comprobacion exacta: se simula el mismo recorrido del stream en
            # Python y se compara donde ha dejado el puntero el reproductor Z80.
            # Asi se detecta que el player se desincronice, no solo que suene.
            psg, _ = nn._musica(nn.musicdir_por_defecto(path))
            pos = 0
            for _ in range(titulo['frames'] - 1):
                pos += 1
                while pos < len(psg) and psg[pos] not in (0xFF, 0xFD):
                    pos += 2
                if pos >= len(psg) or psg[pos] == 0xFD:
                    pos = 0
                    break
            print('        puntero del stream: %d (esperado %d)'
                  % (titulo['psgpos'], pos))
            res.append(('el reproductor PSG recorre el stream sin desincronizarse',
                        abs(titulo['psgpos'] - pos) <= 2))
            res.append(('suenan registros del AY en la portada', titulo['ay'] > 10))

    ini = (game.get('metadata') or {}).get('start_message') or ''
    if ini.strip():
        print()
        print('    --- presentacion (metadata.start_message)')
        for l in presentacion[:6]:
            print('    |' + l)
        if len(presentacion) > 6:
            print('    |... (%d lineas)' % len(presentacion))
        clave = ini.split(chr(10))[0].strip()[:20]
        res.append(('presentacion mostrada y esperando tecla',
                    bool(presentacion) and any(clave in l for l in presentacion)))

    # ---- mensajes iniciales de objeto ----
    objs = (game.get('objects') or {}).values()
    fijos = [o for o in objs
             if 'fixed' in [str(a).lower() for a in (o.get('attributes') or [])]
             and (o.get('initial_message') or '').strip()]
    if fijos:
        texto = ' '.join(' '.join(p) for _, p in jugadas)
        texto = ' '.join(texto.split())
        nombres = [o for o in fijos
                   if ' '.join(str(o.get('name', '')).split())[:18] in texto]
        vistos = [o for o in fijos
                  if ' '.join(str(o['initial_message']).split())[:28] in texto]
        res.append(('los fijos con mensaje inicial salen por su mensaje', bool(vistos)))
        res.append(('...y NO por su nombre de objeto', not nombres))
        if nombres:
            print()
            print('    se listan por nombre y no deberian: %s'
                  % ', '.join(str(o.get('name')) for o in nombres))

    ver = dict(jugadas).get('version', [])
    if ver:
        import scriba_info
        res.append(('VERSION responde con la ficha',
                    any('Scriba ' + scriba_info.SCRIBA_VERSION in l for l in ver)))
    if img:
        print()
        print('    --- Layer 2: %d imagenes en los bancos %s'
              % (img['n'], img['bancos_img']))
        print('        modo $70=%s  activa $69=%s  clip $18=%s'
              % (img['modo'], img['activa'], img['clip']))
        print('        sala actual: slot %s -> banco $12=%s (esperado %s), paleta %s'
              % (img['slot'], img['banco'], img['esperado'],
                 'OK' if img['paleta_ok'] else 'NO COINCIDE'))
        res.append(('Layer 2 arrancado (8bpp, visible, clip 0-63)',
                    img['modo'] == 0 and img['activa'] == 128 and img['clip'] == 63))
        res.append(('banco de imagen de la sala correcto', img['banco'] == img['esperado']))
        print('        en la presentacion: Layer 2 $69=%s, banco $12=%s, texto desde la fila %s'
              % (img['l2_intro'], img['banco_intro'], img['fila_intro']))
        res.append(('la presentacion ya lleva la imagen de la sala inicial',
                    img['l2_intro'] == 128 and img['banco_intro'] == img['esp0']))
        res.append(('...y su texto empieza en la fila 8', img['fila_intro'] == nn.FILA_TEXTO))
        res.append(('paleta de la sala subida entera', img['paleta_ok']))
    ok = sum(1 for _, b in res if b)
    print()
    print('%d/%d comprobaciones correctas' % (ok, len(res)))
    sys.exit(0 if ok == len(res) else 1)


if __name__ == '__main__':
    main()
