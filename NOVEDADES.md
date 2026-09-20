# Novedades de Scriba

Registro de cambios por versión. En cada *release*, añade una nueva sección **arriba**
(justo debajo de «Sin publicar»), con la fecha y los cambios agrupados en **Novedades**
y **Correcciones**. Al publicar, mueve lo acumulado de «Sin publicar» a la nueva versión.

> Formato basado en *Keep a Changelog*. Versionado: `MAYOR.MENOR` (`2.3`).

---

## [Sin publicar]

### Novedades
- (añade aquí lo que vaya entrando para la próxima versión)

### Correcciones
- (…)

---

## 2.47 — 2026-09-20 — Baterias de prueba sobre el .nex real

### Novedades
- **`bateria_next.py`: bateria de pruebas del juego sobre un emulador de Next
  de verdad.** Ejecuta el `.nex` en [jnext](https://github.com/jorgegv/jnext)
  en modo *headless* y comprueba lo que el juego contesta. No lee pixeles ni
  cuenta barridos: el `.nex` se compila en **modo prueba**, que le mete dentro
  el guion de la partida — se teclea solo — y hace que copie cada caracter que
  imprime a un puerto de E/S; jnext vuelca ese puerto a su salida de error
  (`--magic-port`), asi que una partida entera sale como texto plano. El guion
  lleva ademas dos bytes de control: uno pide una foto del estado del motor
  (variables, donde esta cada objeto, dentro de que contenedor, sala actual) y
  otro vuelve a empezar la partida, con lo que toda la bateria cabe en una sola
  ejecucion del emulador. **El `.nex` que se distribuye no lleva nada de esto**:
  son parches que solo se aplican cuando `compila()` recibe un guion.
  En modo prueba la CPU se pone a 28 MHz y se quitan las esperas de barrido
  decorativas: 288 ordenes de *Tifon Negro* tardan minuto y medio.
- **`probar_juego.py`: la misma bateria sin emulador**, dentro del simulador Z80
  de Python, leyendo la pantalla de los pixeles. Mas comoda para el dia a dia
  (no hay que instalar nada); la de jnext prueba ademas el cargador NEX, la ROM,
  la MMU, Layer 2 y el Z80N.
- **Formato `.pru`** compartido por las dos: `===` abre una prueba (y reinicia
  la partida), una linea suelta es una orden, `?` / `!?` comprueban el texto de
  la respuesta, `$` una variable, `@` la localizacion, `%` donde esta un objeto
  (incluido «dentro de tal contenedor») y `<<` mete las ordenes de un
  walkthrough, entero o solo las N primeras.
- **`Games/Operacion Tifon Negro/tifon.pru`**: 12 pruebas del juego, entre ellas
  que se puede acabar con 110/110 siguiendo la ruta optima.

### Correcciones
Las tres las encontro la bateria nueva.

- **`ISAT #objeto #contenedor` no estaba soportado en el motor nativo**, y
  *Tifon Negro* **no se podia acabar** por eso: coger los codigos Enigma o el
  pase del muelle de dentro de la caja fuerte se rechazaba siempre. Un objeto
  dentro de un contenedor guarda `OBJLOC = CONTAINED` y el contenedor aparte, en
  `OBJIN`, asi que no cabe en el byte de destino que compara `ISAT`; ahora
  `nativecc` emite un opcode propio (`ISIN`) cuando el destino es un `#objeto`.
- **Ni la oscuridad ni las fuentes de luz han funcionado nunca en el motor
  nativo** (ni en Next ni en CPC). El motor leia las tablas `locdark`,
  `objlight` y `objlit` dos bytes por encima de donde las deja el constructor de
  la base de datos, de modo que ninguna sala era oscura y ningun objeto
  alumbraba: en *Tifon Negro* el tunel de escape se veia sin linterna.
- **El motor nativo se pasaba de largo con mas de 64 objetos o 64 variables.**
  Las matrices de estado en RAM (`FLAGS`, `OBJLOC`, `OBJLIT`, `OBJOPEN`,
  `OBJLOCK`, `OBJIN`) son de 64 y no habia ninguna comprobacion: el objeto 65
  escribia sobre la matriz siguiente sin dar error. Ahora se corta al compilar
  con un mensaje claro. (Las **localizaciones** si llegan a 255: no llevan
  matriz en RAM.)

- **`PRINT "...{_VARIABLE}..."` imprimia las llaves tal cual** en el motor
  nativo, en vez del valor: salia `[0{_HORA_H}:{_HORA_M}]` y `(Carga restante:
  {_PILAS_CARGA} turnos.)`. Ahora `nativecc` parte el texto por las llaves y va
  alternando mensaje y variable, con un condact nuevo (`PRVAR`) que imprime el
  valor en decimal — lo mismo que hacen los exports BASIC con `STR$()`.

---

## 2.46 — 2026-09-20 — Motor nativo para ZX Spectrum Next

### Novedades
- **Motor nativo de ZX Spectrum Next.** Nuevo destino del editor, «Exportar ZX
  Spectrum Next (.nex, motor nativo)», que sustituye al export BASIC a `.tap`.
  Compila motor y base de datos en Python puro (sin zxbc, sin Boriel y sin
  NextBuild) reutilizando el motor Z80 que ya servia al CPC: de sus ~2800 lineas
  de ensamblador, solo una veintena de simbolos dependian de la maquina. Sale en
  `dist/{juego}_next_{idioma}.nex`.
  - Texto de 42 columnas con la misma tipografia que los builds BASIC, con los
    acentos de español y portugues.
  - Imagenes de localizacion por Layer 2: cada una en su banco de 16K, asi que
    cambiar de sala es apuntar el NextReg $12 a otro banco, sin mover un pixel.
    Se descubren de arriba abajo subiendo la linea de corte del clip.
  - Pantalla de titulo a pantalla completa, con musica del AY (reproductor de
    stream PSG). La musica se ajusta al hueco que quede en el binario.
  - Efectos de sonido FX por AY (el condact `PLAY`).
  - El texto se escribe a ritmo — una descripcion de sala tarda unos 2 s — y se
    para a esperar tecla cada vez que se llena la ventana.
  - Teclado leido por la matriz del puerto &FE, con borrado en CAPS+0.
  - Motor y plataforma ocupan ~8 KB; un juego con 23 imagenes, portada y musica
    se queda en ~35 KB de binario plano mas sus bancos.
  - No usa la ROM para nada (fuente, teclado e impresion son propios): solo la
    aparta un instante, con el MMU, para leer las paletas de su banco.
- **Comando VERSION en el motor nativo**, que quedaba pendiente en 2.45. Ahora
  responden los cuatro motores.
- **`metadata.start_message` en el motor nativo**: la presentacion del juego, que
  hasta ahora solo salia en el interprete y en los exports BASIC. Vale tambien
  para el CPC nativo.
- **`initial_message` de los objetos en el motor nativo**: cada objeto sale con
  su frase propia en vez de listarse por el nombre, y un objeto fijo sin frase
  no se lista, que para eso lo cuenta la descripcion de la sala. Como en el
  interprete, la frase deja de usarse en cuanto el objeto se mueve. Vale tambien
  para el CPC nativo.
- **Nombre de la localizacion en el motor nativo**: solo imprimia la
  descripcion. Vale tambien para el CPC nativo.
- `z80asm.py` y `z80.py` entienden ahora IN/OUT por puertos, los NextRegs y el
  juego de instrucciones **Z80N** (PIXELAD, PIXELDN, LDWS, LDIRX, ADD HL,A...).
  El simulador emula ademas la paginacion de la ranura 0 del MMU.
- `verify_next.py`: arnes que ensambla el motor, lo corre en el simulador,
  **decodifica la pantalla de vuelta a texto** comparando con la fuente, empaqueta
  el `.nex`, lo relee del disco y juega ordenes. A diferencia de `verify_cpc.py`,
  no pone stubs de texto ni de teclado: ese camino se ejercita de verdad.
- `genera_font42.py` genera `font42.py`, la fuente de 6 pixeles del motor nativo,
  a partir de la fuente de la ROM y de las tablas de `print42_*.bas`.

### Correcciones
- **`txtpack`: la segunda compresion de texto de un proceso salia con las frases
  de la primera.** `_expand` llevaba un `dict` mutable como valor por defecto,
  que sobrevivia entre llamadas y se indexaba solo por numero de token. Se veia
  como texto casi correcto con trozos de otro juego metidos. Afecta a **todos**
  los destinos y a cualquier sesion que exporte dos veces sin reiniciar.
- Las salidas se imprimen al final de la descripcion (nombre, descripcion,
  objetos, salidas), como en el export de 128K, y no entre la descripcion y los
  objetos.
- Cada objeto de la sala sale en su propia linea, en vez de amontonados.
- Glifos `_` y `q` corregidos en la fuente de 42 columnas del motor nativo: en
  `print42_*.bas` el subrayado apunta al indice de la `a` acentuada, y el remate
  de la cola de la `q` se sale de la celda e invade el caracter siguiente.
- Los menus de 48K y 128K decian «(.bas)», que es el intermedio: lo que producen
  es un `.tap` en `dist/`.

### Pendiente
- Los glifos `_` y `q` siguen mal en `print42_es.bas` y `print42_pt.bas`, o sea
  en los `.tap` de 128K y de Next.
- El camino `.nex` con Boriel sigue parado por `EmbeddedMmuSwitchAssembleError`
  (`next_export.moduliza_texto`, escrito pero sin usar). El motor nativo resuelve
  lo mismo sin Boriel.
- El DMA y el Copper del Next estan sin usar: el borrado y el desplazamiento de
  pantalla siguen con `LDIR`, que es justo donde el DMA rentaria.

---

## 2.45 — 2026-09-19 — Ficha de identificacion de los compilados

### Novedades
- Comando **VERSION** en todos los juegos y en los cuatro motores. Muestra
  titulo, version y revision del juego con su fecha, autor, idioma, version de
  Scriba, fecha de compilacion y sistema. El texto se resuelve al exportar,
  porque en la maquina destino no hay YAML que consultar.
- El editor sella `metadata.revision` (contador que sube en cada guardado) y
  `metadata.modified` (fecha) al guardar. `metadata.version` sigue siendo del
  autor, para marcar hitos.
- Nuevo modulo `scriba_info.py`: fuente unica de la version de Scriba y de la
  ficha, compartida por editor, interprete y los tres exportadores.
  `build_exe.bat` lee de ahi el numero para nombrar el ejecutable.

### Correcciones
- `build_exe.bat` empaqueta `Scriba_Manual.pdf` en vez del PDF con la version en
  el nombre, que obligaba a renombrarlo en cada release para que el manual
  siguiera abriendose desde el programa.

### Pendiente
- El motor nativo de CPC (`nativecc.py` / `game_engine.py`) no responde todavia
  al comando VERSION; el export a BASIC Locomotive si.

---

## 2.44 — 2026-09-19 — Restauración de los predicados de objeto

### Novedades
- El validador rechaza las condiciones que usan un predicado desconocido, con el
  nombre y la línea. Aparece también en el panel de problemas del editor.
- Al validar, se informa de lo que cada plataforma no soporta del juego.
- `paws_lang.PREDICATES` vuelve a estar completo (21 nombres), de modo que
  `capabilities.py` y `compiler.py` reconocen los predicados de estado.

### Correcciones
- Restaurados los trece predicados de estado (`CARRIED`, `NOTCARR`, `PRESENT`,
  `ABSENT`, `WORN`, `NOTWORN`, `ISAT`, `HASOBJOPEN`, `ZERO`, `NOTZERO`, `EQ`,
  `GT`, `LT`) en el intérprete de PC y en el exportador de Spectrum —del que
  bebe el Next—. Se perdieron en 2.43 al unificar la gramática en `paws_lang`;
  mientras faltaron, toda condición que los usara valía «verdadero» siempre.
  El backend de CPC no se vio afectado y sirvió de referencia.
- `REMOVE` no llegaba a ejecutarse: la detección de comentarios comparaba por
  prefijo con `REM`. Corregido en `interpreter.py`, `nativecc.py` y en tres
  puntos de `editor.py` (depurador, puntos de ruptura y renombrado).
- `CREATE` y `PUT` con destino `INVEN`, `PUESTO` o `NADA` dejaban el objeto en
  «ninguna parte» al exportar a Spectrum, Next y CPC, porque `locval()` solo
  admitía las formas con arroba. Ahora acepta las dos escrituras, igual que
  `_destval()` en `nativecc.py`.
- Un predicado que el motor no reconozca ya no se da por cierto: se avisa una
  vez por consola y se evalúa como falso.

---

## 2.3 — Vocabulario de serie editable y por idioma

### Novedades
- **Verbos y preposiciones de serie editables** desde el editor (botón «Verbos/preposiciones…»),
  con valores **por idioma** (ES/EN/PT) según `metadata.language` y guardados en
  `metadata['vocab_base']`. Válido para PC, Spectrum, Next y CPC (fuente única `vocab_base.py`,
  antes duplicada e inconsistente).
- **CPC:** el aviso **«[+n puntos]»** del condact `ADDSCORE` ahora se muestra (antes solo sumaba
  en silencio) y es **traducible** (`puntos_mas` en Mensajes del sistema).
- Manual **reconstruido como documento fluido** (docx/odt/pdf), con logo, portada 2.3,
  índice, tablas y bloques de código; documentada la cláusula `ON` con **dos nombres**
  (verbo + nombre1 + nombre2) para acciones con dos objetos («poner pilas en linterna»).

### Correcciones
- Generador ZX BASIC: `exDesc` (EXAMINAR) ya no emite un `IF 0 THEN` con bloque vacío
  cuando ningún objeto tiene descripción (Boriel no admite THEN vacío).
- Recordatorio de sintaxis: el `IF` debe terminar en `THEN` (tanto en el intérprete
  interno como al exportar).

---

## 2.2 — FX en Next, localización completa y nombres de distribución

### Novedades
- **Efectos FX por AY también en ZX Spectrum Next.** En Next el heap se ajusta a 2 KB solo
  cuando el juego usa FX (libera RAM para el reproductor); 4 KB si no.
- **`PLAY "nombre"`:** el condact referencia los efectos por **nombre** en vez de por número
  (`PLAY "explosion"`; se sigue admitiendo `PLAY n`). Borrar o reordenar efectos ya no
  descoloca las llamadas.
- **Localización de mensajes del sistema (ES/EN/PT):**
  - Catálogo de mensajes traducibles ampliado (incluye «Salidas:», nombres de salida y
    «Llevas demasiado peso.»); editable con «Mensajes del sistema…».
  - Las traducciones (`metadata['mensajes']`) valen para **Spectrum, Next y CPC**.
  - El **intérprete de PC** se traduce automáticamente por idioma (tablas ES/EN/PT) y respeta
    los textos personalizados del autor.
- **Nombres de distribución unificados:** `{juego}_{plataforma}_{idioma}.{ext}`
  (`48kb`/`128kb`/`next`/`cpc`/`windows`), todos juntos en una única carpeta `dist/`
  (sin subcarpetas por plataforma).
- **CPC:** vocabulario ampliado de **255 a 16 bits** (hasta 65535 palabras tras quitar duplicados).

---

## 2.1 — Efectos de sonido FX (AY)

### Novedades
- **Pestaña FX** en el editor: crear efectos sintetizados (bloques de tono/ruido) o
  **importar AYFX** del AY Sound FX Editor de Shiru (`.afx` individual o bancos `.afb`),
  con diálogo de previsualización (oír con las flechas/clic, marcar con la barra espaciadora).
- **Condact `PLAY`** para disparar efectos por el chip **AY** en PC y **Spectrum 128K**.
- En la exportación retro solo se embeben los efectos realmente referenciados por algún `PLAY`.

---

## 2.0 — Motor nativo CPC y exportación a Windows

### Novedades
- **Amstrad CPC:** motor **nativo Z80** (modelo PAW/DAAD), salida en `.dsk` arrancable, con
  **paridad** de lógica con las demás plataformas: objetos vestibles, luz/oscuridad,
  temporizadores, contenedores (candado y llave), límite de peso y parser de dos nombres (NOUN2).
- **Exportación a Windows (.exe):** paquete portable con el reproductor `ScribaPlayer.exe`
  y el juego; el jugador descomprime y ejecuta, sin instalar nada.
- **Peso** (`LLEVAR_MAX` + peso por objeto) en Spectrum/Next y CPC.
- Resumen de compilación **48K** con memoria libre; avisos de compatibilidad por plataforma
  (lo que un destino no soporta).
- Correcciones varias del editor (histórico de walkthrough, Guardar/Cargar/Snapshot, reinicio
  del probador, búsqueda en el código) y de exportación (vocabulario PT, «coger todo»).

---

<!--
Plantilla para una nueva versión (copia y rellena):

## X.Y — Título breve

### Novedades
- …

### Correcciones
- …
-->
