# Preparación de datos para la beta del 19/10/2026

Fecha de revisión: **2026-10-15**, America/Buenos_Aires. HEAD inspeccionado: `85bd0e127b142aadfdce2ba73a552039c0067c94`, rama `main`.

**Estado: preparados para intentar captura y validación offline; NO GO todavía para usar datos auténticos en análisis de mercado.** No se recibió ni validó un SavedVariables real de Forever. El 19/10/2026 es la fecha de captura prevista por el usuario; este documento no verifica el calendario oficial ni la disponibilidad de la beta.

Alcance de esta tarea: revisión y procedimiento. No se ejecutaron tests, importaciones, migraciones, servicios, consultas a PostgreSQL ni scripts del addon. No se modificaron código, tests, datos o documentos previos; no hubo commit ni push. Todos los comandos posteriores son instrucciones para una ejecución futura, no resultados obtenidos.

## 1. Estado actual del pipeline y evidencia revisada

```text
Copia SavedVariables -> AuctionatorAdapter (sin BD)
  -> PartialBatch + NativeExportEvidence + hash de bytes + referencia
  -> PartialIngestionService (con BD, transaccional)
  -> observaciones acumuladas + export nativo sellado + recepción
  -> /partial/history, /market/series, /market/metrics -> React
```

| Componente inspeccionado | Garantía/alcance del código actual |
| --- | --- |
| [Adaptador](../backend/app/ingestion/adapters/auctionator.py), [lector Lua/CBOR](../backend/app/ingestion/saved_variables.py) | Parsing de literales limitado, sin intérprete Lua ni conexión a BD; carga del archivo completo con límite |
| [Contratos parciales](../backend/app/ingestion/partial_contracts.py), [claves](../backend/app/ingestion/auctionator_keys.py) | Validación de contexto, tipo, variantes, enteros y semántica temporal |
| [Evidencia nativa](../backend/app/ingestion/native_exports.py) | Hechos presentes, claves originales y manifest de estructura/presencia; proyección de mínimos explícita |
| [Servicio](../backend/app/ingestion/partial_service.py), migraciones [003](../backend/migrations/003_create_partial_observations.sql) y [004](../backend/migrations/004_create_partial_export_evidence.sql) | Transacciones, idempotencia, separación de contexto y evidencia sellada/append-only |
| [CLI](../backend/scripts/import_auctionator.py) | **No tiene dry-run:** después de parsear siempre llama al servicio de persistencia |
| [Conexión](../backend/app/db/connection.py), [configuración](../backend/app/core/config.py) | La aplicación/CLI usan `DATABASE_URL`. `TEST_DATABASE_URL` no redirige por sí sola una importación |
| [API parcial](../backend/app/api/partial.py), [contratos de mercado](../backend/app/market/contracts.py), [servicio analítico](../backend/app/market/service.py) | Consulta por contexto explícito; análisis en transacción READ ONLY, REPEATABLE READ |

Se contrastaron código y tests del proyecto con la semántica registrada en [AUCTIONATOR_340.md](AUCTIONATOR_340.md), [PHASE_25_EXPORT_EVIDENCE.md](PHASE_25_EXPORT_EVIDENCE.md), [ARCHITECTURE.md](ARCHITECTURE.md), [PHASE_3A_VALIDATION.md](PHASE_3A_VALIDATION.md) y README. Las validaciones antiguas son evidencia histórica de fixtures y PostgreSQL, no resultados de esta revisión ni soporte demostrado del cliente de beta actual. Los fixtures construidos que se llaman `real` prueban segregación del contrato, no autenticidad de datos de Forever.

Cobertura existente inspeccionada, sin volver a ejecutarla:

| Suite | Casos relevantes |
| --- | --- |
| [test_auctionator.py](../backend/tests/test_auctionator.py) | l/h/a/m, claves, Lua no ejecutable, límites, vectores LibCBOR, mapping, enteros, rechazo HTTP, simulación |
| [test_hardening_parser.py](../backend/tests/test_hardening_parser.py) | Fracciones legítimas rechazadas, BOM/marcador simulado, presupuesto compartido, límites antes de construcción |
| [test_native_exports.py](../backend/tests/test_native_exports.py) | l presente frente a fallback, a ausente/vacío/cero, claves originales, colisiones normalizadas, proyección coherente |
| [test_partial_integration.py](../backend/tests/test_partial_integration.py) | Idempotencia, rollback, evolución de extremos, contexto de región/fuente/base/dataset |
| [test_export_integration.py](../backend/tests/test_export_integration.py) | Recepciones de un mismo estado, exports distintos, concurrencia, guards SQL, rollback en varias etapas y retries |
| [test_export_migration.py](../backend/tests/test_export_migration.py) | Upgrade aditivo sin fabricar exports anteriores ni alterar datos legacy |
| [test_market_integration.py](../backend/tests/test_market_integration.py) | Variantes/contextos separados, export frente a acumulado, ceros/ausencias, integridad y lectura consistente |

## 2. Formatos aceptados y límites que debe superar el archivo real

| Área | Aceptado actualmente | Rechazo o incertidumbre |
| --- | --- | --- |
| Archivo exterior | Asignaciones globales Lua a literales; tablas, strings entre comillas, escapes soportados, comentarios de línea, BOM/whitespace inicial | No funciones, expresiones, llamadas, asignaciones indexadas, claves/asignaciones duplicadas, long strings/comments o escapes no soportados |
| Variable de precios | `AUCTIONATOR_PRICE_DATABASE` como tabla, `__dbversion` entero igual a 8 | Otra versión no se migra automáticamente en nuestro lector |
| Mercado | Tabla Lua o string serializado con codec aceptado; `version=2` o marcador ausente | Otros marcadores de versión; nombre externo sin ruleset confirmado |
| Item | Únicamente campos l/h/a/m; l y h deben ser tablas aunque estén vacías; a y m pueden faltar | `pending`, campos nuevos o estructuras distintas requieren investigación |
| Días | Claves textuales ASCII de dígitos, hasta 10 caracteres y valor en rango | Claves numéricas Lua, fechas, negativos o aliases incompatibles no se convierten por suposición |
| Valores | Precios, disponibilidad e índices enteros estrictos en `0..2147483647` | Fracciones, booleanos, strings numéricos, negativos y valores fuera de rango no se redondean ni coercionan |
| Coherencia | l <= h; cada l/a histórico tiene h del mismo día; identidad y tipo coinciden con clave | Huérfanos, duplicados y colisiones al normalizar se rechazan |
| LibCBOR | Subconjunto de longitud definida probado con vectores: enteros, bytes/texto, mapas/arrays y true/false/null; tablas vacías pueden ser arrays vacíos. A nivel mercado o item; requiere `allow_libcbor=True` / `--allow-libcbor` explícito | Floats, tags, extensiones, longitudes indefinidas, corrupción y bytes sobrantes se rechazan |
| CBOR nativo del cliente | **No verificado** `C_EncodingUtil.SerializeCBOR/DeserializeCBOR` | El flag LibCBOR no certifica ni habilita soporte del codec nativo; no usarlo por ensayo y error |
| Presupuestos | 16 MiB por archivo, profundidad 32, un millón de nodos compartidos Lua/CBOR; 200.000 observaciones, hechos y límite de estructura | Muchos mercados/items vacíos también consumen presupuesto. La proyección puede producir más filas que los hechos nativos |

Se parsean también otras variables globales como literales, pero sólo se normaliza la base de precios. Una estructura no soportada en otra variable puede impedir leer el archivo completo. No recortar el original ni eliminar campos problemáticos para hacerlo pasar. `AUCTIONATOR_POSTING_HISTORY` no se incorpora: publicaciones propias no son ventas confirmadas ni mercado global.

**Precios fraccionarios:** los tests y la investigación versionada contemplan valores por unidad no enteros legítimos de ModernAH. Un rechazo por fracción puede ser incompatibilidad del importador, no corrupción del archivo. El parser preserva el literal decimal Lua hasta rechazarlo; el lector CBOR rechaza floats. No convertir a int, redondear ni reconstruir buyout/count a partir del agregado.

Un archivo completamente vacío de hechos/observaciones no cumple los contratos (`min_length=1`). Sí se conservan mercados/items vacíos dentro de un archivo que contenga evidencia válida en otra entrada. Un archivo con sólo m puede aceptarse como evidencia sin fecha, pero no aporta buckets para estadísticas temporales.

No existe selección parcial de mercados por CLI: el archivo completo debe ser aceptable y cada clave externa debe estar resuelta. No anunciar soporte para un archivo mixto si sólo se verificó una de sus partes.

## 3. Identidad y separación de datos

| Dimensión | Cómo se representa | Qué conservar/comprobar en la captura |
| --- | --- | --- |
| Servidor y facción | No hay columnas separadas en `partial_markets`; una clave externa puede codificarlos literalmente | Nombre mostrado por el cliente, facción, ruleset y clave raw. No inventar un parser de nombres |
| Mercado | `market_key` exacta y ruleset; unicidad por `(region, market_key, dataset)` | PvE/PvP/HC/RP literales se reconocen; no son nombres de reinos. Cualquier otra clave necesita mapping explícito a uno de esos rulesets |
| Región | `region` introducida por el operador | Confirmar región del cliente; no usar timezone o el idioma como región. `wow-forever` en un fixture no prueba una región real |
| Fuente | `source_id` estable y seudónimo; `source_type=auctionator` para dataset real | Mismo origen/cuenta y contexto de reloj conservan ID entre exports; otra cuenta/historia o contexto incompatible no debe mezclarse |
| Dataset | `real` o `simulated`, coherente con source_type | Captura auténtica usa real. No etiquetarla simulated como mecanismo de aislamiento |
| Versión | `source_version=340` y `database_version=8` | 340 es formato seleccionado por parser/operador; 8 sí se exige en el archivo. Ninguno es el build de Forever |
| Item | `partial_items.id` interno, `item_key` única global, ID numérico y `key_kind` | La fila se comparte entre contextos; ni PK ni coincidencia numérica prueban identidad auténtica |
| Build/producto/canal | No incluidos como campos dedicados en el contrato de ingestión actual | Registrar externamente producto beta, build, locale y revisión del addon. No inferirlos de la fecha/import |

Mapping: preservar exactamente la clave original, incluidos espacios significativos internos, y asociarla sólo al ruleset comprobado. No se permite remapear las claves literales PvE/PvP/HC/RP, aunque el mapping repita el mismo valor. Si no se puede determinar región, facción/alcance o ruleset de una clave, detener la persistencia; no elegir PvE por defecto. Si un fichero mezcla productos/builds y no podemos separar su procedencia con evidencia, no fusionarlo como una sola serie por comodidad.

Variantes soportadas por [normalize_item_key](../backend/app/ingestion/auctionator_keys.py):

| Forma | Interpretación | Regla |
| --- | --- | --- |
| `ID` | Item básico | Ceros iniciales se normalizan; original preservado en evidencia nativa |
| `g:ID:nivel` | Variante gear level | No fusionar con el item base u otro nivel |
| `gr:ID:sufijo` | Variante por sufijo | Conservar sufijo opaco y clave completa |
| `p:speciesID` | Especie de mascota | No equivale al item con ese número; `external_item_id` contiene aquí una especie |

Los formatos anteriores son esquemas, no ejemplos auténticos de Forever. Item links completos y nuevas variantes no se aceptan como DBKey por analogía.

La identidad de observaciones incluye mercado, item con variante, fuente/tipo y base temporal; las diarias añaden día y estadística, m usa hash de evidencia normalizada. Las consultas analíticas mantienen además `series_mode` y `export_id` cuando corresponde.

**Segregación no equivale a aislamiento:** el dataset separa mercados/series, pero `partial_items` es compartida y la CLI no restringe destino. El marcador del simulador se detecta con BOM/whitespace, pero es una protección frente a error de etiqueta, no autenticación. Un fixture sin marcador puede declarar real. No enlazar los IDs ficticios `1900000000...` con items auténticos ni asociar automáticamente samples legacy que reutilizan IDs conocidos. Ver [ITEM_CATALOG_RESEARCH.md](ITEM_CATALOG_RESEARCH.md).

## 4. Semántica de l/h/a/m y tiempo

| Campo nativo | Proyección | Interpretación que debe conservarse |
| --- | --- | --- |
| `l[day]` presente | `daily_minimum`, origen l en consulta por export | Mínimo almacenado del bucket, no prueba de mínimo absoluto de todas las subastas/scans |
| l ausente para un h | `daily_minimum=h`, origen `h_fallback` | Proyección de GetPriceHistory; no insertar un hecho l inexistente |
| `h[day]` | `daily_highest_minimum` | Mayor mínimo guardado, no mayor precio de todas las subastas |
| `a[day]` presente | `daily_max_available` | Mayor disponibilidad guardada, no unidades vendidas, ventas ni auction_count |
| `m` presente | `last_minimum`, `scan_day=null` | Último mínimo guardado sin día/timestamp verificable; fuera de métricas temporales |

Estas equivalencias están implementadas y ejercitadas con fixtures en el proyecto. Deben contrastarse con las lecturas que muestre la instalación real, especialmente si cambia la revisión/ruta AH. No se importan promedios de listings, nombres, calidad, compradores/vendedores ni ventas desde estos campos.

- a ausente, a vacía y a con cero son estados distintos; conservar ceros, no completar huecos con cero.
- La investigación versionada registra que el addon puede dejar l ausente después de precios ascendentes; no reconstruir un mínimo previo perdido.
- El índice nominal usa buckets de 86.400 segundos respecto del `SCAN_DAY_0` del cliente. Se registra además que el addon fija el índice al cargar su módulo: una sesión que cruza el límite puede seguir escribiendo el bucket anterior.
- Primera validación: `scan_day_zero=None`, por tanto `temporal_basis="unknown"` y fechas de bucket desconocidas. La captura del 19/10 no convierte todos los índices en ese día.
- Una base ISO con timezone sólo puede incorporarse si su valor y contexto de reloj se midieron y revisaron. Medianoche UTC de 2020, timezone del host, mtime o `imported_at` no son sustitutos.
- Capturas antes/después y hora local/UTC sirven para auditar la sesión, no convierten agregados acumulados del addon en scans individuales. Conservar también qué datos ya existían antes de esa sesión y la configuración de retención/poda.

**Export frente a acumulado:** cada export sellado conserva su estado decodificado. La tabla acumulada combina extremos entre imports compatibles mediante LEAST/GREATEST, no representa necesariamente GetPriceHistory del último archivo. Ejemplo de fixture: h=100 sin l y luego h=200 sin l conservan dos proyecciones de mínimo (100/200), mientras el acumulado retiene mínimo 100 y mayor mínimo 200. Nunca presentar el acumulado como último scan.

## 5. Evidencia original y procedencia

| Evidencia | Dónde queda | Límite |
| --- | --- | --- |
| Bytes originales | Copia privada externa que debe guardar el operador | **No se almacenan en PostgreSQL**; `raw_reference` es sólo una referencia/ruta |
| SHA-256 de entrada | `partial_import_runs.source_hash` para archivo | Identifica bytes, no firma del cliente. HTTP calcula hash de JSON normalizado, no del Lua original |
| Recepción | `partial_import_runs`: contexto, versión, imported_at, estado y referencia | Parsing/Pydantic previos a persistencia no generan un run; conservar esos errores externamente |
| Estado decodificado | `partial_exports`: hash canónico v1, manifest, contexto, conteo, sellado | No conserva todos los globals Lua, orden, bytes o cada scan físico |
| Hechos presentes | `partial_export_facts`: l/h/a/m, claves de item/día originales, identidades copiadas | No se crea l por fallback ni se reconstruyen exports antiguos |
| Transporte/recepción | `partial_export_imports`: import/export, `input_format`, decoder `auctionator340-v1` | Cada reimport agrega recepción aunque reutilice el estado |
| Acumulación | `partial_observations`: extremos, primer/último import que cambió valor | No conserva cada versión anterior de un extremo reemplazado |

El hash de estado incluye contexto, estructura/presencia, hechos y claves originales. Excluye recepción, ruta y codec: Lua y LibCBOR equivalentes pueden compartir estado. Un nuevo l explícito igual a h puede crear otro export aunque no cambien métricas acumuladas. El hash normalizado usado para m tampoco aporta cronología de scans.

`POST /partial/imports` acepta sólo `PartialBatch` normalizado: puede importar observaciones, pero no aporta `NativeExportEvidence`, `export_id` ni estructura original; declara evidencia unavailable. Para aceptar el primer archivo se debe usar la ruta del adaptador de archivo y conservar su objeto completo, no convertirlo a JSON manualmente para sortear un rechazo.

## 6. Checklist de captura prevista para el 19/10

### Antes de jugar

- [ ] Confirmar acceso a la beta y producto/directorio exactos; no asumir que otro cliente Classic produce el mismo formato.
- [ ] Registrar versión/build/interface medidos (`GetBuildInfo()` si la UI lo permite), locale, región, servidor mostrado, facción y ruleset. Anotar fecha/hora con offset y UTC, inicio de sesión y cualquier cambio de reloj.
- [ ] Registrar versión y revisión/distribución real de Auctionator, `.toc` y hashes de archivos relevantes del addon instalado; no basta el 340 asignado por nuestro parser.
- [ ] Registrar ruta AH efectiva (ModernAH/LegacyAH si puede verificarse), modo de captura, filtros, retención, configuración de base de precios y codec si se identifica. Función `C_EncodingUtil` presente no prueba por sí sola codec ni bytes compatibles.
- [ ] Guardar una copia previa del SavedVariables existente, sin limpiar la historia, y registrar si contenía datos de otros personajes/productos/sesiones. No borrar datos para fabricar una captura aparentemente fresh.
- [ ] Preparar carpeta privada fuera del proyecto/Git con subcarpetas separadas por captura; asignar `source_id` seudónimo estable y hoja de contexto. `data/imports/` está ignorada por Git, pero eso no ofrece control de acceso ni sustituye un respaldo.

### Durante y después

- [ ] Usar sólo las funciones normales de Auctionator disponibles en ese cliente. Preferir una observación acotada y registrar si fue búsqueda, scan u otra ruta; no prometer que cada acción escriba a o una historia completa.
- [ ] Anotar unas pocas claves/items visibles para cotejo, sus mínimos y disponibilidad cuando existan, y las limitaciones de cobertura. Una pantalla de listings actual no equivale automáticamente al agregado diario guardado.
- [ ] Esperar la finalización que indique la UI, anotar errores y salir normalmente para obtener un guardado estable. Registrar si hubo `/reload`, logout o cierre: no asumir bytes/codec idénticos entre esos casos.
- [ ] Con el cliente cerrado, copiar el archivo sin editar y calcular SHA-256. No leer un archivo mientras se está escribiendo: `AuctionatorAdapter.load()` limita tamaño pero no implementa una comprobación de estabilidad por mtime/inodo.
- [ ] Conservar copia original, respaldo previo, hash, tamaño, fecha de copia y contexto por separado. No hacer `dofile`, `loadstring` ni abrirlo ejecutándolo en Lua.
- [ ] Verificar que una sesión posterior restaura la base guardada, conservando antes las copias. Si se pierde o aparece vacía, registrar el fallo y parar; no instalar fixes ni cambiar el cliente como parte de esta aceptación.

### Archivos necesarios y ubicaciones esperadas

| Archivo/dato | Ubicación / necesidad |
| --- | --- |
| `Auctionator.lua` de cuenta | Esperado bajo `<producto del cliente>/WTF/Account/<cuenta>/SavedVariables/Auctionator.lua`. En una instalación con carpeta `_classic_beta_`, queda dentro de ella; confirmar ruta y archivo real |
| `Auctionator.lua.bak`, si existe | Mismo directorio. Respaldo adicional; no sustituye automáticamente la captura elegida ni su hash |
| `Auctionator.toc` y versión/revisión | `<producto>/Interface/AddOns/Auctionator/`; guardar identificación y hashes, sin copiar código del addon al proyecto |
| Configuración por personaje, si hace falta aclarar contexto | Puede estar en `WTF/Account/<cuenta>/<reino>/<personaje>/SavedVariables/`; no es el archivo principal de precios ni una entrada adicional de la CLI |
| Hoja de captura privada | Producto/build, addon, región/facción/ruleset, raw market keys, codec confirmado/desconocido, fuente, reloj, acciones, retención, hashes y resultados |
| Mapping y base temporal revisados, si existen | Sidecars privados; la CLI admite `--market-map` JSON y `--scan-day-zero`. Ausencia de evidencia de reloj obliga a unknown |

El archivo puede contener búsquedas, listas, configuración y publicaciones privadas. No publicarlo completo ni incluir nombres de cuenta/personaje o credenciales en logs compartidos. Para pedir ayuda, preparar posteriormente una muestra mínima anonimizada con hash/referencia al original y sin eliminar la característica que causó el error; no reemplazar el original por esa muestra derivada.

## 7. Primera validación offline, sin PostgreSQL

No usar todavía `scripts/import_auctionator.py`, endpoints POST ni el dashboard conectado a desarrollo. Desde `backend`, con el entorno Python ya instalado, el siguiente bloque llama únicamente al adaptador y valida la proyección. No escribe archivos ni abre conexiones. Las variables BETA_* son contexto temporal de la terminal; reemplazar los placeholders antes de ejecutarlo:

```powershell
$env:BETA_COPY = 'C:\ruta\privada\captura-01\Auctionator.lua'
$env:BETA_SOURCE_ID = 'beta-20261019-cuenta-A-reloj-A'
$env:BETA_REGION = '<region verificada del cliente>'
Get-FileHash -LiteralPath $env:BETA_COPY -Algorithm SHA256

@'
import json, os
from collections import Counter
from pathlib import Path
from app.ingestion.adapters.auctionator import AuctionatorAdapter

region = os.environ['BETA_REGION']
if not region or '<' in region:
    raise SystemExit('Falta verificar y completar la region')
mapping = {}  # Completar SOLO con claves externas y rulesets comprobados.
r = AuctionatorAdapter().load(
    Path(os.environ['BETA_COPY']), source_id=os.environ['BETA_SOURCE_ID'],
    region=region, dataset='real', market_mapping=mapping,
    scan_day_zero=None, allow_libcbor=False,
)
if r.native is None:
    raise SystemExit('Falta evidencia nativa')
expected = sorted(o.model_dump_json() for o in r.native.projected_observations())
actual = sorted(o.model_dump_json() for o in r.batch.observations)
if expected != actual:
    raise SystemExit('La proyeccion nativa no coincide con el batch')
print(json.dumps({
    'source_hash': r.source_hash,
    'state_hash': r.native.state_hash(r.batch),
    'decoder_version': r.native.decoder_version,
    'input_format': r.native.input_format,
    'markets': len(r.native.markets),
    'items_in_manifest': sum(len(m.items) for m in r.native.markets),
    'native_facts': len(r.native.facts),
    'observations': len(r.batch.observations),
    'native_fields': dict(Counter(f.native_field for f in r.native.facts)),
    'temporal_basis': 'unknown',
}, indent=2))
'@ | .\.venv\Scripts\python.exe -B -
```

No activar LibCBOR sólo porque falló el primer intento: primero identificar el productor/codec de los strings. Si se confirma LibCBOR, hacer una segunda ejecución declarada con `allow_libcbor=True` y registrar esa elección; no implica soporte CBOR nativo. Para claves externas, completar el mapping por evidencia sin remapear literales. La CLI posterior debe recibir exactamente el mismo contexto/codec revisados.

Conservar salida, tipo de error y fase en un log privado. Recalcular el hash de la copia al finalizar y compararlo con el inicial y con `source_hash`. Revisar manualmente unos pocos hechos y claves originales contra la evidencia del addon; incluir l explícito/fallback y a ausente/cero sólo si existen realmente. Lo ausente en la muestra se marca **no ejercitado**, no aprobado ni fallido por obligación artificial.

Resultados incompatibles: detenerse, conservar bytes/contexto y documentar la forma encontrada; no probar parsers permisivos, quitar globals, cambiar versión, redondear valores, reducir límites o convertir a HTTP para forzar aceptación. Resolver la incompatibilidad requeriría otra tarea con evidencia y alcance de soporte explícito.

## 8. Ensayo de persistencia aislado, posterior al GO offline

Este procedimiento futuro sí escribe **únicamente en un laboratorio separado**. No se ejecuta en esta entrega. La separación real/simulated dentro de desarrollo no reemplaza este laboratorio.

1. Crear/provisionar una BD nueva exclusiva, por ejemplo `wow_forever_beta_20261019_test`, preferentemente con un rol que sólo pueda operar allí. No reutilizar la BD que contiene simulación ni una base de pruebas con otros trabajos. Registrar servidor/puerto/nombre/schema previstos; no imprimir el DSN o la contraseña.
2. Antes de ejecutar herramientas de preparación, confirmar independientemente que el destino es nuevo/exclusivo y no contiene datos ajenos. En una terminal nueva ubicada en `backend`, dejar `DATABASE_URL` representando el desarrollo correcto para que la comparación de seguridad lo conozca. Configurar `TEST_DATABASE_URL` al laboratorio y ejecutar **sólo allí** `scripts/setup_test_database.py`: crea la base si falta y aplica las migraciones existentes 001–004. No crea una migración nueva del proyecto. Detenerse ante cualquier error.
3. El [validador existente](../backend/scripts/setup_test_database.py) exige nombre terminado en `_test` y distinto del nombre de desarrollo. No garantiza por sí solo aislamiento de credenciales/servidor ni que la BD esté vacía. Confirmar destino, permisos y ausencia de tablas/datos ajenos antes de usarlo.
4. Sólo después de provisionar y verificar, configurar `DATABASE_URL` de esa terminal al DSN del laboratorio. La CLI utiliza esa variable: **configurar únicamente TEST_DATABASE_URL no alcanza**. No modificar `.env` ni reiniciar el backend de desarrollo con ese destino. Cada proceso Python debe iniciarse después de seleccionar el entorno.
5. Verificar mediante una conexión de lectura `current_database()`, schema/search_path y destino del servidor. Tomar un inventario basal de tablas y conteos; las tablas de snapshots completos deben estar vacías en el laboratorio. Si no coincide con el destino previsto, no importar.
6. Ejecutar la CLI con la copia inmutable, `--dataset real`, fuente y región verificadas. Añadir mapping/LibCBOR sólo si la etapa offline los aprobó. Omitir `--scan-day-zero` mientras sea unknown. No existe `--dry-run`.

Ejemplo de selección del destino, con DSN privado real a completar; no ejecutar los imports si falla un paso:

```powershell
# backend; DATABASE_URL todavia representa desarrollo en esta etapa.
$env:TEST_DATABASE_URL = '<DSN privado del laboratorio dedicado terminado en _test>'
.\.venv\Scripts\python.exe -B scripts/setup_test_database.py
if ($LASTEXITCODE -ne 0) { throw 'Fallo la preparacion del laboratorio; no importar.' }
```

Detener aquí la ejecución y completar las comprobaciones de destino, permisos, esquema y estado basal de los pasos anteriores. Sólo después, en esa misma terminal:

```powershell
$env:DATABASE_URL = $env:TEST_DATABASE_URL
# Confirmar mediante lectura current_database()/schema del destino seleccionado.
# No ejecutar la linea siguiente si esa comprobacion no coincide.
.\.venv\Scripts\python.exe -B scripts/import_auctionator.py $env:BETA_COPY --source-id $env:BETA_SOURCE_ID --region $env:BETA_REGION --dataset real
if ($LASTEXITCODE -ne 0) { throw 'Fallo el import; revisar logs y estado del laboratorio.' }
```

Las BETA_* deben definirse también en esta terminal. Si la muestra necesitó mapping/LibCBOR, agregar los parámetros explícitos correspondientes al comando. Las revisiones manuales indicadas son condiciones de paso; pegar todo el bloque sin detenerse a verificarlas no constituye un ensayo seguro.

En una BD nueva con evidencia aceptada, esperar `completed`, `evidence_status=created`, un `export_id` y conteo de hechos coincidente con el offline. Verificar sello, manifest y hechos persistidos; no exigir que el número de observaciones iguale el de hechos, porque un h puede originar una proyección adicional de mínimo.

Reimportar **el mismo archivo con idéntico contexto**. Esperar `duplicate`, cero cambios acumulados y mismo export reutilizado; debe existir otra recepción/import y vínculo. Reimportar no significa “cero escrituras”: se audita la recepción. Un contexto diferente produce otra identidad y no sirve para demostrar idempotencia.

Para inspeccionar API, iniciar un proceso FastAPI adicional sólo con el laboratorio, en un puerto diferente, y comprobar ese destino antes de consultar. No dirigir el dashboard habitual a una mezcla de bases. Consultas de lectura:

- `/partial/markets`: identificar mercado por región/clave/dataset real; no asumir IDs locales.
- `/partial/items?market_id=...`: paginar con limit/offset; sólo lista items con observaciones. Items nativos vacíos pueden existir únicamente en el manifest para ese export.
- `/partial/history`: proporcionar mercado, clave completa, fuente y base; añadir el export_id devuelto para cotejar el archivo. Comprobar `minimum_origin`, `source_fact_id`, claves originales y m sin fecha.
- `/market/series`: descubrir contextos del mercado/item y elegir explícitamente fuente, base y modo.
- `/market/metrics`: usar ese contexto, `source_type=auctionator`, `series_mode=export`, el export elegido y `window_type=observed_buckets` con una ventana válida. La fuente/clave debe codificarse correctamente en la query; no mezclar contextos obtenidos de otros entornos.

Para confrontar por primera vez el archivo, preferir export. Acumulado se revisa aparte con su semántica. Ninguna consulta convierte `imported_at` en fecha de scan ni agrega el nombre del catálogo. Mantener copia de respuestas y conteos antes/después; desarrollo y sus simulaciones deben permanecer sin importaciones ni cambios.

## 9. Pruebas pequeñas de aceptación del primer archivo

| ID | Prueba | Criterio de aceptación |
| --- | --- | --- |
| A1 | Captura y procedencia | Archivo propio/consentido, producto/build/addon/contexto registrados, copia estable con hash, sin simulado renombrado |
| A2 | Parseo sin BD | Etapa 7 termina sin error; dbversion, shape, tipos, límites y codec corresponden a soporte probado; proyección y batch coinciden |
| A3 | Cotejo semántico | Revisar 3–5 claves/días si existen, o todas si hay menos: raw/normalizado, l/h/a/m, fallback, ceros y ausencias coinciden con evidencia disponible |
| A4 | Destino e identidad | Laboratorio exclusivo comprobado; región/mapping/fuente confirmados; variantes/facciones/mercados no fusionados; tablas legacy y desarrollo intactos |
| A5 | Primer import y repetición | completed/created y luego duplicate/reused para igual contexto; hechos/export no duplicados, segunda recepción conservada |
| A6 | Lectura de mercado | Histórico por export reproduce hechos/proyección, m queda excluido del tiempo, calendario unknown, métricas/avisos correctos para la cobertura real |
| A7 | Fallo y aislamiento | Revisar las garantías de rollback de las suites existentes; en una futura ejecución de integración usar sus schemas aislados. Un error real no deja datos parciales y su eventual run failed queda identificado |

A3 no exige que la primera captura contenga todas las variantes ni todos los estados de a/l. Registrar lo no ejercitado. A7 no autoriza corromper manualmente la copia original, provocar fallos en desarrollo ni modificar tests en esta tarea. Si se decide ejecutar regresiones existentes después, [conftest.py](../backend/tests/conftest.py) crea/migra un schema aleatorio en TEST_DATABASE_URL y lo elimina al terminar; no conserva automáticamente una muestra real. Usar otro laboratorio para la revisión manual que deba conservarse.

Formato de resultado a conservar fuera de Git: caso, fecha, hash, ref del proyecto y del addon, contexto, esperado, observado, passed/failed/not_exercised y referencia de evidencia. No reutilizar una aprobación de fixture como resultado del primer archivo real.

## 10. Fallos, rollback y cuarentena

| Punto de fallo | Comportamiento actual / respuesta segura |
| --- | --- |
| Parsing/contrato offline | No hay conexión ni escrituras; tampoco import_run automático. Conservar el error y original, NO GO para persistir |
| Discordancia nativo/batch | El servicio la valida antes de acceder a BD; el cotejo offline debe detectarla antes |
| Error PostgreSQL durante import | La transacción revierte items/mercados, observaciones, export, hechos y vínculos de ese intento; el servicio intenta registrar failed por otra conexión/transacción |
| Base caída al registrar failed | Ese registro puede no existir. La ausencia de run no prueba que no se intentó importar; conservar log externo |
| Deadlock SQLSTATE 40P01 | Hasta tres intentos de la transacción completa, con esperas 10/20 ms; otros errores SQL no reciben ese retry automático |
| Excepción no SQL | Los context managers revierten si no se confirmó; no se garantiza un run failed para excepciones fuera del manejo de psycopg |
| Conexión perdida cerca del commit | El resultado visto por la CLI puede ser incierto; verificar estado/hash/imports en el laboratorio antes de concluir rollback. Reintento sólo con mismo archivo/contexto y apoyo en idempotencia |
| Import confirmado pero semánticamente incorrecto | No es un rollback transaccional. Apartar el laboratorio y repetir en uno nuevo después de corregir contexto/compatibilidad de forma revisada |

Los guards de 004 rechazan UPDATE/DELETE/TRUNCATE sobre exports sellados y modificaciones de hechos/vínculos. **No desactivarlos para limpiar un ensayo.** Borrar un import/fuente tampoco recompone los extremos acumulados anteriores: no hay undo/deimport del servicio ni historial de cada extremo reemplazado. Por eso el primer intento debe ser aislado.

Tras un fallo: detener procesos del laboratorio, guardar logs/hashes y resultados, dejar la base en cuarentena y preparar otra base vacía si se requiere repetir. No borrar tablas compartidas, resetear volúmenes de Docker ni aplicar DELETE por prefijo/IDs. Si accidentalmente se usó desarrollo, detener nuevas escrituras y preparar una recuperación revisada desde respaldo completo hacia otra base; no improvisar cirugía SQL ni asegurar recuperación selectiva que el esquema no permite.

El retorno operativo mínimo es cerrar los procesos/terminales del laboratorio y mantener el backend de desarrollo apuntando a su configuración original. No hace falta alterar ni restaurar los datos simulados si nunca se importó en esa base.

## 11. Riesgos y puertas GO / NO GO

Bloqueos principales que puede revelar el primer archivo:

1. Otro build/revisión del addon, dbversion nueva, rama AH distinta, configuración que no guarda precios o persistencia beta fallida.
2. Codec nativo no probado, serialización mixta de mercados inactivos, globals Lua no soportados o límite real de tamaño/estructura.
3. Precios fraccionarios legítimos o valores fuera de INTEGER; el formato actual no los soporta.
4. Claves de mercado/variantes desconocidas, facciones no identificables, colisiones normalizadas, contexto regional o ruleset no comprobados.
5. Historia previa de otras sesiones/productos, poda, disponibilidad ausente y falta de base temporal verificable.
6. Interpretar real como lanzamiento, archivo guardado como scan individual, a como ventas o hashes como autenticación.

| Puerta | GO | NO GO / alcance limitado |
| --- | --- | --- |
| Captura | Acceso normal, identidad registrada y copia verificable | Sin archivo auténtico o persistencia fallida: conservar evidencia y resolver captura |
| Validación offline | A1–A3 aprobados, formato y contexto comprendidos | Codec/shape/fracción/mapping desconocidos: investigar sin forzar import |
| Laboratorio | A4–A5 aprobados y rollback/aislamiento comprendidos | DSN dudoso, riesgo para desarrollo, incoherencias o evidencia unavailable: no persistir/usar |
| Análisis descriptivo de esa muestra | A6 aprobado, contexto único, valores cotejados y límites visibles | Sólo m, sin buckets de precio: evidencia archivada, sin análisis temporal. Datos sin identidad/contexto fiables: no usar |
| Uso más amplio | Validación de capturas repetidas y alcance AH/codec/reloj documentado | Primera muestra aceptada no certifica toda la beta, todos los items/variantes, lanzamiento, predicción ni oportunidades |

Según [statistics.py](../backend/app/market/statistics.py), un bucket de precio permite mínimo/media/mediana; cambios y desviación requieren al menos dos valores y pendiente al menos tres. Porcentajes con base cero y CV con media cero quedan indefinidos. m no aumenta ese n. [quality.py](../backend/app/market/quality.py) advierte muestras menores de siete buckets; siete es un umbral de presentación, no garantía estadística. Varias capturas del mismo índice no producen varios buckets independientes.

`temporal_basis=unknown` no bloquea el análisis por índices/buckets observados si el resto es válido; sí impide ventanas de calendario verificadas. Disponibilidad ausente limita esas métricas, pero no obliga a rechazar mínimos válidos. Mostrar cobertura y avisos, sin elevar una prueba de ingestión a señal de trading. Fase 3B no está implementada.

**Decisión al 15/10:** GO para preparar la captura del 19/10 y ejecutar primero el adaptador offline cuando exista la copia. NO GO para importar en la base con simulación o afirmar que los datos reales ya están listos para analizar. El avance será captura -> offline -> laboratorio -> lectura por export -> análisis limitado de la muestra, con registro de aceptación en cada puerta.

## 12. Estado Git y alcance de esta entrega

Al iniciar ya existía `?? docs/ITEM_CATALOG_RESEARCH.md`; se conserva sin editar. El único archivo creado por esta tarea es `docs/BETA_DATA_READINESS.md`, también sin seguimiento hasta decisión posterior del usuario. No se modificaron ROADMAP, backend, frontend, tests, migraciones, configuración privada ni datos. HEAD permanece en `85bd0e127b142aadfdce2ba73a552039c0067c94`, sin commit ni push.

La revisión final de esta entrega comprueba formato, referencias locales y estado Git. Los tests citados fueron inspeccionados, no ejecutados. No se certifica el contenido actual de PostgreSQL ni una instalación de cliente/addon.
