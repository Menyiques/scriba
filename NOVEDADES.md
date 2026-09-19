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
