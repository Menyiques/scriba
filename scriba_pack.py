# -*- coding: utf-8 -*-
"""
scriba_pack.py - El juego, dentro del propio ejecutable.

El problema: "Exportar para Windows" dejaba el `game.yaml` en texto plano al
lado del .exe. Cualquiera que abra la carpeta con el Bloc de notas se encuentra
las respuestas de los acertijos, la combinacion de la caja fuerte y el final.

Lo que hace esto: mete el juego y sus imagenes en un solo bloque -serializado,
comprimido y cifrado- y lo PEGA AL FINAL de una copia del reproductor. El
jugador recibe un unico .exe y en su carpeta no hay nada que leer. El
reproductor se lee a si mismo al arrancar y lo descifra en memoria: no se
escribe en disco en ningun momento.

HASTA DONDE PROTEGE (importa decirlo): el reproductor tiene que poder leer el
juego para jugarlo, asi que la clave viaja dentro del binario. Quien sepa
Python y tenga ganas la saca. Esto es un candado contra la curiosidad -no hay
texto legible, ni con el Bloc de notas ni con `strings`, y dos exportaciones
del mismo juego no se parecen entre si porque cada una lleva su sal-, no una
caja fuerte. Para eso no hay nada que hacer en un programa que se distribuye.

POR QUE SE PUEDE PEGAR AL FINAL DE UN .EXE DE PYINSTALLER: el arranque de
PyInstaller no espera su cabecera en el ultimo byte. La busca escaneando el
fichero de atras hacia delante en trozos de 8 KB
(`pyi_utils_find_magic_pattern`), precisamente para sobrevivir a las firmas
digitales, que tambien se pegan detras. Como el escaneo va de atras hacia
delante y se queda con la PRIMERA coincidencia que encuentra, lo unico que hay
que garantizar es que nuestro bloque no contenga por casualidad ese patron de
8 bytes; `empaqueta()` lo comprueba y, si pasara, cambia la sal y vuelve a
cifrar.

Formato del bloque pegado:

    SELLO(8) | version(1) | sal(16) | u32 len(cuerpo) | cuerpo | u64 total | SELLO(8)

y el cuerpo es zlib(TLV) cifrado con un keystream SHA-256. El pie repetido al
final es lo que permite encontrarlo leyendo los ultimos 16 bytes.
"""

import hashlib
import io
import json
import os
import struct
import zlib

SELLO = b'SCRIBAPK'
VERSION = 1

# El patron que busca el arranque de PyInstaller (MAGIC_BASE con el 4o byte a
# 0x0C). Nuestro bloque NO puede contenerlo o el .exe dejaria de arrancar.
MAGIC_PYI = b'MEI' + bytes([0x0C, 0x0B, 0x0A, 0x0B, 0x0E])

EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')

# La clave no es un literal suelto: se deriva, para que no aparezca tal cual en
# el binario. Sigue estando ahi para quien la busque (ver la nota de arriba).
_CLAVE = hashlib.sha256(
    b'Scriba' + bytes([0x9E, 0x37, 0x79, 0xB9, 0x7F, 0x4A, 0x7C, 0x15])
    + b'reproductor' + bytes([0x2B, 0x9D, 0x5A, 0x33])).digest()


def _keystream(n, sal):
    out = bytearray()
    i = 0
    while len(out) < n:
        out += hashlib.sha256(_CLAVE + sal + struct.pack('<I', i)).digest()
        i += 1
    return bytes(out[:n])


def _cifra(datos, sal):
    k = _keystream(len(datos), sal)
    return bytes(a ^ b for a, b in zip(datos, k))


def _tlv(partes):
    """[(nombre, bytes)] -> un bloque plano."""
    out = [struct.pack('<I', len(partes))]
    for nombre, datos in partes:
        n = nombre.encode('utf-8')
        out.append(struct.pack('<H', len(n)) + n +
                   struct.pack('<I', len(datos)) + datos)
    return b''.join(out)


def _des_tlv(blob):
    n = struct.unpack_from('<I', blob, 0)[0]
    i = 4
    partes = []
    for _ in range(n):
        ln = struct.unpack_from('<H', blob, i)[0]; i += 2
        nombre = blob[i:i + ln].decode('utf-8'); i += ln
        ld = struct.unpack_from('<I', blob, i)[0]; i += 4
        partes.append((nombre, blob[i:i + ld])); i += ld
    return partes


def _imagenes(img_dir):
    if not img_dir or not os.path.isdir(img_dir):
        return []
    out = []
    for fn in sorted(os.listdir(img_dir)):
        if fn.lower().endswith(EXTS):
            with open(os.path.join(img_dir, fn), 'rb') as f:
                out.append(('img/' + fn, f.read()))
    return out


def empaqueta(game, img_dir=None, titulo=None):
    """(juego, carpeta de imagenes) -> el bloque listo para pegar al .exe."""
    meta = {'titulo': titulo or (game.get('metadata') or {}).get('title', 'Scriba')}
    partes = [('meta.json', json.dumps(meta, ensure_ascii=False).encode('utf-8')),
              ('juego.json', json.dumps(game, ensure_ascii=False).encode('utf-8'))]
    partes += _imagenes(img_dir)
    comprimido = zlib.compress(_tlv(partes), 9)
    for _ in range(64):
        sal = os.urandom(16)
        cuerpo = _cifra(comprimido, sal)
        cab = SELLO + bytes([VERSION]) + sal + struct.pack('<I', len(cuerpo))
        total = len(cab) + len(cuerpo) + 8 + len(SELLO)
        bloque = cab + cuerpo + struct.pack('<Q', total) + SELLO
        assert len(bloque) == total
        if MAGIC_PYI not in bloque:
            return bloque
    raise RuntimeError('no consigo un bloque sin el patron de PyInstaller')


def abre(bloque):
    """El bloque -> (juego, {nombre: bytes}, titulo). None si no es nuestro."""
    if len(bloque) < 40 or not bloque.startswith(SELLO):
        return None
    i = len(SELLO)
    version = bloque[i]; i += 1
    if version != VERSION:
        raise ValueError('bloque de una version desconocida: %d' % version)
    sal = bloque[i:i + 16]; i += 16
    n = struct.unpack_from('<I', bloque, i)[0]; i += 4
    crudo = zlib.decompress(_cifra(bloque[i:i + n], sal))
    juego, imgs, titulo = None, {}, None
    for nombre, datos in _des_tlv(crudo):
        if nombre == 'juego.json':
            juego = json.loads(datos.decode('utf-8'))
        elif nombre == 'meta.json':
            titulo = json.loads(datos.decode('utf-8')).get('titulo')
        elif nombre.startswith('img/'):
            imgs[nombre[4:]] = datos
    if juego is None:
        raise ValueError('el bloque no trae juego')
    return juego, imgs, titulo


def lee_de(path):
    """Lee el bloque pegado al final de un fichero. None si no lleva ninguno."""
    try:
        tam = os.path.getsize(path)
        if tam < 16:
            return None
        with open(path, 'rb') as f:
            f.seek(-16, os.SEEK_END)
            cola = f.read(16)
            if cola[8:] != SELLO:
                return None
            total = struct.unpack_from('<Q', cola, 0)[0]
            if not (0 < total <= tam):
                return None
            f.seek(-total, os.SEEK_END)
            return abre(f.read(total))
    except Exception:
        return None


def pega(exe_origen, exe_destino, bloque):
    """Copia el reproductor y le pega el bloque detras. Devuelve el destino."""
    with open(exe_origen, 'rb') as f:
        base = f.read()
    if base.rstrip(b'\x00')[-len(SELLO):] == SELLO or lee_de(exe_origen):
        raise ValueError('el reproductor de origen ya lleva un juego pegado')
    with open(exe_destino, 'wb') as f:
        f.write(base)
        f.write(bloque)
    return exe_destino


def imagen(imgs, loc_id):
    """La imagen de una localizacion, como fichero en memoria. None si no hay."""
    if not imgs or not loc_id:
        return None
    for ext in EXTS:
        datos = imgs.get(str(loc_id) + ext)
        if datos is not None:
            return io.BytesIO(datos)
    return None
