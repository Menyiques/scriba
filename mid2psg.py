#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mid2psg.py — Convierte un MIDI a un volcado de registros del AY (formato PSG
compacto propio), en Python puro y SIN dependencias externas.

Pipeline:
  1. Parser MIDI minimo (formato 0/1: note on/off, set tempo, running status).
  2. Linea de tiempo de notas en segundos (respeta cambios de tempo).
  3. Muestreo a 50 Hz (frames) y arreglo a 3 voces con CONTINUIDAD de canal
     (una nota se queda en su canal del AY mientras suena, para no chasquear).
  4. Registros del AY por frame: periodo de tono (segun el RELOJ del AY de la
     maquina), volumen (de la velocity) y mezclador. Sin ruido ni envolvente.
  5. Codificacion PSG compacta: por frame solo los registros que cambian.

Reloj del AY por maquina (Hz):  CPC 1_000_000 ; Spectrum128/Next 1_773_400.

Formato PSG de salida (lo lee el reproductor Z80 que lleva Scriba):
  · pareja (R, V): escribe V en el registro R (0..13)
  · 0xFF  fin del frame (el reproductor para hasta el siguiente frame)
  · 0xFE  fin de la musica -> el reproductor vuelve al principio (bucle)
"""

CLOCK_CPC = 1_000_000
CLOCK_ZX = 1_773_400


# ─── Parser MIDI minimo ─────────────────────────────────────────────────────
def _vlq(data, i):
    v = 0
    while True:
        b = data[i]; i += 1
        v = (v << 7) | (b & 0x7F)
        if not (b & 0x80):
            return v, i


def parse_midi(data):
    """Devuelve (tpq, eventos) con eventos = (abs_tick, kind, a, b).
    kind: 'on'(nota,vel) 'off'(nota,_) 'tempo'(us_por_negra,_)."""
    if data[:4] != b'MThd':
        raise ValueError('no es un MIDI (falta MThd)')
    ntr = (data[10] << 8) | data[11]
    tpq = (data[12] << 8) | data[13]
    if tpq & 0x8000:
        raise ValueError('division SMPTE no soportada')
    eventos = []
    pos = 14
    for _ in range(ntr):
        if data[pos:pos+4] != b'MTrk':
            break
        length = int.from_bytes(data[pos+4:pos+8], 'big')
        pos += 8
        end = pos + length
        tick = 0
        status = 0
        while pos < end:
            dt, pos = _vlq(data, pos)
            tick += dt
            b0 = data[pos]
            if b0 & 0x80:
                status = b0; pos += 1
            # else: running status (status se mantiene)
            ev = status & 0xF0
            if ev in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                d1 = data[pos]; d2 = data[pos+1]; pos += 2
                if ev == 0x90 and d2 > 0:
                    eventos.append((tick, 'on', d1, d2))
                elif ev == 0x80 or (ev == 0x90 and d2 == 0):
                    eventos.append((tick, 'off', d1, 0))
            elif ev in (0xC0, 0xD0):
                pos += 1
            elif status == 0xFF:
                mtype = data[pos]; pos += 1
                mlen, pos = _vlq(data, pos)
                if mtype == 0x51 and mlen == 3:
                    us = (data[pos] << 16) | (data[pos+1] << 8) | data[pos+2]
                    eventos.append((tick, 'tempo', us, 0))
                pos += mlen
            elif status in (0xF0, 0xF7):
                mlen, pos = _vlq(data, pos)
                pos += mlen
            else:
                pos += 1
        pos = end
    eventos.sort(key=lambda e: e[0])
    return tpq, eventos


# ─── MIDI -> frames (notas activas por frame, a 50 Hz) ──────────────────────
def midi_to_active(data, fps=50):
    tpq, eventos = parse_midi(data)
    # pasar a segundos respetando los cambios de tempo
    tempo = 500000  # us/negra por defecto (120 BPM)
    last_tick = 0; secs = 0.0
    notas = []          # (t_on, t_off, nota, vel)
    sonando = {}        # nota -> (t_on, vel)
    for tick, kind, a, b in eventos:
        secs += (tick - last_tick) * tempo / tpq / 1e6
        last_tick = tick
        if kind == 'tempo':
            tempo = a
        elif kind == 'on':
            sonando[a] = (secs, b)
        elif kind == 'off':
            if a in sonando:
                t_on, vel = sonando.pop(a)
                notas.append((t_on, secs, a, vel))
    for nota, (t_on, vel) in sonando.items():
        notas.append((t_on, secs + 0.1, nota, vel))
    total = int(secs * fps) + 1
    activos = []        # por frame: lista de (nota, vel)
    for f in range(total):
        t = (f + 0.5) / fps
        activos.append([(n, v) for (a0, a1, n, v) in notas if a0 <= t < a1])
    return activos


# ─── Arreglo a 3 voces con continuidad de canal ─────────────────────────────
def arrange(activos, voces=3):
    asignados = []      # por frame: [nota|None, nota|None, nota|None]
    chan = [None, None, None]
    for act in activos:
        notas = sorted({n for (n, v) in act}, reverse=True)  # de aguda a grave
        velm = {n: v for (n, v) in act}
        # libera canales cuya nota ya no suena
        for i in range(voces):
            if chan[i] is not None and chan[i] not in notas:
                chan[i] = None
        # asigna notas nuevas (prioriza las mas agudas) a canales libres
        en_canal = set(c for c in chan if c is not None)
        for n in notas:
            if n in en_canal:
                continue
            for i in range(voces):
                if chan[i] is None:
                    chan[i] = n; en_canal.add(n); break
        asignados.append([(c, velm.get(c, 0)) if c is not None else None
                          for c in chan])
    return asignados


# ─── Notas -> registros del AY ──────────────────────────────────────────────
def _period(nota, clock):
    freq = 440.0 * 2 ** ((nota - 69) / 12.0)
    p = round(clock / (16 * freq))
    return max(1, min(4095, p))


def _vol(vel):
    return max(1, min(15, round(vel / 127 * 15)))


def frames_ay(asignados, clock):
    """Cada frame -> lista de 14 valores (R0..R13); None = no escribir."""
    out = []
    for voces in asignados:
        regs = [None] * 14
        mixer = 0x3F                    # todo apagado; ruido siempre off
        for i, nv in enumerate(voces):  # i = canal A/B/C
            if nv is None:
                regs[8 + i] = 0          # volumen 0 (silencio)
            else:
                nota, vel = nv
                p = _period(nota, clock)
                regs[2 * i] = p & 0xFF
                regs[2 * i + 1] = (p >> 8) & 0x0F
                regs[8 + i] = _vol(vel)
                mixer &= ~(1 << i)       # habilita tono del canal i
        regs[7] = mixer
        out.append(regs)
    return out


# ─── Codificacion PSG compacta (solo deltas) ────────────────────────────────
def encode_psg(frames):
    prev = [None] * 14
    out = bytearray()
    for regs in frames:
        for r in range(14):
            v = regs[r]
            if v is None:
                continue
            if prev[r] != v:
                out.append(r); out.append(v); prev[r] = v
        out.append(0xFF)
    out.append(0xFE)
    return bytes(out)


def midi_to_psg(path_or_bytes, clock=CLOCK_CPC, fps=50, voces=3):
    data = (path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray))
            else open(path_or_bytes, 'rb').read())
    activos = midi_to_active(data, fps)
    asign = arrange(activos, voces)
    frames = frames_ay(asign, clock)
    return encode_psg(frames), len(frames)


# ─── Decodificador (para verificacion) ──────────────────────────────────────
def decode_psg(psg):
    """Devuelve la lista de estados de 14 registros por frame (expandido)."""
    frames = []
    regs = [0] * 14
    i = 0
    while i < len(psg):
        b = psg[i]; i += 1
        if b == 0xFF:
            frames.append(list(regs))
        elif b == 0xFE:
            break
        else:
            regs[b] = psg[i]; i += 1
    return frames


# ─── Reproductor PSG en Z80 para CPC (lo lleva Scriba, sin ensamblador) ─────
# ORG &8B00. Puntos de entrada: &8B00 Init, &8B03 Play (1 frame), &8B06 Stop.
# Escribe el AY con CALL &BD34 (firmware MC SOUND REGISTER: A=registro, C=valor),
# que ademas preserva la linea de teclado (convive con INKEY). Los datos PSG van
# justo tras el codigo, en &8B47. Verificado con un simulador Z80 en Python.
PLAYER_CPC = bytes([
    0xC3, 0x09, 0x8B, 0xC3, 0x10, 0x8B, 0xC3, 0x2F, 0x8B,   # jp Init/Play/Stop
    0x21, 0x47, 0x8B, 0x22, 0x45, 0x8B, 0xC9,               # Init
    0x2A, 0x45, 0x8B,                                       # Play: ld hl,(PTR)
    0x7E, 0x23, 0xFE, 0xFF, 0x28, 0x12, 0xFE, 0xFE, 0x28, 0x09,
    0x47, 0x4E, 0x23, 0x78, 0xCD, 0x34, 0xBD, 0x18, 0xED,
    0x21, 0x47, 0x8B, 0x18, 0xE8,                           # PRESET (bucle)
    0x22, 0x45, 0x8B, 0xC9,                                 # PDONE
    0x3E, 0x08, 0x0E, 0x00, 0xCD, 0x34, 0xBD,               # Stop: silencia
    0x3E, 0x09, 0x0E, 0x00, 0xCD, 0x34, 0xBD,
    0x3E, 0x0A, 0x0E, 0x00, 0xCD, 0x34, 0xBD, 0xC9,
    0x00, 0x00,                                             # PTR (&8B45)
])


def cpc_music_bin(path_or_bytes, clock=CLOCK_CPC):
    """Binario para cargar en &8B00 en el CPC: reproductor Z80 + datos PSG.
    Devuelve (bytes, n_frames). El BASIC del titulo hace CALL &8B00/&8B03/&8B06."""
    psg, nf = midi_to_psg(path_or_bytes, clock=clock)
    return PLAYER_CPC + psg, nf


# ─── Encoder PSG ESTANDAR (para el reproductor que ya tiene Spectrum/Next) ──
def encode_psg_standard(frames):
    """Formato .psg estandar: cada frame empieza por 0xFF + las parejas (reg,val)
    de los registros que cambian; fin de musica = 0xFD (el reproductor hace
    bucle). Es lo que consume aplica_musica del Spectrum 128."""
    prev = [None] * 14
    out = bytearray()
    for regs in frames:
        out.append(0xFF)
        for r in range(14):
            v = regs[r]
            if v is None:
                continue
            if prev[r] != v:
                out.append(r); out.append(v); prev[r] = v
    out.append(0xFD)
    return bytes(out)


def midi_to_psg_standard(path_or_bytes, clock=CLOCK_ZX, fps=50, voces=3):
    """MIDI -> stream .psg estandar (Spectrum 128 / Next; reloj AY 1,77 MHz)."""
    data = (path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray))
            else open(path_or_bytes, 'rb').read())
    frames = frames_ay(arrange(midi_to_active(data, fps), voces), clock)
    return encode_psg_standard(frames)


if __name__ == '__main__':
    import sys
    psg, nf = midi_to_psg(sys.argv[1])
    print(f'[mid2psg] {sys.argv[1]} -> PSG {len(psg)} bytes, {nf} frames '
          f'({nf/50:.1f}s a 50Hz)')
