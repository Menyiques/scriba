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
| `interpreter.py` | probador de PC y `.exe` de Windows |
| `player.py` + `scriba_pack.py` | reproductor de ventana y el juego cifrado pegado al `.exe` |
| `nativecc.py` + `game_engine.py` | motor Z80 nativo (bytecode), común a las cuatro máquinas |
| `spectrum48_nativo.py`, `spectrum128_nativo.py` | ZX Spectrum 48K y 128K, a `.tap` |
| `next_nativo.py` | ZX Spectrum Next, a `.nex` |
| `cpc_nativo.py` | Amstrad CPC, a `.dsk` |
| `spectrum_export.py` | ya NO es un backend: queda como biblioteca (`recolecta`, acentos, PSG, dzx0, imágenes) de la que tiran todos los demás |

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

**El mapa de 128K y Next (v2.7).** Dos mitades con una regla: por debajo de
`&C000` vive todo lo que el motor necesita siempre —código, índices, vocabulario,
objetos, respuestas y la pila, en `&BFF0`—; `&C000-&FFFF` es una **ventana de
paginación pura** por la que se leen, cada uno de su banco, el texto (por
mensaje, vía `TXTPAGE`), la música del título, los FX, las imágenes y las
muestras. Nada permanente vive en la ventana, así que se pagina cuando hace
falta y no se devuelve nada a su sitio. La base de datos lleva, por mensaje, el
banco (`msgbnk`) y la dirección en la ventana; `expand_msg` pagina antes de
seguir el puntero. En 48K y CPC `TXTPAGE` es un `RET` y el texto sigue plano.
El mapa plano son 24.432 bytes (`&6000-&BF70`): menos que los 40K del 48K, pero
sin el texto, que es dos tercios de la base de datos. Y los bancos del 128K son
**seis** (1, 3, 4, 6, 7 y 0, en ese orden de carga): el 0 dejó de ser la RAM
alta del juego y es uno más. Como valor de `&7FFD` los ids son 17, 19, 20, 22,
23 y 16 — nunca 0, que en `msgbnk`/`fxbnk`/`psgbnk` significa «plano».

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

### Baterías del juego, no del motor

Los arneses de arriba prueban el **motor**. Para probar **una aventura** —¿se
puede acabar?, ¿la linterna luce sin pilas?— hay dos corredores que comparten
formato de fichero (`.pru`):

```powershell
python probar_juego.py 'Games\Operacion Tifon Negro\Operacion Tifon Negro.yaml' `
                       'Games\Operacion Tifon Negro\tifon.pru'
python bateria_next.py 'Games\Operacion Tifon Negro\Operacion Tifon Negro.yaml' `
                       'Games\Operacion Tifon Negro\tifon.pru' --jnext 'C:\...\jnext.exe'
```

- `probar_juego.py` juega dentro del simulador Z80 de Python y lee la pantalla
  de los píxeles. No hace falta instalar nada.
- `bateria_next.py` ejecuta el `.nex` en **jnext** (`--headless`), un emulador
  de Next de verdad: prueba además el cargador NEX, la ROM, la MMU, Layer 2 y el
  Z80N. Se baja de <https://github.com/jorgegv/jnext/releases>; la ruta va en
  `--jnext`, en la variable de entorno `JNEXT` o en el `PATH`.

**La traza llega con los saltos de línea del sistema.** El puerto mágico sale
por la salida de error de jnext, y en Windows el runtime de C convierte cada
`\n` en `\r\n`, así que una marca llega como `\r\n#RESET\r\n`. `descodifica()`
tira los retornos de carro y las expresiones los toleran igualmente. Si se
vuelve a tocar el troceo de la traza, **probarlo con CRLF**, no solo en Linux:
esto costó una tarde.

**La primera vez en una máquina, jnext no tiene la imagen de tarjeta SD** — de
ahí saca las ROMs, igual que una máquina real — y pregunta si se la baja. Se
resuelve con `--bajar-sd` (1 GB), con `--sdcard FICHERO` si ya se tiene una, o
ejecutando jnext a mano una vez. Ojo a **dónde** la deja: jnext lee `$HOME`, y
si no está puesta —lo normal en Windows— usa `.jnext` **de la carpeta desde la
que se le lance**, no la del usuario. `$JNEXT_CONFIG_DIR` manda sobre las dos. `bateria_next.py` lanza el emulador con la
entrada estándar cerrada a propósito, para que esa pregunta se responda sola
que no y salga con su mensaje en vez de quedarse colgada esperando una tecla
que nadie ve que haga falta; y corta si pasan `--paciencia` segundos (120 por
defecto) sin noticias del puerto.

Cómo lo hace `bateria_next.py`: `next_nativo._modo_prueba()` compila un `.nex`
**de pruebas** que lleva el guion dentro y se teclea solo (parchea `KMREAD`),
copia cada carácter impreso a un puerto de E/S (parchea `TXTO`) que jnext vuelca
con `--magic-port`, no gasta guion en las esperas de tecla (parchea `KMW`), pone
la CPU a 28 MHz y se salta las esperas de barrido decorativas. Dos bytes de
control en el guion: `1` vuelca el estado del motor (variables, `OBJLOC`,
`OBJIN`, sala) y `2` reinicia la partida, así que **toda la batería cabe en una
sola ejecución del emulador**. El `.nex` que se distribuye no lleva nada de esto.

Formato `.pru`:

| línea | qué hace |
|---|---|
| `=== nombre` | abre una prueba y **reinicia** la partida |
| `MIRAR` | una orden, tal cual la teclearía el jugador |
| `? texto` / `!? texto` | la respuesta debe / no debe contener ese texto |
| `$ PUNTOS = 110` | una variable (`=`, `<>`, `>`, `<`, `>=`, `<=`) |
| `@ @playa` | dónde está el jugador |
| `% #linterna = INVEN` | dónde está un objeto: `@sala`, `INVEN`, `PUESTO`, `NADA` o `#contenedor` |
| `* 40 I` | repite una orden 40 veces (dejar pasar turnos) |
| `<< fichero : 21` | mete las 21 primeras órdenes de un walkthrough |

Los dos aceptan `-v` (cuenta cada orden según pasa: dónde acaba el jugador, la
puntuación y el principio de la respuesta, y cada comprobación con su `ok` o su
`FALLA`) y `-vv` (además la respuesta entera). `bateria_next.py` lee la salida
del emulador **según sale**, no al terminar, así que con `-v` se ve la partida
avanzar en vivo.

El emulador se corta en cuanto el guion llega al final, así que `--frames` solo
tiene que ser generoso, no exacto: las 690 órdenes de *Tifón Negro* tardan unos
30 s. El texto se compara **sin acentos**, que en pantalla son códigos propios
de la fuente.

El guion va en su propio banco, paginado sobre la ROM en `&2000`: caben 8 KB de
teclas. Si no cabe, la batería lo dice; `* 40 I` en vez de repetir una orden
larga cuarenta veces suele bastar.

Las comprobaciones miran la respuesta a la **última orden**, no la pantalla
entera. Los nombres de variable se escriben sin guiones bajos (`_PILAS_CARGA`
se comprueba como `$ PILASCARGA`), que es como los indexa el motor.

---

## Imágenes por plataforma

| carpeta | para | formato |
|---|---|---|
| `img/Original/<id>.png\|jpg` | máster, y fallback de todo | lo que sea; se autocontrasta |
| `img/Spectrum/<id>.scr` | 48/128K | 6912 o 2304 bytes |
| `img/Spectrum/<id>.jpg\|png\|bmp` | 48/128K | **4:1** (256×64); se convierte **sin** autocontraste |
| `temp/Next/data/<id>.nxi` | Next | Layer 2, lo genera el editor; manda la grafía **con** arroba |

El nombre vale **con arroba y sin ella** (`@playa.jpg` = `playa.jpg`): los
másteres se guardan con la del id y el arte de `img/Spectrum`, históricamente,
sin ella. Lo que está en `img/Spectrum` es la versión definitiva, así que si no
cumple el 4:1 **se corta la exportación** con un error que dice cuánto mide;
los másteres de `img/Original`, en cambio, se escalan sin protestar. Margen del
2% en la proporción. La pantalla de carga (`screen.*`) va a pantalla completa,
4:3, y no se le exige proporción.

---

## Trampas que ya han mordido

- **`run_condacts` recibe la longitud del cuerpo en DE.** `run_response` la
  deja ahí y cualquier `ld de,...` por el medio la destruye: el cuerpo de la
  respuesta se ejecuta con un final absurdo y la regla parece no casar. Costó
  una tarde y no da ningún error, solo «No entiendo eso».

- **Comodines de sustantivo (manual):** `_` = hueco vacío, o sea que NO puede
  haber palabra; `*` = cualquier palabra o ninguna. En la tabla de respuestas
  se codifican 254 y 255, y 0 es la ranura que la regla no declara.

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

- **Los offsets de la cabecera de la base de datos son el final de cada campo,
  no el principio.** En `build_game_db` el comentario `# 55` de `w16(locdark)`
  quiere decir «después de esto `len(out)` vale 55», o sea que `locdark` empieza
  en 53. El motor leía `locdark`, `objlight` y `objlit` dos bytes más arriba y
  **la oscuridad no funcionó nunca**, ni en Next ni en CPC. Al añadir un campo,
  comprobar los `ld hl,(DBB+n)` de `init` contra la tabla, no contra los
  comentarios.

- **El motor nativo no admite mas de 64 objetos ni 64 variables.** `FLAGS`,
  `OBJLOC`, `OBJLIT`, `OBJOPEN`, `OBJLOCK` y `OBJIN` son `defs 64` fijos y
  pasarse no daba error: escribia sobre la matriz siguiente. Desde 2.47
  `build_game_db` y `nativecc` cortan con un mensaje claro
  (`game_engine.NRAM`). Las **localizaciones** si llegan a 255: no tienen
  matriz en RAM. Subir el tope cuesta ~1,1 KB de RAM por las seis matrices.

- **`ISAT` tiene tres clases de destino, no dos**: sentinel (`INVEN`/`PUESTO`/
  `NADA`), localización (`@sala`) y **contenedor** (`#objeto`). El tercero no
  cabe en el byte de `OBJLOC` — un objeto contenido guarda `CONTAINED` ahí y el
  contenedor en `OBJIN` — y por eso lleva opcode propio (`ISIN`). Si vuelve a
  caer en `ctx.loc()`, el juego se queda sin poder sacar nada de una caja.

- **Los glifos `_` y `q` de `print42_es.bas` / `print42_pt.bas` están mal**: el
  subrayado apunta al índice de la `á`, y la cola de la `q` invade un píxel del
  carácter siguiente. `genera_font42.py` los corrige al generar la tabla del
  motor nativo, así que hoy no afecta a ningún binario; los `.bas` siguen ahí
  porque son la fuente de esa tabla.

---

## Trampas

- **Tras tocar un módulo del motor, reconstruir `Scriba.exe` ANTES de probar una
  exportación desde el editor.** El `.exe` es una foto congelada: lleva dentro su
  propia copia de `game_engine`, `nativecc`, `next_nativo`, `spectrum*_nativo`…
  Si exportas desde el `.exe` viejo obtienes un binario sin el arreglo, y desde
  la línea de comandos el mismo juego sale bien — dos resultados distintos para
  el mismo código fuente. Nos costó dos vueltas con los FX del Next en la v2.53.
  Para comparar binarios, mirar la fecha de `dist/Scriba.exe` antes que nada.

- **`ScribaPlayer.exe` no está en el repositorio** (`*.exe` está en
  `.gitignore`) y se pierde en cuanto se limpia `dist/`. Sin él, «Exportar para
  Windows» falla. Se reconstruye con `build_scribaplayer.bat`, una vez, y se
  deja junto a `Scriba.exe`.

- **El bloque que se pega al final del `.exe` no puede contener el patrón de
  8 bytes de PyInstaller** (`MEI\x0c\x0b\x0a\x0b\x0e`). Su arranque busca su
  archivo escaneando el fichero de atrás hacia delante y se queda con la
  primera aparición; si la nuestra apareciera por casualidad, el `.exe` dejaría
  de arrancar **en la máquina del jugador**, no en la nuestra.
  `scriba_pack.empaqueta()` lo comprueba en cada empaquetado y cambia la sal si
  hiciera falta. No quitar esa comprobación.

- **En 128K y Next, nada del arnés puede vivir en `&C000-&FFFF`.** Es la
  ventana de paginación: la primera llamada a `TXTPAGE` se lleva lo que hubiera
  ahí. `verify_next.ejecutar` ponía su pila y su retorno postizo en `&FFEE`, y
  al sacar el texto a bancos `describe` "no terminaba nunca": el `RET` final
  volvía a un banco de texto. Ahora `PILA_ARNES` lo baja a `&BFEE` en
  `verify_128` y en `verificar_nex`. Cualquier arnés nuevo para esas dos
  máquinas tiene que hacer lo mismo.

- **Los símbolos de plataforma que en una máquina son una rutina de verdad y en
  otra un `RET` se rompen en silencio.** `MCWAIT` estuvo así desde que existe el
  motor nativo en Spectrum: en CPC era la espera de barrido del firmware y en la
  capa de Spectrum/Next un `RET` del montón de stubs. `PAUSE` no esperaba y
  **ningún FX sonó nunca** en 48K, 128K ni Next. Mismo patrón que `END`
  compilándose a `DONE`. Al añadir un símbolo de plataforma, comprobar que las
  CUATRO implementaciones hacen algo, y dejar una prueba que lo verifique.

---

## Estado

Rama de trabajo: `fix/predicados-objeto-v2.44`. Scriba 2.8.

**Boriel se ha ido** (v2.54). Las cuatro máquinas salen del motor nativo Z80 y
no hay otro camino: se borraron `next_export.py`, `cpc_export.py`,
`empaqueta_cpc.py`, `empaqueta_nextap.py`, `construye_nextap.py`,
`empaqueta48.py` y `build_nextap.bat`, y con ellos el submenú «Exportaciones
heredadas», el diálogo de configuración del TAP y todo lo que invocaba `zxbc`.
Queda un resto: el transpilador a BASIC sigue DENTRO de `spectrum_export.py`,
sin que lo llame nadie, esperando a que se separe lo que sí se usa. El informe
de `EmbeddedMmuSwitchAssembleError` para upstream sigue en
`reporte_boriel_splitmodules/`, ya solo como documento.

El motor nativo del Next tiene imágenes (Layer 2, un banco por sala), pantalla
de título, música del AY, efectos FX y muestras digitalizadas. Desde la 2.7, en
128K y Next el texto, la música y los FX van en bancos (ver «El mapa de 128K y
Next»); el CPC sigue plano y va al límite (`imgbuf` por encima de `&8B00` es el
arreglo pendiente).

Lo que queda: los glifos `_` y `q` siguen mal en los `.tap` de 128K y Next
(`genera_font42.py` solo corrige la tabla del motor nativo), el DMA y el Copper
están sin usar, y los dos arneses suponen que los objetos 0, 5 y 6 tienen
ciertas propiedades, cosa que en NIVEL7 y "1" no se cumple.
