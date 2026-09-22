# -*- coding: utf-8 -*-
"""
presupuesto.py - Cuentas de memoria de cada maquina, con la misma cara.

Cada backend tiene sus topes -- el mapa plano de 64K, los bancos conmutables,
las ranuras de cache del CPC -- y hasta la v2.53 cada uno avisaba a su manera,
o no avisaba: el 48K y el CPC no miraban nada y generaban un binario corrupto,
y el CPC ademas tiraba en silencio las imagenes que no le cabian.

Aqui se juntan las dos cosas que hacen util un aviso de memoria: QUE ocupa cada
cosa (si no, el autor no sabe por donde recortar) y POR CUANTO se pasa.

Y las mismas cuentas sirven cuando SI cabe: cada `comprueba` deja su tabla
apuntada, y el exportador la recoge con `informe()` para ensenarla al terminar.
El autor no tiene que esperar a pasarse para saber cuanto le queda.
"""

# Las tablas de la exportacion en curso. Es estado de modulo a proposito: se
# exporta una maquina cada vez, y asi los exportadores no tienen que ir pasando
# el informe por cinco firmas de funcion hasta la ventana del editor.
_TABLAS = []


def empieza():
    """Borra las cuentas de la exportacion anterior. Lo llama el exportador
    antes de compilar nada."""
    del _TABLAS[:]


def apunta(texto):
    """Mete una linea suelta en el informe (algo que no es un tope: la cache de
    imagenes del CPC, el tamano del disco...)."""
    _TABLAS.append(str(texto))


def informe():
    """Todo lo medido desde el ultimo `empieza()`, listo para ensenar."""
    return (chr(10) * 2).join(_TABLAS)


def _miles(n):
    return '{:,}'.format(int(n)).replace(',', '.')


def tabla(partidas, tope, nombre_tope, unidad='bytes'):
    """Las partidas y el total, en columnas, con el tope de cabecera.

    El tope va arriba y no pegado al total, para que ninguna linea se pase de
    ancho: esto se lee en una ventana del editor, en monoespaciado, y una linea
    larga obliga a estirar la ventana entera."""
    total = sum(b for _, b in partidas)
    # Ancho minimo generoso: asi las tablas de una misma exportacion (la RAM
    # principal y los bancos, por ejemplo) salen con las columnas alineadas
    # entre si y se leen como un solo informe.
    ancho = max([len(e) for e, _ in partidas] + [26])
    cab = nombre_tope.strip()
    L = ['%s: %s %s' % (cab[:1].upper() + cab[1:], _miles(tope), unidad)]
    L += ['   %-*s %10s' % (ancho, e, _miles(b)) for e, b in partidas]
    L.append('   ' + '-' * (ancho + 11))
    L.append('   %-*s %10s' % (ancho, 'total', _miles(total)))
    L.append('   %-*s %10s' % (ancho, 'libre' if total <= tope else 'SE PASA POR',
                               _miles(abs(tope - total))))
    return chr(10).join(L)


def comprueba(maquina, partidas, tope, nombre_tope, consejos=(), primero=False,
              unidad='bytes'):
    """Levanta ValueError con la cuenta desglosada si no cabe. Devuelve los
    bytes libres si cabe.

    `primero` pone su tabla la primera del informe aunque se mida la ultima:
    en el 128K y el Next los bancos se comprueban antes de compilar (es lo que
    mas suele pasarse, y asi no se espera a compilar para saberlo), pero quien
    lee el informe espera ver primero la RAM principal."""
    total = sum(b for _, b in partidas)
    t = tabla(partidas, tope, nombre_tope, unidad)
    _TABLAS.insert(0 if primero else len(_TABLAS), t)
    if total <= tope:
        return tope - total
    msg = ['%s: no cabe en %s. Se pasa por %s %s.'
           % (maquina, nombre_tope, _miles(total - tope), unidad), '', t]
    if consejos:
        msg += ['', 'Por donde recortar:'] + ['  - ' + c for c in consejos]
    raise ValueError(chr(10).join(msg))


# Consejos por tipo de tope, para no repetirlos en cada exportador.
RECORTA_PLANO = (
    'en 48K y CPC, acorta texto: las descripciones y los mensajes son la '
    'mayor parte de la base de datos',
    'en 48K y CPC, quita efectos FX que no se usen (cada uno son 5 bytes por '
    'frame)',
    'en 128K y Next el texto, los FX y la musica ya van en bancos: lo que '
    'queda plano son las respuestas, el vocabulario y los objetos',
)
RECORTA_BANCOS = (
    'quita imagenes de localizacion (unos 1.900 bytes cada una en 128K; un '
    'banco entero en Next)',
    'acorta o quita muestras digitalizadas (5.512 bytes por segundo a 11 kHz)',
    'acorta texto: en 128K y Next va en los bancos, con la musica y los FX',
    'quita la pantalla de presentacion',
)
