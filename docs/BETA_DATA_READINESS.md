# Preparación de datos para la beta del 19/10/2026

Fecha de revisión: **2026-10-15**, America/Buenos_Aires. Investigación original sobre `85bd0e1`; actualización de seguridad sobre `4b93efc`, rama `main`, sin commit de implementación todavía.

**Actualización 21/10/2026: soporte de persistencia 341 preparado para revisión de trial, no autorización de importación auténtica.** La captura real y la validación offline están en [FIRST_REAL_AUCTIONATOR_VALIDATION.md](FIRST_REAL_AUCTIONATOR_VALIDATION.md). Las secciones 1–13 siguientes conservan el estado histórico del 15/10; para 341, metadatos verificados y segregación de stress test prevalece la sección 14. La región de la captura sigue pendiente.

**Cierre técnico:** ver sección 15 para la auditoría y suite completa final. La documentación histórica de cada etapa no constituye autorización de importar capturas auténticas.

**Estado: preparados para intentar captura y validación offline; NO GO todavía para usar datos auténticos en análisis de mercado.** No se recibió ni validó un SavedVariables real de Forever. El 19/10/2026 es la fecha de captura prevista por el usuario; este documento no verifica el calendario oficial ni la disponibilidad de la beta.

La entrega documental original no ejecutó tests ni operaciones en PostgreSQL. La actualización de seguridad sí agrega un modo de ensayo y pruebas con fixtures, exclusivamente en un laboratorio nuevo; sus resultados están en la sección 13. No se obtuvo un SavedVariables auténtico ni se alteraron datos existentes de desarrollo/tests. Los comandos de captura/importación de datos reales siguen siendo instrucciones para una ejecución futura.

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
| [Servicio](../backend/app/ingestion/partial_service.py), migraciones [003](../backend/migrations/003_create_partial_observations.sql) y [004](../backend/migrations/004_create_partial_export_evidence.sql) | Transacciones, idempotencia y evidencia sellada. Factory opcional de conexiones para que import, retries y registro de fallos usen el destino verificado |
| [CLI](../backend/scripts/import_auctionator.py) | Ruta ordinaria preservada. Nuevo `--trial` con selección explícita; `--check-target` verifica identidad sin parsear archivo ni persistir. No hay dry-run del archivo completo en CLI: usar el adaptador offline |
| [Conexión](../backend/app/db/connection.py), [configuración](../backend/app/core/config.py), [guard de ensayo](../backend/app/db/trial.py) | Ordinario usa `DATABASE_URL`. Ensayo compara su identidad efectiva con el destino seleccionado; no cambia settings ni usa automáticamente `TEST_DATABASE_URL` |
| [API parcial](../backend/app/api/partial.py), [contratos de mercado](../backend/app/market/contracts.py), [servicio analítico](../backend/app/market/service.py) | Consulta por contexto explícito; análisis en transacción READ ONLY, REPEATABLE READ |

Se contrastaron código y tests del proyecto con la semántica registrada en [AUCTIONATOR_340.md](AUCTIONATOR_340.md), [PHASE_25_EXPORT_EVIDENCE.md](PHASE_25_EXPORT_EVIDENCE.md), [ARCHITECTURE.md](ARCHITECTURE.md), [PHASE_3A_VALIDATION.md](PHASE_3A_VALIDATION.md) y README. Las validaciones antiguas son evidencia histórica de fixtures y PostgreSQL, no resultados de esta revisión ni soporte demostrado del cliente de beta actual. Los fixtures construidos que se llaman `real` prueban segregación del contrato, no autenticidad de datos de Forever.

Cobertura inspeccionada en la entrega original; las suites repetidas durante la actualización se identifican en la sección 13:

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

## 8. Ensayo seguro con selección explícita del destino

La CLI ordinaria continúa usando `DATABASE_URL`. Para un ensayo se debe usar `--trial`; no sobrescribir DATABASE_URL ni cambiar `.env` para apuntar al laboratorio. Esa configuración identifica la base **protegida**, cuya identidad se consulta en modo READ ONLY. `TEST_DATABASE_URL` por sí sola no selecciona el destino; puede usarse como fuente del DSN sólo si se nombra expresamente con `--database-url-env`.

### Condiciones previas y comprobación real

1. Provisionar una base dedicada a ensayos, con nombre sencillo terminado en `_test`, distinta de desarrollo. La CLI no crea bases, no aplica migraciones y no limpia registros. Antes de importar debe tener las migraciones existentes 001–004, preparadas exclusivamente allí por un operador que haya verificado el destino. `setup_test_database.py` conserva su guard anterior basado en nombres: **no es sustituto** del nuevo guard de importación ni debe ejecutarse contra un destino incierto.
2. Mantener DATABASE_URL en su valor habitual. La validación exige conexiones con host, port, dbname y user explícitos, un solo host y sin `service`, `options`, replicación o parámetros no admitidos. Se admiten password/passfile y opciones TLS listadas en el guard; no hay que incluir credenciales en argumentos.
3. Se rechazan overlays de routing/sesión PGHOST, PGHOSTADDR, PGPORT, PGDATABASE, PGUSER, PGSERVICE, PGSERVICEFILE, PGOPTIONS, PGTARGETSESSIONATTRS y PGLOADBALANCEHOSTS. Usar una terminal limpia. Timeout de conexión: 3 s; statement_timeout: 15 s; lock_timeout: 5 s; search_path fijo public.
4. Se consulta `pg_catalog.pg_control_system().system_identifier` y el OID de `pg_database` correspondiente a `current_database()` en **ambas conexiones reales**. El par clúster/OID debe ser diferente. Cambiar hostname, URL/conninfo o parámetros no permite eludirlo. Además se exige que el nombre efectivo coincida con `--expected-database`, y que el destino no está en recovery.
5. Si desarrollo no es accesible o falta permiso para leer la identidad del clúster, se rechaza el ensayo. No hay fallback a comparar textos, nombres o direcciones IP. No se conceden permisos automáticamente. Un administrador debe revisar los privilegios mínimos si se usa un rol restringido.
6. Antes de entregar cada escritor se vuelve a consultar **también la identidad protegida**, mediante una transacción READ ONLY en la conexión protegida conservada. Deben coincidir clúster/OID/nombre y estado de recovery con la lectura inicial. Si la conexión se pierde, queda ocupada, deja de ser READ ONLY o falla la consulta, se aborta; no se reconecta automáticamente la base protegida. La identidad del destino se comprueba dentro de la propia transacción que va a escribir: import, retry y registro de failed. Si cambia, se detiene antes de INSERT/nextval. Las reconexiones del destino deben conservar su identidad inicial y pasan otra vez por ambas comprobaciones; no hay fallback global.

El alcance soportado es **PostgreSQL directo y estable, con un laboratorio confiable**. No se afirma soporte para PgBouncer, proxies que redistribuyan transacciones, balanceo entre clústeres ni cambios de routing/DNS/backend durante el ensayo. No existe una comprobación puntual que garantice el comportamiento futuro de un router arbitrario. Un único hostname tampoco demuestra conexión directa: el operador debe comprobar la topología. La revalidación detecta cambios observados; no convierte una topología dinámica en soportada.

Como defensa complementaria, usar un rol exclusivo del laboratorio, sin permisos de escritura sobre desarrollo ni otras bases. La conexión protegida sólo necesita conexión y lectura de identidad, no DML sobre tablas. No usar superusuario como requisito del ensayo ni conceder pg_monitor por defecto. En PostgreSQL 16.15 local se comprobó EXECUTE para PUBLIC sobre pg_control_system(); otros servidores pueden restringirlo y entonces el guard rechaza el ensayo. Un administrador debe evaluar cualquier permiso mínimo necesario por separado. La CLI y estas pruebas no crean roles ni cambian permisos de las bases existentes.

La identidad de clúster es una propiedad de PostgreSQL documentada en [Control Data Functions](https://www.postgresql.org/docs/16/functions-info.html#FUNCTIONS-PG-CONTROL). Clones físicos pueden compartir system_identifier y OIDs: el guard los rechaza conservadoramente si coinciden con la base protegida. No se puede certificar que un laboratorio está vacío o que sus datos sean descartables sólo por su nombre; eso sigue siendo una comprobación del operador. Los servidores y sus catálogos deben ser de confianza.

### Comandos exactos, desde backend

Con la base ya provisionada, seleccionar el DSN privado en una variable de entorno del proceso. No añadir BETA_TRIAL_DATABASE_URL a `.env`: no es un campo de Settings y continúa siendo una configuración no reconocida. El prompt protegido evita guardarlo como texto en el historial; no imprimir la variable. Reemplazar el nombre esperado por el de la base realmente creada:

```powershell
$trialDsnSecret = Read-Host 'DSN privado del laboratorio (host/port/dbname/user explicitos)' -AsSecureString
$env:BETA_TRIAL_DATABASE_URL = [System.Net.NetworkCredential]::new('', $trialDsnSecret).Password
Remove-Variable trialDsnSecret
$trialDatabaseName = 'wow_forever_beta_20261019_test'

.\.venv\Scripts\python.exe -B scripts/import_auctionator.py --trial --database-url-env BETA_TRIAL_DATABASE_URL --expected-database $trialDatabaseName --check-target
if ($LASTEXITCODE -ne 0) { throw 'Destino no verificado; no importar.' }
```

`--check-target` no requiere archivo, source-id, región ni dataset; no parsea ni escribe datos. Su JSON contiene sólo nombre, OID de base y system_identifier, sin DSN/usuario/password. Comparar esos valores con los esperados del laboratorio y conservarlos en la hoja de ensayo. Para una comprobación independiente en una consola SQL conectada privadamente al laboratorio:

```sql
BEGIN READ ONLY;
SELECT current_database(), d.oid AS database_oid, s.system_identifier,
       inet_server_addr(), inet_server_port(), current_schema(),
       current_setting('transaction_read_only')
FROM pg_catalog.pg_database d CROSS JOIN pg_catalog.pg_control_system() s
WHERE d.datname=current_database();
ROLLBACK;
```

Comprobar asimismo migraciones, tablas y conteos del laboratorio. La comprobación de identidad es automática pero el cotejo con el laboratorio previsto es manual. El import vuelve a verificar todo: un check previo no es un permiso reutilizable para saltar la validación.

Sólo después del GO offline y de destino, usando las BETA_COPY/BETA_SOURCE_ID/BETA_REGION de la sección 7:

```powershell
.\.venv\Scripts\python.exe -B scripts/import_auctionator.py $env:BETA_COPY --source-id $env:BETA_SOURCE_ID --region $env:BETA_REGION --dataset real --trial --database-url-env BETA_TRIAL_DATABASE_URL --expected-database $trialDatabaseName
if ($LASTEXITCODE -ne 0) { throw 'Ensayo fallido; conservar copia y revisar el laboratorio.' }
```

Agregar `--market-map` y/o `--allow-libcbor` sólo cuando la validación offline los haya confirmado. Omitir `--scan-day-zero` si es unknown. Sin --trial, la llamada anterior seguiría la ruta ordinaria: **no omitir ese flag**. --database-url-env/--expected-database/--check-target sin --trial se rechazan. No es válido suministrar un DSN directamente a --database-url-env: el argumento debe ser el nombre de una variable.

Al terminar, cerrar los procesos del laboratorio y retirar sólo la variable de destino de esa terminal (`Remove-Item Env:BETA_TRIAL_DATABASE_URL`). DATABASE_URL no se modifica. El DSN permanece como secreto del proceso mientras se usa; no es un almacén de secretos y no debe compartirse el entorno.

En una BD nueva con evidencia aceptada, esperar `completed`, `evidence_status=created`, un `export_id` y conteo de hechos coincidente con el offline. Verificar sello, manifest y hechos persistidos; no exigir que el número de observaciones iguale el de hechos, porque un h puede originar una proyección adicional de mínimo.

Reimportar **el mismo archivo con idéntico contexto**. Esperar `duplicate`, cero cambios acumulados y mismo export reutilizado; debe existir otra recepción/import y vínculo. Reimportar no significa “cero escrituras”: se audita la recepción. Un contexto diferente produce otra identidad y no sirve para demostrar idempotencia.

La selección --trial afecta sólo a esta CLI, no a servidores FastAPI ya iniciados. Para inspeccionar API, usar otro proceso y otra terminal configurados exclusivamente para el laboratorio, en un puerto diferente, después de verificar ese destino. No cambiar DATABASE_URL en la terminal del ensayo: debe seguir identificando la base protegida. No dirigir el dashboard habitual a una mezcla de bases. Consultas de lectura:

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

A3 no exige que la primera captura contenga todas las variantes ni todos los estados de a/l. Registrar lo no ejercitado. A7 no autoriza corromper manualmente la copia original ni provocar fallos en desarrollo durante la captura. Para regresiones, [conftest.py](../backend/tests/conftest.py) crea/migra un schema aleatorio en TEST_DATABASE_URL y lo elimina al terminar; no conserva automáticamente una muestra real. Usar otro laboratorio para la revisión manual que deba conservarse.

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

## 12. Estado de la entrega documental original

La entrega documental original agregó únicamente `docs/BETA_DATA_READINESS.md`, manteniendo intacta la investigación de catálogo. Ambos documentos quedaron versionados posteriormente en `4b93efc`. El estado previo sin seguimiento y sin cambios de implementación corresponde a esa entrega histórica.

La actualización de seguridad siguiente sí modifica CLI/servicio y agrega tests. No se certifica una instalación del cliente/addon ni una muestra auténtica.

## 13. Actualización de seguridad: alcance y validación

Se inspeccionaron las conexiones globales de `app/db/connection.py`, configuración, CLI, servicios de ingestión parcial/completa y scripts de migración/preparación. El servicio parcial escribe al importar y también al registrar un fallo: ambas rutas aceptan ahora la factory verificada. El servicio de snapshots completos, endpoints de importación ordinarios y scripts de preparación/migración conservan sus conexiones originales; el nuevo modo no los redirige. No se modificó ninguna migración ni contrato Auctionator.

`--trial` requiere selección explícita por nombre de variable y nombre esperado de base. No cambia settings globales. El guard hace probes READ ONLY y revalida la identidad protegida antes de cada escritor; verifica el destino dentro de la transacción que va a escribir. Conserva ambas identidades iniciales durante la ejecución. Los errores del driver y del import se ocultan en stderr; los runs failed del ensayo reciben un mensaje fijo sin datos de conexión. La importación ordinaria conserva su selección de destino y contratos; sus excepciones inesperadas en la CLI también reciben ahora un mensaje fijo.

La CLI protege además los imports que instancian Settings (`partial_service -> connection -> config`). Una configuración inválida, incluida una clave desconocida con DSN en `.env`, termina con código 1 y un mensaje fijo, sin imprimir ValidationError, input_value ni la excepción original. No se ignoran claves desconocidas ni se modifica la configuración global de Pydantic o del backend. No se guardan detalles sensibles para mostrarlos después; el operador debe revisar la configuración privadamente. No se garantiza un run failed para un fallo de inicialización o de identidad: no se entrega una conexión de escritura.

Tests nuevos: [test_trial_database.py](../backend/tests/test_trial_database.py) y [test_trial_database_integration.py](../backend/tests/test_trial_database_integration.py). Cubren selección, ausencia, parámetros ambiguos, permisos/identidad no comprobables, misma base efectiva y alias reales, cambio de identidad, conexión/credenciales incorrectas, preview sin escrituras, errores redactados, registro de failed, retry revalidado, idempotencia y ruta ordinaria. La integración exige `TRIAL_INTEGRATION_DATABASE_URL` y `TRIAL_INTEGRATION_DATABASE_NAME` explícitos, y verifica el laboratorio antes de usarlo; nunca cae a desarrollo.

Se preparó una base nueva dedicada `wow_beta_guard_7af27fd1381d_test`, distinta por identidad efectiva de desarrollo y de la base de tests existente. Sólo allí se aplicaron las migraciones existentes y se escribieron fixtures sintéticos. No se borraron/recrearon bases existentes ni volúmenes. La preparación inicial detectó un search_path que impedía crear tablas; la transacción del laboratorio revirtió y se corrigió el path fijo a public antes de completar las migraciones.

Validación ejecutada: **184 tests aprobados** de selección de ensayo, integración real, Auctionator, parser/hardening, evidencia nativa, ingestión parcial, exports y concurrencia/rollback. Hubo un aviso de deprecación de Starlette/httpx ya presente en las dependencias. Sin datos reales de Forever. La sintaxis/ayuda de los flags se comprobó con la CLI real; los comandos de captura beta no se ejecutaron.

Para repetir esas suites, usar sólo un laboratorio de tests ya provisionado y verificado. Desde backend, después de seleccionar privadamente BETA_TRIAL_DATABASE_URL y confirmar trialDatabaseName como en la sección 8, sin cambiar DATABASE_URL:

```powershell
$env:TRIAL_INTEGRATION_DATABASE_URL = $env:BETA_TRIAL_DATABASE_URL
$env:TRIAL_INTEGRATION_DATABASE_NAME = $trialDatabaseName
$env:TEST_DATABASE_URL = $env:BETA_TRIAL_DATABASE_URL
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_trial_database.py tests/test_trial_database_integration.py tests/test_auctionator.py tests/test_native_exports.py tests/test_hardening_parser.py tests/test_partial_integration.py tests/test_export_integration.py tests/test_hardening_integration.py
```

Estas pruebas escriben fixtures en el laboratorio; no ejecutarlas sobre una base que deba permanecer como captura de aceptación sin datos de tests. No registrar ni publicar valores de las variables de conexión.

Se compararon antes y después hashes de todas las filas y `last_value/is_called` de todas las secuencias de las dos bases existentes: coincidieron exactamente. Desarrollo tiene 13 tablas, 16.785 filas totales y 11 secuencias; la base de tests existente tiene 13 tablas, 4 filas y 11 secuencias. Desarrollo conserva sus **16.628 observaciones parciales**, con SHA-256 de filas ordenadas `0cdfa3139163c304ef862b8082e015be0d9f399596cca738bf96f3a60da0e1b8`. El hash del snapshot de control completo normalizado es `293677505c8b784bd578c24b5cf2873b2b9f624f22f8be289ecb6d45ecbf808d` en ambos extremos. Los snapshots son privados y no contienen DSNs ni filas originales.

Límites: se necesita permiso de lectura de `pg_control_system()` en ambos destinos, un único host y parámetros explícitos; si no se puede verificar se rechaza. La base protegida es la configurada en DATABASE_URL al iniciar: no sobrescribirla para “seleccionar” el ensayo. El operador sigue siendo responsable de provisionar y elegir un laboratorio real, de confianza y con permisos apropiados. El guard no certifica vacío, finalidad o privacidad de cualquier otra base terminada en `_test`. No es una sandbox para un servidor hostil. El rollback SQL no revierte incrementos de secuencias de intentos que sí llegaron a escribir **en el laboratorio**; las validaciones rechazadas antes de escribir sí dejan filas y secuencias intactas.

No se implementa un undo de imports confirmados ni soporte nuevo de codecs/precios. No hubo commit ni push. La preparación técnica del ensayo puede revisarse separadamente del NO GO para analizar datos auténticos que aún no fueron obtenidos.

### Hardening posterior a la auditoría adversarial

Se agregan regresiones en `test_trial_cli_startup.py` mediante procesos reales de la CLI y archivos `.env` exclusivamente temporales: claves desconocidas con credenciales sintéticas, errores Pydantic/decodificación, DSNs inválidos y selección requerida ausente. Se comprueba salida no cero y ausencia de DSN/contraseña/traceback en stdout y stderr. Puede ejecutarse esta suite sin PostgreSQL:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_trial_database.py tests/test_trial_cli_startup.py
```

Las regresiones de identidad cubren cambios de la base protegida y del destino, pérdida de conexión, errores de permisos/consulta, sesiones ocupadas o escribibles y revalidación antes del primer escritor, reconexiones, retry y registro de failed. La integración añade rechazo antes del escritor con filas y secuencias del laboratorio intactas, simulando el cambio de identidad protegida sobre conexiones PostgreSQL reales. No intenta certificar routing dinámico ni modifica permisos para provocar fallos.

Los **184 tests** y hashes anteriores corresponden a la validación inicial, previa a este hardening; no son el resultado de la nueva suite. Para repetir el conjunto completo anterior, agregar `tests/test_trial_cli_startup.py` al comando de integración, manteniendo exclusivamente el laboratorio verificado. Los fixtures de integración sí escriben allí; nunca usar desarrollo o una captura auténtica para estas regresiones.

Validación final de este hardening (15/10/2026): **214 tests aprobados**, incluidos 58 casos unitarios de guard/CLI y procesos reales de inicialización. Se ejecutó el conjunto completo indicado, agregando la suite de startup; la integración se dirigió exclusivamente al laboratorio ya autorizado `wow_beta_guard_7af27fd1381d_test` (OID 339038), después de comprobar su identidad y las migraciones 001–004. Se repitieron ambos contraejemplos originales y fueron rechazados antes del escritor o sin revelar credenciales, respectivamente. El único aviso fue la deprecación existente de Starlette/httpx.

El control de todas las filas por tabla y de `last_value/is_called` de las 11 secuencias coincidió exactamente antes/después en desarrollo (13 tablas, 16.785 filas, incluidas 16.628 observaciones parciales) y en la base de tests existente (13 tablas, 4 filas). El laboratorio pasó de 232 a 340 filas por los fixtures autorizados y sus secuencias pudieron avanzar; no se presenta como preservado ni como captura real. No hubo cambios de roles/permisos, archivos `.env` reales, configuración global de Settings, migraciones ni contratos Auctionator. `git diff --check` y la revisión equivalente de archivos nuevos no detectaron errores de whitespace. No hubo commit ni push. Veredicto técnico: **READY TO COMMIT**, exclusivamente dentro del alcance directo/estable documentado; no certifica datos auténticos ni proxies.

## 14. Persistencia 341 con procedencia verificada y destino trial

**Actualización 5B.1.1 (24/10/2026):** el procedimiento de importación de esta
sección es histórico. Las escrituras 341 ahora requieren identidad económica y
linaje local completos, además de TrialDatabase y 006. La CLI anterior se niega
a importar 341; no ejecutar los comandos históricos para sortear esa restricción.
Ver sección 16 y el informe de 5B.1. `--check-target` continúa siendo sólo lectura.

Actualización del **21/10/2026**, sin commit ni push. El SavedVariables auténtico fue validado offline; **no se importó**, ni siquiera al laboratorio. La preparación técnica está **READY FOR TRIAL REVIEW**, con NO GO para ejecutar la captura mientras falten región/contexto y revisión humana.

### Cambio de alcance respecto de la etapa offline

El modelo l/h/a/m, items, variantes, buckets y transacciones no necesitó nuevas columnas ni tablas. Se añadió [005_auctionator_341_provenance.sql](../backend/migrations/005_auctionator_341_provenance.sql) porque los CHECK existentes sólo admitían versión 340, tres etiquetas de input y un decoder. La migración amplía exclusivamente restricciones de metadatos, agrega comprobaciones de procedencia para 341 y un trigger complementario de transporte; mantiene intactos todos los guards de sellado, inmutabilidad, coherencia y contexto de 004. No cambia filas, no hace backfill ni crea secuencias. Los CHECK ampliados se agregan `NOT VALID` y se validan dentro de la transacción de migración; las versiones originales 003/004 no se editan.

`CaptureProvenance` contiene attestaciones explícitas del operador, separadas de los hechos del Lua. Se guarda en `structure_manifest.provenance`, ya protegido por el sello existente. La recepción conserva codec/perfil y decoder en `partial_export_imports`, versión en el run/export y hash de bytes en `partial_import_runs`. No se etiqueta el productor como confirmado por haber decodificado CBOR.

El hash de archivo de los metadatos debe coincidir con los bytes leídos. Se excluye sólo ese hash del manifest canónico porque ya queda en cada recepción: dos serializaciones equivalentes con igual contexto pueden reutilizar el export, conservando ambas recepciones y sus hashes originales. Los refs/claims y el contexto sí participan del estado canónico; cambiar una attestation produce evidencia distinta. Los manifests 340 sin procedencia conservan exactamente su forma y hash anteriores.

### Segregación de stress test

Para esta captura el contexto requerido es **`dataset=stress_test`, `capture_phase=stress_test`, `source_type=auctionator`**. Continúan siendo datos auténticos; `stress_test` expresa su contexto y no los convierte en simulación. La unicidad existente `(region, market_key, dataset)` crea mercados distintos de `real` (lanzamiento/u otro contexto real) y `simulated`. Las observaciones dependen de ese market_id y mantienen además fuente y base temporal. La clave nativa `PvP` no se reescribe.

El catálogo global `partial_items` sigue compartido por identidad/variante, como antes; la segregación se aplica al mercado y sus observaciones/exports. El primer ensayo auténtico requerirá su propio laboratorio vacío, separado de simulación y de los fixtures de esta validación. No reutilizar el laboratorio de regresiones como captura de aceptación.

### Evidencia requerida para región, mercado y origen

No se infiere región por idioma, ubicación, huso horario, PvP ni producto `wowf`. Se necesita un identificador técnico verificable del cliente/servicio y evidencia de su asociación con **ese producto, mercado y origen de captura**: registro de configuración/selector oficial o información técnica autoritativa que permita establecer dicha asociación. Una región de cuenta sin vínculo demostrado con el mercado técnico no basta. Si el alcance/facción del AH sigue siendo ambiguo, no certificarlo por el nombre PvP.

El operador debe conservar privadamente un registro que vincule SHA-256, sesión, producto, mercado/alcance y origen, y asignar un `source_id` estable seudónimo para esa cuenta/historia/reloj. `region_evidence_ref`, `market_evidence_ref` y `origin_evidence_ref` deben apuntar a esos registros revisados, mediante refs seudónimos sin credenciales ni datos personales. El software verifica presencia, sintaxis y concordancia; **no autentica automáticamente la verdad de una referencia externa**. La revisión del operador sigue siendo necesaria.

Los claims `installed_client_build`/`installed_addon_version` describen la instalación inspeccionada. `capture_client_build`/`capture_addon_version` sólo se completan con evidencia propia de la sesión; nunca se copian automáticamente. `codec_producer=unverified` y ref nulo son válidos con `cbor-definite`; confirmar un productor exige su ref de evidencia separado. El contexto temporal sigue `scan_day_zero=None` hasta medirlo, sin convertir 2485 a fecha civil.

### Metadatos privados: plantilla deliberadamente incompleta

Guardar fuera de Git. **Esta plantilla no pasa validación hasta reemplazar los pendientes con evidencia revisada**; no autoriza ni prepara automáticamente una importación:

```json
{
  "version": 1,
  "source_sha256": "7d5cf3db48fa78ab19d3a359557470752e634da743cebe42833fb07c10aa458b",
  "format_version": "341",
  "source_id": "<SEUDONIMO_ESTABLE_DE_LA_CAPTURA>",
  "region": "<REGION_TECNICA_VERIFICADA>",
  "dataset": "stress_test",
  "capture_phase": "stress_test",
  "market_rulesets": {"PvP": "PvP"},
  "region_evidence_ref": "PENDIENTE",
  "market_evidence_ref": "PENDIENTE",
  "origin_evidence_ref": "PENDIENTE",
  "installed_client_build": null,
  "capture_client_build": null,
  "installed_addon_version": null,
  "capture_addon_version": null,
  "codec_producer": "unverified",
  "codec_producer_evidence_ref": null
}
```

Cada claim conocido usa `{"value":"valor observado","evidence_ref":"ref revisado"}`. Los refs `PENDIENTE`, región ausente/placeholder, JSON duplicado, fase/dataset contradictorios, contexto distinto del CLI, mercados discordantes y hash distinto se rechazan. Se limita el archivo de metadatos a 64 KiB. No hay región ni dataset nuevo seleccionado por defecto.

### Secuencia futura del primer trial auténtico, aún no ejecutada

1. Revisar informe, diff, migración y resultados. Resolver región y contexto de origen/mercado; completar privadamente el JSON. Confirmar el hash original y repetir el adaptador **offline** con ese `CaptureProvenance` para verificar contexto, manifest, 21 hechos, 28 observaciones y proyección.
2. Obtener autorización explícita para la escritura real. Provisionar un destino aislado, vacío y distinto de desarrollo/tests/regresiones. Seleccionar su DSN privadamente por variable de entorno y nombre exacto terminado en `_test`; no cambiar `DATABASE_URL` ni `.env`.
3. Verificar identidad efectiva de origen protegido y destino con `TrialDatabase`. Preparar/aplicar las migraciones pendientes **sólo dentro de `TrialDatabase.connection()`**, con su identidad revalidada y tracking de migraciones en ese destino. No usar el comando ordinario `scripts/migrate.py`, cuyo default sigue siendo desarrollo. La migración 005 requiere locks DDL; planificar esa preparación en un laboratorio sin escritores concurrentes.
4. Ejecutar `--check-target` sin el archivo para una comprobación de identidad sin escritura. Ese preview no valida el Lua ni el JSON y no sustituye los pasos anteriores.
5. Sólo después de las puertas anteriores y de la revisión final, el comando de importación sería el siguiente desde `backend`; **no se ejecutó con datos auténticos**:

```powershell
.\.venv\Scripts\python.exe -B scripts/import_auctionator.py $env:BETA_COPY --source-id $env:BETA_SOURCE_ID --region $env:BETA_REGION --dataset stress_test --source-version 341 --serialized-codec cbor-definite --provenance-file $env:BETA_PROVENANCE_FILE --trial --database-url-env BETA_TRIAL_DATABASE_URL --expected-database $trialDatabaseName
```

`BETA_SOURCE_ID`/`BETA_REGION` deben coincidir exactamente con el JSON; el dataset y formato también. Omitir `--scan-day-zero` mientras sea desconocido. No usar `--allow-libcbor`, quitar evidencia, declarar 340 o convertir a HTTP para sortear el guard. La revisión 341 es selección explícita de formato basada en evidencia disponible, no autodetección del SavedVariables.

El CLI requiere `--trial` y `--provenance-file` para todo perfil nuevo. El servicio exige un objeto `TrialDatabase`, no una factory arbitraria, y valida nuevamente el metadata/batch/evidencia antes de entrar al escritor. La conexión pertenece exclusivamente al target y todas las operaciones, retries y registros de fallo usan `target.connection()`. `TrialDatabase` no cambió: mantiene conexión directa estable, comparación de cluster/OID, verificación del protegido, revalidación en la transacción y mensajes sin credenciales. El servicio comprueba la migración 005 **antes de INSERTar cada run**, incluidos failed, para no consumir secuencias en un destino no preparado.

6. En una futura ejecución autorizada, comprobar por export el sello, el manifest/provenance, origen h_fallback, l vacío, a y m, los 21 hechos/28 observaciones y la repetición idempotente. La aceptación de persistencia no habilita todavía frontend ni cálculos 3A/3B sobre 341: sus contratos no se modificaron en esta tarea y deben evaluarse aparte antes de dirigirles estos datos.

### Pruebas y preservación de esta entrega

Se preparó exclusivamente el laboratorio nuevo `wow_341_persistence_8630425299b0_test` (OID 422588), verificado por `TrialDatabase`, y se aplicaron allí 001–005. Sólo se persistieron fixtures sintéticos, tanto en public como en schemas efímeros de tests dentro de ese laboratorio. No se migró ninguna base existente. No se importó el SavedVariables auténtico; el control final encontró **cero runs con su SHA-256** en el laboratorio.

Resultado: **333 tests aprobados** en el conjunto completo; después del cierre del preflight de schema y del CLI 341 se aprobaron **140 tests focalizados**, con cuatro casos nuevos (**337 casos distintos aprobados**). Incluyen 340, 341, codecs, procedencia, hashes, regiones/contradicciones, variantes, l/h/a/m, equivalencia y repetición, exports distintos, aislamiento stress/launch/simulation, concurrencia, rollback, failed/retry, guards de target y procesos reales de CLI. La captura auténtica se leyó únicamente en la prueba offline. El único warning funcional fue la deprecación existente Starlette/httpx.

La primera preparación de carpetas de pytest falló por ACL de Windows/Python `mkdir(0700)`. Se repitió con una carpeta temporal nueva que hereda la ACL del Temp autorizado, sin cambiar permisos de directorios existentes ni controles de producto. El conjunto final y los casos focalizados terminaron correctamente. Se bloquearon defensivamente las conexiones fuera del laboratorio salvo lecturas del protegido y cualquier intento de crear un run con el hash auténtico; hubo cero intentos de persistencia auténtica.

Antes/después se compararon identidad, hashes de todas las filas por tabla, `last_value/is_called` de todas las secuencias y definiciones de restricciones de las dos bases existentes. **Coincidencia exacta**: desarrollo 13 tablas, 16.785 filas y 11 secuencias; tests existente 13 tablas, cuatro filas y 11 secuencias. Hash agregado de control idéntico: `308c9223cf677c728be3c12509870078e9dd330df2f713a1f959d02143057d23`. Desarrollo conserva sus 16.628 observaciones parciales. Los controles privados contienen conteos/hashes, no filas ni DSNs. Las filas/secuencias del laboratorio sí avanzaron por los fixtures y no se declaran preservadas.

**READY FOR TRIAL REVIEW** describe el código y procedimiento preparados para revisión. La región técnica y la aprobación de la importación real siguen pendientes. Sin commit ni push.

## 15. Cierre técnico de compatibilidad 341

Auditoría final del **21/10/2026**, sobre los cambios de integración y documentación existentes, sin funcionalidades nuevas. Se corrigió una inconsistencia acotada del adaptador: un marcador de versión de mercado presente con null se trataba como ausente. Ahora una clave presente exige exactamente el entero 2; cinco regresiones cubren los marcadores explícitos inválidos. Se mantiene la compatibilidad de marcadores ausentes y de la captura auténtica con versión 2. No se requirió rediseño ni migración adicional.

Se ejecutó **la suite completa del backend: 730 aprobados, uno omitido**, más el warning de deprecación Starlette/httpx ya existente. Se incluyeron las regresiones de 340/341, codec y contratos, exports, ingestión/idempotencia, concurrencia, guards, migraciones y los motores analíticos existentes. El único caso omitido fue el opt-in de captura auténtica, sin `AUCTIONATOR_REAL_CAPTURE`; ninguna prueba obligatoria necesita rutas privadas o el archivo original. La evidencia auténtica offline de las etapas previas conserva su alcance, sin afirmar una nueva validación de esa copia en este cierre.

Para cumplir **cero conexiones a desarrollo**, se prepararon dos bases de laboratorio desechables: target `wow_341_close_target_6bdc10a561_test` y referencia protegida `wow_341_close_protected_928f0886fb_test`. Las variables de selección se limitaron al proceso de tests, sin cambiar `.env`. Un control del driver admitió exclusivamente esas bases y registró 1.376 sesiones, cero intentos fuera de ellas y cero intentos de persistencia auténtica. La referencia permaneció vacía; el target recibió sólo fixtures sintéticos. Se probó nuevamente 005 en destino vacío y su preservación de evidencia 340 sellada. **No se conectó, escribió ni migró desarrollo ni se modificaron sus datos simulados.** Los snapshots de preservación de la sección 14 corresponden a aquella ejecución anterior, no a nuevas lecturas de desarrollo.

Los archivos del commit se limitan a código/tests de integración y documentación; no incluyen Lua auténtico, copias de capturas, credenciales, `.env`, temporales ni bases. `git diff --check` y las comprobaciones de sintaxis/whitespace/enlaces pasaron. El README ahora refleja 341 validado offline, persistencia probada en laboratorio e importación auténtica aún pendiente. La región técnica y procedencia completa siguen sin verificar; build de captura y productor de codec no se dan por confirmados. El índice no se convierte a fecha civil y los datos de stress test no se presentan como mercado de lanzamiento.

Una segunda captura posterior fue informada por el operador y queda fuera de este cierre, sin incorporarla a Git ni anticipar resultados. El roadmap de Fase 5A está en el [README](../README.md): programa Windows para detectar guardados tras `/reload`/salida, esperar escritura completa, validar/archivar una copia independiente, distinguir cambios de precios/configuración, deduplicar por hash y conservar trazabilidad. Primera entrega sin PostgreSQL ni envío automático. Fases posteriores: sincronización autenticada, dos a cuatro escaneos diarios manuales, histórico/análisis reales y estudio de estacionalidad/modelos. Sólo se documentó; no se implementó.

**READY FOR TRIAL REVIEW** sigue siendo el límite de autorización para datos auténticos. El cierre habilita el commit/push autorizado de la integración revisada; no habilita ejecutar el primer trial sin completar las condiciones de la sección 14 y recibir revisión específica.

## 16. Requisitos de identidad y linaje de 5B.1.1

Actualización del **24/10/2026**. Prevalece sobre los comandos históricos 341
anteriores. La auditoría de cierre y publicación se registra en la sección 10
del informe. Ver [modelo, ejemplos, migración y resultados](PHASE_5B1_INGESTION_READINESS.md#9-actualización-5b11-identidad-y-linaje-persistente).

La persistencia 341 exige ahora un binding de captura local completo, además de
la procedencia y TrialDatabase. Quitar el binding o seleccionar el importador
antiguo no permite escribir: **la CLI 341 se niega a importar** hasta que una
fase posterior integre el contrato de archivo completo. `--check-target` sigue
verificando sólo identidad de destino, sin validar una captura ni escribir.
La ruta 340 sigue disponible para su contrato anterior; no se puede etiquetar
un archivo 341 como 340, omitir evidencia ni convertirlo a HTTP para sortearlo.

Antes de una futura ejecución auténtica:

1. Revisar 5B.1.1 y la migración 006. Validar privadamente el ámbito económico
   técnico estable, región, reino cuando conocido y si el AH comparte facciones
   o está separado. La clave PvP y la facción del jugador no prueban ese alcance.
   Conservar unknown como desconocido y detener el caso si falta evidencia.
2. Preparar VerifiedLocalContext (`verified-local-capture-v1`) con CaptureProvenance
   341 y el dataset explícito simulated, stress_test o launch. Launch es un dataset
   nuevo; no renombrar los registros real antiguos. El source_id sigue siendo
   estable por origen/historia y no forma parte de la identidad económica.
3. Conservar el original 5A y CaptureMetadata íntegros. El helper de biblioteca
   prepare_local_capture recibe sus bytes/metadatos y contexto verificado, coteja
   hashes completos y rechaza toda la captura si cualquier precio supera 32 bits.
   No reemplazar adquisición UTC por hora de scan; native_scan_timestamp es null.
4. Obtener autorización específica para datos auténticos y provisionar un destino
   vacío aislado de aceptación, separado de desarrollo y de los laboratorios de
   fixtures. Verificar ambas identidades con TrialDatabase; preparar 001–006 sólo
   en ese destino verificado. No usar el default de migrate.py ni editar .env.
5. La futura escritura de biblioteca deberá usar PartialIngestionService con
   trial_target exclusivamente. Toda escritura 341 exige binding verificado y
   preflight de 005/006 antes de INSERT; retries/failed conservan el mismo guard.
   Este procedimiento describe requisitos: **no se ejecutó con datos auténticos**.

Un mercado verificado puede ser observado por dos fuentes sin duplicarlo.
Export v2 comparte hechos nativos equivalentes; partial_capture_receipts conserva
cada adquisición/procedencia y los hashes originales, con sus propios runs y
vínculos append-only. Dos estados distintos del bucket 2485 siguen siendo dos
estados de un índice, sin fabricar dos días. El camino local no puebla el acumulado
003 ni habilita los lectores/dashboard 3A/3B actuales.

La primera prueba con `/reload` real y la primera importación auténtica siguen
pendientes. Región, ámbito/facción, build de sesión y productor efectivo del codec
de las capturas privadas no se dan por confirmados. Los laboratorios de esta fase
contienen sólo fixtures sintéticos y no son capturas de aceptación.
