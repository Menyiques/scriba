# -*- coding: utf-8 -*-
"""
afx.py — Lectura de efectos del "AY Sound FX Editor" de Shiru.

Formato (del readme):
  Cada frame = byte de flags + bytes variables:
    bit0..3 = volumen (0-15)
    bit4    = desactiva T (tono) en el mixer
    bit5    = cambia tono   -> siguen 2 bytes (LSB,MSB), periodo 12 bits
    bit6    = cambia ruido  -> sigue 1 byte, periodo de ruido (0-31)
    bit7    = desactiva N (ruido) en el mixer
  Fin del efecto: flag #D0 seguido de byte de ruido #20 (ruido==0x20 = sentinel).
  Los valores que no cambian se arrastran del frame anterior.

  .afx = efecto único.  .afb = banco: [n] + n*offset(2) + datos (+nombres).
"""


def parse_afx(data):
    """Decodifica un efecto único (.afx) -> lista de frames.
    Cada frame: {'vol','t','n','tone','noise'} (t/n = canal activado en el mixer)."""
    frames = []
    i, n = 0, len(data)
    tone, noise = 0, 0
    while i < n:
        flag = data[i]; i += 1
        vol = flag & 0x0F
        t_on = not (flag & 0x10)
        n_on = not (flag & 0x80)
        end = False
        if flag & 0x20:                      # cambia tono
            if i + 1 >= n:
                break
            tone = (data[i] | (data[i + 1] << 8)) & 0x0FFF
            i += 2
        if flag & 0x40:                      # cambia ruido
            if i >= n:
                break
            nv = data[i]; i += 1
            if nv == 0x20:                   # marca de fin
                end = True
            else:
                noise = nv & 0x1F
        if end:
            break
        frames.append({'vol': vol, 't': bool(t_on), 'n': bool(n_on),
                       'tone': tone, 'noise': noise})
    return frames


def effect_end(data, start=0):
    """Índice justo tras el terminador (#D0,#20) del efecto que empieza en start."""
    i, n = start, len(data)
    while i < n:
        flag = data[i]; i += 1
        if flag & 0x20:
            i += 2
        if flag & 0x40:
            if i < n and data[i] == 0x20:
                return i + 1
            i += 1
    return i


def split_afb(data):
    """Banco .afb -> lista de bytes crudos de cada efecto (cada uno parseable
    con parse_afx)."""
    if not data:
        return []
    n = data[0] or 256
    out = []
    for k in range(n):
        p = 1 + k * 2
        if p + 1 >= len(data):
            break
        off = data[p] | (data[p + 1] << 8)
        addr = p + off
        end = effect_end(data, addr)
        out.append(bytes(data[addr:end]))
    return out


def parse_afb(data):
    """Decodifica un banco (.afb) -> lista de efectos (cada uno lista de frames)
    y sus nombres si están. Devuelve (effects, names)."""
    if not data:
        return [], []
    n = data[0] or 256
    effects, names = [], []
    for k in range(n):
        p = 1 + k * 2
        off = data[p] | (data[p + 1] << 8)
        addr = p + off                        # offset relativo al 2º byte del offset
        # el efecto va hasta su fin (#D0,#20); parse_afx para en el sentinel
        frames = parse_afx(data[addr:])
        effects.append(frames)
        names.append('')                      # (los nombres requieren rastrear el fin)
    return effects, names


def render_wav(frames, clock=1773400, sr=22050, fps=50):
    """Renderiza los frames AYFX a un WAV (PCM 8-bit mono) para vista previa en PC.
    clock por defecto = reloj del AY del Spectrum. Aproxima 1 canal (tono+ruido)."""
    import wave
    import io
    import random
    spf = max(1, sr // fps)
    pcm = bytearray()
    tphase = 0.0
    tlevel = 1
    nlevel = 1
    nphase = 0.0
    for f in frames:
        vol = f['vol']
        amp = int(110 * (vol / 15.0))
        tone = f['tone'] or 1
        noise = f['noise'] or 1
        tfreq = clock / (16.0 * tone)
        nfreq = clock / (16.0 * noise)
        thalf = (sr / (2.0 * tfreq)) if tfreq > 0 else 1e9
        nstep = (sr / nfreq) if nfreq > 0 else 1e9
        on = (f['t'] or f['n']) and vol > 0
        for _ in range(spf):
            tphase += 1
            if tphase >= thalf:
                tphase -= thalf
                tlevel ^= 1
            nphase += 1
            if nphase >= nstep:
                nphase -= nstep
                nlevel = 1 if random.random() < 0.5 else 0
            if f['t'] and f['n']:
                bit = tlevel & nlevel
            elif f['t']:
                bit = tlevel
            else:
                bit = nlevel
            if on:
                pcm.append(128 + amp if bit else 128 - amp)
            else:
                pcm.append(128)
    bio = io.BytesIO()
    w = wave.open(bio, 'wb')
    w.setnchannels(1)
    w.setsampwidth(1)
    w.setframerate(sr)
    w.writeframes(bytes(pcm))
    w.close()
    return bio.getvalue()


if __name__ == '__main__':
    import sys
    for path in sys.argv[1:]:
        data = open(path, 'rb').read()
        fr = parse_afx(data)
        print('%s: %d bytes -> %d frames' % (path, len(data), len(fr)))
        for j, f in enumerate(fr[:4]):
            print('   frame %d: %s' % (j, f))
        if len(fr) > 4:
            print('   ... último: %s' % fr[-1])
