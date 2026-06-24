#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, io
# En modo --windowed (PyInstaller) no hay consola: sys.stdout/stderr son None.
if getattr(sys.stdout, 'buffer', None) is not None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if getattr(sys.stderr, 'buffer', None) is not None:
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
"""
Scriba - validador de aventuras conversacionales
Valida un juego (YAML o JSON): estructura, referencias entre entidades y
sintaxis de los scripts BASIC (condacts). NO genera ningún binario: el
intérprete de Python y el exportador a ZX Spectrum leen el YAML directamente.

Uso:  python compiler.py juego.yaml          → valida y muestra errores/avisos
      python compiler.py -v juego.yaml       → además resumen del juego
"""

import json
import yaml
import os
import argparse
import paws_lang


def validate_game(game: dict) -> list[str]:
    """Valida la estructura del juego y devuelve lista de errores."""
    errors = []

    # Metadata obligatoria
    meta = game.get("metadata", {})
    for field in ["title", "author", "start_location"]:
        if field not in meta:
            errors.append(f"metadata.{field} es obligatorio")

    # Localización inicial debe existir
    start_loc = meta.get("start_location")
    locations = game.get("locations", {})
    if start_loc and start_loc not in locations:
        errors.append(f"start_location '{start_loc}' no existe en locations")

    # Verificar salidas de localizaciones
    valid_dirs = ('N', 'S', 'E', 'O', 'U', 'D')
    for loc_id, loc in locations.items():
        for direction, dest in loc.get("exits", {}).items():
            if direction not in valid_dirs:
                errors.append(f"locations.{loc_id}.exits: dirección '{direction}' "
                              f"no válida (usa N/S/E/O/U/D)")
            if dest and dest not in locations:
                errors.append(f"locations.{loc_id}.exits.{direction} → '{dest}' no existe")

    # Verificar objetos
    objects = game.get("objects", {})
    for obj_id, obj in objects.items():
        # Location válida
        loc = obj.get("location")
        if loc and loc not in ("INVEN", "PUESTO", "NADA") and loc not in locations and loc not in objects:
            errors.append(f"objects.{obj_id}.location '{loc}' no existe")

        # Llave del contenedor existe
        key = obj.get("key")
        if key and key not in objects:
            errors.append(f"objects.{obj_id}.key '{key}' no existe en objects")

    # Detectar ciclos de contención (A dentro de B dentro de A): provocarían
    # recursión infinita al calcular pesos
    reported_cycles = set()
    for obj_id in objects:
        seen = {obj_id}
        cur = objects[obj_id].get("location")
        while cur in objects:
            if cur in seen:
                cyc = frozenset(seen)
                if cyc not in reported_cycles:
                    reported_cycles.add(cyc)
                    errors.append(f"objects: ciclo de contención que incluye "
                                  f"'{obj_id}' y '{cur}'")
                break
            seen.add(cur)
            cur = objects[cur].get("location")

    # Verificar timers
    timers = game.get("timers", {})
    for tim_id, tim in timers.items():
        if tim.get("turns", 0) <= 0:
            errors.append(f"timers.{tim_id}.turns debe ser > 0")

    return errors


# ─── VALIDACIÓN DE SCRIPTS BASIC ─────────────────────────────────────────────

_OBJ_CMDS = {'GET', 'DROP', 'LIT', 'UNLIT', 'OPEN', 'CLOSE', 'LOCK', 'UNLOCK',
             'DESTROY', 'WEAR', 'REMOVE'}


def _resolves_to_object(arg: str, objects: dict) -> bool:
    """¿arg es un id de objeto o coincide con el noun (5 letras) de alguno?"""
    if arg in objects:
        return True
    a5 = arg[:5].upper()
    return any((o.get("noun") or "")[:5].upper() == a5 for o in objects.values())


def validate_script(name: str, script, game: dict, errors: list, warnings: list):
    """
    Valida un script BASIC: bloques IF/ENDIF y ON/ENDON equilibrados y
    referencias a objetos/localizaciones/timers existentes.
    Los bloques en formato JSON legacy se ignoran.
    """
    if isinstance(script, list):
        if not script or not isinstance(script[0], str):
            return  # formato JSON legacy
        lines = script
    elif isinstance(script, str):
        lines = script.split('\n')
    else:
        return

    objects   = game.get("objects", {})
    locations = game.get("locations", {})
    timers    = game.get("timers", {})
    if_depth = on_depth = 0

    for raw in lines:
        code = raw.strip()
        if not code:
            continue
        parts = code.split(None, 1)
        if parts[0].isdigit():  # quitar número de línea
            code = parts[1].strip() if len(parts) > 1 else ''
            if not code:
                continue
        tokens = code.split()
        cmd = tokens[0].upper()
        up  = code.upper()

        if cmd == 'IF' and ' THEN' in up:
            if_depth += 1
            # Validar la sintaxis de la condición con el parser compartido
            cond = code[2:up.rfind(' THEN')].strip()
            try:
                paws_lang.parse_condition(cond)
            except paws_lang.ParseError as e:
                errors.append(f"{name}: condición inválida '{cond}': {e}")
        elif cmd == 'LET' and '=' in code:
            # Validar la sintaxis de la expresión del LET
            rhs = code.split('=', 1)[1].strip()
            try:
                paws_lang.parse_expr(rhs)
            except paws_lang.ParseError as e:
                errors.append(f"{name}: expresión LET inválida '{rhs}': {e}")
        elif cmd == 'ENDIF':
            if_depth -= 1
            if if_depth < 0:
                errors.append(f"{name}: ENDIF sin IF")
                if_depth = 0
        elif cmd == 'ON':
            on_depth += 1
        elif cmd == 'ENDON':
            on_depth -= 1
            if on_depth < 0:
                errors.append(f"{name}: ENDON sin ON")
                on_depth = 0
        elif cmd in _OBJ_CMDS and len(tokens) > 1:
            if not _resolves_to_object(tokens[1], objects):
                warnings.append(f"{name}: {cmd} '{tokens[1]}' no es un objeto conocido")
        elif cmd == 'GOTO' and len(tokens) > 1:
            if tokens[1] not in locations:
                errors.append(f"{name}: GOTO '{tokens[1]}' no existe en locations")
        elif cmd in ('TIMER_START', 'TIMER_STOP', 'TIMER_RESET') and len(tokens) > 1:
            if tokens[1] not in timers:
                errors.append(f"{name}: {cmd} '{tokens[1]}' no existe en timers")
        elif cmd in ('CREATE', 'PUT') and len(tokens) > 2:
            if not _resolves_to_object(tokens[1], objects):
                warnings.append(f"{name}: {cmd} '{tokens[1]}' no es un objeto conocido")
            dest = tokens[2]
            if dest not in locations and dest not in ("INVEN", "PUESTO", "NADA") \
               and dest not in objects:
                errors.append(f"{name}: destino '{dest}' de {cmd} no existe")
        elif cmd in ('PUTIN', 'TAKEOUT') and len(tokens) > 2:
            for a in tokens[1:3]:
                if not _resolves_to_object(a, objects):
                    warnings.append(f"{name}: {cmd} '{a}' no es un objeto conocido")

    if if_depth:
        errors.append(f"{name}: {if_depth} IF sin ENDIF")
    if on_depth:
        errors.append(f"{name}: {on_depth} ON sin ENDON")


def validate_scripts(game: dict) -> tuple:
    """Valida todos los scripts BASIC del juego. Devuelve (errors, warnings)."""
    errors, warnings = [], []

    for sec, script in game.get("condacts", {}).items():
        validate_script(f"condacts.{sec}", script, game, errors, warnings)

    for lid, loc in game.get("locations", {}).items():
        for hook in ("on_enter", "on_look"):
            validate_script(f"locations.{lid}.{hook}", loc.get(hook),
                            game, errors, warnings)

    for tid, tim in game.get("timers", {}).items():
        validate_script(f"timers.{tid}.on_expire", tim.get("on_expire"),
                        game, errors, warnings)

    # Nouns duplicados entre objetos: el parser solo distingue las primeras
    # 5 letras, así que dos objetos con el mismo noun son ambiguos
    seen_nouns = {}
    for oid, obj in game.get("objects", {}).items():
        n5 = (obj.get("noun") or "")[:5].upper()
        if not n5:
            warnings.append(f"objects.{oid}: sin noun — el jugador no podrá "
                            f"referirse a él")
            continue
        if n5 in seen_nouns:
            warnings.append(f"objects: '{seen_nouns[n5]}' y '{oid}' comparten "
                            f"el noun '{n5}' (ambiguo para el parser)")
        else:
            seen_nouns[n5] = oid

    return errors, warnings


def check_vocabulary(game: dict) -> tuple:
    """
    Analiza el vocabulario. Devuelve (truncated, duplicates):
    - truncated: aliases más largos de 5 caracteres (el intérprete los trunca)
    - duplicates: misma palabra (5 letras) asignada a dos entradas distintas —
      solo una "ganará" en el intérprete.
    """
    vocab = game.get("vocabulary", {})
    truncated = []
    duplicates = []
    assigned = {}   # w5 → (section, key)

    section_types = [("verbs", "VERB"), ("nouns", "NOUN"), ("prepositions", "PREP")]
    for section, tipo in section_types:
        for key, aliases in vocab.get(section, {}).items():
            seen = set()
            for alias in (aliases or []):
                if len(alias) > 5:
                    truncated.append(f"'{alias}' → '{alias[:5]}' ({section}/{key})")
                w5 = alias[:5].upper()
                if w5 in seen:
                    continue
                seen.add(w5)
                prev = assigned.get(w5)
                if prev and prev != (section, key):
                    duplicates.append(
                        f"'{w5}' en {prev[0]}/{prev[1]} y {section}/{key} "
                        f"(ganará {section}/{key})")
                assigned[w5] = (section, key)

    return truncated, duplicates


def normalize_vocabulary(game: dict, verbose: bool = False) -> dict:
    """Imprime los avisos de vocabulario (ver check_vocabulary)."""
    truncated, duplicates = check_vocabulary(game)

    if truncated and verbose:
        print(f"  Aliases truncados a 5 chars ({len(truncated)}):")
        for w in truncated[:10]:
            print(f"  {w}")
        if len(truncated) > 10:
            print(f"  ... y {len(truncated)-10} más")

    if duplicates:
        print(f"AVISO: aliases duplicados en el vocabulario ({len(duplicates)}):")
        for w in duplicates:
            print(f"  {w}")

    return game


def validate_file(input_path: str, verbose: bool = False) -> bool:
    """Valida un juego YAML/JSON. Devuelve True si no hay errores."""

    print(f"[Scriba] Leyendo: {input_path}")

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            if input_path.lower().endswith('.json'):
                game = json.load(f)
            else:
                game = yaml.safe_load(f)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        print(f"ERROR: Formato inválido: {e}")
        return False
    except FileNotFoundError:
        print(f"ERROR: Archivo no encontrado: {input_path}")
        return False

    # Estructura + scripts BASIC (condacts, on_enter, on_expire...)
    errors = validate_game(game)
    s_errors, s_warnings = validate_scripts(game)
    errors += s_errors

    if s_warnings:
        print(f"AVISOS EN SCRIPTS ({len(s_warnings)}):")
        for w in s_warnings:
            print(f"  ! {w}")

    # Avisos de vocabulario (aliases truncados, duplicados)
    normalize_vocabulary(game, verbose=verbose)

    if errors:
        print(f"ERRORES ({len(errors)}):")
        for err in errors:
            print(f"  ✗ {err}")
        return False

    print("[Scriba] OK  El juego es válido (sin errores)")

    if verbose:
        meta = game.get("metadata", {})
        print(f"\n  Título:        {meta.get('title', 'Sin título')}")
        print(f"  Autor:         {meta.get('author', 'Desconocido')}")
        print(f"  Localizaciones:{len(game.get('locations', {}))}")
        print(f"  Objetos:       {len(game.get('objects', {}))}")
        print(f"  Timers:        {len(game.get('timers', {}))}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Scriba - Valida aventuras conversacionales (YAML/JSON)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python compiler.py juego.yaml       → valida y muestra errores/avisos
  python compiler.py -v juego.yaml    → además un resumen del juego

El intérprete (interpreter.py) y el exportador a ZX (spectrum_export.py)
leen el YAML directamente; ya no se genera ningún binario .pawb.
        """
    )
    parser.add_argument('input', help='Archivo de entrada (.yaml o .json)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Salida detallada')
    args = parser.parse_args()
    sys.exit(0 if validate_file(args.input, verbose=args.verbose) else 1)


if __name__ == '__main__':
    main()
