# Fase 5A.2 — Watcher local de Auctionator.lua

Implementación sobre `9e3836b4029cc276b2af37f2ab82a255d371997e` (base 5A.1).
Watcher de un único archivo configurable, ejecutado en primer plano. Sin nuevas
dependencias, servicio de Windows, instalación automática al inicio, control del
juego, conexiones PostgreSQL, migraciones, API, sincronización ni modificaciones
de frontend o motores 3A/3B.

## Rutas independientes: origen real, fixtures y archivo

El origen del watcher durante el lanzamiento es el `Auctionator.lua` **real**
dentro de `WTF` de la instalación de Forever elegida por el operador. No hay una
ruta personal o de instalación fijada en el código. La CLI recibe exactamente
un archivo; no busca clientes, cuentas o SavedVariables recorriendo discos.

Las copias históricas `scan01` y `scan02` son sólo fixtures externos de la stress
test. **Su carpeta no es el lugar donde escribe WoW.** En la validación se leen
como entradas inalteradas y se copian a otro archivo temporal independiente.
La ruta real de juego no se utiliza en la simulación ni queda configurada por ella.

```text
Durante el lanzamiento:
  Forever/WTF/Account/<cuenta>/SavedVariables/Auctionator.lua  origen real elegido
        -> watcher -> directorio privado de archivo externo al proyecto y a WTF

En la validación:
  fixtures externos scan01/scan02 (sólo lectura)
        -> temporal/simulation-source/Auctionator.lua          origen simulado observado
        -> temporal/archive/                                  archivo aislado
```

El directorio padre del origen debe existir. El archivo puede estar ausente al
iniciar y aparecer después. Se rechazan directorios como origen, links/reparse
points y rutas ambiguas conforme a 5A.1. El archivo de capturas no puede estar
dentro del proyecto, dentro del directorio padre del origen, ni contener ese
origen. Las comprobaciones resuelven alias Windows y son independientes de Git.
El destino predeterminado sigue siendo el de 5A.1:
`%LOCALAPPDATA%\WoWForeverCompanion\local-capture`, con su fallback documentado.

## Arquitectura e integración

- `backend/app/local_capture/watcher.py`: observador y estado en memoria,
  configuración validada, eventos, `step(now)` sin sleeps y `run()` con polling.
- `backend/scripts/watch_auctionator.py`: argumentos, mensajes legibles y salida
  limpia. No contiene parsing Lua, deduplicación ni lógica de publicación.
- El único camino para validar/publicar es `archive.capture_file()` de 5A.1.
  Se reutilizan además sus comprobaciones de rutas y lectura estable acotada.

La función de captura añade un parámetro opcional restrictivo
`expected_source_sha256`. El watcher pasa el hash de la versión estabilizada.
5A.1 compara ese hash con el buffer que acaba de leer, **antes de parsear o crear
el archivo**. Si no coincide devuelve `source_changed`; el watcher inicia otro
intervalo de estabilidad. Así no acepta una versión nueva por haber estabilizado
otra anterior. La CLI manual no cambia su uso; sin ese parámetro mantiene su
contrato previo. No se añaden bypasses ni copias temporales propias al archivador.

Se mantienen todos los límites de formato/tamaño, hashes de bytes y evidencia,
deduplicación, validación, independencia de originales, publicación, bloqueo y
recuperación de 5A.1. Los precios locales siguen en `0..2**63-1` y la ingestión
conserva 32 bits: el watcher no habilita importar esos valores.

## Funcionamiento

1. Inspeccionar al iniciar. En cada ciclo permitido se comprueban ruta y lectura
   consistente mediante el mismo lector de 5A.1: dos lecturas acotadas, identidad
   y tamaño/mtime; Windows impide compartir escritura/borrado mientras se lee.
2. Calcular SHA-256 completo en cada inspección y combinarlo con la identidad
   del archivo. Así se detectan cambios de bytes con tamaño y mtime conservados,
   además de reemplazos por rename. No se depende sólo de metadatos del SO.
3. Cuando cambia la firma observada, reiniciar la espera. Debounce y estabilidad
   transcurren en paralelo: se exige el **máximo** de ambos períodos sin otro
   cambio observado, con al menos dos inspecciones consistentes.
4. Ante una versión estable, llamar a 5A.1 con el hash esperado. Sólo después de
   su éxito se guarda el hash confirmado en memoria. Un error nunca lo sustituye
   por el hash rechazado, ni convierte un inválido en procesado exitosamente.
5. Un hash ya confirmado durante esta ejecución no se parsea ni archiva en cada
   poll. Una reescritura/reaparición idéntica emite una sola confirmación tras
   estabilizarse. Otros bytes, incluidos cambios de configuración, pasan a 5A.1:
   éste decide si crean evidencia de mercado nueva o sólo otro original.
6. El archivo ausente se inspecciona en ciclos posteriores, con aviso sólo al
   cambiar de disponibilidad. Bloqueos, lecturas cambiantes y fallos del archivo
   se reintentan por lotes acotados. Después del lote hay una pausa de recuperación;
   no se abandona la observación por un bloqueo temporal.
7. Ctrl+C interrumpe la ejecución sin traceback y devuelve código 0. El lector y
   el archivador cierran sus handles/locks. Si se interrumpió una escritura de
   archivo, 5A.1 conserva su recuperación mediante `pending`; el watcher no marca
   una captura interrumpida como exitosa. La CLI habilita su propio manejo de
   SIGINT/Ctrl+Break y limpia la marca Windows de ignorar Ctrl+C que puede heredar
   de un launcher; restaura sus handlers al terminar. No afecta al cliente de
   juego. El API también permite un `stop_event`.

No se guarda otro índice mutable ni checkpoint persistente del watcher. Al
reiniciar se vuelve a inspeccionar/estabilizar el archivo actual y 5A.1 comprueba
el archivo de capturas persistido: un duplicado conserva sus metadatos originales.

## Ejecución en PowerShell durante el lanzamiento

Con las dependencias Python del backend ya instaladas, desde la raíz:

```powershell
# Ingresar la ruta REAL de la instalación de Forever, no la carpeta de fixtures.
$foreverSavedVariables = Read-Host 'Ruta completa de Auctionator.lua real dentro de WTF'
.\backend\.venv\Scripts\python.exe -X utf8 -B .\backend\scripts\watch_auctionator.py `
  $foreverSavedVariables --source-version 341 --serialized-codec cbor-definite
```

`-X utf8` facilita mensajes correctos también al redirigir la consola. La versión
es la selección del operador, no detección del addon. CBOR requiere el perfil
explícito; Lua no serializado puede observarse sin `--serialized-codec`.

Para configurar otro archivo de capturas independiente:

```powershell
$privateArchive = Read-Host 'Directorio privado para capturas, fuera del proyecto y de WTF'
.\backend\.venv\Scripts\python.exe -X utf8 -B .\backend\scripts\watch_auctionator.py `
  $foreverSavedVariables --destination $privateArchive `
  --source-version 341 --serialized-codec cbor-definite
```

Para encontrar el origen real:

1. Identificar la carpeta donde está instalada la copia de Forever que se usa
   para jugar. No asumir que otro cliente WoW o un backup comparten `WTF`.
2. Localizar manualmente su subdirectorio de SavedVariables, por ejemplo
   `WTF\Account\<cuenta>\SavedVariables\Auctionator.lua` dentro de esa instalación.
   Elegir la cuenta correspondiente; no publicar ese nombre ni la ruta completa.
3. Después de usar Auctionator, ejecutar `/reload` o salir normalmente y comprobar
   que ese archivo es el guardado por la instalación elegida. Una copia histórica
   en otra carpeta no sirve como origen en vivo aunque sus bytes sean auténticos.
4. Ingresar la ruta en la CLI. Si todavía falta el archivo pero su padre existe,
   el watcher espera. Se detiene con **Ctrl+C** en esa terminal; al cerrarlo no
   queda un servicio instalado ni se inicia al volver a entrar a Windows.

`/reload` es una acción **manual del operador**. El watcher no lo envía ni controla
el cliente. Cuando WoW termine de guardar o reemplazar el archivo, se observará
el nuevo estado y se esperará estabilidad. Un cierre anormal que no guarde los
SavedVariables no puede producir evidencia que no llegó al disco.

**Pendiente: primera prueba con un `/reload` real de WoW Forever.** Al volver
a abrir el juego, configurar el origen real y un archivo de capturas privado,
iniciar la CLI y realizar manualmente un escaneo seguido de `/reload`. Comprobar
el resultado tras la estabilización: otra evidencia sólo si cambia el mercado;
un guardado idéntico o sólo de configuración no añade estados económicos.
Repetir `/reload`, verificar deduplicación y detener con Ctrl+C. La simulación
no sustituye esta comprobación con el cliente real.

## Configuración y mensajes

| Argumento | Default | Rango/semántica |
| --- | ---: | --- |
| `--poll-interval` | 2 s | 0,25..60 s; hashing y comprobación de bytes por inspección |
| `--debounce` | 2 s | 0..300 s desde el último cambio observado |
| `--stable-seconds` | 4 s | 0,25..300 s; espera efectiva = máximo con debounce |
| `--retry-delay` | 2 s | 0,25..60 s entre intentos del lote, sujeto al polling |
| `--max-attempts` | 3 | 1..10 intentos por lote |
| `--recovery-interval` | 30 s | 1..3600 s de pausa tras agotar un lote |

`--origin-id` admite un alias opaco y `--market-rule 'Clave externa=PvP'` mappings
confirmados, con las mismas restricciones del capturador manual. No necesitan
configuración `.env`, región, dataset ni DATABASE_URL. NaN, infinito y tiempos
fuera de rango se rechazan. Un error de configuración devuelve código 1;
argumentos CLI inválidos, 2. Un archivo inválido no termina el watcher: se registra
el estado y se aplican los reintentos/recuperación, sin marcarlo como exitoso.

| Mensaje | Significado |
| --- | --- |
| Observando Auctionator.lua | Inspección de la única ruta elegida |
| Archivo detectado o actualizado; esperando estabilidad | Se detectó otra firma; comienza la espera |
| Archivo ausente / disponible nuevamente | Desaparición o reaparición |
| Captura archivada; primer estado / mercado actualizado | Resultado devuelto por 5A.1, no una nueva hora de scan |
| Archivo diferente, sin cambios económicos | Original distinto con evidencia de mercado equivalente |
| Archivo idéntico; sin cambios | Bytes confirmados en memoria o duplicado confirmado por 5A.1 al reiniciar |
| No disponible temporalmente; reintentando | Archivo bloqueado/cambiante o archivo de capturas ocupado |
| Error de validación | Sin publicación de esa entrada ni confirmación de éxito |
| Error de archivado / reintentos agotados | Fallo pendiente, intentos acotados y recuperación posterior |
| Observación detenida | Cierre limpio del bucle |

Los avisos de espera, disponibilidad y error se suprimen mientras no cambie su
estado; no se repiten en cada ciclo. Cada resultado incluye ID corto, número de
mercados/items y número de estados nuevos, sin nombres de cuenta/personaje,
claves privadas de mercados, precios ni rutas de origen/destino.

## Fiabilidad y privacidad

- Polling no es una cola de eventos de WoW. Puede perder estados entre dos
  inspecciones, durante pausas por bloqueo/error o mientras estaba cerrado. Al
  reiniciar sólo se recupera el archivo actual, no estados ya sobrescritos.
- Estabilidad es una heurística sobre muestras, no prueba de fin de scan lógico.
  Un escritor puede pausar y continuar. Se conservan sólo bytes que superan las
  validaciones existentes; el hash esperado evita capturar otra versión sin
  haberla estabilizado. Nada convierte adquisición UTC en hora nativa de scan.
- Cambios posteriores a una lectura ya validada se detectan en el siguiente
  ciclo; no modifican la copia guardada. Sigue siendo posible guardar evidencia
  válida del mismo bucket 2485 con valores diferentes.
- El costo en reposo es dos lecturas acotadas y SHA-256 por inspección; no parsing
  continuo ni escritura de copias idénticas. El límite sigue siendo 16 MiB.
  Subir el intervalo reduce I/O. Con datos nuevos, la verificación de archivo de
  5A.1 sigue teniendo costo proporcional a todas las capturas ya guardadas.
  El handle Windows no comparte escritura sólo durante las lecturas breves;
  no se conserva abierto durante la espera de estabilidad o recuperación.
- Una versión inválida o un fallo permanente puede ser reintentado en lotes
  posteriores, con pausa y sin spam de mensajes. La corrección de bytes inicia
  otra espera automáticamente. La recuperación de lectura puede demorarse hasta
  la pausa configurada más polling y estabilización; no promete captura inmediata.
- El watcher no audita continuamente el directorio de archivo cuando la fuente
  no cambia. Una nueva captura o un reinicio vuelve a la verificación de 5A.1.
  No repara automáticamente una captura completa corrupta ni borra pendientes.
- Presupone filesystem local y directorios privados con escritores cooperantes.
  No protege de un administrador hostil. Hereda ACL, límites y garantías de
  durabilidad de 5A.1; no requiere elevar permisos del programa.
- Los SavedVariables originales archivados pueden contener datos personales.
  Mantener el archivo privado, fuera de Git y de carpetas compartidas/sincronizadas.
  No se registran rutas completas ni excepciones/Pydantic con datos del archivo.

## Validación y siguiente etapa

Los tests usan archivos sintéticos y reloj inyectado, sin sleeps prolongados,
cliente de juego ni rutas privadas. La simulación práctica usa exclusivamente
copias de los dos fixtures auténticos externos, nunca sus originales como origen
observado. La ruta real de la instalación de Forever no se buscó ni se observó
durante estas pruebas: queda como configuración explícita del operador.

### Pruebas automáticas

Resultado final en Windows/Python 3.13: **716 aprobados, 0 omitidos, 148 no
ejecutados** por requerir PostgreSQL. Se recolectaron **864 casos**: los 809
existentes de 5A.1 más **55 tests nuevos**. Los 78 de captura 5A.1 siguen aprobados;
la colección anterior sin DB tenía 661 aprobados y los 55 nuevos suman 716.

Se inspeccionó toda la colección con un filtro temporal por fixtures
`isolated_database`, `test_database_url` y `lab`, y se bloqueó `psycopg.connect`:
**0 intentos de conexión**. Los 148 excluidos son los mismos de la validación
5A.1; no se ejecutaron migraciones ni se les atribuye aprobación actual.
El caso opt-in del parser auténtico se ejecutó sólo en lectura sobre el fixture
histórico conocido, con su SHA-256 fijado. Un warning Starlette/httpx existente.
Tras revisar la declaración de `BOOL` de Win32 se repitieron los siete casos de
CLI/Ctrl+C seleccionados, todos aprobados; son parte de los 55 casos nuevos.

Los casos nuevos cubren inicio con archivo presente/ausente, escrituras por
etapas, espera conjunta, reescritura idéntica, configuración, evidencia diferente
en el mismo bucket, edición in-place y rename con mismo tamaño/mtime restaurado,
desaparición/recreación, bloqueos reales Windows, entrada inválida corregida,
reintentos y recuperación, carrera entre observación/captura, reinicio, Ctrl+C,
stop-event, separación de directorios, rutas/links/tamaño, parámetros inválidos,
hash esperado, CLI con ambas codificaciones Windows y privacidad/imports sin DB.

Para ejecutar sólo las suites sintéticas 5A.1/5A.2, desde `backend`:

```powershell
$watcherTestRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('wow-watcher-tests-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $watcherTestRoot) { throw 'Temporary target must be new' }
.\.venv\Scripts\python.exe -X utf8 -B -m pytest -q -p no:cacheprovider --basetemp $watcherTestRoot `
  tests/test_local_capture.py tests/test_local_watcher.py
```

Para todas las regresiones sin DB se ejecutaron además las suites Auctionator,
CBOR, evidencia nativa, hardening del parser, procedencia 341, guard/CLI trial,
file adapter, validación HTTP, ventanas, estadística y validaciones/señales 3A/3B
existentes. Sin la variable opt-in de captura auténtica ese único caso del parser
se omite; los tests de captura/watcher no necesitan archivos privados.

### Simulación con copias auténticas y CLI real

Se verificaron los dos fixtures históricos proporcionados, sin usarlos como
fuente observada. Se creó una fuente temporal independiente, se copió el estado
inicial y se reemplazó mediante rename. Archivo de capturas y fuente simulada
quedaron en directorios hermanos distintos, fuera del proyecto y del archivo
personal de capturas.

| Paso | Resultado | Nuevos estados | Originales archivados |
| --- | --- | ---: | ---: |
| Copia de `scan01` al origen simulado: 7 items | `archived`, primer estado | 1 | 1 |
| Reemplazo por copia de `scan02`: 27 items | `archived`, mercado diferente | 1 | 2 |
| Repetir los mismos bytes de `scan02` | Idéntico, sin nuevo archivado | 0 | 2 |
| Detener y reiniciar sobre `scan02` | `duplicate` de 5A.1, mostrado como idéntico | 0 | 2 |

Resultado: **2 originales independientes, 2 estados económicos, 0 pendientes**
en cada archivo de validación. Ambos mercados son PvP y usan el bucket nativo
2485; no se creó otro bucket ni se atribuyó el tiempo de archivo al escaneo.
Los hashes completos y de mercado coinciden con los documentados en 5A.1 para
esas copias. Los fixtures originales conservaron SHA-256, tamaño, mtime y modo.

Se probaron el bucle real con `stop_event` y la **CLI en una terminal Windows**,
con archivos de capturas temporales separados. La primera prueba de terminal
detectó la herencia de Ctrl+C deshabilitado; tras corregir la inicialización se
comprobó reinicio/deduplicación y **Ctrl+C real con salida 0**, sin traceback.
Todas las instancias de prueba quedaron detenidas. No hubo un WoW abierto ni
una observación del SavedVariables real de lanzamiento durante la validación.

Los informes privados `simulation-report.json` y `cli-validation-report.json`
quedaron en un directorio temporal externo a Git. `archive` pertenece a la
simulación del API y `cli-archive` a la de terminal; cada uno conserva dos
capturas, sin mezclarse con el archivo personal. Los informes de colección y
regresiones también quedaron fuera del repositorio. Ningún original, ruta
personal o archivo temporal se añadió al repositorio.

### Cierre de la entrega

`git diff --check` y revisión de sintaxis/whitespace de archivos nuevos forman
parte del cierre. Cambios: watcher, CLI y tests nuevos; guard opcional de hash en
el capturador; README/arquitectura y este documento. Sin cambios de ingestión,
frontend, Market Intelligence, migraciones ni dependencias. Las pruebas que
necesitan crear ACL privadas de pytest se ejecutaron fuera del sandbox del agente;
la aplicación no requiere permisos elevados.

La revisión final de 5A.2 no encontró bloqueos de código. La publicación se limita
al watcher, su CLI, la protección de hash esperado, sus regresiones y estos tres
documentos. La prueba real con `/reload` permanece pendiente, sin atribuirle los
resultados de las simulaciones.

**Revisión de cierre (22/10/2026): READY TO COMMIT.** Se repitió la suite completa
comparable: 864 recolectados, 716 aprobados, 0 omitidos y 148 integraciones
PostgreSQL no ejecutadas, con 0 intentos de conexión. El fixture auténtico usado
en lectura conservó SHA-256, tamaño, mtime y modo. Sin nuevas correcciones de
código en esta revisión; sólo ajustes documentales de cierre. Se verificaron
el alcance de los siete archivos, la ausencia de datos privados en los cambios
y `git diff --check`.

La sincronización posterior deberá definir autenticación, confirmaciones e
idempotencia por hash, separación de fuente/dataset/mercado y compatibilidad de
precios locales de 64 bits con ingestión de 32 bits. No enviar datos ni completar
metadatos pendientes automáticamente; requiere otra etapa y revisión.
