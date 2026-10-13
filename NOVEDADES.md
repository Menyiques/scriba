# Novedades de Scriba

Registro de cambios por versión. En cada *release*, añade una nueva sección **arriba**
(justo debajo de «Sin publicar»), con la fecha y los cambios agrupados en **Novedades**
y **Correcciones**. Al publicar, mueve lo acumulado de «Sin publicar» a la nueva versión.

> Formato basado en *Keep a Changelog*. Versionado: `MAYOR.MENOR` (`2.3`).

---

## [Sin publicar]

### Novedades
- (añade aquí lo que vaya entrando para la próxima versión)
- **`build_exe.bat` pone al día `NOVEDADES_distribucion.md`**, las novedades
  para el usuario que van en el zip de Scriba (`novedades_distribucion.py`): la
  versión del título sale de `scriba_info.py`, y una sección «Últimos cambios»
  lista los títulos de las entradas de este registro posteriores a lo que ya
  cuenta el texto escrito a mano (la marca `AUTO:INICIO desde="..."`), sin las
  internas (pruebas, scripts, módulos). Y al terminar, si PyInstaller ha ido
  bien, monta el paquete `Scriba vX.Y.zip` (`paquete_distribucion.py`): el
  `.exe`, el manual, esas novedades y los ejemplos, comprobado fichero a
  fichero.
- **Hasta 255 objetos y 256 variables en las máquinas (antes, 64 y 64).** Las
  tablas de estado del motor (`FLAGS`, `OBJLOC`, `OBJLIT`, `OBJOPEN`, `OBJLOCK`,
  `OBJIN`) ya no son de 64 fijos: cada juego las reserva a su medida
  (`game_engine.tamanos_equ`), así que uno pequeño gasta menos que antes (DAS
  BOOT deja 104 bytes más libres en el 128K) y uno grande llega a 255 objetos y
  256 variables. GRABAR y RECUPERAR copian las tablas a su tamaño. Comprobado
  con un juego de 255 objetos y 256 variables que usa los números más altos (el
  objeto 255 de contenedor, la variable 254, `LLEVAR_MAX` en el sitio de la
  255) en PC y en las siete máquinas, con el mismo resultado en todas.
- **Más memoria para el juego en las máquinas.** Lo que ha crecido el motor con
  esta versión (subrutinas, órdenes, `DOALL`, los verbos de serie) se recupera
  así: el banco de cada mensaje ya no es un byte por mensaje sino una tabla de
  tramos (en DAS BOOT, 600 bytes menos en la memoria plana del 128K); las
  tablas de llaves y de capacidad solo van si algún objeto las usa; y en el CPC
  la partida grabada (`SNAPBUF`) sale del motor y va detrás de `MTABLE`, así
  que el motor ya no se acerca a `&4000`. DAS BOOT cabe en las siete máquinas
  en sus cinco idiomas (en el 128K, en inglés, con 148 bytes de sobra).
- **Subrutinas: `SUB nombre` … `ENDSUB` y `CALL nombre`.** Un bloque con nombre,
  escrito al nivel de arriba de cualquier sección de condacts (lo normal, al
  final de las respuestas), que se llama desde cualquier sitio: respuestas,
  `before_turn`, `after_turn`, `on_start`, `on_enter`, temporizadores y otras
  subrutinas. `RETURN` sale de la subrutina antes de su final; `MATCH` y `END`
  cortan también a quien la llamó. Ve el verbo y los nombres del turno. Hasta
  8 llamadas una dentro de otra (la novena no se hace, y el probador de PC lo
  dice): una subrutina que se llame a sí misma sin parar no cuelga la partida.
  Hasta 256 por juego. En las máquinas, el cuerpo de una subrutina no tiene el
  límite de 255 bytes de una respuesta, así que también sirve para partir las
  largas. En el motor, `CALL` (64) y `RETURN` (65), con su pila de llamadas en
  memoria (`CSTK`, 6 bytes por nivel) y no en la del Z80, que en el 48K y el
  Next es de 128 bytes. «Validar juego» avisa de un `CALL` a una subrutina que
  no existe, de un `RETURN` fuera de una, de una `SUB` dentro de un `ON` o de
  un `IF`, de las repetidas y de las que no se cierran.
- **Órdenes a personajes: `JUAN, COGE LA LLAVE` y `PARSE`.** Si el jugador
  escribe un nombre, una coma y una orden, el verbo del turno es `DECIR` (un
  verbo de serie nuevo, en los cinco idiomas: decir/di/dile, say/tell,
  dizer/diz/diga, dir/digues, dire/dis) y el nombre, el del personaje; lo de
  detrás de la coma queda aparte. También vale `DECIR A JUAN "COGE LA LLAVE"`.
  En la respuesta, `PARSE` hace que `VERB`, `NOUN1` y `NOUN2` sean los de la
  orden durante el resto del turno; si no hay orden o no se entiende, no hay
  verbo (`IF VERB _`). Antes de las acciones de serie vuelven las palabras del
  jugador, así que una orden sin respuesta no la cumple el jugador. Una coma
  que no sigue a un nombre solo («coge la llave, la lámpara») es un espacio,
  como antes. En el Spectrum y el Next la coma y las comillas se escriben con
  SYMBOL SHIFT (N y P), que el teclado del motor no leía: ahora da también `.`,
  `'`, `-`, `?`, `!`, `:` y `;`. En el PCW no hay comillas (la coma sí).
- **`DOALL destino` … `ENDDOALL`: recorrer objetos.** El cuerpo se ejecuta una
  vez por cada objeto que esté en el destino (`@sala`, `INVEN`, `PUESTO`,
  `NADA`, `AQUI` o `#contenedor`), en el orden del juego, con ese objeto como
  `#DOALL`: vale en las sentencias (`GET #DOALL`, `PUT #DOALL @pozo`…), en las
  condiciones (`IF CARRIED #DOALL`, `IF #DOALL.lit`, `IF #DOALL = #libro`) y en
  los textos. Lo que el cuerpo mueve cuenta ya: el destino se mira al llegar a
  cada objeto. Hasta 4 uno dentro de otro (también a través de `CALL`).
- **`PRINT "{#objeto}"` escribe el nombre del objeto.** Como `{_variable}` su
  valor; con `DOALL`, `PRINT "Llevas {#DOALL}."`.
- **`AQUI` es un destino nuevo: la sala del jugador.** Vale en `DOALL AQUI`,
  `ISAT #x AQUI`, `#x.isat = AQUI` y `PUT #x AQUI`.

### Correcciones
- **Los mensajes de serie dicen lo mismo en PC y en las máquinas.** Una orden
  que se entiende pero que nada atiende da «No puedes hacer eso.» (las máquinas
  decían «No entiendo eso.»), y una que no se entiende, «No entiendo eso.» en
  todas partes (el PC añadía «Escribe AYUDA para ver los comandos», aunque
  Scriba no trae AYUDA de serie; el autor puede cambiar los dos en el editor).
  COGER, DEJAR, la descripción de la sala e INVENTARIO usan en las máquinas los
  mensajes enteros, con su punto final («Coges una llave.», «Aquí hay una
  roca.»), y responden igual que en PC a COGER sin nada («¿Qué quieres
  coger?»), a coger lo que ya llevas («Ya llevas una llave.»), al peso («No
  puedes cargar tanto peso.») y a EXAMINAR algo sin descripción («No ves nada
  especial.»). Los mensajes de sistema de las máquinas salen ahora del idioma
  del juego también cuando el autor no los ha traducido (antes, en español).
- **COGER TODO y DEJAR TODO pasan cada objeto por las respuestas del juego en
  las máquinas.** Como en PC: un `ON COGER X` con sus puntos o su negativa vale
  también al coger todo. Antes las máquinas los cogían o dejaban sin mirarlas.
- **El inventario de las máquinas es como el de PC.** Lo que llevas, con lo que
  hay dentro de cada contenedor («(contiene: ...)»), lo que llevas puesto
  aparte («Llevas puesto:») y, si hay límite de peso, el peso («Peso: 6/8»).
- **`LLEVAR_MAX`: sin la variable, o a 0, no hay límite de peso.** También en
  PC. El PC ponía 50 sin variable y, a 0, no dejaba coger nada que pesara; las
  máquinas no limitaban. El inventario solo dice el peso si hay límite.
- **El condact `GET` hace en las máquinas lo mismo que en PC.** No coge lo fijo (dice «No
  puedes coger eso.»), respeta el peso y deja como está lo que ya llevas
  (antes, a un objeto puesto se lo quitaba).
- **`_PESO_ACT` vale en las máquinas el peso que se lleva.** Como en PC (antes,
  0): el motor lo calcula cuando se lee, en una condición o en un `PRINT`.
- **`PRINT "{_PUNTOS}"` y las demás variables de sistema salían a 0 en PC.**
  Se guardan sin el guion bajo y la sustitución las buscaba con él.
- **`before_turn` ve la orden del turno también en PC.** El PC corría
  `before_turn` antes de analizar la orden, y ni él ni los temporizadores ni
  `after_turn` veían `VERB`, `NOUN1` y `NOUN2` (un `IF VERB SALTAR` en
  `before_turn` no se cumplía nunca); las máquinas sí. Ahora en todas partes
  se analiza primero y los tres ven las palabras del turno, como en PAWS.
- **En las máquinas, los temporizadores iban después de `after_turn`.** El
  manual y el PC dicen al revés: respuestas, acción de serie, temporizadores y
  `after_turn`. Ahora es así en todas partes.
- **El `on_enter` de una sala corre cuando se entra, también en las máquinas.**
  Hasta ahora iba al final del turno (detrás de `after_turn`), y el de la sala
  inicial después de la primera orden. Ahora, como en PC: al andar, después de
  describir la sala; al empezar, después de describir la inicial; y con `GOTO`,
  en ese momento, así que lo que va detrás del `GOTO` sale después. Un `GOTO` a
  la misma sala también lo corre.
- **Las máquinas no tenían PONERSE, QUITARSE, ABRIR, CERRAR, METER ni SACAR.**
  Respondían «No entiendo eso», aunque el manual decía que sí. Ahora hacen lo
  mismo que el intérprete de PC y con sus mismos mensajes (los del autor en
  `metadata.mensajes` o los de serie del idioma del juego): ponerse solo lo que
  llevas y se puede poner, abrir con la llave si la llevas (y decir lo que hay
  dentro), no meter nada en un contenedor cerrado ni pasar de su capacidad, y
  no sacar algo si luego llevarías demasiado peso. PONER X EN Y es METER. En el
  motor, los mensajes son plantillas (`game_engine.PLANTILLAS`, impresas por
  `print_tpl`) con el nombre del objeto donde toque.
- **EXAMINAR hace en las máquinas lo mismo que en PC.** Ve también lo que llevas puesto y
  lo que hay en un contenedor abierto, dice lo que tiene dentro un contenedor
  abierto (o que está vacío) y a oscuras no ve nada.
- **El peso, en las máquinas, cuenta lo que va dentro de los contenedores.**
  Como en PC: un saco con una piedra pesa los dos, y coger un contenedor lleno
  cuenta lo que lleva. Antes solo contaban los objetos sueltos, y en un byte que
  pasado 255 se daba la vuelta.
- **`ON COGER LINTERNA` no casaba nunca en las máquinas.** Las palabras de las
  cabeceras `ON` se buscaban enteras, y el vocabulario guarda 5 letras: una
  palabra de más de 5 daba 0, que en el hueco del verbo no casa nunca y en el
  de un nombre es «la regla no pide nada», o sea que `ON COGER LINTERNA`
  casaba con cualquier cosa que se cogiera. En PC iba bien. Ahora se buscan
  como en PC (5 letras, sin tildes), `ON CAVAR #arena` vale por el nombre de la
  arena también en las máquinas, y una palabra que no está en el vocabulario
  deja la regla fuera con un aviso en vez de hacerla casar con todo. Ningún
  juego de ejemplo lo usaba; en *La aventura original* (importada de DAAD) dos
  reglas con nombres con tilde casaban con cualquier nombre.
- **`IF VERB EXAMINAR` o `IF NOUN1 LINTERNA` no se cumplían nunca.** En las máquinas una
  palabra larga valía 0 (`NOUN1 0` es «no hay nombre») y en PC se comparaba sin
  recortar, así que no se cumplían nunca en ninguno de los dos. Ahora las dos
  partes las comparan en su forma de 5 letras (o por el nombre de un objeto).
- **Una respuesta vacía hacía RECUPERAR en las máquinas.** Un `ON` sin nada que
  compilar (solo comentarios) se rellenaba con el opcode 63 para no confundirlo
  con un alias, y el 63 es `RAMLOAD` desde la 3.0. Ahora es un 255, que el
  motor se salta.
- **`#objeto.isat = INVEN` (sin arroba) no se cumplía nunca en PC.** El
  intérprete tomaba `INVEN`, `PUESTO` y `NADA` por variables; las máquinas no.
- **Multiplicar, dividir y MOD en las máquinas.** El manual los daba por
  buenos, pero `nativecc` solo sabía sumar y restar: `LET _x = _a * 2` hacía
  fallar la exportación con un error interno. Ahora son tres operaciones del
  evaluador del motor (`MUL` 34, `DIV` 35, `MOD` 36) y también se compila el
  menos delante (`-_x`). Dan lo mismo que el intérprete de PC (división entera;
  entre 0, da 0) con una diferencia que ya había con `+` y `-`: en las máquinas
  las variables son bytes y lo que pasa de 255 da la vuelta (20 * 20 = 144).
- **Las máquinas solo admitían 90 salas y 90 objetos, aunque el manual decía
  255.** `recolecta` cortaba en 90, un resto del antiguo exportador a BASIC.
  Ahora el tope de salas es 252 (en el motor, 252-255 son las ubicaciones
  especiales de los objetos: dentro de un contenedor, puesto, en ninguna parte
  y llevado) y el de objetos, 255.
- **Más de 251 verbos o de 253 nombres distintos se perdían sin avisar.** Van
  numerados con un byte, y pasarse hacía que la palabra cayera en un comodín o
  en otra y dejara de entenderse. Ahora la exportación se para y dice cuántos
  hay. Los nombres se numeran seguidos (los de los objetos, los del vocabulario
  y TODO); antes el de cada objeto era su número de objeto, TODO el 95 y los
  demás desde el 100.
- **El manual decía «65.535 palabras de vocabulario».** Era el tamaño del
  contador de entradas, no un tope de palabras: ahora explica los topes de
  verbos y nombres y que el de sinónimos lo pone la memoria.

---

## 3.0 — 2026-10-12 — La distribución: Amstrad PCW, catalán y francés, grabar y recuperar, y exportarlo todo de una vez

### Novedades
- **El analizador nativo distingue 5 letras.** En 48K, 128K, Next, CPC, MSX2 y
  PCW el motor solo comparaba las 4 primeras letras de cada palabra y se
  quedaba con la primera de la tabla, donde van los verbos antes que los
  nombres. En los juegos traducidos eso dejaba sin entender palabras del
  camino principal: en DAS BOOT, PRISONER se leía como PRISE (abrir), el PASSE
  portugués y el PASSI catalán como PASSAR (dar), y en francés CARTE, PLAN y
  MONTRE como CARTA, PLANQUER y MONTER, así que la partida no se podía acabar
  en esas máquinas. En español también se perdían LIBROS, AGUA, BOLSA y
  CONTRASEÑA. Ahora el motor busca primero las 5 letras exactas y, si ninguna
  casa, las 4 de antes, así que todo lo que ya se entendía (EXAM, por ejemplo)
  se sigue entendiendo igual. La tabla de vocabulario ocupa un byte más por
  palabra (de 240 a 350 bytes más en DAS BOOT). Queda algún choque de 5 letras:
  en español CERRADURA sigue siendo CERRAR (CANDADO sí vale).
- **Nombre de los ficheros exportados** (Metadatos, «Nombre de los ficheros»,
  `metadata.nombre_export`). Si está relleno, es el principio del nombre de todo
  lo que se exporta a `dist/`, en vez del nombre del .yaml: con `DAS-BOOT` salen
  `DAS-BOOT_128kb_es.tap`, `DAS-BOOT_next_ca.nex`, `DAS-BOOT_windows_en.zip`…,
  también desde «Exportar todos los idiomas y máquinas». Vacío, todo sigue
  como antes (y no se guarda en el YAML). Se quitan los caracteres que Windows
  no admite en un nombre de fichero. DAS BOOT lo trae puesto (`DAS-BOOT`).
- **Exportar todos los idiomas y máquinas** (menú Archivo). Un diálogo con los
  idiomas del juego y las nueve exportaciones (48K, 128K, Next, CPC Modo 1 y 2,
  MSX2, PCW 8256 y 8512, Windows), todo marcado de entrada; recuerda las
  máquinas elegidas mientras dure la sesión. Los idiomas son el del juego
  abierto, uno por cada CSV traducido `<juego>_textos_<idioma>.csv` que haya
  junto al YAML (se aplica al juego tal como está en el editor, así que sale
  siempre al día) y, de los idiomas sin CSV, los YAML hermanos
  `<juego>_<idioma>.yaml` (como los de apolo11). Lo exporta todo a `dist/` en
  segundo plano, con barra de progreso y un botón para parar, con los mismos
  nombres que cada opción suelta; en Windows, cada `.exe` lleva el idioma en
  el nombre (`DAS BOOT_es.exe`, `DAS BOOT_ca.exe`…) para no pisarse. Un fallo (un juego que no cabe en 48K) no para el resto: el informe
  final dice, por idioma y máquina, el fichero o el error, y lo que cada
  máquina no soporta.
- **El borde de Metadatos es el de la partida, en todas las máquinas.** Hasta
  ahora el combo «Borde (loader)» solo llegaba al cargador del export en BASIC;
  los motores nativos lo ignoraban y arrancaban con el `BORDER` del `on_start`
  o en blanco. Ahora `metadata.border` es el borde del cargador del .tap (48K y
  128K), de la cabecera del .nex, del arranque del motor (Spectrum, Next, MSX2)
  y del CPC (convertido a su color del firmware; sin él, el del papel, como
  antes). El PCW no tiene borde de color y en Windows no hay borde. Un `BORDER`
  en el `on_start` sigue mandando después: es código del autor. El combo se
  llama ahora «Borde», se aplica nada más elegirlo (antes había que pulsar
  «Aplicar metadata» o se exportaba con el de antes) y avisa si el `on_start`
  pone otro.
- **Catalán y francés.** El vocabulario de serie (`vocab_base.py`: verbos,
  direcciones y preposiciones) y los mensajes propios del intérprete de PC
  tienen ya versión catalana (`ca`) y francesa (`fr`); antes un juego en esos
  idiomas tiraba del español (y en francés el SUR de serie, la dirección, se
  comía la preposición *sur*). En las máquinas nativas, las letras francesas y
  catalanas sin glifo propio se escriben sin acento en vez de con «?» (À, Ê,
  Ô, Ù, Ï, œ → A, E, O, U, I, oe…), y la ele geminada sale como «l.l».
- **Traducciones: los textos de los temporizadores.** `traduccion.py` exporta
  e importa también los literales del `on_expire` de cada temporizador
  (`tim.<id>.on_expire#n`), que en muchos juegos son los finales.
- **GRABAR y RECUPERAR la partida** (el RAMSAVE y el RAMLOAD de PAWS y DAAD),
  en el intérprete de PC y en las máquinas nativas salvo el 48K. GRABAR guarda
  una sola partida en memoria (variables, objetos, temporizadores, la sala y
  las pantallas puestas con `SCR @sala`), y RECUPERAR la devuelve y describe la
  sala. Ninguna de las dos gasta turno (ni `after_turn` ni temporizadores), y
  lo grabado sobrevive a «jugar otra vez», así que se puede recuperar después
  de un final malo. Palabras de serie: GRABAR, GUARDAR, SALVAR y SAVE;
  RECUPERAR, CARGAR, RESTAURAR y LOAD (en inglés SAVE y LOAD/RESTORE; en
  portugués GRAVAR y CARREGAR). Si una choca con una palabra del juego, manda la
  del juego. Los mensajes están en el catálogo (`grabada`, `no_grabar`,
  `recuperada`, `sin_grabar`). En el motor son los condacts `RAMSAVE` (62) y
  `RAMLOAD` (63), con la copia (unos 440 bytes, `SNAPBUF`) dentro del propio
  motor; el 48K no tiene sitio y GRABAR dice que esa versión no puede. En el
  reproductor de Windows, al acabar la partida ENTER empieza otra (antes se
  quedaba sin entrada), como en las máquinas nativas.
- **Imagen de presentación (`intro`)**. Si el juego trae una imagen `intro` en
  tira, como las de las salas (`img/Original/intro.jpg`, o la de cada máquina en
  `img/Spectrum/`, `img/AmstradCPC/`, `img/MSX/` o `img/PCW/`; en el Next la
  convierte el editor a `temp/Next/data/intro.nxi`), la presentación la pinta
  con el mensaje inicial en vez de la imagen de la sala inicial. Si no la hay,
  todo sigue como siempre. Es una pantalla suelta más: va la última de la lista
  de `SCR` (o reutiliza la suya si el guion ya usa `SCR intro`) y la pinta el
  condact nuevo `SCRINTRO` (61), que en una máquina que no la tenga cae en la
  imagen de la sala. Una intro de pantalla entera (4:3) se ignora, con aviso al
  exportar. En el reproductor de Windows, con intro la partida espera ENTER
  después del mensaje inicial, como el `PAUSE 0` de las nativas (sin intro no
  se para). En 48K no hay imagen de presentación. El editor la enseña en
  Metadatos, debajo de la de menú, como saldrá en la plataforma elegida (o la
  de la sala inicial, si no hay intro o no vale, con una nota que lo dice).
- **Importar DAAD (.ddb → YAML)**, en el menú Archivo (`ddb2scriba.py`,
  `daad_ddb.py`). Trae vocabulario, localizaciones con sus salidas, objetos,
  mensajes y la lógica: el proceso 0 como respuestas y el 1 y el 2 como
  before/after_turn; las llamadas PROCESS de cola se aplanan en bloques ON.
  Lo que no tiene equivalente (ventanas, gráficos, PARSE, DOALL, `@flag`,
  SAVE/LOAD) queda como REM y el informe lo cuenta. DAAD 1 y 2 de 8 bits.
- **Un clic ligero al teclear**, en todas las máquinas. Cada tecla que acepta la
  línea de órdenes (letras, BORRAR y ENTER) hace un clic corto; la pausa de
  «pulsa una tecla» y la portada quedan en silencio. En el Spectrum 48K/128K y
  el Next, por el altavoz (bit 4 del puerto &FE, dos ciclos de ~2 kHz, sin
  tocar el borde): la ROM lo hacía al teclear y el motor nativo no usa la ROM.
  En el CPC, un soplo de ruido por el canal A del AY a volumen bajo (~2 ms,
  con la misma `SNDREG` de los efectos). En el MSX2, el bit de clic del PPI
  (`&AB`, el del teclado de la BIOS). En el PCW, el pitido puesto y quitado
  (`&F8`, órdenes 11 y 12) en ~1 ms. En el reproductor de Windows, un tic de
  4 ms (`winsound`). Es una rutina por máquina, `KCLICK`, que `read_line`
  llama y que conserva todos los registros; `verify_click.py` cuenta los
  clics en 48K, 128K, CPC y PCW.
- **EX abrevia EXAMINAR** en todos los juegos y máquinas (`EX obj`, y `EX` a
  secas describe la sala, como EXAMINAR). Es una palabra de serie más de
  EXAMINAR en español, inglés y portugués (en inglés ya valía `X`), así que no
  hay que tocar el vocabulario de cada juego. Ningún juego de la carpeta usaba
  ya la palabra `ex`.
- **Nuevo comando SALIDAS (EXITS)** en el intérprete de PC y en las seis
  máquinas nativas: dice por dónde se puede ir, con la misma línea que cierra
  una descripción («Salidas: N E»), sin volver a describir la sala; a oscuras
  dice que está oscuro. Sus palabras de serie son SALIDAS, SALIDA, SALIR, EXITS
  y EXIT (en portugués SAÍDAS/SAIR). Es un condact nuevo, `EXITS`, y va como
  respuesta de serie al final de las del autor: un `ON SALIDAS` del juego se
  ejecuta antes que la de serie.
- **El verbo de abandonar la partida pasa a llamarse ACABAR** (canónico
  ACABA; también ABANDONAR, FIN y QUIT). Hasta ahora era SALIR, y las
  máquinas comparan solo las cuatro primeras letras de cada palabra: SALIDAS y
  SALIR eran la misma (SALI) y escribir SALIDAS acababa la partida. Los juegos de antes que declaran el verbo SALIR
  siguen funcionando: su verbo se toma por ACABAR (sin las palabras que ahora
  son de SALIDAS) y su bloque `ON SALIR` es el de abandonar. DAS BOOT ya
  usa ACABAR, con su AYUDA al día y pruebas nuevas en `tifon.pru`.
- **Amstrad PCW**: exportación a disco autoarrancable (`pcw_nativo.py`), con el
  mismo motor y la misma base de datos. 90×32 columnas en la pantalla de
  720×256, imágenes tramadas (Bayer) y comprimidas en ZX0. Para el PCW8256,
  un disco de 180K; para el 8512, «Exportar PCW 8512» saca dos discos: el A
  arranca y el B (720K) lleva la portada y las imágenes. `probar_pcw.py`
  pasa la batería `.pru` en un PCW simulado (`--8512`).
- **Editor: Ctrl+F en la pestaña de Referencia** busca texto en la página.
- **Editor: la tabla de objetos se ordena por cualquier columna** pinchando en
  la cabecera (ascendente, descendente y vuelta al orden del juego). Solo
  cambia la vista: el orden del YAML, que es el número del objeto en el motor,
  no se toca.

### Correcciones
- **Máquinas nativas: `#objeto.propiedad` no funcionaba.** `IF #pilas.carried`,
  `IF #linterna.lit` o `IF #caja.open` se compilaban como una variable nueva que
  valía siempre 0 (el motor nativo nunca aprendió lo que hacía el exportador a
  BASIC), y `LET #obj.lit = 1` ni siquiera compilaba. El validador no decía nada
  y en PC funcionaba. Ahora `carried`, `worn`, `present`, `open` e `isat` (con =
  y <> contra @sala, @INVEN, @ONME, @NOWHERE o #contenedor) van a los predicados
  del motor; `lit` y `locked`, a dos operaciones nuevas del evaluador (`OBJLIT`
  32 y `OBJLOCK` 33); y `fixed`, `weight`, `light_source`, `openable` y
  `wearable`, que en nativo no cambian, valen lo que diga el YAML. `LET
  #obj.lit|open|locked = 0/1` usa LIT/UNLIT, OPEN/CLOSE y LOCK/UNLOCK; las demás
  asignaciones dan un error claro al exportar. Comprobado propiedad a propiedad
  contra el intérprete de PC, antes y después de cambiarlas.
- **Máquinas nativas: un objeto que empezaba en el inventario (`location:
  '@INVEN'`) o puesto (`@ONME`) empezaba en ninguna parte.** El compilador solo
  miraba el campo `worn`. La linterna de El Faro no estaba en el inventario y,
  con lo anterior, El Faro no se podía acabar en ninguna máquina nativa.
- **Los ejemplos, al día para la 3.0.** El Faro y la demo de DAS BOOT ya no
  declaran el verbo SALIR (ahora SALIR enseña las salidas y ACABAR abandona) y
  su AYUDA lo dice; la demo, además, pasa a la convención de prefijos (`@sala`,
  `#objeto`, `_variable`). Los dos se juegan enteros en PC y en las siete
  máquinas nativas.
- **128K, Next, MSX2, PCW y 48K: las salidas de un juego traducido salían en
  español.** Los exportadores recogían los nombres de salida del catálogo de
  mensajes (`dir_n`…`dir_d`, que las traducciones traen) y no se los pasaban a
  la base de datos, así que salía la línea de serie: en inglés «Exits: O Bajar»
  en vez de «Exits: W Down», y quien tecleaba lo que veía recibía «I don't
  understand that». Ahora todos los pasan, como ya hacía el CPC. En español no
  cambia nada (los nombres de serie son esos): el .tap español sale idéntico.
- **Windows: una pantalla de `SCR` pedida sin arroba no salía** si el fichero
  la lleva (`SCR @sala_enigma morfina` con `@morfina.jpg`): el reproductor solo
  probaba el nombre tal cual. Ahora prueba con arroba y sin ella, como las
  máquinas nativas.
- **48K y 128K: VERSION decía «Sistema: spectrum128»** (o «spectrum48») en vez
  de «ZX Spectrum 128K»: los exportadores llaman a `scriba_info.ficha` con una
  clave que no estaba en su tabla.
- **Máquinas nativas: «Pulsa una tecla para jugar otra vez» salía en español
  en todos los idiomas.** No está en el catálogo de mensajes; ahora, si el juego
  no lo redefine, sale en el idioma del juego (es, en, pt, ca, fr).
- **Máquinas nativas, juegos traducidos: QUIT no abandonaba la partida.** El
  motor compara las 4 primeras letras y se queda con la primera entrada de la
  tabla de vocabulario que casa. Las claves de los verbos (identificadores
  internos, en español: QUITA, DECIR, COGER…) iban delante de las palabras de
  serie, y en DAS BOOT en inglés, portugués, catalán y francés, y en apolo11 en
  inglés y portugués, QUIT era QUITARSE una prenda («I don't understand that»).
  Ahora las claves que no son también una palabra de su lista van al final de la
  tabla (`spectrum_export.recolecta`): solo cambia el orden, no a qué verbo va
  cada palabra. En los juegos en español no cambia nada (comprobado combinación
  a combinación de 4 letras en DAS BOOT, apolo11, la demo y La aventura
  original). En inglés, además, DECIPHER (DECI) era DECIR y ahora es USAR, como
  dice el juego. En español QUIT sigue siendo QUITAR, que es palabra del juego,
  y por eso ya no sale en el manual.
- **Los ficheros exportados de un juego en catalán o francés se llamaban
  `_es`.** El nombre (`{juego}_{plataforma}_{idioma}`) solo conocía es, en y pt:
  `Operacion Tifon Negro_ca` salía como `Operacion Tifon Negro_ca_128kb_nativo_es.tap`.
  Ahora el idioma sale de `vocab_base.norm_lang` (también ca y fr) y el sufijo
  de idioma del nombre del juego se quita igual: `Operacion Tifon Negro_128kb_ca.tap`.
  Además, los `.tap` ya no llevan `_nativo` (todo es nativo desde que se fue
  Boriel): `_128kb_es.tap` y `_48kb_es.tap`.
- **Juegos traducidos: lo que dependía de palabras en español.** Al traducir
  DAS BOOT a cuatro idiomas salieron varias cosas que solo iban en español:
  - las direcciones: las claves de los verbos de dirección del juego (NORTE,
    ARRIB…) solo eran dirección si coincidían con una palabra del idioma del
    juego, así que en un juego traducido `ON ARRIB` no casaba al escribir
    AMUNT o MONTER. Ahora esas claves (`vocab_base.CLAVES_DIRECCION`) son
    dirección en cualquier idioma, en PC y en nativo;
  - COGER TODO: la palabra TODO es la de cada idioma (ALL, TUDO, TOT/TOTS,
    TOUT/TOUS; TODO y ALL valen siempre), en PC y en nativo;
  - los apóstrofos y guiones separan palabras (`posa't l'uniforme`,
    `mettre l'uniforme`, `prends-la`), en PC y en las máquinas nativas, y el
    intérprete de PC compara sin acentos (PÊCHEUR = PECHEUR);
  - la línea de salidas traducida sin `{dirs}` se quedaba sin las direcciones.
- **Dos sinónimos del mismo nombre ya no son dos nombres.** ABRIR CAJA FUERTE
  (CAJA y FUERTE son el mismo nombre) llegaba con ese nombre dos veces y no
  casaba con la respuesta de abrir la caja; ahora el repetido se descarta, en
  PC y en nativo.
- **PC: PONER X EN Y es METER X EN Y.** Con un segundo nombre, PONER se
  trataba como ponerse una prenda.
- **Traducciones: los objetos no se importaban.** Las claves de objeto llevan
  el `#` de su id (`obj.#linterna.name`) y el importador lo tomaba por el
  número de literal de un guion: ninguna traducción de nombre, descripción o
  mensaje inicial de objeto llegaba al juego. Ahora solo cuenta un `#` seguido
  de un número.
- **Máquinas nativas: un verbo de serie podía quitarle la palabra a un nombre
  del juego.** En el compilador nativo los verbos y los nombres van en tablas
  separadas, y si una palabra de serie coincidía con un nombre (en Tifón,
  CERRAR con la «cerra»dura del candado), el verbo se la quedaba y las
  respuestas con ese nombre dejaban de casar. Ahora manda la palabra del juego,
  como ya pasaba en el intérprete de PC.
- **Windows y CPC: a oscuras se veía la imagen de la sala.** El reproductor
  del .exe y el motor del CPC la pintaban igual; ahora, como en Spectrum,
  Next, MSX2 y PCW, una sala oscura sin luz no enseña su imagen, y aparece
  en cuanto hay luz. Una pantalla suelta de `SCR` se sigue viendo.
- **Next (y MSX2/PCW): tras EXIT, la partida siguiente salía sin imágenes.**
  El motor recordaba la última imagen pintada y no la volvía a pintar;
  reiniciar la partida la olvida.
- **Windows: «Exportar para Windows» ya no necesita nada al lado.** Pedía un
  `ScribaPlayer.exe` que había que compilar aparte y dejar junto a Scriba.exe;
  si no estaba, no exportaba. Ahora el reproductor es el propio Scriba.exe: la
  exportación lo copia con el juego (texto e imágenes, cifrado) pegado detrás,
  y ese ejecutable, al arrancar, ve que lleva un juego y lo abre en vez del
  editor. Sale un único .exe con el juego dentro, siempre con el intérprete de
  la misma versión que el editor.
- **Windows: el juego exportado salía sin imágenes.** Dentro del .exe,
  `ImageTk` necesita `PIL._tkinter_finder`, que PyInstaller no incluye solo
  (su hook de Pillow excluye tkinter). `build_exe.bat` (y
  `build_scribaplayer.bat`) lo añaden a mano.
- **CPC: tras salir el prompt, lo que se tecleaba no aparecía y se perdían
  letras.** En los ratos sin teclear el motor precargaba del disco las imágenes
  de las salas contiguas. Mientras el disco lee, el CPC no atiende al teclado:
  en un 6128 de verdad (y en MAME) eso eran un par de segundos por imagen en
  los que lo escrito no salía, y además se comía letras («inventario» llegaba
  como «ivnario»). Ya no se precarga nada: cada imagen se lee al entrar en su
  sala, cuando el jugador ya está esperando, y se guarda en los bancos del 6128,
  así que al volver sale al instante.
- **CPC: los discos cargaban a la mitad de velocidad.** Los sectores de cada
  pista iban seguidos (C1..C9); el formato DATA del CPC los entrelaza
  (C1 C6 C2 C7 C3 C8 C4 C9 C5) porque AMSDOS no llega a leer dos sectores
  consecutivos en la misma vuelta. Con ellos seguidos, cada sector costaba una
  vuelta entera del disco. Ahora `dsk.make_dsk` los graba entrelazados: DAS
  BOOT pasa de 45 a 22 segundos de carga (medido en MAME). Además, las
  entradas libres del directorio van a &E5, como las deja FORMAT.
- **CPC: la pausa de «texto lleno» se comía la primera letra de la orden.**
  Si el jugador, al ver el texto parado, se pone a escribir, esa letra sigue
  el texto y además se queda para la orden. ESPACIO o ENTER solo hacen seguir.
- **CPC: el texto largo se iba por arriba sin dar tiempo a leerlo.** El CPC
  escribía con TXT OUTPUT del firmware, que desplaza la ventana sin esperar:
  la presentación de DAS BOOT pasaba entera en un par de segundos. Ahora hace
  lo mismo que el Spectrum, el Next y el MSX2: cuenta las líneas desde la
  última orden (o tecla, o borrado) y, cuando se ha escrito una ventana entera
  y la siguiente línea tiraría una por arriba, espera una tecla.
- **CPC: la portada se veía dibujarse a trozos, muy despacio.** Cargaba derecha
  a la pantalla con su paleta puesta. Ahora el cargador pone las 16 tintas del
  color del fondo, la carga oculta y luego pone su paleta: aparece entera.
  Igual con las pantallas enteras del `SCR` (Modo 0).
- **CPC: al acabar la partida (FIN/SALIR) y pedir otra, el ordenador se
  reiniciaba.** La portada se recargaba con la paleta del juego (se veía con
  otros colores) y la música del título ya no estaba: vive en el buffer de las
  imágenes, que las salas habían pisado, y el reproductor saltaba a basura.
  Ahora la portada se recarga oculta y MUSIC.BIN se vuelve a leer del disco.
- **Las máquinas nativas no hacían caso a `start_location`**: el motor
  empezaba siempre en la primera localización del YAML (`nativecc` pasaba
  `startloc=0` a fuego). Ahora sale de `metadata.start_location`, como en el
  intérprete de PC, con el id con arroba o sin ella; si no es ninguna
  localización, se avisa y se empieza en la primera. Los juegos del
  repositorio tienen la salida en la primera sala, así que no cambian.

---

## 3.0 — 2026-09-27 — El CPC en Modo 1 y con el texto en los bancos del 6128, portadas lo primero y MSX2

### Novedades
- **MSX2**: exportación a cartucho MegaROM ASCII16 (`.rom`), con el mismo
  motor y la misma base de datos que las demás máquinas (`msx2_nativo.py`).
  SCREEN 5, 42 columnas, sonido por el PSG; las imágenes salen de `img/MSX`
  o, si no, de `img/Original`. `bateria_msx2.py` pasa la batería `.pru`
  sobre el cartucho en openMSX.
- **CPC en Modo 1**: 40 columnas e imágenes de 4 colores. Dos son las del
  texto (papel y pluma: las del `on_start`, si las pone, o negro y blanco) y
  las otras dos las elige cada imagen entre los 27 colores del CPC. Tramado
  ordenado y una gamma que conserva la noche de las escenas oscuras. Es lo que
  hace ahora *Exportar Amstrad CPC*; el Modo 2 (80 columnas, blanco y negro)
  sigue en el menú, en su propia entrada.
- **El texto que no cabe va a los bancos del 6128.** Si el juego no entra en
  la RAM base, se quedan planos los primeros mensajes (los del sistema, los
  nombres...) hasta llenarla y el resto va a `TEXTn.BIN`, que el cargador
  BASIC deja en los bancos 4-7. El motor copia cada mensaje por debajo de
  `&4000` antes de expandirlo. Un juego que cabe entero sigue arrancando en un
  464. Si el texto va en bancos y el ordenador no tiene RAM extra, el cargador
  lo dice con el mensaje de sistema `necesita_6128` (traducible). El motor ya
  no empieza siempre en `&1200`: sube lo que haga falta para que a BASIC le
  queden 4 KB libres debajo de `HIMEM` para el buffer de `LOAD` (si no,
  «Memory full»); Tifón Negro va en `&1500`.
- **Imágenes en ZX0** en vez de RLE: bastante menos disco. Tifón Negro entra
  con sus 23 salas, las 3 pantallas del SCR y el texto en 163 de los 178
  bloques. Comprimir en Python es lento, así que el resultado se guarda en
  `temp/CPC` del juego y la segunda exportación tarda segundos.
- **Caché de imágenes a medida**: cada imagen ocupa lo suyo en lo que deja
  libre el texto en los bancos, en vez de 12 ranuras fijas de 5 KB.
- **La portada, lo primero que se carga** en 48K, 128K y CPC, para que se vea
  mientras carga el resto. En las cintas de 48K y 128K es un `LOAD "" SCREEN$`
  antes que nada (sin los «Bytes:» encima); en el 48K, que hasta ahora no
  tenía portada, el juego la deja puesta hasta que pulsas una tecla. En el
  CPC el cargador pone la paleta de la portada y la carga antes que la
  música, el texto y el juego, así que se ve dibujarse en sus colores (antes
  cargaba en negro). El cargador del CPC es más largo por las 16 tintas y el
  motor empieza donde haga falta para que BASIC tenga su buffer de 4 KB.
- **VERSION en el CPC** (la ficha, como en las otras máquinas) y la imagen de
  la sala de salida puesta antes de la presentación, que sale debajo.
- **`probar_cpc.py`**: la batería `.pru` sobre el `.dsk` real, en el
  simulador: interpreta el cargador BASIC, imita el firmware (texto, teclado,
  disco, tintas) y pagina la RAM de 128K. Cada vez que se describe una sala
  compara la imagen de la pantalla con la convertida. Tifón: 64 de 64 en Modo
  1 y en Modo 2. `verify_scr.py` prueba ya el SCR del CPC en el simulador.
- Las imágenes de sala de las traducciones (ids sin arroba, como `playa`)
  encuentran los másteres `@playa.png` de `img/Original`; también las del SCR
  (`@morfina.jpg`).

### Correcciones
- **CPC: la tabla de los acentos pisaba la base de datos en los juegos
  grandes.** Estaba fija en `&8000` (256 bytes) y el buffer de disco de 2 KB
  iba justo detrás de la DB aunque se metiera en el de imagen; el presupuesto
  no contaba ninguno de los dos. Apolo 11 acababa en `&8996`. Ahora van detrás
  de la DB, en los 32 KB centrales, y cuentan.
- CPC: al buscar la RAM extra se escribía en los bancos 4 y 5 sin devolver lo
  que había.

---

## 2.16 — 2026-09-26 — ENTER sin nada tiene su propio mensaje

### Novedades
- **Mensaje de sistema `linea_vacia`**: lo que sale al pulsar ENTER sin
  escribir nada. Cada juego lo redacta en la ventana de mensajes del editor
  (p. ej. «El tiempo pasa.» en un juego con reloj); si se deja vacío, sale el
  de «No entiendo eso.», como hasta ahora. Una línea con palabras que el
  parser no conoce sigue diciendo «No entiendo»: solo cambia la línea vacía.
  En las máquinas nativas es el mensaje de sistema `SVACIO` (NSYS pasa a 22).

### Correcciones
- **En PC, ENTER sin nada no hacía nada**: ni mensaje ni turno, así que el
  reloj del juego no avanzaba, mientras que en Spectrum, Next y CPC sí. Ahora
  en el intérprete de PC, en el reproductor del .exe y en la ventana de
  prueba del editor es un turno completo (before_turn, temporizadores y
  after_turn), igual que en las máquinas nativas.
- Las baterías de pruebas (`.pru`) admiten `(ENTER)` para pulsar ENTER sin
  escribir nada.

---

## 2.15 — 2026-09-26 — En el 48K, efectos FX y pantallas SCR entran si caben

### Novedades
- **48K: los efectos FX (PLAY) son lo primero que se sacrifica.** El 48K de
  serie no tiene AY y los efectos ocupan 5 bytes por frame en el mapa plano:
  si el juego no cabe, entran los que quepan en el orden de la pestaña FX y
  los demás quedan mudos (su PLAY compila igual), como ya hacía el CPC. El
  informe de presupuesto dice cuáles se quedan fuera. Primero se prueba a
  guardar las descripciones de los objetos quitando FX; si ni así caben, se
  quitan las descripciones y vuelven los FX que quepan.
- **48K: las pantallas SCR también se ajustan al sitio.** Van comprimidas en el
  mapa plano; si ni sin FX ni sin descripciones cabe el juego, se quitan
  pantallas: primero las sueltas (`SCR nombre`), de la última en aparecer a la
  primera, y solo después las que se asignan a una sala (`SCR @sala nombre`),
  que hacen de imagen de la sala. Luego vuelven las que quepan. Una pantalla
  quitada no pinta nada, como si faltara el fichero. El informe lo dice.

---

## 2.14 — 2026-09-24 — Un texto repetido se guarda una vez

### Novedades
- **Los textos fijos iguales comparten mensaje** en las máquinas nativas
  (48K, 128K, CPC, Next). Dos objetos con el mismo nombre (un PNJ despierto y
  dormido, el U-571 amarrado y hundido), dos descripciones iguales o un PRINT
  que repite el mensaje inicial de un objeto ya no se guardan dos veces. Los
  PRINT iguales ya se compartían; ahora también los nombres, descripciones y
  mensajes iniciales. En *Tifón Negro* son 92 bytes menos en el 48K. Los
  mensajes de sistema no entran: van en índices fijos.

---

## 2.13 — 2026-09-24 — COGER TODO y DEJAR TODO hablan claro, y el ensamblador ya no calla

### Correcciones
- **COGER TODO sin nada que coger** decía «No ves eso aquí.» en las máquinas
  nativas; ahora dice el mensaje `nada_coger` («No ves nada que puedas coger
  aquí.»), como en PC. **DEJAR TODO sin nada** decía «No llevas eso.»; ahora
  `nada_dejar` («No llevas nada que dejar.»).
- **COGER TODO a oscuras** cogía a ciegas lo que hubiera en la sala. Ahora
  dice `oscuro_hay` («Está demasiado oscuro para ver qué hay.») y no coge
  nada, igual que en PC.
- Son tres mensajes de sistema nuevos (`SNADAC`, `SNADAD`, `SOSCHAY`; NSYS
  pasa de 18 a 21), editables desde la pestaña de mensajes del editor.
- **`z80asm`: un símbolo sin definir es un error en la pasada final.** Antes
  valía 0 en silencio: el motor de Spectrum no llevaba los equates nuevos y
  COGER TODO imprimía el mensaje 0 («No puedes ir en esa dirección») sin que
  nada avisara. Ahora el ensamblado se para y dice qué símbolo falta.

---

## 2.12 — 2026-09-23 — El inventario, un objeto por línea

### Correcciones
- **INVENTARIO en las máquinas nativas salía todo seguido**, sin comas ni
  saltos: «Llevas: un paquete de cigarrillos Juno una cantimplora de la
  Wehrmacht una linterna militar». Ahora `do_inven` pone cada objeto en su
  línea con «  - », igual que el intérprete de PC. Vale para 48K, 128K, Next
  y CPC (motor común).

---

## 2.11 — 2026-09-23 — EXAMINAR describe los objetos en las máquinas nativas

### Novedades
- **Las descripciones de los objetos llegan al motor nativo.** Hasta ahora
  `nativecc` no las emitía y EXAMINAR imprimía solo el nombre en 48K, 128K,
  Next y CPC (en PC sí salían). Ahora cada objeto lleva su descripción como
  un mensaje más (tabla nueva en la cabecera, `DBB+87`) y `do_exam` la
  imprime; si el objeto no tiene, el nombre como antes. Las reglas `ON EXAMI`
  del autor siguen mandando: si una casa, el motor no llega a describir.
- **Si no caben, se quedan fuera con aviso.** En 48K y CPC, cuando la base de
  datos con descripciones se pasa del mapa plano, el export las omite
  (`obj_desc=False`), lo dice en el informe y EXAMINAR vuelve a dar solo el
  nombre. En CPC van antes que los FX: Apolo 11 las incluye a cambio de un
  efecto mudo. En 128K y Next van a bancos con el resto del texto y caben.
- **El editor edita el mensaje inicial de los objetos.** El formulario de
  Objetos tiene un campo «Mensaje inicial» bajo la descripción (con la misma
  regla de columnas). Antes solo se podía tocar en el YAML a mano. Vacío =
  sin mensaje: la clave desaparece del YAML y el motor dice «Aquí hay…».
- **Pruebas por máquina en los `.pru`:** `=== [128 next pc] nombre` corre esa
  prueba solo en las máquinas listadas (48, 128, next, pc); en las demás se
  salta sin contar ni fallar. Sirve para lo que no cabe en 48K.

### Correcciones
- `verify_next` (arnés plano de 64K) recompila sin descripciones si el juego
  no cabe bajo la pila; con Tifón desbordaba los 64K y el tick de los
  temporizadores fallaba por corrupción, no por el motor.

---

## 2.10 — 2026-09-23 — Respuestas compartidas y tres bugs viejos del motor

### Novedades
- **Las respuestas con alternativas ya no se guardan por triplicado.** Un
  `ON (USAR OR METER OR PONER) (PILAS OR LINTE) (LINTE OR PILAS)` generaba doce
  entradas con el cuerpo completo repetido en cada una. Ahora `build_game_db`
  guarda cada cuerpo una vez y las demás entradas llevan longitud 0 y un
  puntero (el motor lo resuelve en `run_response`). También se comparten dos
  reglas distintas con el mismo cuerpo. En Tifón son 3,8 KB menos; Apolo 11
  gana 900 bytes en CPC sin tocar el juego. El cuerpo de una respuesta sigue
  limitado a 255 bytes: ahora el export lo dice en vez de corromper la tabla.
- **Tifón 2.0: seis cadenas de puzles nuevas** (cantimplora → prisionero →
  cinta buena entre tres; cartas → botas → llave → prisionero libre → ganzúa
  → candado del túnel; un solo paquete de pilas para linterna, detonador y
  señal a Peregrine; Obstler → Brandt → pase; mochila → cigarrillos → Losung
  del Bootsmann; reloj → ronda del maquinista). Título DAS BOOT, subtítulo
  Operation Black Typhoon, 130 puntos, misión desde las 03:30. Batería de 40
  pruebas en PC, 48K, 128K y Next. **El CPC queda fuera para este juego**: no
  cabe ni recortando.

### Correcciones
- **`IF … PRESENT #obj …` falso saltaba mal en las cuatro máquinas nativas.**
  `c_if` guardaba la longitud del cuerpo en `ctmp`, y `obj_present` (PRESENT
  y ABSENT) usa `ctmp` de borrador: el salto era el índice del objeto en vez
  de la longitud. Según el objeto, se comía o ejecutaba bytecode a ciegas
  (en Tifón acababa con un GOTO a la playa). `LET` con una expresión que
  llevara PRESENT tenía el mismo fallo. Ahora ambos usan `iftmp`.
- **`END` dentro de una respuesta corta el bloque**, como en PC. Antes
  levantaba `quitf` y seguía ejecutando lo que viniera detrás en la misma
  respuesta (se veía el final y luego más texto).
- **`nativecc` no emitía las descripciones de los objetos**: en las máquinas
  nativas EXAMINAR sólo imprime el nombre. No se ha tocado (pendiente de
  decidir), pero queda anotado: toda pista de un objeto debe ir en un
  `ON EXAMI` propio si el juego sale de PC.

---

## 2.9 — 2026-09-23 — CREATE y PUT con destino en las máquinas nativas

### Correcciones
- **`CREATE #obj destino` y `PUT #obj destino` ignoraban el destino en 48K,
  128K, Next y CPC.** El compilador nativo los convertía en `CREATE`/`DROP` a
  secas, que dejan el objeto en la localización actual. En Tifón,
  `CREATE #credencial_falsa INVEN` dejaba la credencial en el suelo de la
  trastienda (quien no la cogía se quedaba en el puesto de control), y el
  paquete de pilas de repuesto aparecía a los pies del jugador en vez de en el
  sitio al azar. Ahora, con destino, compilan al `PLACE` del motor, que ya
  admitía localizaciones y los centinelas `INVEN`, `PUESTO` y `NADA`; sin
  destino siguen siendo `CREATE`/`DROP`. El intérprete de PC siempre lo hizo
  bien: la batería de Tifón entraba en la base por la brecha y nunca pasó por
  el puesto de control con la credencial, así que no se vio. Ahora sí lo prueba.

---

## 2.8 — 2026-09-23 — El condact SCR: pantallas donde tú digas

### Novedades
- **`SCR nombre`: pinta una pantalla del disco de imágenes.** Un condact nuevo,
  en las cinco máquinas. La imagen se busca junto a las de localización (por
  nombre, con o sin extensión) y su proporción decide el tamaño:
  - **4:1 (256×64)**: una tira en el tercio superior, con el texto debajo, igual
    que la imagen de una sala.
  - **4:3 (256×192)**: una pantalla entera que tapa todo hasta el siguiente
    `CLS` o `DESC`, o hasta que el jugador se mueve.
- **`SCR @sala nombre`: reasigna la imagen de una localización.** A partir de
  ahí esa sala se describe con esa pantalla en vez de con su imagen, y si el
  jugador está en ella se refresca en el acto. Útil para cambiar el decorado de
  un sitio según lo que pase (una base intacta y luego en llamas).
- Cada máquina guarda las pantallas donde guarda las de sala: el **48K** las
  lleva comprimidas (ZX0) en el mapa plano; el **128K** y el **Next**, en bancos
  (en Next, Layer 2 con su paleta); el **CPC** las lee del disco (`SCRnn.SCR`,
  las de 24 filas en Modo 0 con sus 16 tintas, como la portada). El motor es
  común: un símbolo de plataforma `SHOWSCR`/`SCRREST` que cada una resuelve a su
  manera, igual que con las imágenes y las muestras.
- El editor convierte las imágenes que use algún `SCR` al exportar a Next, como
  ya hacía con las de sala.
- `verify_scr.py`, 15 comprobaciones (48K, 128K, Next y el export del CPC): la
  tira de 8 filas deja el texto debajo, `SCR @sala` repinta y la sala se sigue
  describiendo con esa pantalla, la de 24 tapa todo y se va con el `DESC`.

### Presupuesto
- El presupuesto de cada exportación desglosa las pantallas del SCR: en 48K
  cuentan contra el mapa plano; en 128K y Next, contra los bancos; en CPC, contra
  el disco (178 bloques de 1K), y si no caben todas entran las primeras y se
  avisa de las que no.

---

## 2.7 — 2026-09-23 — El texto, a los bancos

### Novedades
- **En 128K y Next el texto del juego vive en los bancos, y con el la musica
  del titulo y los FX.** El mapa se parte en dos con una regla simple: por
  debajo de `&C000`, todo lo que el motor necesita siempre (codigo, indices,
  vocabulario, objetos, respuestas y la pila, ahora en `&BFF0`); `&C000-&FFFF`
  es una ventana de paginacion pura por la que se leen, cada uno de su banco,
  los mensajes, la musica, los FX, las imagenes y las muestras. Como nada
  permanente vive en la ventana, se pagina cuando hace falta y no hay que
  devolver nada a su sitio.
  - El texto era el **64 % de la base de datos** (15.796 bytes en Tifon
    Negro). En el mapa plano de Tifon quedan ahora 7.591 bytes libres en 128K
    y 7.609 en Next, frente a 2.412 y 2.599; Apolo 11 pasa de 3.715 a 9.717.
  - **La musica del titulo suena entera**: 6.577 bytes en vez de los 4.481 a
    los que se recortaba por no caber plana. El recorte solo actua ya si una
    cancion pasara de un banco (16K).
  - La base de datos lleva, por mensaje, el banco donde esta (tabla `msgbnk`) y
    su direccion dentro de la ventana; `expand_msg` llama a `TXTPAGE` antes de
    seguir el puntero. `TXTPAGE` es un simbolo de plataforma: en 48K y CPC no
    hace nada (su texto sigue plano, como siempre); en 128K escribe el banco en
    `&7FFD`; en Next pone sus dos paginas de 8K en las ranuras 6 y 7 del MMU.
  - En el 128K desaparece el baile de la pila de emergencia en `&5C00` que
    hacia falta para paginar con la pila en `&FF00`: ya no hay nada que
    proteger.
  - El presupuesto de cada exportacion lo refleja: el mapa plano son 24.432
    bytes (`&6000-&BF70`) y los bancos se desglosan en texto, FX, musica,
    imagenes y muestras.
  - **Y son seis bancos, no cinco: 98.304 bytes.** El banco 0 era la RAM alta
    del juego (la parte alta de la base de datos y la pila en `&FF00`) y no se
    podia tocar. Con el mapa plano acabando bajo `&C000` es un banco mas. Va el
    ultimo en el orden de carga (1, 3, 4, 6, 7 y 0) para que los cinco de
    siempre no cambien de sitio.
- `verify_128` (15 comprobaciones) y `verify_next` prueban que la descripcion
  de la sala sale de su banco, que la musica se lee del suyo y que la pila
  nunca asoma por la ventana. El simulador emula ahora las ranuras 6 y 7 del
  MMU del Next, y el arnes `ejecutar` pone su pila bajo `&C000` cuando el
  binario tiene el texto en bancos (antes la ponia en `&FFEE`, justo dentro de
  la ventana, y la primera paginacion se la llevaba).

### Correcciones
- **`[+5 puntos]` sale en linea nueva.** ADDSCORE imprimia pegado a lo que
  hubiera antes (el mensaje de la respuesta, normalmente) y dejaba un salto
  detras; ahora hace como MESSAGE y SCORE: salto delante y ninguno detras, que
  es como lo escribe el interprete de PC.
- `_trunca_psg` reventaba con un `IndexError` cuando la cancion cabia entera:
  nunca habia pasado porque nunca cabia.

### Avisos
- El CPC pierde 3 bytes de margen por los dos campos nuevos de la cabecera de
  la base de datos (comun a las cuatro maquinas), y con Tifon Negro eso deja
  fuera un FX mas (`senal`): 5 mudos en vez de 4. El arreglo de fondo del CPC
  sigue siendo subir `imgbuf` por encima de `&8B00`.

---

## 2.6 — 2026-09-22 — El juego, dentro del ejecutable

### Novedades
- **«Exportar para Windows» da un solo `.exe`, y el juego ya no viaja en texto
  plano.** Hasta ahora dejaba el `game.yaml` al lado del ejecutable: cualquiera
  que abriera la carpeta con el Bloc de notas tenia delante las soluciones de
  los acertijos y el final. Ahora el juego entero —texto e imagenes— va en un
  bloque serializado, comprimido y cifrado (`scriba_pack.py`) que se PEGA AL
  FINAL de una copia del reproductor. El jugador recibe un fichero y en su
  carpeta no hay nada que leer.
  - El reproductor se lee a si mismo al arrancar y lo descifra **en memoria**:
    no se escribe en disco en ningun momento.
  - Cada exportacion lleva su propia sal, asi que dos copias del mismo juego no
    se parecen entre si.
  - Se sigue leyendo el formato antiguo (game.yaml + player_cfg.json +
    img/Original al lado del .exe) para que los paquetes ya repartidos no dejen
    de funcionar.
  - `build_game_exe.py` (un `.exe` por juego, compilado con PyInstaller) tenia
    el mismo agujero por otra puerta: un `.exe` *onefile* se descomprime al
    arrancar en una carpeta temporal, donde el `.yaml` volvia a estar en claro.
    Ahora lo que mete —y lo que aparece en ese temporal— es el bloque cifrado.
  - Hasta donde protege: el reproductor tiene que leer el juego para jugarlo,
    asi que la clave va dentro del binario. Es un candado contra la
    curiosidad, no una caja fuerte.
- La pestaña «Muestras» del editor pasa a llamarse **«Sonido WAV»**, que es lo
  que se importa ahí y lo que la gente busca.
- **`verify_pack.py`**, 12 comprobaciones: el juego vuelve identico, las
  imagenes byte a byte, ninguna de las 638 frases largas de Tifon Negro se lee
  en el bloque, y el reproductor lo encuentra solo dentro del `.exe`.

### Notas
- **Por que se puede pegar algo al final de un `.exe` de PyInstaller**: su
  arranque no espera la cabecera en el ultimo byte, la busca escaneando de
  atras hacia delante en trozos de 8 KB (`pyi_utils_find_magic_pattern`),
  precisamente para sobrevivir a las firmas digitales. Como se queda con la
  primera aparicion que encuentra yendo hacia atras, lo unico que hay que
  garantizar es que el bloque no contenga por casualidad ese patron de 8 bytes:
  `empaqueta()` lo comprueba y, si pasara, cambia la sal y vuelve a cifrar.

---

## 2.54 — 2026-09-22 — Se acabo la partida, y vuelta a empezar

### Novedades
- **Fuera Boriel.** Las cuatro maquinas salen del motor nativo Z80 desde la
  v2.53, y desde esta ya no hay otro camino: se han quitado del menu del editor
  las «Exportaciones heredadas (ZX BASIC / Boriel)» y el dialogo de
  configuracion del TAP, y con ellos todo lo que invocaba `zxbc` —unas 830
  lineas del editor, incluidos los exportadores a BASIC de CPC y Next que ya no
  estaban ni en el menu—. Se han borrado siete ficheros: `next_export.py`,
  `cpc_export.py`, `empaqueta_cpc.py`, `empaqueta_nextap.py`,
  `construye_nextap.py`, `empaqueta48.py` y `build_nextap.bat`.
  - `build_exe.bat` ya no arrastra esos cuatro modulos ni empaqueta los
    `print42/64_*.bas` dentro del `.exe` (siguen en el repositorio: son la
    fuente de la que `genera_font42.py` saca la tabla del motor nativo).
  - Queda un resto a proposito: el transpilador a ZX BASIC sigue DENTRO de
    `spectrum_export.py`, ya sin que lo llame nadie. Ese fichero es ademas la
    biblioteca de la que tiran los cinco exportadores nativos y los
    verificadores (`recolecta`, los acentos, el reproductor PSG, dzx0, las
    imagenes), asi que separarlo es un paso aparte, con su propia tanda de
    pruebas.
- **Al terminar, otra partida.** Hasta ahora el motor salia de `mainloop` con un
  `RET` y devolvia el control al BASIC de la maquina: en el Next, el copyright
  de Sinclair Research; en cinta, a recargar. Ahora se ofrece otra partida
  («Pulsa una tecla para jugar otra vez.», mensaje de sistema `SOTRA`, traducible
  como los demas) y al pulsar se vuelve a la **pantalla de presentacion con su
  musica** y de ahi al juego reinicializado, que es lo que hacia cualquier
  aventura de los ochenta.
  - **128K y Next**: se repinta la portada de su banco y el reproductor PSG
    rebobina, asi que la musica suena entera otra vez.
  - **CPC**: la portada la dejaba puesta el cargador BASIC y el juego escribe
    encima, asi que ahora se vuelve al Modo 0 y se **recarga `TITLE.SCR` del
    disco** —lo mismo que ya hace con las imagenes de sala—. Sin disco en la
    unidad no hay portada, pero la partida nueva arranca igual.
  - **48K**: no hay portada que repintar (la suya es la pantalla de carga de la
    cinta), pero la partida nueva empieza con la pantalla limpia.
- **El presupuesto de memoria, en la ventana de cada exportacion.** Las cuentas
  de `presupuesto.py` ya no salen solo cuando algo NO cabe: cada exportacion
  (48K, 128K, Next y CPC) termina enseñando en que se va la memoria y cuanto
  queda libre, en una tabla monoespaciada —motor, musica del titulo, base de
  datos, imagenes en bancos— con su tope delante. Antes eso solo existia como
  excepcion, o sea que el autor se enteraba de lo justo que iba el juego el dia
  que se pasaba.
  - La ventana de resultado es nueva (`_ventana_resultado`): sustituye al
    *messagebox*, donde las columnas no cuadraban por ser fuente proporcional,
    y de paso **enseña los avisos del exportador**, que hasta ahora se quedaban
    en el diccionario de info sin que los viera nadie: los efectos FX que no
    caben en el CPC y quedan mudos, la musica recortada del 128K, las salas que
    se leeran del disco cada vez.
  - El Next tambien pasa por `presupuesto.comprueba` para el mapa plano, que era
    el unico backend que se quejaba a mano.
- **`verify_reinicio.py`.** Arnes nuevo, 20 comprobaciones, que juega el final de
  la partida en los tres binarios (48K, 128K y Next) y comprueba que se sale de
  `mainloop`, que se pasa por la portada y arranca la musica, que `quitf` vuelve
  a cero y el jugador a la sala inicial, y que no queda en pantalla el texto de
  la partida anterior.

### Correcciones
- **La pantalla se limpia antes de reiniciar.** Sin esto, la portada del 128/Next
  se levantaba sobre el texto de la partida anterior y en el 48K la partida nueva
  empezaba debajo del «FIN DEL JUEGO» de la anterior.
- **El arnes `.pru` sabia que la partida habia acabado porque el motor hacia
  `RET`** (una direccion postiza en la pila). Como ya no lo hace, se vigila la
  etiqueta `gameover` del motor, justo detras del `call mainloop`: se llega a
  ella con la pantalla del final todavia puesta, que es lo que la prueba quiere
  leer.
- **`probar_pc.py` tardaba 30 segundos por cada final de partida.** Esperaba el
  turno con un `get(timeout=30)` a secas y, cuando la partida terminaba, no habia
  nadie que soltara la ficha. Ahora mira ademas si el hilo del juego sigue vivo:
  la bateria de Tifon Negro ha pasado de mas de dos minutos a 3 segundos.

---

## 2.53 — 2026-09-21 — El motor nativo en 48K, y los juegos vuelven a terminar

### Novedades
- **ZX Spectrum 48K con el motor nativo Z80, sin Boriel.** `spectrum48_nativo.py`
  ensambla motor, capa de plataforma y base de datos en el mapa plano
  `&6000-&FF00` y empaqueta un `.tap`. La capa de plataforma del Next ya era un
  48K —imprime sobre la pantalla ULA, lee el teclado por la matriz del puerto
  `&FE` y no toca la ROM—, asi que no se ha reescrito: se le sustituyen las
  siete instrucciones Z80N que usaba (`PIXELAD`, `PIXELDN`, `ADD HL,nn`,
  `ADD HL,A`) por Z80 normal. Operacion Tifon Negro ocupa 31.530 de los 40.704
  bytes del mapa; entran los nueve juegos del repositorio.
- **`probar_pc.py`: la bateria `.pru` sobre el interprete de Python.** Los otros
  corredores van todos contra el motor nativo; este va contra `interpreter.py`,
  que es el que mueve «Probar juego» del editor y el `.exe` de PC, y que no
  tenia ni una prueba automatica. Mismo `.pru`, mismas ordenes y mismo juez que
  `probar_48.py`, de modo que una divergencia entre los dos motores sale sola.
- **ZX Spectrum 128K con el motor nativo Z80.** `spectrum128_nativo.py`: el
  48K nativo mas los bancos. El juego entero sigue en el mapa plano
  &6000-&FF00 y los cinco bancos conmutables quedan ENTEROS para las
  imagenes, porque el texto viaja comprimido dentro de la base de datos y ya
  no compite con ellas. En el export de BASIC el texto se lleva 26.176 de los
  81.920 bytes de banco y deja 10.863 libres; aqui quedan **37.039**, que a
  1.951 bytes de media por pantalla sube el techo de unas 28 imagenes a unas
  42. Las imagenes son los mismos flujos ZX0 que ya produce
  `spectrum_export.imagenes_128k`, con su misma verificacion, y el
  descompresor es el `dzx0_standard` de Saukas/Urusergi que ya usaba el
  export. Tifon Negro: 31.887 bytes de RAM principal, 44.881 de imagenes en
  tres bancos, `.tap` de 77.224 frente a los 108.044 del build de BASIC.
- **`verify_48.py` y `verify_128.py`**: arneses de validacion del 48K y del
  128K, hermanos de `verify_next.py` y `verify_cpc.py`. El del 128K compara la
  imagen descomprimida byte a byte con la que saca el simulador de dzx0, y
  comprueba que el motor devuelve el banco 0 a su sitio (si no, se llevaria
  por delante la mitad alta de su propia base de datos).
- **`probar_128.py`**: la bateria `.pru` sobre el binario de 128K, con la
  paginacion del puerto &7FFD emulada.
- **`bateria_next --maquina 48|128`**: la bateria sobre EMULADOR llega a las
  otras dos maquinas. Hasta ahora 48K y 128K solo se probaban en el simulador
  de Python; ahora el mismo binario que va en el `.tap` se envuelve en un
  `.nex` y lo arranca jnext, con su Z80 ciclo a ciclo, su ULA y -- en 128K --
  su paginacion por &7FFD y el descompresor de imagenes. El `.tap` sigue
  siendo lo que se distribuye: lo que NO cubre esta bateria es el cargador
  BASIC de la cinta.
- **El guion de la bateria ya no cabe en una pagina.** Se lee por una ventana
  de 8 KB sobre la ROM y el motor salta a la pagina siguiente al agotarla, asi
  que una bateria larga deja de ser un problema del que escribe las pruebas.
  Hacia falta: `tifon.pru` pasa de 8 KB al partir en cuatro la prueba del
  patio, y con el limite de una pagina el `.nex` de pruebas ya no compilaba.
- **Presupuesto de memoria en las cuatro maquinas** (`presupuesto.py`). Cada
  backend tenia sus topes y avisaba a su manera, o no avisaba: el 48K y el CPC
  no miraban nada y sacaban un binario corrupto, y el Next no contaba sus
  bancos. Ahora el aviso es el mismo en todas y dice las DOS cosas que hacen
  falta: que ocupa cada partida y por cuanto te pasas.
- **En CPC los FX entran hasta donde haya hueco.** Es la maquina mas apretada
  -- su RAM util acaba en &8B00, donde empieza el buffer de imagen -- y con los
  doce efectos nuevos Tifon Negro se pasaba por 517 bytes: el `.dsk` habria
  salido con la base de datos solapando el buffer. Ahora entran los que quepan
  EN EL ORDEN de la pestana FX, y los que se quedan fuera no rompen la
  numeracion (su ranura va a cero y `PLAY` sale mudo). De paso, las imagenes
  que no entran en las 12 ranuras de cache del CPC dejan de caerse en silencio.
- **Sonido digitalizado por el AY, en 128K y Next.** El AY no tiene DAC,
  pero su registro de volumen es de 4 bits: apagando el mezclador y
  escribiendo la amplitud a ritmo constante hace de DAC, que es lo que llevan
  haciendo los digidrums desde los ochenta. `wav2ay.py` convierte un WAV
  pasandolo por la curva LOGARITMICA real del chip -- volcar los cuatro bits
  altos del PCM amontona todo arriba y la parte baja no se oye -- y empaqueta
  dos muestras por byte. `sample_ay.py` es el reproductor, 64 bytes, con los
  retardos calculados en T-estados: los dos tramos del bucle cuestan 32 y 68 T,
  asi que hay que igualarlos o la onda sale con cojera audible. El condact es
  `SAMPLE "nombre"`, existe en las cuatro maquinas y no hace nada donde no hay
  AY (48K y CPC). En 128K las muestras van detras de las imagenes, en los
  mismos bancos; en Next, en bancos propios, con una ventana de 16K sobre la
  ROM -- se puede tapar entera porque el reproductor corre con las
  interrupciones quitadas y lo unico que hace falta de ella es el gestor de
  &0038. Pestana «Muestras» en el editor, con importacion de WAV y una
  audicion que suena con los MISMOS 16 niveles que la maquina.
- **Musica del AY en el 128K nativo.** El reproductor de PSG del Next se
  reaprovecha tal cual: el 128K lleva el mismo chip y los mismos puertos
  (&FFFD para elegir registro, &BFFD para el dato). Suena sobre la portada
  hasta que se pulsa tecla, y el hueco que se le da es el que queda libre en
  el mapa plano, medido despues de todo lo demas, con tope en PSG_MAX.
- **Las cuatro maquinas pasan a exportarse por el motor nativo.** El menu
  Archivo ofrece 48K, 128K, Next y CPC sin apellidos: las cuatro se compilan
  aqui, en Python puro. El camino por ZX BASIC se conserva en un submenu,
  «Exportaciones heredadas (ZX BASIC / Boriel)», hasta que los cuatro targets
  nativos esten rodados en maquina con todos los juegos. Nada se ha borrado.
- **`BRIGHT`, `FLASH` e `INVERSE` en el motor nativo.** Eran el unico agujero
  real frente al export de BASIC, y no era teorico: Apolo 11 usa `BRIGHT` en
  sus tres idiomas y lo perdia en las cuatro maquinas nativas. Los tres pasan
  por un simbolo de plataforma nuevo, `SCRATTR`. En Spectrum, 128K y Next,
  `BRIGHT` y `FLASH` son bits del atributo; `INVERSE` no lo es -- en el
  Spectrum invierte los PIXELES del caracter, no sus colores -- asi que se
  guarda un flag y `nxplot` complementa los seis pixeles del glifo, dejando a
  cero los dos que son del vecino. En el CPC, que no tiene nada de esto,
  `SCRATTR` es un RET.

### Correcciones
- **`capabilities.py` mentia sobre el Next.** `CAPS['next'] = CAPS['spectrum']`
  decia que Next iba en BASIC y lo soportaba todo, cuando lleva el motor
  nativo desde la v2.0: daba via libre a un `BEEP` que en el `.nex` no suena.
  Ahora el contrato del motor nativo se define UNA vez (`CAPS_NATIVO`) y lo
  comparten CPC, Next, 48K y 128K, con la excepcion del 48K, que no lleva AY
  y por tanto no tiene `PLAY`.
- **`PAUSE` no esperaba y los efectos de sonido eran mudos en Spectrum, 128K
  y Next.** `MCWAIT` -- en el CPC la espera de barrido del firmware -- estaba en
  el grupo de stubs de la capa de plataforma que solo hacen `RET`. El motor lo
  llama en dos sitios: `c_pause`, entre frame y frame de `PAUSE`, y `c_play`,
  entre frame y frame de un efecto. Con un `RET`, `PAUSE n` era instantaneo y
  un FX entero se reproducia en microsegundos, o sea que no sonaba. En el CPC
  siempre funcionaron, y por eso no habia saltado: era el unico backend donde
  `MCWAIT` era la rutina de verdad. Ahora es `EI`+`HALT`, que con IM1 da el
  barrido exacto. `verify_48` comprueba que `PAUSE 3` pasa tres veces por ahi.
- **`END` se comia un `ENDIF` o un `ENDON` sueltos.** El reconocedor era
  `startswith('END')`, asi que una de esas dos palabras fuera de su bloque se
  habria compilado como fin de partida. Ahora es `END` exacto.

### Correcciones
- **Ningun juego terminaba en maquina real.** `nativecc` compilaba el condact
  `END` a `DONE`, que en semantica PAW solo significa «esta entrada ha acertado,
  siguiente turno». El texto del final se imprimia y el juego devolvia el
  prompt: en Tifon Negro te capturaban las SS y seguias jugando, y ningun final
  —ganador o perdedor— era alcanzable en CPC, Next ni 48K. `END` pasa a
  compilarse a un condact propio, `ENDGAME`, que imprime el cierre con la
  puntuacion (mensaje de sistema `SFIN`, del catalogo de `mensajes.py`) y
  levanta `quitf`. `mainloop` ademas mira `quitf` donde lo mira el interprete de
  PC —tras `before_turn` y tras el despacho—, y no solo al final del turno.
  Lo encontro `probar_pc.py` en su primera pasada.
- **Las salidas se escribian distinto en PC que en las maquinas.** El motor
  nativo saca los nombres del catalogo compartido (`dir_n`..`dir_d`, de
  `mensajes.py`) y el interprete de Python los llevaba cableados en
  `DIR_NAMES_L`: el Spectrum decia «Salidas: N S» y el PC «Salidas: Norte,
  Sur». Peor aun, una traduccion hecha en el editor cambiaba las maquinas y no
  el PC. `interpreter._dir_name()` pasa a leer el mismo catalogo, con la tabla
  por idioma de ultimo recurso, y la linea se separa por espacios como en el
  motor nativo. Lo encontro `probar_pc.py`.
- **El arnes del Z80 no sabia que una partida puede acabarse.** Que el motor
  dejara de pedir ordenes se vivia como un cuelgue, a 40 millones de pasos de
  simulador por orden. Ahora se deja una direccion de retorno reconocible en la
  pila y `teclea` corta ahi.

---

## 2.52 — 2026-09-21 — Las imagenes del Next, por el nombre bueno

### Correcciones
- **El Next cogia imagenes viejas cuando el id de la localizacion no llevaba
  arroba.** Los `.nxi`/`.nxp` se buscaban con el id tal cual, y en `temp/Next/
  data` conviven las dos epocas: las que escribe el editor hoy, con arroba, y
  un resto de antes de la convencion de prefijos, sin ella. Un juego con ids
  sin arroba -la version portuguesa de Tifon Negro- se llevaba las de junio,
  con su borde blanco. Ahora se prueban las dos grafias y manda la de la
  arroba, que es la que el editor mantiene al dia.

---

## 2.51 — 2026-09-21 — Los comodines del manual, y COGER TODO como debe

### Novedades
- **Una linea en blanco antes de las salidas** en la descripcion de sala.

### Correcciones
- **`COGER TODO` ya coge todo lo que se pueda coger**, este suelto en la sala o
  dentro de un contenedor abierto y presente. `COGER <objeto>` tambien. El
  motor nativo solo miraba lo que hubiera suelto; el export de 128K si sacaba
  de los contenedores, asi que los dos backends daban resultados distintos ante
  la misma orden.
- **Los comodines de sustantivo funcionan como dice el manual.** `_` es hueco
  vacio (no puede haber palabra) y `*` es cualquier palabra o ninguna. En el
  motor nativo `_` se compilaba a 0 y 0 significaba "cualquier cosa", justo lo
  contrario; y **el segundo sustantivo de la cabecera `ON` se tiraba entero**,
  de modo que `ON COGER PASE _` casaba con "coger pase embarque". Ahora la
  tabla de respuestas lleva las dos ranuras y las compara con esas reglas.
  `*` en un predicado `NOUN1`/`NOUN2` tambien pasa a ser cierto sin palabra.

---

## Sin publicar — correccion de Tifon Negro (YAML 1.5)

### Correcciones
- **Tifon Negro se volvia inacabable si vaciabas la caja fuerte con `COGER
  TODO`.** El flag del pase y el de los codigos solo se ponian en las
  respuestas de `COGER PASE` y `COGER CODIGOS` exactas; con cualquier otra
  forma de cogerlos se los llevaba el `GET` generico y los flags se quedaban a
  cero: con el pase en la mano el Bootsmann no te dejaba subir al submarino, y
  con los codigos encima el amanecer te mataba igual. Ahora `after_turn` mira
  **lo que llevas**, no como lo cogiste, y ahi se ponen el flag y el punto.
  Mas visible en 128K, porque alli `COGER TODO` **si** vacia los contenedores
  abiertos (el motor nativo no), asi que era el camino natural.
- Tres pruebas nuevas en `tifon.pru`: los objetos de la caja cuentan se cojan
  como se cojan, con el pase se sube a la torre y sin el no.

---

## 2.5 — 2026-09-20 — Arte de Spectrum en JPG, PNG o BMP

### Novedades
- **`img/Spectrum` ya no obliga a trabajar en `.scr`.** Ademas del `.scr` de
  siempre, la carpeta admite `.jpg`, `.png` y `.bmp` **en 4:1** —la tira de
  256x64 del tercio superior—, que se incrustan como si fueran un `.scr`: se
  pasan a tinta y papel con el mismo dithering Bayer de 2 colores por bloque de
  8x8. Igual para la pantalla de carga (`screen.*`, esa a pantalla completa).
  - Lo que se deja en `img/Spectrum` es arte **ya preparado para la maquina**,
    asi que se convierte **sin tocar niveles**. El autocontraste se queda donde
    tiene sentido: en el fallback de los masteres fotograficos de `img/Original`.
  - Y si no viene en 4:1 **se rechaza con un error que dice cuanto mide y cuanto
    deberia medir**, en vez de achatarlo en silencio. Hay un 2% de margen, que
    recortar a mano nunca sale exacto.
  - El orden de preferencia queda: `Spectrum/<id>.scr`, luego
    `Spectrum/<id>.jpg|png|bmp`, y por ultimo el master de `Original/<id>.*`.
- **El nombre vale con arroba y sin ella**: `@playa.jpg` y `playa.jpg` valen los
  dos. Los masteres de `img/Original` se guardan con la arroba del id y el arte
  de `img/Spectrum`, historicamente, sin ella; buscar solo una de las dos formas
  dejaba fuera media carpeta sin decir nada.
- El editor previsualiza estas imagenes **exactamente como van a salir**, con el
  mismo tratamiento que el export, y si una no cumple el 4:1 lo dice en el hueco
  de la imagen en vez de dibujar algo que luego no sera.

---

## 2.48 — 2026-09-20 — El guion de la bateria, fuera del mapa plano

### Novedades
- **El guion del modo prueba viaja en su propio banco**, paginado sobre la ROM
  en `&2000-&3FFF` (la ranura de abajo no vale: `nxsubepal` la usa un instante
  para leer las paletas). Antes iba en el mapa plano y una bateria de 690
  ordenes —6,5 KB de teclas— no cabia junto al juego; ahora el tope son 8 KB de
  guion y el binario no se entera. Es, literalmente, el truco de mapear RAM
  sobre la ROM que el Next permite.
- **`* 40 ORDEN` en el `.pru`**: repite una orden N veces. Dejar pasar turnos es
  lo que mas se repite en una bateria y el guion viaja dentro del `.nex`, asi
  que conviene que ocupe poco (`* 103 I` son 206 bytes; 103 `PUNTUACION`, 1133).
- **Las comprobaciones de texto ya no miran los acentos.** En pantalla los
  acentos son codigos propios de la fuente del juego y obligar a escribirlos en
  el `.pru` solo servia para que una prueba fallara por una tilde.
- Cuando el guion no cabe, la bateria lo dice con todas las letras en vez de
  soltar el error del exportador, que habla de direcciones y no de pruebas.

### Correcciones
- **La puntuacion salia pegada al eco de la orden** en el motor nativo
  (`puntuacionPuntuacion: 25`): el condact `SCORE` imprimia sin saltar de linea
  antes, al reves que `MESSAGE` y que el export de 128K.

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
- **`Games/Operacion Tifon Negro/tifon.pru`**: 14 pruebas del juego, entre ellas
  que se puede acabar con 110/110 siguiendo la ruta optima.
- **Modo verboso en las dos** (`-v`, `-vv`): cuenta cada orden segun pasa
  — donde acaba el jugador, la puntuacion y el principio de la respuesta — y
  cada comprobacion con su `ok` o su `FALLA` en su sitio, en vez de una lista
  al final. `bateria_next.py` lee la salida del emulador **segun sale**, asi
  que la partida se ve avanzar en vivo.
- **La bateria ya no se puede quedar colgada.** El emulador se lanza con la
  entrada estandar cerrada, que es lo que hacia falta para que la pregunta de
  «¿me bajo la imagen de tarjeta SD?» — que sale por su salida estandar, no por
  la de error — se responda sola que no en vez de esperar una tecla que nadie
  ve que haga falta. Ademas se corta a los `--paciencia` segundos sin noticias
  (120 por defecto) y se cuenta lo que dijo el emulador, con la pista de la
  tarjeta si es lo que falla. Opciones nuevas: `--bajar-sd`, `--paciencia`.
- **Arreglado en Windows**: el puerto magico sale por la salida de error de
  jnext y alli el runtime de C convierte cada `\n` en `\r\n`, asi que las marcas
  del volcado llegaban como `\r\n#RESET\r\n` y no casaba ninguna: la bateria se
  tiraba la partida entera sin enterarse de nada y daba las 12 pruebas por no
  alcanzadas. Ahora se tiran los retornos de carro al descodificar. De paso, el
  aviso de la tarjeta SD mira donde la busca jnext de verdad (`$JNEXT_CONFIG_DIR`,
  `$HOME/.jnext` y, si HOME no esta puesta, `.jnext` de la carpeta desde la que
  se lance), no la carpeta del usuario a secas.
- **Y va seis veces mas rapida**: el emulador se corta en cuanto el guion llega
  al final, en lugar de seguir barriendo hasta el tope. Las 288 ordenes de
  *Tifon Negro* pasan de 91 s a 14 s.

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

- **La puntuacion salia pegada al eco de la orden** en el motor nativo
  (`puntuacionPuntuacion: 25`): el condact `SCORE` imprimia sin saltar de linea
  antes, al reves que `MESSAGE` y que el export de 128K.

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
