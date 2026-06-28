#!/usr/bin/env python3
"""
Scriba - interprete de aventuras conversacionales
Intérprete CLI para aventuras conversacionales en formato YAML (o JSON)

Uso:
  python interpreter.py ejemplo.yaml
  python interpreter.py ejemplo.json
"""

import json
import sys
import os
import argparse
import random
import re
import yaml
import textwrap
import paws_lang

# Direcciones válidas y sus opuestos
DIRECTIONS = {
    'N': 'N', 'NORTE': 'N', 'NORTH': 'N',
    'S': 'S', 'SUR': 'S', 'SOUTH': 'S',
    'E': 'E', 'ESTE': 'E', 'EAST': 'E',
    'O': 'O', 'OESTE': 'O', 'WEST': 'O', 'W': 'O',
    'U': 'U', 'ARRIBA': 'U', 'UP': 'U', 'SUBIR': 'U',
    'D': 'D', 'ABAJO': 'D', 'DOWN': 'D', 'BAJAR': 'D'
}

DIR_NAMES = {
    'N': 'Norte', 'S': 'Sur', 'E': 'Este',
    'O': 'Oeste', 'U': 'Arriba', 'D': 'Abajo'
}

# Nombres de dirección por idioma (para la lista "Salidas:").
DIR_NAMES_L = {
    'es': {'N': 'Norte', 'S': 'Sur', 'E': 'Este', 'O': 'Oeste', 'U': 'Arriba', 'D': 'Abajo'},
    'en': {'N': 'North', 'S': 'South', 'E': 'East', 'O': 'West', 'U': 'Up', 'D': 'Down'},
    'pt': {'N': 'Norte', 'S': 'Sul', 'E': 'Este', 'O': 'Oeste', 'U': 'Acima', 'D': 'Abaixo'},
}

# Mensajes del sistema del INTÉRPRETE de PC por idioma (es/en/pt). El idioma sale
# de metadata['language']; metadata['mensajes'][id] (catálogo compartido) tiene
# prioridad si existe, así una traducción personalizada del editor vale también en
# PC. Placeholders: {o} objeto, {p} puntos, {max} máximo, {c} contenido, {k} llave,
# {dirs} salidas.
MSGS = {
    'no_entiendo_ayuda': ("No entiendo eso. Escribe AYUDA para ver los comandos.",
                          "I don't understand that. Type HELP for the commands.",
                          "Não percebo isso. Escreve AJUDA para ver os comandos."),
    'no_hacer':       ("No puedes hacer eso.", "You can't do that.", "Não podes fazer isso."),
    'no_direccion':   ("No puedes ir en esa dirección.", "You can't go that way.", "Não podes ir nessa direção."),
    'pasa_tiempo':    ("Pasa el tiempo...", "Time passes...", "O tempo passa..."),
    'oscuro_total':   ("Está completamente oscuro. No puedes ver nada.",
                       "It's completely dark. You can't see anything.",
                       "Está completamente escuro. Não consegues ver nada."),
    'oscuro_ver':     ("Está demasiado oscuro para ver nada.", "It's too dark to see anything.", "Está escuro demais para ver."),
    'oscuro_hay':     ("Está demasiado oscuro para ver qué hay.", "It's too dark to see what's here.", "Está escuro demais para ver o que há."),
    'no_especial':    ("No ves nada especial.", "You see nothing special.", "Não vês nada de especial."),
    'no_ves_eso':     ("No ves eso aquí.", "You don't see that here.", "Não vês isso aqui."),
    'aqui_hay':       ("Aquí hay {o}.", "There is {o} here.", "Aqui está {o}."),
    'salidas':        ("Salidas: {dirs}", "Exits: {dirs}", "Saídas: {dirs}"),
    'sin_salidas':    ("No hay salidas visibles.", "There are no visible exits.", "Não há saídas visíveis."),
    'no_llevas_nada': ("No llevas nada.", "You aren't carrying anything.", "Não levas nada."),
    'llevas_cab':     ("Llevas:", "You are carrying:", "Levas:"),
    'contiene_inline':("(contiene: {c})", "(contains: {c})", "(contém: {c})"),
    'puesto_cab':     ("Llevas puesto:", "You are wearing:", "Vestes:"),
    'peso_inv':       ("Peso: {p}/{m}", "Weight: {p}/{m}", "Peso: {p}/{m}"),
    'ya_llevas':      ("Ya llevas {o}.", "You already have {o}.", "Já levas {o}."),
    'no_coger':       ("No puedes coger eso.", "You can't take that.", "Não podes apanhar isso."),
    'no_cabe_peso':   ("No puedes cargar tanto peso.", "You can't carry that much.", "Não podes carregar tanto peso."),
    'peso_max':       ("Llevas demasiado peso.", "You're carrying too much weight.", "Levas peso demais."),
    'coges':          ("Coges {o}.", "You take {o}.", "Apanhas {o}."),
    'nada_coger':     ("No ves nada que puedas coger aquí.", "You see nothing you can take here.", "Não vês nada que possas apanhar aqui."),
    'que_coger':      ("¿Qué quieres coger?", "What do you want to take?", "O que queres apanhar?"),
    'dejas':          ("Dejas {o}.", "You drop {o}.", "Largas {o}."),
    'nada_dejar':     ("No llevas nada que dejar.", "You have nothing to drop.", "Não levas nada para largar."),
    'que_dejar':      ("¿Qué quieres dejar?", "What do you want to drop?", "O que queres largar?"),
    'no_llevas_eso':  ("No llevas eso.", "You aren't carrying that.", "Não levas isso."),
    'contiene':       ("Contiene: {c}", "Contains: {c}", "Contém: {c}"),
    'vacio':          ("Está vacío.", "It's empty.", "Está vazio."),
    'que_poner':      ("¿Qué quieres ponerte?", "What do you want to wear?", "O que queres vestir?"),
    'no_inventario':  ("No llevas eso o no está en tu inventario.", "You don't have that in your inventory.", "Não tens isso no teu inventário."),
    'no_ponerte':     ("No puedes ponerte {o}.", "You can't wear {o}.", "Não podes vestir {o}."),
    'te_pones':       ("Te pones {o}.", "You put on {o}.", "Vestes {o}."),
    'que_quitar':     ("¿Qué quieres quitarte?", "What do you want to take off?", "O que queres tirar?"),
    'no_puesto':      ("No llevas puesto eso.", "You aren't wearing that.", "Não tens isso vestido."),
    'te_quitas':      ("Te quitas {o}.", "You take off {o}.", "Tiras {o}."),
    'que_abrir':      ("¿Qué quieres abrir?", "What do you want to open?", "O que queres abrir?"),
    'no_abrir':       ("No puedes abrir {o}.", "You can't open {o}.", "Não podes abrir {o}."),
    'ya_abierto':     ("Ya está abierto.", "It's already open.", "Já está aberto."),
    'abres_con':      ("Abres {o} con {k}.", "You open {o} with {k}.", "Abres {o} com {k}."),
    'cerrado_llave':  ("Está cerrado con llave.", "It's locked.", "Está trancado."),
    'abres':          ("Abres {o}.", "You open {o}.", "Abres {o}."),
    'dentro_hay':     ("Dentro hay: {c}.", "Inside there is: {c}.", "Lá dentro há: {c}."),
    'que_cerrar':     ("¿Qué quieres cerrar?", "What do you want to close?", "O que queres fechar?"),
    'no_cerrar':      ("No puedes cerrar {o}.", "You can't close {o}.", "Não podes fechar {o}."),
    'ya_cerrado':     ("Ya está cerrado.", "It's already closed.", "Já está fechado."),
    'cierras':        ("Cierras {o}.", "You close {o}.", "Fechas {o}."),
    'que_meter':      ("¿Qué quieres meter?", "What do you want to put?", "O que queres pôr?"),
    'donde_meter':    ("¿Dónde quieres meterlo?", "Where do you want to put it?", "Onde queres pô-lo?"),
    'primero_coger':  ("Primero tienes que coger {o}.", "You need to take {o} first.", "Primeiro tens de apanhar {o}."),
    'no_meter_si':    ("No puedes meter algo dentro de sí mismo.", "You can't put something inside itself.", "Não podes pôr algo dentro de si mesmo."),
    'no_contenedor_p':("No puedes meter nada en {o}.", "You can't put anything in {o}.", "Não podes pôr nada em {o}."),
    'cont_cerrado':   ("{o} está cerrado.", "{o} is closed.", "{o} está fechado."),
    'no_cabe':        ("No cabe en {o}.", "It doesn't fit in {o}.", "Não cabe em {o}."),
    'metes':          ("Metes {o} en {c}.", "You put {o} in {c}.", "Pões {o} em {c}."),
    'que_sacar':      ("¿Qué quieres sacar?", "What do you want to take out?", "O que queres tirar?"),
    'no_dentro':      ("No está en ningún contenedor.", "It's not in any container.", "Não está em nenhum recipiente."),
    'peso_sacar':     ("Llevarías demasiado peso.", "You'd be carrying too much.", "Ficarias com peso demais."),
    'sacas':          ("Sacas {o} de {c}.", "You take {o} out of {c}.", "Tiras {o} de {c}."),
    'puntos_mas':     ("[+{n} puntos]", "[+{n} points]", "[+{n} pontos]"),
    'puntuacion':     ("Puntuación: {p}/{max}", "Score: {p}/{max}", "Pontuação: {p}/{max}"),
    'fin_juego':      ("FIN DEL JUEGO - Puntuación: {p}/{max}", "GAME OVER - Score: {p}/{max}", "FIM DO JOGO - Pontuação: {p}/{max}"),
    'abandonar':      ("¿Seguro que quieres abandonar la aventura? (s/n)", "Are you sure you want to quit the adventure? (y/n)", "Tens a certeza que queres abandonar a aventura? (s/n)"),
    'hasta_luego':    ("¡Hasta luego!", "See you later!", "Até logo!"),
    'fin_aventura':   ("¡Hasta la próxima aventura!", "Until the next adventure!", "Até à próxima aventura!"),
}

# Verbos de dirección (completos y truncados a 5) → forma canónica corta.
# Se usa tanto al construir el vocabulario como al casar responses legacy.
DIR_VERB_CANON = {
    'NORTE': 'N', 'NORTH': 'N',
    'SUR': 'S', 'SOUTH': 'S',
    'ESTE': 'E', 'EAST': 'E',
    'OESTE': 'O', 'WEST': 'O',
    'ARRIBA': 'U', 'ARRIB': 'U', 'UP': 'U', 'SUBIR': 'U',
    'ABAJO': 'D', 'DOWN': 'D', 'BAJAR': 'D',
}



# ─── VOCABULARIO PREDEFINIDO (constantes de handle_builtin) ─────────────────
# Las claves se truncan a 5 letras para obtener el canonical que usa handle_builtin.
# Estos verbos se inyectan automáticamente en todos los juegos.

BUILTIN_VERBS = {
    'examinar':   ['examinar', 'mirar', 'ver', 'observar', 'ex'],
    'coger':      ['coger', 'tomar', 'agarrar', 'recoger'],
    'dejar':      ['dejar', 'soltar', 'depositar'],
    'poner':      ['ponerse', 'vestir', 'equipar'],       # canonical: PONER
    'quita':      ['quitarse', 'desvestir', 'quitar'],    # canonical: QUITA
    'meter':      ['meter', 'introducir', 'insertar'],
    'sacar':      ['sacar', 'extraer'],
    'inventario': ['inventario', 'inv', 'i'],             # canonical: INVEN
    'punt':       ['puntos', 'puntuacion', 'score'],      # canonical: PUNT
    'salir':      ['salir', 'abandonar', 'quit'],
    'abrir':      ['abrir', 'abre'],
    'cerrar':     ['cerrar', 'cierra'],                   # canonical: CERRA
}

BUILTIN_PREPS = {
    'en':     ['en', 'dentro', 'interior'],
    'con':    ['con'],
    'a':      ['a', 'al', 'hacia'],
    'de':     ['de', 'del', 'desde'],
    'sobre':  ['sobre', 'encima'],
    'bajo':   ['bajo', 'debajo'],
    'para':   ['para'],
    'entre':  ['entre'],
    'sin':    ['sin'],
}

# ─── LENGUAJE BASIC PARA CONDACTS ────────────────────────────────────────────

class PAWSBasic:
    """
    Intérprete del mini-lenguaje BASIC para condacts PAWS.

    Sintaxis:
        [num] REM comentario
        [num] IF condicion THEN
        [num]   comandos...
        [num] ELSE
        [num]   comandos...
        [num] ENDIF

    Condiciones: AT loc, NOTAT loc, CARRIED obj, NOTCARR obj, PRESENT obj,
                 ABSENT obj, WORN obj, ISAT obj loc, DARK, CHANCE pct,
                 TIMER id val, NOT <cond>
                 Expresiones: VAR=0, VAR>5, VAR!=0, VAR>=10, NOT(VAR=0)

    Comandos: PRINT "texto", LET var = expr, ADDSCORE n, GOTO loc,
              GET obj, DROP obj, CREATE obj loc, DESTROY obj,
              PUTIN obj contenedor, LIT obj, UNLIT obj,
              TIMER_START id, TIMER_STOP id, TIMER_RESET id,
              DESC, SCORE, END, QUIT
    """

    def __init__(self, interp):
        self.interp = interp
        self.lines = []
        self.pos = 0
        self._stop = False
        self._current_verb = None
        self._current_noun1 = None
        self._current_noun2 = None
        # Hook de debug: callable(line_text, condition_result=None) o None
        self.pre_exec_hook = None

    def run(self, script):
        """Ejecuta un script BASIC (string o lista de strings)."""
        if isinstance(script, list):
            raw = script
        else:
            raw = script.split('\n')

        self.lines = []
        for line in raw:
            line = line.strip()
            if not line:
                continue
            # Quitar número de línea opcional
            parts = line.split(None, 1)
            if parts[0].isdigit():
                code = parts[1].strip() if len(parts) > 1 else ''
            else:
                code = line
            if code:
                self.lines.append(code)

        self.pos = 0
        try:
            self._run_block()
        except Exception as e:
            # Un script malformado no debe tumbar la partida
            print(f"[Error en script BASIC: {e}]")

    # ── Ejecución de bloques ─────────────────────────────────────────────────

    def _run_block(self):
        """Ejecuta líneas hasta ELSE, ENDIF, ENDON o fin de script."""
        while self.pos < len(self.lines) and self.interp.running and not self._stop:
            line = self.lines[self.pos]
            upper = line.upper().strip()

            if upper in ('ENDIF', 'ELSE', 'ENDON'):
                return  # el padre leerá este token

            self.pos += 1

            if upper.startswith('REM'):
                if self.pre_exec_hook:
                    self.pre_exec_hook(line, None)
                continue
            elif upper.startswith('IF ') and ' THEN' in upper:
                then_idx = upper.rfind(' THEN')
                cond_str = line[3:then_idx].strip()
                cond_result = self._eval_condition(cond_str)
                if self.pre_exec_hook:
                    self.pre_exec_hook(line, cond_result)
                # ejecutar el bloque IF directamente ya evaluado
                if cond_result:
                    self._run_block()
                    if self.pos < len(self.lines):
                        upper2 = self.lines[self.pos].upper().strip()
                        self.pos += 1
                        if upper2 == 'ELSE':
                            self._skip_to_endif()
                else:
                    self._skip_to_else_or_endif()
                    if self.pos < len(self.lines):
                        upper2 = self.lines[self.pos].upper().strip()
                        self.pos += 1
                        if upper2 == 'ELSE':
                            self._run_block()
                            if self.pos < len(self.lines) and \
                               self.lines[self.pos].upper().strip() == 'ENDIF':
                                self.pos += 1
            elif upper.startswith('ON '):
                on_match = self._eval_on_match(line)
                if self.pre_exec_hook:
                    self.pre_exec_hook(line, on_match)
                self._execute_on(line)
            else:
                if self.pre_exec_hook:
                    self.pre_exec_hook(line, None)
                self._execute_statement(line)

    def _skip_to_else_or_endif(self):
        """Salta hasta ELSE o ENDIF al nivel actual (IFs anidados aumentan nivel)."""
        depth = 0
        while self.pos < len(self.lines):
            upper = self.lines[self.pos].upper().strip()
            if upper.startswith('IF ') and ' THEN' in upper:
                depth += 1
            elif upper == 'ENDIF':
                if depth == 0:
                    return
                depth -= 1
            elif upper == 'ELSE' and depth == 0:
                return
            self.pos += 1

    def _skip_to_endif(self):
        """Salta hasta el ENDIF de cierre (manejando IFs anidados)."""
        depth = 0
        while self.pos < len(self.lines):
            upper = self.lines[self.pos].upper().strip()
            if upper.startswith('IF ') and ' THEN' in upper:
                depth += 1
            elif upper == 'ENDIF':
                if depth == 0:
                    self.pos += 1
                    return
                depth -= 1
            self.pos += 1
    # ── ON / ENDON / MATCH ──────────────────────────────────────────────────

    def _eval_on_match(self, line):
        """¿El bloque ON casa con el verbo/nombres del turno? Cada hueco admite
        palabra, * (cualquiera), _ (ninguno) o alternativas (A OR B)."""
        rest = line.split(None, 1)
        rest = rest[1] if len(rest) > 1 else ''
        s = paws_lang.parse_on(rest)
        return (paws_lang.on_slot_matches(s[0], self._current_verb) and
                paws_lang.on_slot_matches(s[1], self._current_noun1) and
                paws_lang.on_slot_matches(s[2], self._current_noun2))

    def _execute_on(self, line):
        """
        Ejecuta un bloque ON verbo [nombre1 [nombre2]] ... ENDON.
        Cada hueco: palabra, * (cualquiera), _ (ninguno) o (A OR B) alternativas.
        MATCH dentro del bloque detiene el script (handled).
        """
        if self._eval_on_match(line):
            self._run_block()                    # ejecuta cuerpo hasta ENDON
            if self.pos < len(self.lines) and self.lines[self.pos].upper().strip() == 'ENDON':
                self.pos += 1                    # consume ENDON
        else:
            self._skip_to_endon()                # salta bloque

    def _skip_to_endon(self):
        """Salta hasta ENDON al nivel actual."""
        depth = 0
        while self.pos < len(self.lines):
            upper = self.lines[self.pos].upper().strip()
            if upper.startswith('ON '):
                depth += 1
            elif upper == 'ENDON':
                if depth == 0:
                    self.pos += 1
                    return
                depth -= 1
            self.pos += 1

    # ── Evaluación de condiciones ────────────────────────────────────────────

    # La gramática de condiciones y expresiones vive ahora en paws_lang
    # (parser único compartido con el compilador y el export al Spectrum).

    def _predicate(self, name, args):
        """Resuelve una condición-palabra-clave. VERB/NOUN1/NOUN2 acceden al
        estado del parser (verbo/nombres del turno); el resto se delega a
        interp.check_condition (AT, CARRIED, ISAT, DARK, CHANCE, TIMER...)."""
        if name == 'VERB':
            pattern = args[0].upper() if args else '*'
            return pattern == '*' or self._current_verb == pattern
        if name == 'NOUN1':
            pattern = args[0].upper() if args else '*'
            if pattern == '_':
                return self._current_noun1 is None
            return pattern == '*' or self._current_noun1 == pattern
        if name == 'NOUN2':
            pattern = args[0].upper() if args else '*'
            if pattern == '_':
                return self._current_noun2 is None
            return pattern == '*' or self._current_noun2 == pattern
        return self.interp.check_condition({"condition": name, "args": args})

    def _eval_condition(self, cond_str):
        """Evalúa una condición con el parser compartido (paws_lang):
        AND/OR/NOT, paréntesis, comparaciones con expresiones aritméticas
        completas y las condiciones-palabra-clave PAWS. Un error de sintaxis
        no tumba la partida (avisa y devuelve False)."""
        try:
            return paws_lang.eval_condition(
                paws_lang.parse_condition(cond_str),
                lambda n: self.interp.variables.get(n, 0),
                self._predicate)
        except paws_lang.ParseError as e:
            print(f"[Error de sintaxis en condición '{cond_str}': {e}]")
            return False

    # ── Evaluación de expresiones ────────────────────────────────────────────

    def _eval_expr(self, expr):
        """Evalúa una expresión aritmética con el parser compartido
        (paws_lang): números, variables, + - * / MOD, paréntesis y menos
        unario con precedencia correcta."""
        try:
            return paws_lang.eval_expr(
                paws_lang.parse_expr(expr),
                lambda n: self.interp.variables.get(n, 0))
        except paws_lang.ParseError as e:
            print(f"[Error de sintaxis en expresión '{expr}': {e}]")
            return 0

    def _extract_str(self, s):
        """Quita comillas de un string si las tiene."""
        s = s.strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
            return s[1:-1]
        return s

    def _format_str(self, s):
        """
        Extrae el string y sustituye {VARIABLE} por su valor.
        Ejemplo: PRINT "Llevas {TURNOS} turnos y {PUNTOS} puntos"
        """
        text = self._extract_str(s)
        def replace(m):
            name = m.group(1)
            return str(self.interp.variables.get(name, 0))
        return re.sub(r'\{([A-Z_][A-Z0-9_]*)\}', replace, text)

    # ── Ejecución de comandos ────────────────────────────────────────────────

    def _execute_statement(self, line):
        """Ejecuta un comando BASIC."""
        interp = self.interp
        parts = line.strip().split(None, 1)
        if not parts:
            return
        cmd = parts[0].upper()
        rest = parts[1].strip() if len(parts) > 1 else ''

        if cmd in ('PRINT', 'PRINTLN'):
            msg = self._format_str(rest)
            if '\n' in msg:
                print(msg)
            else:
                print(textwrap.fill(msg, width=76))

        elif cmd == 'LET':
            if '=' in rest:
                lhs, rhs = rest.split('=', 1)
                interp.variables[lhs.strip()] = self._eval_expr(rhs)

        elif cmd == 'ADDSCORE':
            try:
                n = int(rest.strip())
                interp.variables['PUNTOS'] = interp.variables.get('PUNTOS', 0) + n
                print(self.interp._t('puntos_mas', n=n))
            except ValueError:
                pass

        elif cmd == 'GOTO':
            # Por diseño NO describe la localización (los juegos existentes
            # hacen GOTO + DESC explícito). Usa DESC para mostrarla.
            loc_id = rest.strip()
            if loc_id in interp.locations:
                interp.player_location = loc_id
                interp.execute_condact_blocks(
                    interp.locations[loc_id].get('on_enter', []))

        elif cmd == 'DESC':
            interp.describe_location()

        elif cmd == 'SCORE':
            interp.execute_action({"action": "SCORE", "args": []})

        elif cmd == 'END':
            interp.execute_action({"action": "END", "args": []})

        elif cmd == 'MATCH':
            self._stop = True          # respuesta manejada, no seguir ON blocks

        elif cmd == 'QUIT':
            interp.running = False

        elif cmd == 'NEWLINE':
            print()

        elif cmd in ('BEEP', 'BORDER', 'PAUSE', 'INK', 'PAPER', 'BRIGHT',
                     'FLASH', 'INVERSE', 'CLS'):
            pass   # comandos ZX BASIC literales: solo en la exportacion a Spectrum

        elif cmd == 'PLAY':
            interp.play_fx(rest.strip())   # efecto de sonido (FX)

        elif cmd in ('GET', 'DROP', 'LIT', 'UNLIT', 'OPEN', 'CLOSE',
                     'LOCK', 'UNLOCK', 'DESTROY', 'WEAR', 'REMOVE'):
            interp.execute_action({"action": cmd, "args": [rest.strip()]})

        elif cmd in ('TIMER_START', 'TIMER_STOP', 'TIMER_RESET'):
            interp.execute_action({"action": cmd, "args": [rest.strip()]})

        elif cmd in ('CREATE', 'PUTIN', 'TAKEOUT', 'PUT'):
            args = rest.split()
            interp.execute_action({"action": cmd, "args": args[:2]})

        else:
            # Antes se ignoraba en silencio; avisar ayuda a depurar el juego
            print(f"[BASIC: comando desconocido '{cmd}']")

class PAWSInterpreter:
    def play_fx(self, n):
        """Reproduce el efecto de sonido referenciado por PLAY (nombre entre
        comillas o número, 1-based) como vista previa (WAV). En Windows suena; en
        otros sistemas o sin audio, se ignora en silencio."""
        fx = self.game.get('fx') or []
        try:
            import fx_engine
            idx = fx_engine.fx_index(fx, n) - 1
        except Exception:
            try:
                idx = int(n) - 1
            except (TypeError, ValueError):
                return
        if not (0 <= idx < len(fx)):
            return
        try:
            import winsound
            e = fx[idx]
            if e.get('afx'):
                import afx as _afx
                data = _afx.render_wav(_afx.parse_afx(bytes.fromhex(e['afx'])))
            else:
                import fx_engine
                data = fx_engine.wav_bytes(e)
            winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
        except Exception:
            pass

    def _t(self, mid, **subs):
        """Mensaje de sistema localizado. Prioridad: override del autor
        (metadata['mensajes'][mid], catálogo compartido) > tabla del idioma del
        juego (MSGS) > español. Sustituye los placeholders {x} por subs."""
        ov = (self.meta.get('mensajes') or {})
        txt = ov.get(mid)
        if not txt:
            row = MSGS.get(mid)
            if row:
                idx = {'en': 1, 'pt': 2}.get(self._lang, 0)
                txt = row[idx] if idx < len(row) else row[0]
            else:
                txt = ''
        txt = str(txt)
        if '{max}' in txt:
            txt = txt.replace('{max}', str(self.meta.get('max_score', 0) or 0))
        for k, v in subs.items():
            txt = txt.replace('{' + k + '}', str(v))
        return txt

    def _dir_name(self, d):
        """Nombre de la dirección 'd' (N/S/E/O/U/D) en el idioma del juego."""
        return DIR_NAMES_L.get(self._lang, DIR_NAMES_L['es']).get(d, d)

    def __init__(self, game: dict):
        self.game = game
        self.meta = game.get("metadata", {})
        _lng = str(self.meta.get('language') or 'es').strip().lower()
        self._lang = ('pt' if _lng.startswith(('pt', 'por'))
                      else 'en' if _lng.startswith('en') else 'es')
        self.variables = dict(game.get("variables", {}))
        self.locations = game.get("locations", {})
        self.objects = {}
        self.timers = {}
        self.vocab_lookup = {}  # siempre se reconstruye desde el juego
        self.responses = game.get("responses", {}).get("entries", [])
        self.condacts = game.get("condacts", {})

        # Estado del juego
        self.player_location = self.meta.get("start_location", "")
        self.running = True
        self.turns = 0
        self.last_command = ""

        # Copiar objetos con estado mutable
        for obj_id, obj_data in game.get("objects", {}).items():
            self.objects[obj_id] = dict(obj_data)

        # Copiar timers con estado mutable
        for tim_id, tim_data in game.get("timers", {}).items():
            self.timers[tim_id] = dict(tim_data)

        # Localización original de cada objeto: initial_message solo se
        # muestra mientras el objeto siga donde lo dejó el autor.
        self._initial_locs = {oid: o.get("location")
                              for oid, o in self.objects.items()}

        # Reconstruir vocab_lookup si no viene compilado
        if not self.vocab_lookup:
            self._build_vocab_lookup()

        # Sincronizar PESO_ACT con el inventario inicial real
        self.recalc_weight()

    def _build_vocab_lookup(self):
        """Construye tabla de vocabulario desde la definición del juego."""
        vocab = self.game.get("vocabulary", {})
        self.vocab_lookup = {}

        # Vocabulario de SERIE desde vocab_base (idioma del juego + overrides del
        # autor en metadata['vocab_base']). Fuente única compartida con el motor
        # retro. El vocabulario del juego se carga DESPUÉS y puede sobreescribirlo.
        import vocab_base
        meta = self.game.get('metadata') or {}
        _lang = meta.get('language')
        _ov = meta.get('vocab_base') or {}
        vb_verbs = vocab_base.verbs(_lang, _ov)
        vb_dirs = vocab_base.dirs(_lang, _ov)
        vb_preps = vocab_base.preps(_lang, _ov)

        for canonical, syns in vb_verbs.items():
            for alias in syns:
                self.vocab_lookup[alias[:5].upper()] = ("VERB", canonical)
            self.vocab_lookup[canonical] = ("VERB", canonical)
        for canonical, syns in vb_preps.items():
            for alias in syns:
                self.vocab_lookup[alias[:5].upper()] = ("PREP", canonical)
            self.vocab_lookup[canonical] = ("PREP", canonical)
        # Direcciones de serie como verbos (N/S/E/O/U/D) + mapa palabra->canónico.
        dir_verb_map = {}
        for canonical, syns in vb_dirs.items():
            self.vocab_lookup[canonical] = ("VERB", canonical)
            for alias in syns:
                w5 = alias[:5].upper()
                self.vocab_lookup[w5] = ("VERB", canonical)
                dir_verb_map[w5] = canonical
        self._dir_words = dict(dir_verb_map)

        # Palabra especial TODO ("COGER TODO") — integrada en el intérprete.
        # El vocabulario del juego se carga después y puede redefinirla.
        for alias in ('todo', 'all'):
            self.vocab_lookup[alias[:5].upper()] = ("NOUN", "TODO")

        for verb_key, aliases in vocab.get("verbs", {}).items():
            raw_canonical = verb_key[:5].upper()
            # Si es un verbo de dirección, normalizar a forma corta
            canonical = dir_verb_map.get(verb_key.upper(), dir_verb_map.get(raw_canonical, raw_canonical))
            for alias in aliases:
                w5 = alias[:5].upper()
                # También normalizar alias de dirección
                mapped = dir_verb_map.get(w5)
                self.vocab_lookup[w5] = ("VERB", mapped if mapped else canonical)
            # El propio key
            self.vocab_lookup[raw_canonical] = ("VERB", canonical)

        for noun_key, aliases in vocab.get("nouns", {}).items():
            canonical = noun_key[:5].upper()
            for alias in aliases:
                self.vocab_lookup[alias[:5].upper()] = ("NOUN", canonical)
            self.vocab_lookup[canonical] = ("NOUN", canonical)

        for prep_key, aliases in vocab.get("prepositions", {}).items():
            canonical = prep_key[:5].upper()
            for alias in aliases:
                self.vocab_lookup[alias[:5].upper()] = ("PREP", canonical)
            self.vocab_lookup[canonical] = ("PREP", canonical)

    # ─── PARSER ──────────────────────────────────────────────────────────────

    def parse(self, text: str) -> tuple:
        """
        Parsea la entrada del jugador.
        Devuelve (verb, noun1, noun2) en forma canónica de 5 letras,
        o None si no se reconoce.
        """
        words = text.strip().upper().split()
        if not words:
            return None, None, None

        verb = None
        noun1 = None
        noun2 = None
        nouns_before = []   # sustantivos antes de la primera preposición
        nouns_after = []    # sustantivos después de la primera preposición
        prep_seen = False

        for word in words:
            w5 = word[:5]
            entry = self.vocab_lookup.get(w5)
            if not entry and len(w5) >= 3:
                # Coincidencia parcial solo por prefijo y con un mínimo de
                # 3 letras (evita falsos positivos con palabras muy cortas).
                # Determinista: se prefiere la clave más corta y, a igualdad,
                # la primera por orden alfabético (no el orden del dict).
                candidates = [(key, val) for key, val in self.vocab_lookup.items()
                              if key.startswith(w5)]
                if candidates:
                    candidates.sort(key=lambda kv: (len(kv[0]), kv[0]))
                    entry = candidates[0][1]

            if entry:
                tipo, canonical = entry
                if tipo == "VERB" and verb is None:
                    verb = canonical
                elif tipo == "NOUN":
                    (nouns_after if prep_seen else nouns_before).append(canonical)
                elif tipo == "PREP":
                    # Las preposiciones separan noun1 de noun2
                    prep_seen = True

        # Dirección como verbo (primer término): según el vocabulario del idioma.
        dir_key = words[0][:5]
        if dir_key in getattr(self, '_dir_words', {}):
            verb = self._dir_words[dir_key]

        nouns_found = nouns_before + nouns_after
        if nouns_found:
            noun1 = nouns_found[0]
        if nouns_before and nouns_after:
            noun2 = nouns_after[0]
        elif len(nouns_found) > 1:
            noun2 = nouns_found[1]

        return verb, noun1, noun2

    # ─── OBJETOS ─────────────────────────────────────────────────────────────

    def get_objects_at(self, location: str) -> list:
        """Objetos en una localización."""
        return [oid for oid, obj in self.objects.items()
                if obj.get("location") == location]

    def get_inventory(self) -> list:
        """Objetos en el inventario del jugador."""
        return [oid for oid, obj in self.objects.items()
                if obj.get("location") == "INVEN"]

    def get_worn_objects(self) -> list:
        """Objetos puestos."""
        return [oid for oid, obj in self.objects.items()
                if obj.get("location") == "PUESTO" or obj.get("worn", False)]

    def resolve_obj(self, arg: str) -> str:
        """Resuelve un argumento de condact a un ID de objeto.
        Intenta primero como ID directo; si no existe, busca por noun (primeras 5 letras)."""
        if arg in self.objects:
            return arg
        return self.find_object_by_noun(arg, accessible_only=False) or arg

    def find_object_by_noun(self, noun5: str, accessible_only: bool = True) -> str:
        """Busca el ID de objeto por su noun canónico. Prioriza inventario/sala."""
        candidates = []
        for oid, obj in self.objects.items():
            if obj.get("noun", "")[:5].upper() == noun5[:5].upper():
                loc = obj.get("location", "NADA")
                if not accessible_only:
                    candidates.append((oid, loc))
                elif loc in ("INVEN", "PUESTO") or loc == self.player_location:
                    candidates.append((oid, loc))
                else:
                    # Buscar en contenedores accesibles
                    for container_id in self.get_inventory() + self.get_objects_at(self.player_location):
                        cont_obj = self.objects.get(container_id, {})
                        if cont_obj.get("container") and cont_obj.get("open") and loc == container_id:
                            candidates.append((oid, loc))
                            break

        if not candidates:
            return None
        # Priorizar inventario
        for oid, loc in candidates:
            if loc in ("INVEN", "PUESTO"):
                return oid
        return candidates[0][0]

    def get_object_weight(self, obj_id: str, _visited=None) -> int:
        """Peso de un objeto, sumando los objetos contenidos.
        Protegido contra ciclos de contención (A dentro de B dentro de A)."""
        if _visited is None:
            _visited = set()
        if obj_id in _visited:
            return 0
        _visited.add(obj_id)
        obj = self.objects.get(obj_id, {})
        weight = obj.get("weight", 0)
        if obj.get("container"):
            for oid, o in self.objects.items():
                if o.get("location") == obj_id:
                    weight += self.get_object_weight(oid, _visited)
        return weight

    def recalc_weight(self) -> int:
        """
        Recalcula PESO_ACT a partir del estado real del inventario y de los
        objetos puestos (incluyendo el contenido de contenedores). Sustituye
        a la contabilidad incremental, que se descuadraba con CREATE/DESTROY/
        PUT de objetos llevados.
        """
        carried = set(self.get_inventory()) | set(self.get_worn_objects())
        total = sum(self.get_object_weight(oid) for oid in carried)
        self.variables["PESO_ACT"] = total
        return total

    def has_light(self) -> bool:
        """¿Hay fuente de luz activa accesible? Cuentan las que lleva el
        jugador y también las encendidas presentes en la sala."""
        accessible = (self.get_inventory() + self.get_worn_objects()
                      + self.get_objects_at(self.player_location))
        for oid in accessible:
            obj = self.objects.get(oid, {})
            if obj.get("light_source") and obj.get("lit"):
                return True
        return False

    def location_is_dark(self) -> bool:
        """¿La localización actual está oscura?"""
        loc = self.locations.get(self.player_location, {})
        return loc.get("dark", False) and not self.has_light()

    # ─── CONDICIONES ─────────────────────────────────────────────────────────

    def check_condition(self, cond: dict) -> bool:
        """Evalúa una condición. Nunca propaga excepciones: un script con
        datos malos (args que faltan, no numéricos...) avisa y devuelve False
        en lugar de tumbar la partida."""
        try:
            return self._check_condition(cond)
        except Exception as e:
            print(f"[Error en condición {cond.get('condition', '?')} "
                  f"{cond.get('args', [])}: {e}]")
            return False

    def _check_condition(self, cond: dict) -> bool:
        condition = cond.get("condition", "")
        args = cond.get("args", [])

        if condition == "AT":
            return self.player_location == args[0]
        elif condition == "NOTAT":
            return self.player_location != args[0]
        elif condition == "PRESENT":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            loc = obj.get("location", "NADA")
            return loc in ("INVEN", "PUESTO") or loc == self.player_location
        elif condition == "ABSENT":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            loc = obj.get("location", "NADA")
            return loc not in ("INVEN", "PUESTO") and loc != self.player_location
        elif condition == "CARRIED":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            return obj.get("location", "") in ("INVEN", "PUESTO")
        elif condition == "NOTCARR":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            return obj.get("location", "") not in ("INVEN", "PUESTO")
        elif condition == "WORN":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            return obj.get("location") == "PUESTO" or obj.get("worn", False)
        elif condition == "NOTWORN":
            return not self.check_condition({"condition": "WORN", "args": args})
        elif condition == "ISAT":
            # args[1] puede ser una localización, un id de objeto (contenedor)
            # o un noun de objeto. Las localizaciones tienen prioridad.
            obj_id = self.resolve_obj(args[0])
            target = args[1] if args[1] in self.locations else self.resolve_obj(args[1])
            obj = self.objects.get(obj_id, {})
            return obj.get("location") == target
        elif condition == "ZERO":
            return self.variables.get(args[0], 0) == 0
        elif condition == "NOTZERO":
            return self.variables.get(args[0], 0) != 0
        elif condition == "EQ":
            return self.variables.get(args[0], 0) == int(args[1])
        elif condition == "GT":
            return self.variables.get(args[0], 0) > int(args[1])
        elif condition == "LT":
            return self.variables.get(args[0], 0) < int(args[1])
        elif condition == "CHANCE":
            return random.randint(1, 100) <= int(args[0])
        elif condition == "DARK":
            return self.location_is_dark()
        elif condition == "HASOBJOPEN":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            return obj.get("open", False)
        elif condition == "TIMER":
            tim_id, val = args[0], int(args[1])
            timer = self.timers.get(tim_id, {})
            return timer.get("current", 0) == val
        return True

    # Estas se usan desde PAWSBasic._eval_condition via check_condition
    # (VERB/NOUN1/NOUN2 se delegan aquí para acceder al estado del intérprete)

    def check_conditions(self, conditions: list) -> bool:
        return all(self.check_condition(c) for c in conditions)

    # ─── ACCIONES ────────────────────────────────────────────────────────────

    def execute_action(self, action_def: dict):
        """Ejecuta una acción. Las excepciones de scripts defectuosos se
        notifican sin interrumpir la partida."""
        try:
            self._execute_action(action_def)
        except Exception as e:
            print(f"[Error en acción {action_def.get('action', '?')} "
                  f"{action_def.get('args', [])}: {e}]")

    def _execute_action(self, action_def: dict):
        action = action_def.get("action", "")
        args = action_def.get("args", [])

        if action == "PRINTLN":
            msg = args[0] if args else ""
            msg = self.format_message(msg)
            print(textwrap.fill(msg, width=76) if '\n' not in msg else msg)

        elif action == "PRINT":
            msg = args[0] if args else ""
            print(self.format_message(msg), end="")

        elif action == "NEWLINE":
            print()

        elif action == "GOTO":
            loc_id = args[0]
            if loc_id in self.locations:
                self.player_location = loc_id
                dest_loc = self.locations.get(loc_id, {})
                self.execute_condact_blocks(dest_loc.get("on_enter", []))
            else:
                print(f"[Error GOTO: loc '{loc_id}' no existe]")

        elif action == "GET":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            if obj and obj.get("location") not in ("INVEN", "PUESTO"):
                if "fixed" in obj.get("attributes", []):
                    print(self._t('no_coger'))
                else:
                    new_weight = self.recalc_weight() + self.get_object_weight(obj_id)
                    max_w = self.variables.get("LLEVAR_MAX", 50)
                    if new_weight > max_w:
                        print(self._t('peso_max'))
                    else:
                        obj["location"] = "INVEN"
                        self.recalc_weight()

        elif action == "DROP":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            if obj:
                obj["location"] = self.player_location
                obj["worn"] = False
                self.recalc_weight()

        elif action == "WEAR":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            if obj and obj.get("wearable"):
                obj["location"] = "PUESTO"
                obj["worn"] = True

        elif action == "REMOVE":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            if obj:
                obj["location"] = "INVEN"
                obj["worn"] = False

        elif action == "PUT":
            obj_id = self.resolve_obj(args[0])
            loc_id = args[1]
            obj = self.objects.get(obj_id, {})
            if obj:
                obj["location"] = loc_id
                obj["worn"] = False
                self.recalc_weight()

        elif action == "PUTIN":
            obj_id       = self.resolve_obj(args[0])
            container_id = self.resolve_obj(args[1])
            obj = self.objects.get(obj_id, {})
            container = self.objects.get(container_id, {})
            if obj and container:
                obj["location"] = container_id
                obj["worn"] = False
                self.recalc_weight()

        elif action == "TAKEOUT":
            obj_id       = self.resolve_obj(args[0])
            container_id = self.resolve_obj(args[1]) if len(args) > 1 else None
            obj = self.objects.get(obj_id, {})
            # Si se indica contenedor, el objeto debe estar realmente dentro
            if obj and (container_id is None or obj.get("location") == container_id):
                obj["location"] = "INVEN"
                self.recalc_weight()

        elif action == "DESTROY":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            if obj:
                obj["location"] = "NADA"
                obj["worn"] = False
                self.recalc_weight()

        elif action == "CREATE":
            obj_id, loc_id = args[0], args[1]
            obj = self.objects.get(obj_id, {})
            if obj:
                obj["location"] = loc_id
                self.recalc_weight()

        elif action == "SET":
            self.variables[args[0]] = int(args[1])

        elif action == "ADD":
            self.variables[args[0]] = self.variables.get(args[0], 0) + int(args[1])

        elif action == "SUB":
            self.variables[args[0]] = self.variables.get(args[0], 0) - int(args[1])

        elif action == "ADDSCORE":
            self.variables["PUNTOS"] = self.variables.get("PUNTOS", 0) + int(args[0])
            print(self._t('puntos_mas', n=args[0]))

        elif action == "SCORE":
            pts = self.variables.get("PUNTOS", 0)
            max_pts = self.meta.get("max_score", 0)
            print(self._t('puntuacion', p=pts))

        elif action == "DESC":
            self.describe_location()

        elif action == "LOOK":
            self.describe_location()

        elif action == "INVEN":
            self.show_inventory()

        elif action == "OPEN":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            if obj:
                obj["open"] = True
                obj["locked"] = False

        elif action == "CLOSE":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            if obj:
                obj["open"] = False

        elif action == "LOCK":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            if obj:
                obj["locked"] = True

        elif action == "UNLOCK":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            if obj:
                obj["locked"] = False

        elif action == "LIT":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            if obj:
                obj["lit"] = True
                obj["light_source"] = True

        elif action == "UNLIT":
            obj_id = self.resolve_obj(args[0])
            obj = self.objects.get(obj_id, {})
            if obj:
                obj["lit"] = False

        elif action == "TIMER_START":
            tim_id = args[0]
            timer = self.timers.get(tim_id, {})
            if timer:
                timer["active"] = True
                timer["current"] = timer.get("turns", 10)

        elif action == "TIMER_STOP":
            tim_id = args[0]
            timer = self.timers.get(tim_id, {})
            if timer:
                timer["active"] = False

        elif action == "TIMER_RESET":
            tim_id = args[0]
            timer = self.timers.get(tim_id, {})
            if timer:
                timer["current"] = timer.get("turns", 10)

        elif action == "END":
            pts = self.variables.get("PUNTOS", 0)
            max_pts = self.meta.get("max_score", 0)
            print(f"\n{'='*50}")
            print(self._t('fin_juego', p=pts))
            print(f"{'='*50}")
            self.running = False

        elif action == "QUIT":
            self.running = False

        elif action == "WAIT":
            print(self._t('pasa_tiempo'))

        elif action == "IF_NOT":
            cond = action_def.get("condition", {})
            if not self.check_condition(cond):
                for a in action_def.get("then", []):
                    self.execute_action(a)
            else:
                for a in action_def.get("else", []):
                    self.execute_action(a)

        elif action == "IF":
            cond = action_def.get("condition", {})
            if self.check_condition(cond):
                for a in action_def.get("then", []):
                    self.execute_action(a)
            else:
                for a in action_def.get("else", []):
                    self.execute_action(a)

    def execute_actions(self, actions: list):
        for action_def in actions:
            if not self.running:
                break
            self.execute_action(action_def)


    def execute_condact_blocks(self, script):
        """
        Ejecuta condacts en formato BASIC (str o lista de str)
        o en formato JSON legacy (lista de bloques {conditions, actions}).
        """
        if not script:
            return
        if isinstance(script, str):
            PAWSBasic(self).run(script)
        elif isinstance(script, list):
            if script and isinstance(script[0], str):
                PAWSBasic(self).run('\n'.join(script))
            else:
                # Formato JSON legacy: lista de bloques {conditions, actions}
                # o lista de acciones directas {action, args}
                for block in script:
                    if not self.running:
                        break
                    if "action" in block:
                        self.execute_action(block)
                    elif self.check_conditions(block.get("conditions", [])):
                        self.execute_actions(block.get("actions", []))
    def format_message(self, msg: str) -> str:
        """Sustituye placeholders en mensajes."""
        # {obj_description:obj_id}
        import re
        def replace_obj_desc(m):
            obj_id = m.group(1)
            obj = self.objects.get(obj_id, {})
            return obj.get("description", f"[{obj_id}]")

        msg = re.sub(r'\{obj_description:(\w+)\}', replace_obj_desc, msg)
        msg = re.sub(r'\{var:(\w+)\}', lambda m: str(self.variables.get(m.group(1), 0)), msg)
        return msg

    # ─── MOVIMIENTO ──────────────────────────────────────────────────────────

    def move_player(self, direction: str):
        """Mueve al jugador en la dirección indicada."""
        loc = self.locations.get(self.player_location, {})
        exits = loc.get("exits", {})

        # Normalizar dirección
        dir_canon = DIRECTIONS.get(direction.upper(), direction.upper())

        dest = exits.get(dir_canon)
        if not dest:
            print(self._t('no_direccion'))
            return

        self.player_location = dest
        self.describe_location()

        # Ejecutar on_enter
        dest_loc = self.locations.get(dest, {})
        on_enter = dest_loc.get("on_enter", [])
        self.execute_condact_blocks(on_enter)

    # ─── DESCRIBIR ───────────────────────────────────────────────────────────

    def describe_location(self):
        loc = self.locations.get(self.player_location, {})
        if not loc:
            print("[Error: localización no encontrada]")
            return

        print(f"\n{loc.get('name', 'Lugar desconocido')}")

        if self.location_is_dark():
            print(self._t('oscuro_total'))
            return

        desc = loc.get("description", "")
        print(textwrap.fill(desc, width=70))

        # Objetos en la sala
        room_objects = self.get_objects_at(self.player_location)
        visible_obj_msgs = []
        for oid in room_objects:
            obj = self.objects.get(oid, {})
            if "fixed" in obj.get("attributes", []):
                # Objetos fijos (escenario, PNJ): se listan solo si el autor
                # definió initial_message. Sin él se asume que la descripción
                # de la sala ya los menciona. Antes se ocultaban SIEMPRE, y
                # PNJ como el pescador o el troll eran invisibles al mirar.
                if obj.get("initial_message"):
                    visible_obj_msgs.append(obj["initial_message"])
            else:
                # initial_message solo mientras el objeto esté donde lo puso
                # el autor; si ya se movió, mensaje genérico (estilo PAW)
                if obj.get("initial_message") and \
                   obj.get("location") == self._initial_locs.get(oid):
                    msg = obj["initial_message"]
                else:
                    msg = self._t('aqui_hay', o=obj.get('name', oid))
                visible_obj_msgs.append(msg)
        if visible_obj_msgs:
            print()
            for msg in visible_obj_msgs:
                print(textwrap.fill(msg, width=70))

        # Salidas
        exits = loc.get("exits", {})
        available = [self._dir_name(d) for d, dest in exits.items() if dest]
        if available:
            print("\n" + self._t('salidas', dirs=', '.join(available)))
        else:
            print("\n" + self._t('sin_salidas'))

    def show_inventory(self):
        inventory = self.get_inventory()
        worn = self.get_worn_objects()

        if not inventory and not worn:
            print(self._t('no_llevas_nada'))
            return

        print(self._t('llevas_cab'))
        for oid in inventory:
            obj = self.objects.get(oid, {})
            line = f"  - {obj.get('name', oid)}"
            # Ver si el objeto contiene algo
            contents = [self.objects[cid].get("name", cid)
                       for cid, co in self.objects.items()
                       if co.get("location") == oid]
            if contents:
                line += " " + self._t('contiene_inline', c=', '.join(contents))
            print(line)

        if worn:
            print(self._t('puesto_cab'))
            for oid in worn:
                obj = self.objects.get(oid, {})
                print(f"  - {obj.get('name', oid)}")

        peso = self.variables.get("PESO_ACT", 0)
        max_peso = self.variables.get("LLEVAR_MAX", 50)
        print(self._t('peso_inv', p=peso, m=max_peso))

    # ─── TIMERS ──────────────────────────────────────────────────────────────

    def tick_timers(self):
        for tim_id, timer in self.timers.items():
            if not timer.get("active"):
                continue
            timer["current"] = timer.get("current", 0) - 1
            if timer["current"] <= 0:
                # Timer expirado
                self.execute_condact_blocks(timer.get("on_expire", []))
                if timer.get("loop"):
                    timer["current"] = timer.get("turns", 10)
                else:
                    timer["active"] = False

    # ─── RESPUESTAS ──────────────────────────────────────────────────────────

    def find_response(self, verb: str, noun1: str, noun2: str) -> bool:
        """Busca y ejecuta la primera respuesta que coincida. Devuelve True si encontró."""
        matched = False
        for entry in self.responses:
            ev = entry.get("verb", "_")[:5].upper() if entry.get("verb","_") not in ("*","_") else entry.get("verb","_")
            # Normalizar verbos de dirección (el parser canoniza NORTE → N)
            ev = DIR_VERB_CANON.get(ev, ev)
            en1 = entry.get("noun1", "*")[:5].upper() if entry.get("noun1","*") not in ("*","_") else entry.get("noun1","*")
            en2 = entry.get("noun2", "*")[:5].upper() if entry.get("noun2","*") not in ("*","_") else entry.get("noun2","*")

            # Comparar verbo
            if ev != "*" and ev != verb:
                continue

            # Comparar noun1
            if en1 != "*":
                if en1 == "_" and noun1 is not None:
                    continue
                if en1 != "_" and en1 != noun1:
                    continue

            # Comparar noun2
            if en2 != "*":
                if en2 == "_" and noun2 is not None:
                    continue
                if en2 != "_" and en2 != noun2:
                    continue

            # Verificar condiciones
            if not self.check_conditions(entry.get("conditions", [])):
                continue

            # Ejecutar acciones
            self.execute_actions(entry.get("actions", []))
            if entry.get("message"):
                print(self.format_message(entry["message"]))
            matched = True
            break  # Primera coincidencia

        return matched

    # ─── COMANDOS BUILT-IN ───────────────────────────────────────────────────

    def _builtin_take(self, obj_id: str):
        """Lógica COGER del intérprete para un objeto ya resuelto."""
        obj = self.objects.get(obj_id, {})
        if obj.get("location") in ("INVEN", "PUESTO"):
            print(self._t('ya_llevas', o=obj.get('name', obj_id)))
            return
        if "fixed" in obj.get("attributes", []):
            print(self._t('no_coger'))
            return
        new_w = self.recalc_weight() + self.get_object_weight(obj_id)
        max_w = self.variables.get("LLEVAR_MAX", 50)
        if new_w > max_w:
            print(self._t('no_cabe_peso'))
            return
        obj["location"] = "INVEN"
        self.recalc_weight()
        print(self._t('coges', o=obj.get('name', obj_id)))

    def take_all(self):
        """
        COGER TODO: intenta coger cada objeto no fijo de la sala. Cada
        objeto pasa por el pipeline normal (responses BASIC → legacy →
        builtin) para respetar los puntos, flags y bloqueos del juego
        (p. ej. un GET con ADDSCORE en un bloque ON COGER).
        """
        if self.location_is_dark():
            print(self._t('oscuro_hay'))
            return
        # Candidatos: objetos sueltos en la sala + contenido de los
        # contenedores ABIERTOS presentes en la sala
        holders = {self.player_location}
        for cid, c in self.objects.items():
            if (c.get("location") == self.player_location
                    and c.get("container") and c.get("open")):
                holders.add(cid)
        oids = [oid for oid, o in self.objects.items()
                if o.get("location") in holders
                and "fixed" not in o.get("attributes", [])]
        if not oids:
            print(self._t('nada_coger'))
            return
        for oid in oids:
            if not self.running:
                return
            obj = self.objects.get(oid, {})
            noun5 = (obj.get("noun") or "")[:5].upper()
            handled = False
            if noun5:
                resp_script = self.condacts.get("responses", "")
                if resp_script:
                    basic = PAWSBasic(self)
                    basic._current_verb  = "COGER"
                    basic._current_noun1 = noun5
                    basic._current_noun2 = None
                    basic.run(resp_script)
                    handled = basic._stop or not self.running
                if not handled:
                    handled = self.find_response("COGER", noun5, None)
            # Si ninguna response lo manejó y sigue accesible, GET normal
            if not handled and obj.get("location") in holders:
                self._builtin_take(oid)

    def _builtin_drop(self, obj_id: str):
        """Lógica DEJAR del intérprete para un objeto ya resuelto."""
        obj = self.objects.get(obj_id, {})
        obj["location"] = self.player_location
        obj["worn"] = False
        self.recalc_weight()
        print(self._t('dejas', o=obj.get('name', obj_id)))

    def drop_all(self):
        """
        DEJAR TODO: deja cada objeto del inventario, pasando cada uno por
        el pipeline normal (responses → builtin). No toca lo que llevas
        puesto (PUESTO): para eso está QUITARSE.
        """
        oids = self.get_inventory()
        if not oids:
            print(self._t('nada_dejar'))
            return
        for oid in oids:
            if not self.running:
                return
            obj = self.objects.get(oid, {})
            noun5 = (obj.get("noun") or "")[:5].upper()
            handled = False
            if noun5:
                resp_script = self.condacts.get("responses", "")
                if resp_script:
                    basic = PAWSBasic(self)
                    basic._current_verb  = "DEJAR"
                    basic._current_noun1 = noun5
                    basic._current_noun2 = None
                    basic.run(resp_script)
                    handled = basic._stop or not self.running
                if not handled:
                    handled = self.find_response("DEJAR", noun5, None)
            if not handled and obj.get("location") == "INVEN":
                self._builtin_drop(oid)

    def handle_builtin(self, verb: str, noun1: str, noun2: str) -> bool:
        """Maneja comandos built-in del intérprete. Devuelve True si se manejó."""

        # Movimiento
        if verb in ('N', 'S', 'E', 'O', 'U', 'D'):
            # Primero buscar en responses (puede haber condiciones especiales)
            if not self.find_response(verb, noun1, noun2):
                self.move_player(verb)
            return True

        if verb == "INVEN":
            self.show_inventory()
            return True

        if verb == "EXAMI":
            if self.location_is_dark():
                print(self._t('oscuro_ver'))
                return True
            if noun1:
                obj_id = self.find_object_by_noun(noun1)
                if obj_id:
                    obj = self.objects.get(obj_id, {})
                    print(obj.get("description") or self._t('no_especial'))
                    # Si es contenedor abierto, mostrar contenido
                    if obj.get("container") and obj.get("open"):
                        contents = [self.objects[cid].get("name", cid)
                                   for cid, co in self.objects.items()
                                   if co.get("location") == obj_id]
                        if contents:
                            print(self._t('contiene', c=', '.join(contents)))
                        else:
                            print(self._t('vacio'))
                else:
                    print(self._t('no_ves_eso'))
            else:
                self.describe_location()
            return True

        if verb == "COGER":
            if not noun1:
                print(self._t('que_coger'))
                return True
            if noun1 == "TODO":
                self.take_all()
                return True
            obj_id = self.find_object_by_noun(noun1)
            if not obj_id:
                print(self._t('no_ves_eso'))
                return True
            self._builtin_take(obj_id)
            return True

        if verb == "DEJAR":
            if not noun1:
                print(self._t('que_dejar'))
                return True
            if noun1 == "TODO":
                self.drop_all()
                return True
            obj_id = self.find_object_by_noun(noun1, accessible_only=False)
            if not obj_id or self.objects.get(obj_id, {}).get("location") not in ("INVEN", "PUESTO"):
                print(self._t('no_llevas_eso'))
                return True
            self._builtin_drop(obj_id)
            return True

        if verb == "PONER":
            if not noun1:
                print(self._t('que_poner'))
                return True
            obj_id = self.find_object_by_noun(noun1, accessible_only=False)
            if not obj_id or self.objects.get(obj_id, {}).get("location") != "INVEN":
                print(self._t('no_inventario'))
                return True
            obj = self.objects.get(obj_id, {})
            if not obj.get("wearable"):
                print(self._t('no_ponerte', o=obj.get('name', obj_id)))
                return True
            obj["location"] = "PUESTO"
            obj["worn"] = True
            print(self._t('te_pones', o=obj.get('name', obj_id)))
            return True

        if verb == "QUITA":
            if not noun1:
                print(self._t('que_quitar'))
                return True
            obj_id = self.find_object_by_noun(noun1, accessible_only=False)
            obj = self.objects.get(obj_id, {}) if obj_id else {}
            if not obj_id or obj.get("location") != "PUESTO":
                print(self._t('no_puesto'))
                return True
            obj["location"] = "INVEN"
            obj["worn"] = False
            print(self._t('te_quitas', o=obj.get('name', obj_id)))
            return True

        if verb == "ABRIR":
            if not noun1:
                print(self._t('que_abrir'))
                return True
            obj_id = self.find_object_by_noun(noun1)
            if not obj_id:
                print(self._t('no_ves_eso'))
                return True
            obj = self.objects.get(obj_id, {})
            if not obj.get("openable"):
                print(self._t('no_abrir', o=obj.get('name', obj_id)))
                return True
            if obj.get("open"):
                print(self._t('ya_abierto'))
                return True
            if obj.get("locked"):
                key_id = obj.get("key")
                key = self.objects.get(key_id, {}) if key_id else {}
                if key_id and key.get("location") in ("INVEN", "PUESTO"):
                    obj["locked"] = False
                    obj["open"] = True
                    print(self._t('abres_con', o=obj.get('name', obj_id),
                                  k=key.get('name', key_id)))
                else:
                    print(self._t('cerrado_llave'))
                return True
            obj["open"] = True
            print(self._t('abres', o=obj.get('name', obj_id)))
            if obj.get("container"):
                contents = [self.objects[cid].get("name", cid)
                            for cid, co in self.objects.items()
                            if co.get("location") == obj_id]
                if contents:
                    print(self._t('dentro_hay', c=', '.join(contents)))
            return True

        if verb == "CERRA":
            if not noun1:
                print(self._t('que_cerrar'))
                return True
            obj_id = self.find_object_by_noun(noun1)
            if not obj_id:
                print(self._t('no_ves_eso'))
                return True
            obj = self.objects.get(obj_id, {})
            if not obj.get("openable"):
                print(self._t('no_cerrar', o=obj.get('name', obj_id)))
                return True
            if not obj.get("open"):
                print(self._t('ya_cerrado'))
                return True
            obj["open"] = False
            print(self._t('cierras', o=obj.get('name', obj_id)))
            return True

        if verb == "METER":
            # METER obj1 EN obj2 (genérico; las responses tienen prioridad)
            if not noun1:
                print(self._t('que_meter'))
                return True
            if not noun2:
                print(self._t('donde_meter'))
                return True
            obj_id = self.find_object_by_noun(noun1, accessible_only=True)
            if not obj_id:
                print(self._t('no_ves_eso'))
                return True
            obj = self.objects.get(obj_id, {})
            if obj.get("location") not in ("INVEN", "PUESTO"):
                print(self._t('primero_coger', o=obj.get('name', obj_id)))
                return True
            container_id = self.find_object_by_noun(noun2, accessible_only=True)
            if not container_id:
                print(self._t('no_ves_eso'))
                return True
            if container_id == obj_id:
                print(self._t('no_meter_si'))
                return True
            container = self.objects.get(container_id, {})
            if not container.get("container"):
                print(self._t('no_contenedor_p',
                              o=container.get('name', container_id)))
                return True
            if container.get("openable") and not container.get("open"):
                print(self._t('cont_cerrado',
                              o=container.get('name', container_id).capitalize()))
                return True
            cap = container.get("capacity", 0)
            if cap > 0:
                contents_w = sum(self.get_object_weight(cid)
                                 for cid, co in self.objects.items()
                                 if co.get("location") == container_id)
                if contents_w + self.get_object_weight(obj_id) > cap:
                    print(self._t('no_cabe', o=container.get('name', container_id)))
                    return True
            obj["location"] = container_id
            obj["worn"] = False
            self.recalc_weight()
            print(self._t('metes', o=obj.get('name', obj_id),
                          c=container.get('name', container_id)))
            return True

        if verb == "SACAR":
            if not noun1:
                print(self._t('que_sacar'))
                return True
            # Buscar el objeto dentro de algún contenedor
            obj_id = self.find_object_by_noun(noun1, accessible_only=True)
            if not obj_id:
                print(self._t('no_ves_eso'))
                return True
            obj = self.objects.get(obj_id, {})
            container_id = obj.get("location")
            container = self.objects.get(container_id, {}) if container_id else {}
            if not container.get("container"):
                print(self._t('no_dentro'))
                return True
            # Mover provisionalmente y validar contra el peso real: si el
            # contenedor ya lo llevaba el jugador, el peso total no cambia.
            prev_loc = obj.get("location")
            obj["location"] = "INVEN"
            if self.recalc_weight() > self.variables.get("LLEVAR_MAX", 50):
                obj["location"] = prev_loc
                self.recalc_weight()
                print(self._t('peso_sacar'))
                return True
            print(self._t('sacas', o=obj.get('name', obj_id),
                          c=container.get('name', container_id)))
            return True

        if verb == "PUNT":
            pts = self.variables.get("PUNTOS", 0)
            max_pts = self.meta.get("max_score", 0)
            print(self._t('puntuacion', p=pts))
            return True

        if verb == "SALIR":
            # Confirmación delegada (p. ej. intérprete embebido en el editor)
            confirm = getattr(self, "confirm_quit", None)
            if callable(confirm):
                if confirm():
                    self.running = False
                return True
            # Sin consola interactiva (GUI, entrada redirigida): salir directo
            try:
                interactive = sys.stdin is not None and sys.stdin.isatty()
            except Exception:
                interactive = False
            if not interactive:
                self.running = False
                return True
            print(self._t('abandonar'))
            try:
                resp = input("> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                resp = "s"
            if resp in ("s", "si", "sí", "yes", "y"):
                self.running = False
            return True

        return False

    # ─── BUCLE PRINCIPAL ─────────────────────────────────────────────────────

    def run(self):
        """Bucle principal del juego."""
        title = self.meta.get("title", "Aventura sin título")
        print(f"\n{title}")

        start_msg = self.meta.get("start_message", "")

        # CONDACTS on_start: tras la presentacion, ANTES del mensaje inicial
        self.execute_condact_blocks(self.condacts.get("on_start", []))

        if start_msg:
            print(f"\n{start_msg}\n")

        # Describir localización inicial
        self.describe_location()

        # on_enter de la localización inicial (antes nunca se ejecutaba;
        # solo se lanzaba al entrar andando)
        self.execute_condact_blocks(
            self.locations.get(self.player_location, {}).get("on_enter", []))

        while self.running:
            # Prompt
            try:
                print()
                raw = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n" + self._t('hasta_luego'))
                break

            if not raw:
                continue

            self.last_command = raw
            self.turns += 1

            # CONDACTS before_turn
            self.execute_condact_blocks(self.condacts.get("before_turn", []))
            if not self.running:
                break

            # Parsear
            verb, noun1, noun2 = self.parse(raw)

            if not verb:
                print(self._t('no_entiendo_ayuda'))
                # El turno cuenta igualmente: before_turn ya corrió, así que
                # timers y after_turn también deben correr (antes se saltaban
                # y el reloj de misión se congelaba con entradas no válidas).
            else:
                # 1. Responses en BASIC (condacts.responses con ON/ENDON/MATCH)
                handled = False
                resp_script = self.condacts.get("responses", "")
                if resp_script:
                    basic = PAWSBasic(self)
                    basic._current_verb  = verb
                    basic._current_noun1 = noun1
                    basic._current_noun2 = noun2
                    basic.run(resp_script)
                    # MATCH fue llamado, o el script terminó la partida (END):
                    # en ambos casos no hay que caer a los built-ins (END
                    # detiene el script antes de su MATCH y sin esto se
                    # imprimía "No puedes hacer eso." tras el final).
                    handled = basic._stop or not self.running

                # 2. Responses en formato JSON legacy (compatibilidad)
                if not handled:
                    handled = self.find_response(verb, noun1, noun2)

                # 3. Comandos built-in del intérprete
                if not handled:
                    handled = self.handle_builtin(verb, noun1, noun2)

                if not handled:
                    print(self._t('no_hacer'))

            if not self.running:
                break

            # Tick timers
            self.tick_timers()

            # CONDACTS after_turn
            self.execute_condact_blocks(self.condacts.get("after_turn", []))

        print("\n" + self._t('fin_aventura'))


# ─── CARGA DE ARCHIVO ────────────────────────────────────────────────────────

def load_game(path: str) -> dict:
    """Carga un juego desde YAML (o JSON)."""
    if not os.path.exists(path):
        print(f"ERROR: Archivo no encontrado: {path}")
        sys.exit(1)
    with open(path, 'r', encoding='utf-8') as f:
        if path.lower().endswith('.json'):
            return json.load(f)
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description='Scriba')
    parser.add_argument('game', help='Archivo de juego (.yaml o .json)')
    args = parser.parse_args()
    game = load_game(args.game)
    interp = PAWSInterpreter(game)
    interp.run()


if __name__ == '__main__':
    main()
