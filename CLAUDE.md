# SCRIBA

Sistema de autoría de aventuras conversacionales. El juego se escribe en YAML y
de ahí salen cinco destinos: probador de PC, ZX Spectrum 48K/128K, ZX Spectrum
Next, Amstrad CPC y .exe de Windows.

---

## Reglas permanentes

**1. Los comandos, siempre en PowerShell.**
Nada de `^` para partir líneas (eso es CMD). `&` delante de una ruta de
ejecutable entrecomillada. Para volcar a fichero, `2>&1 | Out-File -Encoding utf8`
y nunca `>`, que escribe UTF-16 y deja el log ilegible.

**2. Cada cambio en un YAML sube `metadata.version`.**
El editor sella `revision` y `modified` al guardar, pero una edición hecha
fuera del editor se salta ese sello: hay que poner `version`, `revision` y
`modified` a mano.

---

## Lo que hay que saber antes de tocar nada

**`paws_lang.py` es el único analizador del lenguaje de condacts.** Produce un
AST que consumen todos los destinos. Un predicado nuevo hay que darlo de alta
en `PREDICATES` y **además** implementarlo en cada backend. Si falta en uno, ese
destino lo evalúa mal y no avisa.

Backends:

| Fichero | Destino |
|---|---|
| `interpreter.py` | probador de PC |
| `spectrum_export.py` | ZX BASIC (48K, 128K y Next lo heredan) |
| `nativecc.py` + `game_engine.py` | motor Z80 nativo (bytecode) |
| `cpc_export.py`, `cpc_nativo.py` | Amstrad CPC |
| `next_nativo.py` | ZX Spectrum Next nativo, a `.nex` |

**`compiler.py::check_predicates()`** detecta predicados no soportados por
destino. Pásalo antes de dar nada por bueno.

---

## Motor nativo Z80

`game_engine.ENGINE_ASM` (~2800 líneas de Z80) es independiente de máquina:
parser, VM de condacts, evaluador de expresiones, tablas, temporizadores y
word-wrap. Toda su dependencia de la máquina está en ~20 símbolos externos que
cada plataforma resuelve a su manera:

- CPC: al firmware (`&BBxx`/`&BCxx`), en el prefijo de `assemble_engine()`.
- Next: a rutinas propias en `next_nativo.PLAT_ASM`, sin tocar `game_engine.py`.

El backend del Next **no usa la ROM para nada** (fuente, teclado e impresión son
propios), así que los slots MMU 0 y 1 quedan libres para mapear RAM sobre
`&0000-&3FFF` si algún día hace falta. Hoy no hace falta: cabe de sobra.

`z80asm.py` ensambla (incluye Z80N) y `z80.py` simula (incluye Z80N, puertos y
NextRegs). Eso permite verificar el motor entero sin emulador.

`font42.py` lo genera `genera_font42.py`. **No editarlo a mano.**

---

## Verificación

```powershell
Set-Location 'C:\CLAUDE\PAWS\SCRIBA_NEXT'
python verify_cpc.py                      # motor nativo en CPC
python verify_next.py                     # motor nativo en Next, incluido el .nex
python verify_next.py 'Games\apolo11\apolo11_pt.yaml'
```

`verify_next.py` es el arnés bueno: no pone stubs de texto, así que ejercita el
impresor de verdad contra la pantalla simulada y **decodifica los píxeles de
vuelta a texto**. Además empaqueta el `.nex`, lo relee del disco y juega un par
de órdenes. `verify_cpc.py` sí anula el firmware con stubs, o sea que el camino
de texto del CPC nunca se prueba ahí.

Los dos arneses suponen que los objetos 0, 5 y 6 tienen ciertas propiedades. En
juegos donde no es así (NIVEL7, "1") fallan dos comprobaciones **en los dos**.
Eso es del arnés, no del motor: antes de perseguir un fallo del Next, comprueba
si el CPC falla igual.

---

## Trampas que ya han mordido

- **`startswith('REM')` se come `REMOVE`.** Fue un bug real en cinco sitios. Al
  detectar comentarios, `upper == 'REM' or upper.startswith('REM ')`.

- **`Scriba.exe` va congelado con PyInstaller.** Editar el `.py` no cambia el
  `.exe`. Hay que reconstruirlo con `build_exe.bat`, que lee la versión de
  `scriba_info.py`.

- **`scriba_info.py` es la única fuente de la versión.** No repartirla.

- **Las ubicaciones internas llevan `@`**: `@INVEN`, `@ONME`, `@NOWHERE`.
  `spectrum_export.locval()` y `nativecc._destval()` tienen que aceptar las dos
  formas, con y sin `@`. Si no, `CREATE #obj INVEN` compila a "en ninguna parte"
  y el juego se vuelve imposible de terminar sin que salte ningún error.

- **Borrar en la carpeta conectada está desactivado por defecto.** Si aparece un
  `.git/index.lock` huérfano, hay que pedir permiso de borrado antes.

- **Los glifos `_` y `q` de `print42_es.bas` / `print42_pt.bas` están mal**: el
  subrayado apunta al índice de la `á`, y la cola de la `q` invade un píxel del
  carácter siguiente. `genera_font42.py` los corrige para el motor nativo, pero
  **los builds BASIC de 128K y Next siguen teniéndolos**.

---

## Estado

Rama de trabajo: `fix/predicados-objeto-v2.44`. Scriba 2.45.

El camino `.nex` con Boriel está **parado**: `next_export.moduliza_texto()` está
escrito pero no lo llama nadie, bloqueado por `EmbeddedMmuSwitchAssembleError`
de Boriel 2.0.0-beta21. El informe para upstream está en
`reporte_boriel_splitmodules/`. El backend nativo resuelve lo mismo sin Boriel.

Del motor nativo del Next faltan imágenes, música, pantalla de título, y
enchufarlo como destino del editor. Y no se ha ejecutado nunca en CSpect: todo
lo verificado hasta ahora es simulador.
