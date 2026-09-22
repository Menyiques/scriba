# -*- coding: utf-8 -*-
"""
sample_ay.py - Reproductor Z80 de muestras digitalizadas por el AY.

El AY hace de DAC de 4 bits si se apaga el mezclador y se escribe la amplitud
en el registro de volumen a ritmo constante (ver wav2ay.py). Ese ritmo NO lo
marca un temporizador: lo marca el bucle, contando T-estados. De ahi que el
paso de reproduccion se calcule aqui y el conversor remuestree a ese mismo
ritmo: si no coinciden, la muestra suena mas aguda o mas grave.

Cuentas del bucle, a 3.5 MHz (Spectrum 48K/128K):

    de la escritura del nibble ALTO a la del BAJO :  32 T + retardo A
    de la del BAJO a la del ALTO siguiente        :  68 T + retardo B

Los dos tramos tienen que durar lo mismo o la onda sale con cojera audible, asi
que el retardo A lleva 36 T mas que el B. El retardo se hace con DJNZ, que
obliga a recargar BC con el puerto despues (B es la mitad alta de BC).
"""

RELOJ = 3500000.0          # Spectrum 48K/128K
PUERTO_DATO = 0xBFFD       # dato del AY
PUERTO_REG = 0xFFFD        # seleccion de registro

# Coste fijo de cada tramo del bucle, sin retardos (ver la cabecera).
_FIJO_A = 32
_FIJO_B = 68
_DESNIVEL = _FIJO_B - _FIJO_A      # 36 T que hay que devolverle al tramo A


def _djnz(n):
    """T-estados de 'ld b,n / djnz' mas el 'ld bc,puerto' que hay que poner
    detras porque DJNZ se come B."""
    return 7 + (13 * n - 5) + 10


def plan(hz, reloj=RELOJ):
    """Devuelve (nB, nA, hz_real): las cuentas de DJNZ de cada retardo y el
    ritmo que de verdad va a salir. El conversor tiene que remuestrear a
    hz_real, no al hz pedido."""
    periodo = reloj / float(hz)
    objetivo_b = periodo - _FIJO_B
    nb = max(1, int(round((objetivo_b - 12) / 13.0)))
    na = max(1, int(round((objetivo_b + _DESNIVEL - 12) / 13.0)))
    # el ritmo real es la MEDIA de los dos tramos: cada uno redondea su DJNZ
    # por su cuenta y no quedan exactamente iguales
    tramo_b = _FIJO_B + _djnz(nb)
    tramo_a = _FIJO_A + _djnz(na)
    real = reloj / ((tramo_a + tramo_b) / 2.0)
    return nb, na, real


def asm(hz, reloj=RELOJ, etiqueta='SMPLAY', con_di=True):
    """El reproductor, ya con los retardos calculados para 'hz'.

    Entrada:  HL = primer byte de la muestra, DE = cuantos bytes.
    Deja el mezclador como estaba al salir y el volumen a cero.
    Bloquea: mientras suena no corre nada mas, ni interrupciones."""
    nb, na, real = plan(hz, reloj)
    return ('''
; ---------------------------------------------------------------------------
;  Reproductor de muestras por el AY  (%.0f Hz reales, 4 bits)
;  HL = muestra empaquetada, DE = bytes. Bloqueante y con las interrupciones
;  quitadas: cualquier cosa que robe ciclos se oye como un chasquido.
; ---------------------------------------------------------------------------
%s:
%s        push  af
        ld    bc,&FFFD      ; mezclador: ni tono ni ruido en ningun canal,
        ld    a,7           ; que si no la muestra sale sobre un zumbido
        out   (c),a
        ld    bc,&BFFD
        ld    a,&3F
        out   (c),a
        ld    bc,&FFFD      ; y a partir de aqui el registro seleccionado es
        ld    a,8           ; el volumen del canal A: solo se escribe el dato
        out   (c),a
        ld    bc,&BFFD
sm_l:   ld    a,(hl)
        rrca
        rrca
        rrca
        rrca
        and   15
        out   (c),a         ; muestra del nibble alto
        ld    b,%d
sm_da:  djnz  sm_da
        ld    bc,&BFFD
        ld    a,(hl)
        inc   hl
        and   15
        out   (c),a         ; muestra del nibble bajo
        ld    b,%d
sm_db:  djnz  sm_db
        ld    bc,&BFFD
        dec   de
        ld    a,d
        or    e
        jr    nz,sm_l
        xor   a             ; silencio al acabar
        out   (c),a
        pop   af
%s        ret
''' % (real, etiqueta, '        di\n' if con_di else '',
       na, nb, '        ei\n' if con_di else ''))


def simula(code, sym, datos, etiqueta='smplay', tope=40000000):
    """Corre el reproductor en el simulador y devuelve los niveles que ha
    escrito de verdad en el AY, mas los intervalos entre escrituras. Sirve para
    comprobar dos cosas que a ojo no se ven: que salen TODAS las muestras y en
    orden, y que el ritmo es parejo."""
    import z80
    mem = bytearray(65536)
    org = sym['__org__']
    mem[org:org + len(code)] = code
    mem[0x8000:0x8000 + len(datos)] = datos
    cpu = z80.Z80(mem)
    niveles, reloj = [], []
    paso = [0]
    regsel = [None]

    def sel(c, p, v):
        regsel[0] = v

    def dato(c, p, v):
        if regsel[0] == 8:
            niveles.append(v & 15)
            reloj.append(paso[0])
    cpu.hook_out[PUERTO_REG] = sel
    cpu.hook_out[PUERTO_DATO] = dato
    mem[0xFFFE] = 0xC9
    cpu.sp = 0xFFEE
    mem[0xFFEE] = 0xFE
    mem[0xFFEF] = 0xFF
    cpu.pc = sym[etiqueta]
    cpu.hl = 0x8000
    cpu.de = len(datos)
    n = 0
    while n < tope and cpu.pc != 0xFFFE:
        cpu.step()
        paso[0] += 1
        n += 1
    huecos = [b - a for a, b in zip(reloj, reloj[1:])]
    return niveles, huecos, n


def muestras(game, base):
    """Empaqueta las muestras detras del payload de imagenes. Devuelve
    (bytes, {n: (off, len)}). Ninguna cruza frontera de banco: la ventana de
    &C000 solo ve un banco, y el reproductor lee de corrido."""
    smp = game.get('samples') or []
    extra = bytearray()
    tabla = {}
    off = base
    for i, m in enumerate(smp, 1):
        d = m.get('data') or ''
        datos = bytes.fromhex(d) if isinstance(d, str) else bytes(d)
        if not datos:
            continue
        if off % 2:                                  # el offset viaja /2
            extra += b'\x00'
            off += 1
        if off // 16384 != (off + len(datos) - 1) // 16384:
            hueco = 16384 - off % 16384
            extra += b'\x00' * hueco
            off += hueco
        if len(datos) > 16384:
            raise ValueError('la muestra %r ocupa %d bytes y en un banco caben '
                             '16384' % (m.get('name'), len(datos)))
        tabla[i] = (off, len(datos))
        extra += datos
        off += len(datos)
    return bytes(extra), tabla
