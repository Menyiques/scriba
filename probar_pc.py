# -*- coding: utf-8 -*-
"""
probar_pc.py - La bateria .pru, jugada sobre el interprete de Python.

El tercer corredor de la familia. Los otros cuatro (bateria_next, probar_juego,
probar_48, verify_*) van todos contra el motor NATIVO Z80, unos sobre jnext y
otros sobre el simulador. Este va contra `interpreter.py`, que es el motor que
mueve el boton "Probar juego" del editor y el .exe de PC -- y que hasta ahora no
tenia ni una prueba automatica, justo el motor con el que el autor trabaja.

Corre el MISMO fichero .pru y lo juzga el MISMO `probar_juego.corre`, asi que
cualquier divergencia entre el motor de PC y el de Spectrum sale sola:

    python probar_pc.py juego.yaml bateria.pru [-v|-vv]

El gemelo del Z80 es probar_48.py (o probar_juego.py para el Next): mismo .pru,
mismas ordenes, mismo juez. Se pasan los dos y se comparan los fallos.

Nota sobre `pantalla()`: en el Z80 es la pantalla fisica, con lo que quedo de
turnos anteriores hasta que algo la borra. Aqui no hay pantalla, asi que es lo
que ha escrito el juego EN ESTE turno. Es mas estricto: una comprobacion que en
el Z80 pasa porque el texto seguia visible de antes, aqui falla. Eso no es un
fallo del arnes, es justo lo que interesa mirar.
"""
import io
import os
import queue
import sys
import time

import yaml

import player
import probar_juego as pj


class Sesion(player.GameSession):
    """La sesion del reproductor, con un aviso de "ya vuelvo a pedir orden".

    `GameSession` esta pensada para una ventana, que sondea la cola cuando le
    viene bien. Una bateria necesita saber EXACTAMENTE cuando ha terminado el
    turno, y adivinarlo por silencio es la receta de las pruebas intermitentes.
    Como el interprete pide orden con input(), basta con soltar una ficha justo
    antes de bloquearse: una ficha por turno, en orden, sin carreras.
    """

    def __init__(self, game):
        super().__init__(game)
        self._listo = queue.Queue()

    def _input(self, prompt=''):
        if prompt:
            self.out_queue.put(prompt)
        self._listo.put(True)              # "estoy esperando orden"
        linea = self._in_queue.get()
        if linea is None:
            raise EOFError
        return linea

    def espera_orden(self, tope=30.0):
        """True si el juego vuelve a pedir orden. False si se acabo la partida
        (el hilo muere) o si se colgo.

        Se espera a sorbos y mirando si el hilo sigue vivo: cuando la partida
        termina nadie va a soltar la ficha, y un `get(timeout=30)` a secas se
        comia 30 segundos enteros por cada END de la bateria."""
        limite = time.time() + tope
        while True:
            try:
                self._listo.get(timeout=0.05)
                return True
            except queue.Empty:
                pass
            if not self.alive:
                # el hilo puede haber soltado la ficha justo al morir
                try:
                    self._listo.get_nowait()
                    return True
                except queue.Empty:
                    return False
            if time.time() >= limite:
                return False


class JuegoPC(pj.Juego):
    maquina = 'pc'
    """Un juego jugandose en el interprete de Python, con la misma cara que
    `probar_juego.Juego` y `probar_48.Juego48`."""

    TOPE = 30.0            # segundos que se espera a que termine un turno

    def __init__(self, yaml_path, _tap=None):
        self.game = yaml.safe_load(io.open(yaml_path, encoding='utf-8'))
        locs = self.game.get('locations') or {}
        objs = self.game.get('objects') or {}
        self.info = {'localizaciones': len(locs), 'objetos': len(objs),
                     'imagenes': []}
        self.ses = None
        self._lineas = []
        self._acabado = False
        # GameSession se apropia de sys.stdout mientras juega (es su forma de
        # capturar lo que imprime el interprete), asi que cualquier cosa que
        # queramos ENSEÑAR tiene que ir a la consola de verdad, guardada aqui
        # antes de que empiece ninguna partida. `probar_juego.corre` ya se
        # protege sola: captura sys.stdout al entrar, antes del primer arranca.
        self.consola = sys.stdout

    # --- arranque -----------------------------------------------------------
    def arranca(self):
        """Partida nueva. `corre` llama a esto al empezar cada prueba, asi que
        hay que cerrar la anterior: `GameSession` se apropia de sys.stdout
        mientras juega y dos sesiones solapadas se pisarian la salida."""
        if self.ses is not None:
            self.ses.stop()
            hilo = getattr(self.ses, '_hilo', None)
            if hilo is not None:
                hilo.join(timeout=5.0)
        self.ses = Sesion(self.game)
        self._acabado = False
        self.ses.start()
        if not self.ses.espera_orden(self.TOPE):
            raise RuntimeError('el juego no llego a pedir orden al arrancar')
        self._lineas = self._recoge()
        return self

    def _recoge(self):
        texto = self.ses.read_output()
        return [l.rstrip() for l in texto.replace('\r', '').split('\n')
                if l.strip()]

    # --- jugar --------------------------------------------------------------
    def escribe(self, orden):
        """Teclea una orden. Usa el MISMO `tecleable` que el corredor del Z80:
        las dos baterias tienen que meter exactamente lo mismo por la ranura, o
        no se estan comparando dos motores sino dos entradas distintas."""
        texto = self.tecleable(orden)
        if not texto:
            raise ValueError('orden vacia o no tecleable: %r' % orden)
        if self._acabado:
            return self.pantalla()         # la partida ya termino; no hay turno
        self.ses.send(texto)
        vivo = self.ses.espera_orden(self.TOPE)
        lineas = self._recoge()
        if lineas:
            self._lineas = lineas
        if not vivo:
            if self.ses.alive:
                raise RuntimeError('se colgo escribiendo: %s' % orden)
            self._acabado = True           # fin de partida: el hilo se acabo
        return self.pantalla()

    def pantalla(self):
        return list(self._lineas)

    # --- estado -------------------------------------------------------------
    def donde(self):
        return self.ses.interp.player_location

    def var(self, nombre):
        """Misma normalizacion que el corredor del Z80: el .pru escribe
        U571DESTRUIDO y el juego declara _U571_DESTRUIDO."""
        clave = str(nombre).upper().replace('_', '')
        for k, v in self.ses.interp.variables.items():
            if str(k).upper().replace('_', '') == clave:
                return int(v)
        raise KeyError('el juego no tiene la variable %s' % nombre)

    def donde_obj(self, nombre):
        """Donde esta un objeto, con el vocabulario del .pru: una localizacion
        (@loc), INVEN, PUESTO, NADA o #contenedor. El interprete ya guarda la
        ubicacion en esa misma forma, asi que no hay nada que traducir."""
        k = str(nombre).upper()
        for oid, o in self.ses.interp.objects.items():
            if str(oid).upper() == k:
                return str(o.get('location'))
        raise KeyError('el juego no tiene el objeto %s' % nombre)

    def cierra(self):
        if self.ses is not None:
            self.ses.stop()
            hilo = getattr(self.ses, '_hilo', None)
            if hilo is not None:
                hilo.join(timeout=5.0)
            self.ses = None


def main():
    argv = sys.argv[1:]
    sueltos = [a for a in argv if not a.startswith('-')]
    if len(sueltos) < 2:
        sys.stdout.write(__doc__ + chr(10))
        sys.exit(2)
    nivel = 2 if '-vv' in argv else (1 if '-v' in argv else 0)
    juego = JuegoPC(sueltos[0])
    # A la consola de verdad: mientras hay partida, sys.stdout es la cola del
    # juego (ver JuegoPC.__init__).
    eco = juego.consola

    def di(txt=''):
        eco.write(txt + chr(10))
        eco.flush()

    di('juego      %s -> %d localizaciones, %d objetos'
       % (os.path.basename(sueltos[0]), juego.info['localizaciones'],
          juego.info['objetos']))
    di('motor      interpreter.py (el del editor y el .exe de PC)')
    di('bateria    %s' % os.path.basename(sueltos[1]))
    di()
    t0 = time.time()
    try:
        res = pj.corre(juego, sueltos[1], nivel, salida=eco)
    finally:
        juego.cierra()
    tardado = time.time() - t0

    fallos = [(n, d) for n, ok, d in res if ok is False]
    pruebas = sum(1 for _, ok, _ in res if ok is None)
    di()
    if not nivel:
        anterior = None
        for nombre, detalle in fallos:
            if nombre != anterior:
                di('=== %s' % nombre)
                anterior = nombre
            di('        FALLA %s' % detalle)
        if fallos:
            di()
    di('%d prueba(s), %s  (%.0fs)'
       % (pruebas, '%d fallo(s)' % len(fallos) if fallos else 'todo correcto',
          tardado))
    sys.exit(1 if fallos else 0)


if __name__ == '__main__':
    main()
