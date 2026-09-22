# -*- coding: utf-8 -*-
"""
wav2ay.py - Digitaliza un WAV para reproducirlo por el chip AY.

El AY no tiene DAC, pero tiene tres registros de volumen de 4 bits. Si se apaga
el mezclador (ni tono ni ruido) y se va escribiendo la amplitud de la muestra en
el registro de volumen a ritmo constante, el chip se comporta como un DAC de 4
bits. Es lo que hacen los digidrums del 128K y del CPC desde los ochenta.

Dos cosas hay que hacer bien o suena a lata:

  * La escala del AY es LOGARITMICA, no lineal: del nivel 15 al 14 se baja mucho
    mas que del 1 al 0. Volcar los cuatro bits altos del PCM da un sonido
    aplastado y con la parte baja inaudible. Aqui se busca, para cada muestra,
    el nivel cuya amplitud REAL es la mas cercana (tabla AY_AMP).
  * Hay que remuestrear al ritmo EXACTO al que el reproductor Z80 va a escribir,
    porque ese ritmo lo fija el bucle en T-estados, no un temporizador.

Formato de salida: dos muestras por byte (nibble alto primero), que a 11 kHz son
5.512 bytes por segundo. En el 128K las muestras viven en los bancos, que es
donde hay sitio.

    python wav2ay.py voz.wav salida.bin [--hz 11025]
    python wav2ay.py voz.wav --audicion previa.wav   (como va a sonar)
"""
import struct
import sys
import wave

# Amplitud real de cada nivel de volumen del AY-3-8910, normalizada a 1.0.
# Es la tabla medida que usa todo el mundo; la diferencia con una rampa lineal
# es justo lo que hace que una muestra suene o no suene.
AY_AMP = (0.0000, 0.0137, 0.0205, 0.0291, 0.0423, 0.0618, 0.0847, 0.1369,
          0.1691, 0.2647, 0.3527, 0.4499, 0.5704, 0.6873, 0.8482, 1.0000)

HZ_POR_DEFECTO = 11025


def carga_wav(path):
    """Devuelve (muestras en [-1,1], frecuencia). Acepta 8 y 16 bits, mono o
    estereo (se mezcla a mono)."""
    with wave.open(path, 'rb') as w:
        canales, ancho, sr, nframes = (w.getnchannels(), w.getsampwidth(),
                                       w.getframerate(), w.getnframes())
        crudo = w.readframes(nframes)
    if ancho == 1:                      # PCM de 8 bits: sin signo, centro 128
        vals = [(b - 128) / 128.0 for b in crudo]
    elif ancho == 2:
        vals = [v / 32768.0 for v in
                struct.unpack('<%dh' % (len(crudo) // 2), crudo)]
    else:
        raise ValueError('solo 8 o 16 bits por muestra (este trae %d)' % (ancho * 8))
    if canales > 1:
        vals = [sum(vals[i:i + canales]) / canales
                for i in range(0, len(vals) - canales + 1, canales)]
    return vals, sr


def remuestrea(vals, sr_orig, sr_dest):
    """Remuestreo lineal. No es un filtro de libro, pero a 4 bits el ruido de
    cuantizacion tapa de sobra lo que aporte un resampler mejor."""
    if sr_orig == sr_dest or not vals:
        return list(vals)
    n = max(1, int(len(vals) * sr_dest / float(sr_orig)))
    paso = (len(vals) - 1) / float(max(1, n - 1)) if n > 1 else 0.0
    out = []
    for i in range(n):
        x = i * paso
        j = int(x)
        f = x - j
        a = vals[j]
        b = vals[j + 1] if j + 1 < len(vals) else a
        out.append(a + (b - a) * f)
    return out


def normaliza(vals, techo=0.98):
    pico = max((abs(v) for v in vals), default=0.0)
    if pico < 1e-6:
        return [0.0] * len(vals)
    k = techo / pico
    return [v * k for v in vals]


def a_niveles(vals):
    """Cada muestra -> el nivel de volumen del AY (0..15) cuya amplitud real es
    la mas parecida. La señal va de [-1,1] a [0,1]: el AY solo sabe de amplitud,
    asi que el cero de la onda cae a media escala."""
    fuera = []
    for v in vals:
        x = (v + 1.0) * 0.5
        if x < 0.0:
            x = 0.0
        elif x > 1.0:
            x = 1.0
        mejor, dmin = 0, 9.0
        for i, amp in enumerate(AY_AMP):
            d = abs(amp - x)
            if d < dmin:
                mejor, dmin = i, d
        fuera.append(mejor)
    return fuera


def empaqueta(niveles):
    """Dos muestras por byte, la primera en el nibble ALTO."""
    if len(niveles) % 2:
        niveles = list(niveles) + [niveles[-1]]
    return bytes(((niveles[i] & 15) << 4) | (niveles[i + 1] & 15)
                 for i in range(0, len(niveles), 2))


def desempaqueta(datos):
    out = []
    for b in datos:
        out.append((b >> 4) & 15)
        out.append(b & 15)
    return out


def convierte(path, hz=HZ_POR_DEFECTO, normalizar=True):
    """WAV -> (bytes empaquetados, numero de muestras, info legible)."""
    vals, sr = carga_wav(path)
    orig = len(vals)
    vals = remuestrea(vals, sr, hz)
    if normalizar:
        vals = normaliza(vals)
    niveles = a_niveles(vals)
    datos = empaqueta(niveles)
    info = ('%s: %d muestras a %d Hz -> %d a %d Hz -> %d bytes (%.2f s)'
            % (path, orig, sr, len(niveles), hz, len(datos), len(niveles) / float(hz)))
    return datos, len(niveles), info


def wav_de_datos(datos, hz=HZ_POR_DEFECTO):
    """Reconstruye un WAV de 16 bits con lo que de verdad va a salir por el AY:
    los mismos 16 niveles y su curva. Sirve para oir la muestra ANTES de
    gastarse los bytes en un banco."""
    import io as _io
    niveles = desempaqueta(datos)
    pcm = bytearray()
    for nv in niveles:
        v = int(round((AY_AMP[nv] * 2.0 - 1.0) * 32000))
        pcm += struct.pack('<h', max(-32768, min(32767, v)))
    bio = _io.BytesIO()
    with wave.open(bio, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(hz)
        w.writeframes(bytes(pcm))
    return bio.getvalue()


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(2)
    def opt(nombre, pordef=None):
        return argv[argv.index(nombre) + 1] if nombre in argv else pordef
    hz = int(opt('--hz', HZ_POR_DEFECTO))
    audicion = opt('--audicion')
    sueltos = [a for a in argv if not a.startswith('--')
               and a not in (opt('--hz'), audicion)]
    entrada = sueltos[0]
    datos, nm, info = convierte(entrada, hz=hz)
    print(info)
    if audicion:
        open(audicion, 'wb').write(wav_de_datos(datos, hz))
        print('audicion: %s' % audicion)
    if len(sueltos) > 1:
        open(sueltos[1], 'wb').write(datos)
        print('salida:   %s' % sueltos[1])


if __name__ == '__main__':
    main()
