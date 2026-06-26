# -*- coding: utf-8 -*-
"""
fx_engine.py — Efectos de sonido estilo "beeper" para Scriba (modelo propio).

Un efecto es una secuencia de BLOQUES. Cada bloque produce un tono (onda cuadrada
de 1 bit) que puede deslizar su altura de p1 a p2 durante 'dur' unidades, o ruido.

    bloque = {'p1':1..255, 'p2':1..255, 'dur':1..255, 'noise':0/1}
    efecto = {'name': str, 'blocks': [bloque, ...]}

Este módulo es la "verdad" del sonido: el sintetizador (a WAV) sirve de vista
previa en el editor, y los reproductores Z80/AY de cada plataforma lo aproximan
a partir de los mismos bytes (effect_bytes / pack_fx).

Unidades:
  • altura p (1..255): a mayor p, tono más agudo. freq(p) = FBASE + p*FSTEP Hz.
  • dur: 1 unidad = DUR_MS milisegundos.
"""

import struct
import wave
import io

FBASE = 30          # Hz para p=1
FSTEP = 15          # Hz por unidad de altura
DUR_MS = 12         # ms por unidad de duración
SR = 22050          # frecuencia de muestreo de la vista previa

MAX_FX = 64         # límite de efectos por juego
MAX_BLOCKS = 32     # límite de bloques por efecto


def freq_of(p):
    return FBASE + max(1, min(255, int(p))) * FSTEP


# ─── Sintetizador (vista previa) ─────────────────────────────────────────────

def _square_into(buf, freq, nsamples, phase, level, noise=False):
    """Añade nsamples de onda cuadrada (o ruido) a buf (lista de 0/1 niveles).
    Devuelve (phase, level) para continuar. phase en muestras hasta el toggle."""
    if freq < 1:
        freq = 1
    half = max(1, int(SR / (2.0 * freq)))   # muestras por medio periodo
    import random
    for _ in range(nsamples):
        buf.append(level)
        phase += 1
        if phase >= half:
            phase = 0
            if noise:
                level = 1 if random.random() < 0.5 else 0
            else:
                level ^= 1
    return phase, level


def synth(effect, rate=SR):
    """Sintetiza un efecto a PCM 8-bit sin signo (bytes) listo para WAV."""
    levels = []
    phase, level = 0, 0
    for b in effect.get('blocks', []):
        p1 = int(b.get('p1', 1)); p2 = int(b.get('p2', p1))
        dur = max(1, int(b.get('dur', 1)))
        noise = bool(b.get('noise', 0))
        nsamples = int(rate * dur * DUR_MS / 1000.0)
        if nsamples <= 0:
            continue
        # desliza la frecuencia de p1 a p2 en pasos cortos
        steps = max(1, nsamples // 220)     # ~10ms por paso
        per = max(1, nsamples // steps)
        done = 0
        for s in range(steps):
            frac = s / float(steps - 1) if steps > 1 else 0.0
            p = p1 + (p2 - p1) * frac
            n = per if s < steps - 1 else (nsamples - done)
            phase, level = _square_into(levels, freq_of(p), n, phase, level, noise)
            done += n
    # niveles 0/1 -> PCM 8-bit (silencio = 128; onda alrededor)
    lo, hi = 40, 215
    return bytes(hi if v else lo for v in levels)


def wav_bytes(effect, rate=SR):
    """Devuelve el efecto como un WAV completo (bytes) para reproducir/guardar."""
    pcm = synth(effect, rate)
    bio = io.BytesIO()
    w = wave.open(bio, 'wb')
    w.setnchannels(1)
    w.setsampwidth(1)        # 8-bit
    w.setframerate(rate)
    w.writeframes(pcm)
    w.close()
    return bio.getvalue()


# ─── Serialización para los reproductores Z80/AY ─────────────────────────────

def effect_bytes(effect):
    """Bytes de un efecto: [nblocks] + nblocks*(p1,p2,dur,flags)."""
    blocks = effect.get('blocks', [])[:MAX_BLOCKS]
    out = bytearray([len(blocks) & 0xFF])
    for b in blocks:
        out.append(max(1, min(255, int(b.get('p1', 1)))))
        out.append(max(1, min(255, int(b.get('p2', b.get('p1', 1))))))
        out.append(max(1, min(255, int(b.get('dur', 1)))))
        out.append(1 if b.get('noise', 0) else 0)
    return bytes(out)


def pack_fx(effects):
    """Empaqueta la tabla de efectos en un blob autocontenido:
        [nfx][off0_lo,off0_hi]...[offN]  + bloques de cada efecto
    Los offsets son RELATIVOS al inicio del blob. nfx<=MAX_FX."""
    effects = list(effects)[:MAX_FX]
    n = len(effects)
    head = bytearray([n])
    bodies = [effect_bytes(e) for e in effects]
    table_size = 1 + n * 2
    off = table_size
    offs = []
    for body in bodies:
        offs.append(off)
        off += len(body)
    for o in offs:
        head.append(o & 0xFF); head.append((o >> 8) & 0xFF)
    blob = bytes(head) + b''.join(bodies)
    return blob


# ─── Resolver el argumento de PLAY (nombre o número) -> índice 1-based ───────

def fx_index(fx_list, arg):
    """Resuelve el argumento de PLAY a un índice 1-based en fx_list.
    arg puede ser un nombre entre comillas (PLAY "explosion") o un número
    (PLAY 1, compatibilidad). Devuelve 0 si no se encuentra. La comparación de
    nombres ignora mayúsculas/espacios."""
    s = str(arg).strip()
    if not s:
        return 0
    if s[0] in ('"', "'"):
        name = s.strip('\'"').strip().lower()
        for i, e in enumerate(fx_list or []):
            if isinstance(e, dict) and (e.get('name') or '').strip().lower() == name:
                return i + 1
        return 0
    try:
        return int(s)
    except ValueError:
        return 0


# ─── Conversión a frames del AY (reproductores 128K / Next / CPC) ────────────
# Un "frame AY" son los 5 registros que toca cada efecto a 50 Hz, en el canal A:
#   R0 (tono lo), R1 (tono hi 4 bits), R6 (ruido 0..31), R7 (mezclador), R8 (vol).
# El mezclador R7 usa 0x3F como base (todo desactivado, puertos como entrada) y
# limpia el bit0 (tono A) y/o el bit3 (ruido A) según el frame. Reloj del AY:
# Spectrum/Next = 1773400 Hz; CPC = 1000000 Hz (cambia el periodo de tono).

def effect_to_ayframes(effect, clock=1773400, fps=50):
    """Convierte un efecto (AYFX 'afx' hex, o sintetizado 'blocks') a una lista de
    tuplas (R0,R1,R6,R7,R8), una por frame de 1/fps s, en el canal A del AY."""
    frames = []
    afxhex = effect.get('afx')
    if afxhex:
        try:
            import afx as _afx
            data = bytes.fromhex(afxhex) if isinstance(afxhex, str) else bytes(afxhex)
            # Los periodos de un AYFX están calculados para el reloj del AY del
            # Spectrum (1773400 Hz). Si el target usa otro reloj (CPC = 1000000),
            # se reescala el periodo para conservar el tono: per' = per*clock/clk_zx.
            scale = clock / 1773400.0
            for f in _afx.parse_afx(data):
                tone = int(round(int(f.get('tone', 0)) * scale)) if scale != 1.0 \
                    else int(f.get('tone', 0))
                tone &= 0x0FFF
                vol = int(f.get('vol', 0)) & 0x0F
                noise = int(f.get('noise', 0)) & 0x1F
                r7 = 0x3F
                if f.get('t'):
                    r7 &= ~0x01          # activar tono A
                if f.get('n'):
                    r7 &= ~0x08          # activar ruido A
                frames.append((tone & 0xFF, (tone >> 8) & 0x0F, noise, r7 & 0xFF, vol))
        except Exception:
            return []
    else:
        for b in effect.get('blocks', []):
            p1 = int(b.get('p1', 1)); p2 = int(b.get('p2', p1))
            dur = max(1, int(b.get('dur', 1)))
            noise = bool(b.get('noise', 0))
            nfr = max(1, int(round(dur * DUR_MS / (1000.0 / fps))))
            for i in range(nfr):
                frac = i / float(nfr - 1) if nfr > 1 else 0.0
                p = p1 + (p2 - p1) * frac
                per = int(round(clock / (16.0 * max(1.0, freq_of(p)))))
                per = max(1, min(4095, per))
                r7 = 0x3F & ~0x01                      # tono A activo
                if noise:
                    r7 &= ~0x08                        # + ruido A
                frames.append((per & 0xFF, (per >> 8) & 0x0F,
                               16 if noise else 0, r7 & 0xFF, 15))
    return frames


def pack_ay_fx(effects, used, clock=1773400, fps=50, max_frames=255):
    """Empaqueta SOLO los efectos referenciados ('used' = set de índices 1-based)
    como blob autocontenido para el reproductor AY retro:

        [nfx][off0_lo,off0_hi]...[offN-1]  + bloques de los efectos usados

    Cada offset es RELATIVO al inicio del blob (0 = ranura no incluida). Cada
    bloque = [nframes] + nframes*(R0,R1,R6,R7,R8). nfx = mayor índice usado, así
    los números de PLAY se conservan sin renumerar. Devuelve b'' si no hay FX."""
    used = {int(i) for i in used if int(i) >= 1}
    if not used:
        return b''
    nfx = min(max(used), MAX_FX)
    bodies = [b''] * nfx
    for idx in sorted(used):
        if idx > nfx or idx - 1 >= len(effects):
            continue
        frames = effect_to_ayframes(effects[idx - 1], clock=clock, fps=fps)[:max_frames]
        body = bytearray([len(frames) & 0xFF])
        for (r0, r1, r6, r7, r8) in frames:
            body += bytes((r0 & 0xFF, r1 & 0xFF, r6 & 0xFF, r7 & 0xFF, r8 & 0xFF))
        bodies[idx - 1] = bytes(body)
    head = bytearray([nfx & 0xFF])
    off = 1 + nfx * 2
    offs = []
    for body in bodies:
        if body:
            offs.append(off); off += len(body)
        else:
            offs.append(0)
    for o in offs:
        head.append(o & 0xFF); head.append((o >> 8) & 0xFF)
    return bytes(head) + b''.join(bodies)


# ─── Presets de ejemplo (para "nuevo desde plantilla") ───────────────────────

PRESETS = {
    'Disparo':   {'name': 'Disparo',   'blocks': [{'p1': 200, 'p2': 20, 'dur': 6, 'noise': 0}]},
    'Explosión': {'name': 'Explosion', 'blocks': [{'p1': 120, 'p2': 1, 'dur': 18, 'noise': 1}]},
    'Recoger':   {'name': 'Recoger',   'blocks': [{'p1': 120, 'p2': 120, 'dur': 3, 'noise': 0},
                                                  {'p1': 200, 'p2': 200, 'dur': 3, 'noise': 0}]},
    'Error':     {'name': 'Error',     'blocks': [{'p1': 60, 'p2': 60, 'dur': 8, 'noise': 0},
                                                  {'p1': 40, 'p2': 40, 'dur': 10, 'noise': 0}]},
    'Puerta':    {'name': 'Puerta',    'blocks': [{'p1': 90, 'p2': 30, 'dur': 14, 'noise': 1}]},
    'Salto':     {'name': 'Salto',     'blocks': [{'p1': 60, 'p2': 230, 'dur': 7, 'noise': 0}]},
}


if __name__ == '__main__':
    import sys
    e = PRESETS['Disparo']
    data = wav_bytes(e)
    out = sys.argv[1] if len(sys.argv) > 1 else 'fx_test.wav'
    open(out, 'wb').write(data)
    print('WAV %d bytes -> %s' % (len(data), out))
    print('effect_bytes:', effect_bytes(e).hex())
    print('pack_fx(2):', pack_fx([PRESETS['Disparo'], PRESETS['Explosión']]).hex())
