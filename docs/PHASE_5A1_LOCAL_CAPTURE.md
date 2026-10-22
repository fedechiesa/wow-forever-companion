# Fase 5A — Local Capture Companion

Entrega **5A.1**, 22/10/2026: captura manual, validación offline y archivado
local. Sin observador, servicios permanentes, PostgreSQL, migraciones,
sincronización, cambios de frontend ni de motores 3A/3B. La validación inicial
usó archivos sintéticos. La auditoría final distingue la inspección offline de
copias auténticas de su aceptación por el archivador; no importa datos a una base.

## Arquitectura

Se revisaron README, arquitectura, preparación de beta, contratos parciales,
procedencia, evidencia nativa y parser Lua/CBOR del cierre `2d46245`.

```text
scripts/capture_auctionator.py             ejecución manual, resumen sin rutas
  -> app/local_capture/archive.py         lectura estable, bloqueo, publicación
  -> app/local_capture/decoder.py         precios locales enteros acotados
  -> AuctionatorAdapter.decode_bytes()    validaciones nativas existentes
  -> app/local_capture/contracts.py       metadatos y canonicalización local v1
  -> directorio privado externo          originales independientes + metadata.json
```

Módulo dentro del backend Python existente, sin nuevas dependencias ni otra
aplicación. No importa settings, servicios de persistencia ni cliente HTTP.
`decode_bytes()` separa la validación nativa de `load_bytes()`, que conserva
batches y procedencia para el importador anterior. La captura no necesita
inventar región, fuente, dataset o base temporal para satisfacer un contrato
de importación. `CaptureMetadata` tampoco es `CaptureProvenance`: no habilita trial.
`CaptureAdapter` reutiliza los mismos lectores y validadores con modelos locales
de precio; el batch de ingestión conserva sus límites originales y se revalida
desde diccionarios, incluso si el decoder entrega subclases de sus modelos.

## Contrato

`capture_file(source, destination=None, *, origin_id=None, source_version=None,
serialized_codec=None, market_mapping=None) -> CaptureResult`.

| Campo de `CaptureMetadata` | Significado |
| --- | --- |
| `schema_version` | 1, esquema local; no es versión del addon |
| `capture_id`, `source_sha256` | SHA-256 hexadecimal de **todos los bytes originales**, ambos iguales |
| `source_bytes` | Longitud del original validado |
| `market_sha256`, `market_hash_contract` | SHA-256 del payload canónico de **evidencia nativa**, contrato `auctionator-native-market-v1` |
| `captured_at` | Adquisición de la copia en memoria ya validada, con zona y normalizada a UTC; anterior a publicación en disco |
| `native_scan_timestamp` | `null`: el esquema soportado no aporta timestamp verificable del scan |
| `origin` | Tipo SavedVariables, alias opaco opcional y `source_path_stored=false`; sin ruta ni cuenta |
| `validation_status` | `valid`; los rechazados no se publican como capturas |
| `database_version` | 8, comprobado en el contenido |
| `selected_source_version` | `340`, `341` o `null`: selección del operador, **no detección** de la versión al capturar |
| `selected_serialized_codec`, `input_format` | Perfil explícito `cbor-definite` o ninguno; formato observado `lua_tables`, `cbor_definite` o `mixed` |
| `simulated_marker` | Marcador conocido; su ausencia no demuestra autenticidad ni asigna dataset |
| `markets` | Claves originales, ruleset literal o mapping explícito, hash por mercado, versión nativa y conteos |
| `item_count` | Estructuras de item/variante, incluidas estructuras vacías |
| `native_fact_count` | Hechos presentes `l/h/a/m`; no inventa `l` cuando sólo existe `h` |
| `projected_statistic_count` | Estadísticas de la proyección existente con fallback de `l` a `h`; **no** registros persistidos ni subastas |
| `warnings`, `pending_metadata` | Semántica temporal, privacidad y pendientes explícitos |

Cada mercado incluye `bucket_count`, `first_bucket`, `last_bucket`: índices
nativos, nunca fechas civiles. `m` conserva su valor sin fecha. Región, facción,
identidad completa del servidor, build y addon al capturar, productor del codec,
dataset, fase de captura y hora de scan permanecen pendientes. No se extraen
supuestos timestamps de variables ajenas al contrato inspeccionado.

El resultado agrega `status=archived|duplicate` y `comparison` con
`status=first|equivalent|changed`, `equivalent_capture_id` y `new_market_states`.
La comparación usa todas las capturas completas verificadas en esa ejecución.
No se guarda en el metadato inmutable: puede cambiar tras un reintento o la
llegada de otra captura. `changed` significa que el conjunto difiere de todos
los conjuntos archivados, sin establecer orden económico ni hora de scan.

## Canonicalización v1

El payload contiene `contract`, `database_version=8`,
`structure={version:1, markets:[...]}` y `facts=[...]`:

- `structure` reutiliza `NativeExportEvidence.manifest()`, sin procedencia:
  mercados ordenados por clave, items por clave normalizada y campos presentes
  ordenados. Conserva versión del mercado, tablas vacías, claves originales de
  item, variantes, rulesets y presencia/ausencia de `a` y `m`.
- `facts` contiene el `model_dump(mode="json")` de cada `NativeFact`, ordenado
  por `(market_key, item_key, scan_day o -1 para m, native_field)`. Conserva
  valor, campo, índice y escritura original de claves de día/item.
- JSON ASCII con `ensure_ascii=True`, claves ordenadas, separadores `,` y `:`,
  sin whitespace ni NaN/Infinity. SHA-256 de esos bytes. El hash individual
  usa el mismo contrato con un solo mercado y sus hechos.

Excluye configuración, caché de vendedores y otras SavedVariables, rutas,
hora de copia, alias, versión seleccionada, codec/orden de serialización y
contexto de importación. Lua y CBOR con la misma evidencia producen el mismo
hash. **No sustituye** `evidence_hash` ni `state_hash(batch)` del importador,
cuyos contratos incluyen otro contexto.

Límite deliberado: identifica evidencia nativa, no sólo precios normalizados.
`l` explícito frente a fallback, `a` ausente frente a vacío, versión estructural
y escritura original de claves pueden cambiar la identidad aunque la proyección
numérica coincida. Un mapping diferente también cambia la identidad. Nunca se
deduplica sólo por conteo de items o bucket.

## Directorios, privacidad y flujo

Default Windows: `%LOCALAPPDATA%\WoWForeverCompanion\local-capture`. Sin
LOCALAPPDATA, o en otras plataformas: `~/.local/share/WoWForeverCompanion/local-capture`.
Una ubicación dentro de **este proyecto** se rechaza incluso sin `.git` o aunque
esté ignorada. LOCALAPPDATA apuntando al proyecto también se rechaza: la
protección está en código. Para un destino personalizado elegir un directorio
privado externo a repositorios y a carpetas sincronizadas. No se añade Lua a Git.

```text
local-capture/
  .capture.lock
  captures/<SHA-256 completo>/
    Auctionator.lua             original independiente, sólo lectura
    metadata.json               contrato local, sólo lectura
  pending/<SHA-256 completo>/   intento todavía sin publicar
  pending/incomplete-<SHA>-<UUID>/  intento incompleto retenido
```

1. Validar ruta y archivo regular legible; rechazar symlinks, junctions y
   ancestros reparse, rutas de red/dispositivo y alternate streams en Windows.
   Resolver alias 8.3 antes de comprobar el límite del proyecto y rechazar
   componentes ambiguos con punto/espacio final. Aplicar límite de 16 MiB antes
   y durante la lectura.
2. Windows usa `CreateFileW` con lectura y comparte sólo lectura: rechaza un
   escritor abierto e impide escritores/borrado durante la lectura. Comparar
   dos lecturas del mismo handle, tamaño, identidad y mtime antes/durante/después;
   POSIX agrega ctime. Volver a comprobar la ruta. No se compara ctime entre
   path/handle Windows: Python 3.13 puede exponer creación/cambio respectivamente.
3. Parsear **el buffer capturado** sin ejecutar Lua, conservando los límites
   existentes de profundidad, nodos, estructura, estadísticas y tipos. Los
   precios locales `l/h/m` son enteros exactos entre 0 y `2**63-1`; cantidades
   `a` e índices mantienen el máximo `2**31-1`. No se admiten floats ni redondeos.
   Cambios posteriores del original no alteran los bytes archivados.
4. Crear directorios privados y tomar lock de SO no bloqueante sobre
   `.capture.lock`. Otro capturador recibe `archive_busy`; el SO libera el lock
   al terminar o interrumpirse el proceso. El archivo de lock se conserva.
5. Verificar originales y metadatos de todas las capturas completas, recalcular
   hashes y deduplicar. Corrupción, archivos extra y colisiones detienen la
   operación sin reemplazar evidencia existente.
6. Escribir en `pending/<hash>` por creación exclusiva, `flush`, `fsync`,
   comprobación de bytes y marca de sólo lectura: original antes de metadatos.
   No se enlaza el original con hardlinks; se rechazan enlaces extras sobre
   archivos archivados. Los metadatos también tienen límite de 16 MiB.
7. Verificar el par completo y publicar por rename de directorio en el mismo
   filesystem, bajo lock y con destino inexistente. POSIX sincroniza también
   directorios. Un fallo posterior a publicar puede devolver error: el siguiente
   intento reconoce la captura completa. Nunca se sobreescriben capturas.

La inmovilidad corresponde al contrato de la aplicación y la marca de sólo
lectura; el propietario/administrador puede quitarla. Se detecta pérdida de
esa marca, alteración del original, inconsistencias de hashes/conteos y JSON
inválido o con claves duplicadas. No es firma criptográfica de procedencia ni
hora. Windows hereda ACL del destino; el default usa almacenamiento del usuario.
No modifica ACL existentes ni necesita elevar permisos de la aplicación.

El Lua **conserva datos personales originales**: todo el directorio es privado,
incluidos `pending` y metadatos con claves de mercados. El CLI sólo imprime
hashes, estados y conteos; errores públicos sin rutas, Lua, Pydantic ni traceback.

## Duplicados, fallos y reintentos

| Caso | Resultado |
| --- | --- |
| Primera captura válida | `archived`, `first`, original y metadatos independientes |
| Mismo hash completo | `duplicate`; conserva hora/alias/metadatos, sin otra copia ni recepción |
| Otro archivo, mercado equivalente | `archived`, `equivalent`, referencia equivalente y cero estados nuevos; conserva ambos originales |
| Cambia `l/h/a/m` en el mismo bucket | Nueva evidencia aunque el conteo de items no cambie |
| Varios mercados, cambia uno | Guarda el original; `new_market_states` sólo incluye hashes desconocidos |
| Reaparece un estado conocido | Guarda el archivo distinto y reutiliza identidad, sin inventar punto económico |
| Mismos bytes con mapping incompatible | `capture_context_conflict`; conserva el primer metadato |
| Error tras guardar original | Retiene copia pendiente aunque fallen metadatos/publicación |
| Pendiente completo | Reintento verifica y publica ese par; conserva su hora y recalcula comparación |
| Pendiente parcial o sin sello | Lo mueve a `incomplete-...`, conserva bytes y crea otro intento sin sobrescribirlos |

Esta fase no almacena histórico económico. Las identidades por mercado evitan
inflarlo posteriormente. IDs y hora local no establecen cronología de scans;
referencia equivalente expresa igualdad, nunca “último scan”.

Repetir el comando con el original. Si ya no existe, usar como entrada el
`Auctionator.lua` válido retenido en `pending` o `incomplete-...`, con los mismos
parámetros. Sin metadato válido, se registra la hora de esa **nueva adquisición**;
no se reconstruye una hora anterior desde mtime. Un parcial malformado no se
recupera como captura válida. No limpia pendientes ni repara capturas completas
corruptas automáticamente.

## Uso manual

Desde la raíz, con dependencias Python del backend instaladas:

```powershell
$auctionatorFile = 'D:\WoW\WTF\Account\MI_CUENTA\SavedVariables\Auctionator.lua'
.\backend\.venv\Scripts\python.exe -B .\backend\scripts\capture_auctionator.py `
  $auctionatorFile --source-version 341 --serialized-codec cbor-definite
```

Es una instrucción para ejecución futura; no se realizó esa captura en esta
entrega. Ejecutar tras `/reload` o salida normal, cuando termine la escritura.
Para Lua no serializado omitir el codec. La versión es opcional: se puede
capturar sin afirmar 340/341. CBOR requiere perfil explícito `cbor-definite`,
que no identifica al productor.

Opcionales: `--destination 'D:\CompanionPrivate\local-capture'`,
`--origin-id station-1` (alias opaco, nunca cuenta/personaje/ruta) y
`--market-rule 'Clave externa=PvP'` repetible, con reglas confirmadas.
PvE/PvP/HC/RP conservan su ruleset literal y no admiten remapping.
No consulta `.env` ni requiere DATABASE_URL. Éxito devuelve 0, incluido duplicado;
fallo de captura 1; sintaxis CLI inválida 2.

Prueba manual con el fixture **sintético** incluido, sin tocar SavedVariables
privados ni usar el archivo local habitual:

```powershell
$demoArchive = Join-Path ([System.IO.Path]::GetTempPath()) ('wow-capture-demo-' + [guid]::NewGuid().ToString('N'))
.\backend\.venv\Scripts\python.exe -B .\backend\scripts\capture_auctionator.py `
  .\backend\tests\fixtures\auctionator_v8.lua --destination $demoArchive --source-version 340
# Repetir con el mismo $demoArchive devuelve duplicate.
```

## Validación inicial

Windows/Python 3.13: **648 tests aprobados, 1 omitido**, incluidos **66 casos
nuevos** de `test_local_capture.py`. Se omitió el test opcional de captura
auténtica del parser: no se configuró ni leyó ningún archivo privado. Un warning
ya existente de deprecación Starlette/httpx. Sin integraciones PostgreSQL,
migraciones ni importaciones.

Cobertura nueva: copia inicial, deduplicación exacta/configuración/codec/orden,
cuatro campos nativos, múltiples mercados, regreso a estado conocido, límites,
cambios de contenido/fingerprint durante lectura, escritores Windows reales,
buffer independiente, fallos de escritura/metadatos/sellado/publicación,
reintento sin original, interrupción abrupta real de proceso, liberación de lock,
corrupción, colisiones, links/rutas, metadatos, CLI privado y ausencia de imports
de configuración/persistencia en proceso limpio.

Comando ejecutado desde `backend`, con destino temporal nuevo para evitar
reutilizar las ACL del directorio compartido de pytest en este entorno Windows:

```powershell
$captureTestRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('wow-capture-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $captureTestRoot) { throw 'Temporary target must be new' }
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp $captureTestRoot `
  tests/test_local_capture.py tests/test_auctionator.py tests/test_auctionator_cbor.py `
  tests/test_native_exports.py tests/test_hardening_parser.py tests/test_341_persistence.py `
  tests/test_trial_database.py tests/test_trial_cli_startup.py tests/test_file_adapter.py `
  tests/test_import_validation.py tests/test_market_windows.py tests/test_market_statistics.py `
  tests/test_market_validation.py tests/test_market_signals.py tests/test_market_signals_validation.py
```

Para sólo la suite nueva, usar un destino temporal nuevo y ejecutar
`python -m pytest tests/test_local_capture.py -q -p no:cacheprovider --basetemp $captureTestRoot`.
No configurar `AUCTIONATOR_REAL_CAPTURE` al repetir las pruebas sintéticas.
El cierre incluye `git diff --check` y whitespace de archivos nuevos. Sin commit
ni push. Los tests temporales requirieron ejecución fuera del sandbox del agente
por las ACL de pytest en Windows; el componente no requiere permisos elevados.

## Auditoría final antes de 5A.2

Revisión del 22/10/2026. Se conservaron los contratos de ingestión y los motores
3A/3B; no se ejecutaron migraciones, importaciones ni conexiones PostgreSQL.

### Correcciones acotadas

- **Bypass de destino por alias 8.3 Windows:** el chequeo era lexical y aceptaba
  un nombre corto que resolvía dentro del proyecto. Se reprodujo con una ruta
  existente sin crear archivos allí. Ahora se rechazan links primero, se resuelve
  la ruta y después se aplica el límite. También se rechazan componentes con
  puntos/espacios finales antes de normalizar. Tres regresiones Windows verifican
  las variantes y que no se cree un directorio en el proyecto.
- **Metadatos con anidación excesiva:** `json.loads` podía lanzar `RecursionError`
  fuera del contrato público de errores de la API. Se transforma en
  `archive_integrity`, conserva el original archivado y tiene regresión.
- **Rechazo de precios auténticos por un límite de persistencia:** se reprodujo
  mediante CLI que la copia actualizada era rechazada por cuatro precios mayores
  que 2.147.483.647. Se corrigió sólo la evidencia local en `decoder.py`: precios
  enteros exactos hasta `2**63-1`; cantidades e índices siguen limitados a
  `2**31-1`. Ocho regresiones cubren valores grandes, el máximo local, excesos,
  cantidades/índices y equivalencia Lua/CBOR. No hay truncamiento ni redondeo.
  El adaptador de ingestión conserva sus modelos de 32 bits. `load_bytes()`
  revalida explícitamente los datos aunque procedan de subclases locales, para
  impedir que Pydantic acepte sus límites mayores por confiar en instancias ya
  construidas. Ambos caminos de ingestión rechazan esos precios sin conexión.

### Comparación de cobertura

| Ejecución | Aprobados | Omitidos | No ejecutados PostgreSQL | Total |
| --- | ---: | ---: | ---: | ---: |
| Cierre anterior a 5A.1, documentado | 730 | 1 | 0 | 731 |
| Validación inicial de 5A.1 | 648 | 1 | 148 | 797 |
| Auditoría final actual | 661 | 0 | 148 | 809 |

Los 731 casos existentes siguen recolectándose. La primera entrega agregó 66
casos de captura y esta auditoría otros doce: **78 casos locales**. Los 648
aprobados anteriores eran 582 casos existentes sin PostgreSQL más 66 locales;
no hubo una eliminación de 82 tests. La diferencia neta combina 148 integraciones
no ejecutadas y 66 casos añadidos. La auditoría actual también ejecutó el caso
auténtico offline fijado al hash de la primera copia, antes omitido.

Se recolectó todo `backend/tests` mediante `pytest.main`, con un plugin temporal
externo al repositorio que excluyó las dependencias `isolated_database`,
`test_database_url` y `lab`, y bloqueó `psycopg.connect`. Se seleccionaron 661 de
809 casos, todos aprobados, con **cero intentos de conexión**. El plugin y el
resumen de colección se conservan sólo como artefactos privados temporales.
No se atribuyen aprobaciones actuales a las 148 integraciones excluidas.

| Módulo no ejecutado | Casos |
| --- | ---: |
| `test_341_persistence_integration.py` | 11 |
| `test_export_integration.py` | 30 |
| `test_export_migration.py` | 1 |
| `test_hardening_integration.py` | 11 |
| `test_ingestion_integration.py` | 23 |
| `test_market_integration.py` | 39 |
| `test_market_signals_integration.py` | 7 |
| `test_partial_integration.py` | 13 |
| `test_trial_database_integration.py` | 13 |

Un warning de deprecación Starlette/httpx ya existente. Las regresiones verifican
340/341, lectura estable, hash de bytes frente a evidencia nativa, aislamiento por
clave de mercado, idempotencia, fallos, interrupción abrupta y recuperación.

### Validación real adaptada a dos capturas

El operador confirmó dos copias locales, identificadas aquí sólo como `scan01`
y `scan02`. Ambas rutas reales se verificaron antes de la ejecución. La captura
intermedia de 7 items con mercado equivalente no está disponible; el operador
retiró ese requisito de evidencia auténtica y solicitó comprobar configuración
con un fixture sintético. No se creó ni se buscó una tercera captura adicional.

Se ejecutó la CLI existente en orden `scan01`, repetición de `scan01`, `scan02`,
repetición de `scan02`, con `--source-version 341 --serialized-codec cbor-definite`
y un destino temporal inicialmente vacío, fuera del proyecto y del archivo
personal. Todas las ejecuciones finales devolvieron código 0.

| Ejecución | Resultado | Comparación | Items | Hechos nativos | Estadísticas proyectadas | Nuevos estados |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `scan01` | `archived` | `first` | 7 | 21 | 28 | 1 |
| repetición `scan01` | `duplicate` | `equivalent` | 7 | 21 | 28 | 0 |
| `scan02` | `archived` | `changed` | 27 | 84 | 108 | 1 |
| repetición `scan02` | `duplicate` | `equivalent` | 27 | 84 | 108 | 0 |

Ambas copias contienen un único mercado PvP y un único bucket nativo **2485**.
`m` sigue sin fecha. El archivo final contiene **2 originales independientes,
2 estados de evidencia nativa por mercado y 0 entradas pendientes**. Los
duplicados no cambiaron bytes ni mtime de los metadatos ya publicados.

Hashes completos, sin rutas originales ni SavedVariables en Git:

| Captura | Bytes | SHA-256 de archivo completo |
| --- | ---: | --- |
| `scan01` | 4.701 | `7d5cf3db48fa78ab19d3a359557470752e634da743cebe42833fb07c10aa458b` |
| `scan02` | 5.725 | `c46a7b9ed7bc15320c18031b1d05143d39acbd7eea5022b22062eb6371e00e64` |

| Captura | SHA-256 canónico de evidencia nativa de mercado |
| --- | --- |
| `scan01` | `3579118cf4bd5ceaf851248dd6a13c3a200457f4efdd481f81402e9898dfbc54` |
| `scan02` | `9a0d7a35c18f12bbff9b64480021f0038fb8a04a938dfa66b4d9654a39606532` |

Se comprobaron hash, tamaño, mtime y modo de ambos originales antes/después; no
cambiaron. Las copias archivadas coinciden byte por byte con ellos. El rechazo
previo de `scan02` quedó reproducido y registrado antes de la corrección, sin
archivar un parcial ni modificar el original. El hash canónico de `scan01`
permanece idéntico después de introducir el límite local de precios de 64 bits.

Los metadatos finales registran adquisición local UTC:
`2026-10-22T16:03:44.639648Z` para `scan01` y
`2026-10-22T16:03:45.403611Z` para `scan02`. Ambos conservan
`native_scan_timestamp=null`; esas horas no se atribuyen al scan del 21/10 ni
convierten el índice 2485 a una fecha civil. Región, facción, dataset, build,
productor del codec y alcance completo del servidor siguen pendientes.

### Configuración sin cambios de mercado: evidencia sintética

En **otro archivo temporal separado**, la CLI procesó dos copias del fixture
`tests/fixtures/auctionator_v8.lua`. La segunda cambió la configuración y agregó
una caché de vendedores; no se modificó el fixture del repositorio ni los dos
originales auténticos. Ambos originales sintéticos se conservaron y el segundo
devolvió `archived`, `equivalent`, **0 estados nuevos**.

| Archivo sintético | SHA-256 completo |
| --- | --- |
| Base | `ea0e7ac17843e17c70609944a277ae372d38134d914f8983f962e9218f1e7cb4` |
| Configuración/caché | `2fc261fd59993b7e44fa4d82982f5daddcc734abe66f7c93cfb5fca692befcdc` |

Ambos tienen hash canónico
`c1b8a14c8d5cf3eaddb316e0422d3d60d61d8c81d433617229baba298712f38d`.
El fixture contiene cuatro mercados: mantienen sus cuatro identidades separadas.
Esta prueba no se presenta como una tercera captura auténtica.

El hash `market_sha256` representa **estructura y hechos nativos canónicos**,
con los límites de la sección de canonicalización. Distingue presencia de campos
y claves originales; no es un hash de precios exclusivamente. Configuración y
caché quedan fuera. La evidencia real confirmó que dos estados del mismo bucket
pueden ser diferentes, sin crear un bucket ni una hora de scan nuevos.

### Artefactos privados, repetición y veredicto

Los resultados completos, metadatos, comprobaciones de integridad, inventario de
tests y runner sin PostgreSQL están fuera de Git, en el directorio temporal
`wow-real-capture-validation-d4d50e1bbaab46b0bdfee9a0314b63c8`:
`validation-report.json`, `collection-final.json`, `regression-result.json` y
`offline_audit.py`. `sources-private.json` conserva rutas sólo allí.
`after-fix` es el archivo final de dos capturas; `before-fix` conserva la
reproducción inicial en un archivo independiente. Los fixtures sintéticos usan
`synthetic-inputs` y `synthetic-archive`, separados de las capturas auténticas.

Para repetir manualmente sin publicar rutas privadas en esta documentación:

```powershell
# Desde la raíz. Ingresar las dos rutas reales confirmadas en forma privada.
$firstCapture = Read-Host 'Ruta de scan01/Auctionator.lua'
$updatedCapture = Read-Host 'Ruta de scan02/Auctionator.lua'
$validationArchive = Join-Path ([System.IO.Path]::GetTempPath()) ('wow-5a1-manual-' + [guid]::NewGuid().ToString('N'))
foreach ($captureSource in @($firstCapture, $firstCapture, $updatedCapture, $updatedCapture)) {
  .\backend\.venv\Scripts\python.exe -B .\backend\scripts\capture_auctionator.py `
    $captureSource --destination $validationArchive --source-version 341 --serialized-codec cbor-definite
  if ($LASTEXITCODE -ne 0) { throw 'Capture validation failed' }
}
```

**Veredicto: READY TO COMMIT para el núcleo local 5A.1 con estas correcciones.**
Las dos capturas confirmadas y la prueba sintética completan el alcance ajustado
por el operador. Las 148 integraciones PostgreSQL no se ejecutaron en esta
auditoría y no se declaran aprobadas ahora. Archivar precios locales de 64 bits
**no** habilita importarlos: la persistencia mantiene su contrato de 32 bits.
`git diff --check` y revisión de sintaxis/whitespace sin errores. Al terminar
esta auditoría todavía no se habían realizado commit, push ni inicio de 5A.2.

## Límites y próxima etapa 5A.2

- No detecta cambios ni espera estabilización automáticamente. Rechaza archivos
  abiertos para escritura; el operador puede reintentar.
- Un archivo sintácticamente válido no prueba que acabó una actualización
  lógica del addon. POSIX usa doble lectura/identidad sin el bloqueo obligatorio
  de Windows; ninguna lectura certifica bytes futuros.
- Presupone filesystem local y directorio privado con escritores cooperantes.
  No protege de un propietario hostil que reemplace directorios concurrentemente.
  `fsync`/rename no garantizan supervivencia ante todo corte eléctrico, sobre
  todo en Windows.
- Revalida todas las capturas completas: coste proporcional a sus bytes totales,
  sin índice mutable adicional que pueda desincronizarse. Revisar rendimiento
  antes de una colección grande.
- Sin cifrado, retención, compresión ni atribución económica de estados. Una
  base vacía sin hechos se rechaza: conserva el requisito de evidencia útil y
  todos los límites existentes del parser.
- Dos guardados idénticos no prueban dos observaciones; dos estados distintos
  tampoco prueban dos scans.
- **Compatibilidad pendiente antes de sincronizar:** los precios locales admiten
  enteros de hasta 64 bits con signo; la ingestión actual conserva 32 bits.
  Resolver y validar rangos, contratos de API y almacenamiento en una etapa
  explícita antes de enviar esos valores. 5A.1 no modifica ese contrato ni
  permite sortearlo al importar una captura local.

**5A.2 recomendada:** detector local para una ruta elegida, con debounce,
ventana de estabilidad y reintentos acotados de `source_unavailable`,
`source_changed` y `archive_busy`; esta función debe seguir siendo la única vía
de validación/archivado. Probar escrituras escalonadas, reemplazo por rename,
ráfagas, reinicio y bloqueo. Usar hashes por mercado como identidad y mostrar
errores sin información privada. Sincronización autenticada e importaciones
corresponden a otra etapa y revisión; este núcleo no las inicia.
