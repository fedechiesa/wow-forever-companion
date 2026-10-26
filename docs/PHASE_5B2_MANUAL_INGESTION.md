# Fase 5B.2 — Ingestión manual protegida y lectores v2

Revisión: **26/10/2026**, America/Buenos_Aires. Objetivo prelaunch comunicado:
04/11/2026. El alcance es conservar, importar manualmente y consultar evidencia
nativa con contexto verificable. No se importaron capturas auténticas.

**Veredicto: READY FOR REVIEW.** Implementación y validación completadas para el
alcance manual de laboratorio; los bloqueos auténticos se conservan explícitos.

## Estado inicial

`main`, HEAD `d54fef88ad5050955f6af53b6a483234700a043d`, coincidente con el último
commit publicado indicado. `git status --short` vacío: no había trabajo local de
5B.2 que preservar. Se revisaron README, ARCHITECTURE, ROADMAP y los documentos
de 5A.1, 5A.2 y 5B.1, incluidos el diseño 5B.1.1 y su cierre.

La base ya tenía `VerifiedLocalContext`, `prepare_local_capture`, export v2,
escritor con binding local, `TrialDatabase` y migración 006. Se reutilizaron;
no se creó otro modelo económico, tabla de hechos o migración. Los documentos
5A/5B.1 conservan sus resultados históricos; las menciones a CLI/lectores
pendientes en esos informes describen su fecha de cierre.

## Implementación y garantías

```text
5A captures/<SHA-256>/{Auctionator.lua,metadata.json} + contexto privado explícito
  -> preflight_archive: sólo lectura offline, sin settings/SQL
  -> prepare_local_capture: contratos 341, hashes, límites, identidad y procedencia
  -> ingest explícito: TrialDatabase verifica destino y referencia protegida
  -> servicio existente: exige 005/006, transacción, retries/failed
  -> export v2 sellado + hechos únicos + run/recepción append-only

PostgreSQL preparado -> LocalEvidenceReader READ ONLY / REPEATABLE READ
  -> mercados verificados / estados sellados / hechos / recepciones separadas
```

- Selección por SHA-256 completo, nunca por “último archivo”. Sólo se acepta una
  captura publicada de 5A; no archivos sueltos ni `pending`. Se reutilizan controles
  de rutas, links/reparse, archivo regular, lecturas estables, tamaño máximo de
  16 MiB, marca de sólo lectura, archivos extra y JSON de metadatos sin duplicados.
- Contexto JSON privado de hasta 64 KiB, sin claves duplicadas; contrato
  `verified-local-capture-v1` existente. Exige formato 341, dataset explícito
  `simulated|stress_test|launch`, fuente, región técnica y refs revisadas, codec
  explícito/null concordante, todos los mercados y su identidad económica.
  Cada mercado requiere economía verificada, reino claim/null explícito,
  alcance `shared|faction` y facción claim/null explícito. Faction requiere su
  facción; shared requiere null. No se completa identidad desde PvP, idioma,
  cuenta, `origin_id`, ubicación o reloj. Dos aliases de una economía en una
  misma captura siguen rechazándose hasta reconciliar sus hechos.
- Recalcula hashes de bytes y económicos global/por mercado, estructura,
  conteos y claves nativas. Contrasta hash y mercados de procedencia. Un selector
  archivado null puede completarse explícitamente como 341; un 340 contradictorio
  se rechaza. Decodificar CBOR no identifica al productor; puede seguir unverified.
  Refs presentes/coherentes son attestaciones, no autenticación automática.
- Un precio l/h/m >2147483647 bloquea **toda** la captura. El original conserva
  enteros hasta `2**63-1`. No hay descarte de items, redondeo, recorte o saturación.
  Cantidades e índices conservan su límite de 32 bits; no se admiten fracciones.
- Preflight exitoso declara `import_performed=false`, `target_verified=false`
  y `analytics_enabled=false`. No es permiso de escritura ni recibo reutilizable:
  `ingest` repite la validación completa antes de cargar settings o conectar.
- El destino de ingestión siempre requiere DSN por variable de entorno y nombre
  exacto `_test`. `DATABASE_URL` es la referencia protegida, consultada sólo en
  lectura por TrialDatabase. La identidad efectiva cluster/OID impide escribir
  sobre ella incluso con aliases. Retry/failed pasan por el mismo guard.
  El esquema debe estar preparado: no se crea ni migra automáticamente un destino.
  La seguridad del esquema presupone un laboratorio administrado y confiable;
  una fila en schema_migrations no certifica DDL arbitrario o un servidor hostil.
- Los originales quedan en el archivo privado 5A, fuera del proyecto. SQL guarda
  referencia `local-capture:<hash>`, metadatos, ambos hashes, adquisición y contexto
  completo en la recepción; no copia el Lua a una tabla. Conservar/respaldar ese
  archivo es necesario para volver a disponer de los bytes originales.
- Repetir una captura/contexto reutiliza export_id y hechos, con otra recepción
  auditada. Dos observadores comparten economía/estado conservando procedencia
  propia; la cabecera sigue describiendo sólo al primero. Un fallo revierte
  export/hechos/recepción y puede registrar failed separado. Secuencias del lab
  pueden avanzar en duplicados y rollback; no se promete idempotencia de contadores.
- Dos estados distintos del bucket 2485 siguen teniendo **un índice nativo**.
  Adquisición y recepción son tiempos diferentes; native_scan_timestamp permanece
  null y temporal_basis unknown. No se infieren fechas civiles ni orden de scans.

## Comandos manuales

Con dependencias del backend instaladas, desde `backend`. Se requiere una captura
ya archivada y un contexto privado revisado. Estos comandos describen el uso;
en esta entrega se ejecutaron únicamente con fixtures sintéticos.

### Identificar la captura y preparar el contexto

El directorio elegido es la raíz del archivo 5A, que contiene `captures` y
`pending`; no es WTF ni un directorio individual de captura. Listar sólo los
metadatos publicados permite elegir el SHA completo sin abrir ni mostrar el Lua:

```powershell
$privateArchive = Read-Host 'Directorio privado del archivo 5A'
Get-ChildItem -LiteralPath (Join-Path $privateArchive 'captures') -Directory |
  ForEach-Object { Get-Content -LiteralPath (Join-Path $_.FullName 'metadata.json') -Raw -Encoding UTF8 | ConvertFrom-Json } |
  Select-Object capture_id, captured_at, item_count, native_fact_count, selected_source_version
$captureId = Read-Host 'SHA-256 completo de la captura publicada elegida'
if ($captureId -cnotmatch '^[0-9a-f]{64}$') { throw 'Se requiere el SHA-256 completo en minusculas' }
$captureDirectory = Join-Path (Join-Path $privateArchive 'captures') $captureId
$metadata = Get-Content -LiteralPath (Join-Path $captureDirectory 'metadata.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$byteHash = (Get-FileHash -LiteralPath (Join-Path $captureDirectory 'Auctionator.lua') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($byteHash -cne $captureId -or $metadata.capture_id -cne $captureId) { throw 'Captura inconsistente: conservarla e investigar' }
```

Esta inspección no sustituye al preflight, que recalcula además la evidencia
económica y verifica todo el metadato. `captured_at` sólo ayuda a localizar la
adquisición; no selecciona un supuesto último scan ni asigna fecha al bucket.

Preparar el sidecar fuera del proyecto con evidencia revisada de **esa captura**.
La siguiente receta solicita cada dato; no contiene valores de identidad de
Forever ni infiere identidades desde la etiqueta nativa. Si falta una evidencia
obligatoria, detenerse y conservar la captura como evidencia local. Confirmar
antes que el perfil seleccionado sea 341; 340 explícito no se reetiqueta.

```powershell
function Read-RequiredText([string]$Label) {
  $value = Read-Host $Label
  if ([string]::IsNullOrWhiteSpace($value) -or $value -cne $value.Trim()) { throw 'Dato explicito no vacio y sin espacios exteriores requerido' }
  return $value
}
function Read-EvidenceClaim([string]$Label) {
  return @{ value = (Read-RequiredText "$Label - valor verificado"); evidence_ref = (Read-RequiredText "$Label - referencia de evidencia") }
}
$dataset = Read-RequiredText 'Dataset de esta captura: simulated, stress_test o launch'
if ($dataset -notin @('simulated', 'stress_test', 'launch')) { throw 'Dataset no soportado' }
$provenance = @{
  version = 1; source_sha256 = $captureId; format_version = '341'
  source_id = (Read-RequiredText 'Identificador estable del observador/fuente, no la etiqueta PvP')
  region = (Read-RequiredText 'Identificador tecnico de region verificado')
  dataset = $dataset; capture_phase = $dataset
  market_rulesets = [System.Collections.Generic.Dictionary[string, object]]::new([StringComparer]::Ordinal)
  region_evidence_ref = (Read-RequiredText 'Referencia que verifica la region')
  market_evidence_ref = (Read-RequiredText 'Referencia que verifica mercados y rulesets')
  origin_evidence_ref = (Read-RequiredText 'Referencia que verifica origen/procedencia de esta captura')
  codec_producer = 'unverified'; codec_producer_evidence_ref = $null
}
$identities = [System.Collections.Generic.Dictionary[string, object]]::new([StringComparer]::Ordinal)
foreach ($market in $metadata.markets) {
  $key = $market.market_key
  $provenance.market_rulesets[$key] = $market.ruleset
  $economy = Read-EvidenceClaim "Economia tecnica estable para la etiqueta nativa $key"
  $realmKnown = Read-RequiredText "Reino observado con evidencia para ${key}: si o no"
  if ($realmKnown -notin @('si', 'no')) { throw 'Responder si o no explicitamente' }
  $realm = if ($realmKnown -eq 'si') { Read-EvidenceClaim "Reino observado en $key" } else { $null }
  $scope = Read-RequiredText "Alcance del AH verificado para ${key}: shared o faction"
  if ($scope -notin @('shared', 'faction')) { throw 'Alcance no soportado o no verificado' }
  $faction = if ($scope -eq 'faction') { Read-EvidenceClaim "Faccion economica de $key" } else { $null }
  $identities[$key] = @{
    economy = $economy; realm = $realm; faction = $faction; auction_house_scope = $scope
    scope_evidence_ref = (Read-RequiredText "Referencia que verifica el alcance del AH de $key")
  }
}
$context = @{
  contract = 'verified-local-capture-v1'; provenance = $provenance
  serialized_codec = $metadata.selected_serialized_codec; market_identities = $identities
}
$contextFile = Read-RequiredText 'Ruta NUEVA del sidecar privado, fuera del proyecto'
if (Test-Path -LiteralPath $contextFile) { throw 'No sobrescribir un contexto existente' }
$context | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $contextFile -Encoding UTF8
```

`no` para reino sólo es válido si la economía técnica está verificada por otra
evidencia; no habilita una economía desconocida. Shared requiere evidencia de
alcance compartido, no simplemente desconocer la facción. La receta conserva el
productor del codec como no confirmado: si existe evidencia independiente, revisar
el JSON y declarar juntos `codec_producer` y `codec_producer_evidence_ref` según
el esquema. Claims opcionales de build/addon pueden permanecer ausentes; instalado
hoy no prueba versión al capturar. La forma válida del JSON no autentica los claims.

### Preflight, comprobación del destino e ingestión

Con las variables anteriores, ejecutar preflight antes de seleccionar el destino.
Los prompts siguientes también permiten retomar una captura/contexto ya preparados:

```powershell
$privateArchive = Read-Host 'Directorio privado del archivo 5A'
$captureId = Read-Host 'SHA-256 completo de la captura publicada'
$contextFile = Read-Host 'Ruta del JSON privado verified-local-capture-v1'

.\.venv\Scripts\python.exe -X utf8 -B scripts\ingest_local_capture.py preflight `
  --archive $privateArchive --capture-id $captureId --context-file $contextFile
if ($LASTEXITCODE -ne 0) { throw 'Preflight bloqueado: conservar captura y revisar el motivo' }

# Sólo un laboratorio conocido, separado de DATABASE_URL y ya preparado con 006.
$env:AUCTIONATOR_LAB_DSN = Read-Host 'DSN privado del laboratorio preparado'
$labName = Read-Host 'Nombre exacto verificado del laboratorio, terminado en _test'
# El check reutiliza TrialDatabase; no carga captura, migra ni escribe.
.\.venv\Scripts\python.exe -X utf8 -B scripts\import_auctionator.py --trial --check-target `
  --database-url-env AUCTIONATOR_LAB_DSN --expected-database $labName
if ($LASTEXITCODE -ne 0) { throw 'Destino no verificado: no importar' }
# Comprueba acceso de lectura y tracking 006; [] es normal para un lab vacio.
.\.venv\Scripts\python.exe -X utf8 -B scripts\read_local_evidence.py markets --database-url-env AUCTIONATOR_LAB_DSN
if ($LASTEXITCODE -ne 0) { throw 'Esquema/destino no preparado: no importar' }
.\.venv\Scripts\python.exe -X utf8 -B scripts\ingest_local_capture.py ingest `
  --archive $privateArchive --capture-id $captureId --context-file $contextFile `
  --database-url-env AUCTIONATOR_LAB_DSN --expected-database $labName
```

El esquema JSON del sidecar se obtiene del contrato existente, sin generar valores
de identidad por defecto:

```powershell
.\.venv\Scripts\python.exe -B -c "import json; from app.ingestion.local_lineage import VerifiedLocalContext; print(json.dumps(VerifiedLocalContext.model_json_schema(), indent=2))"
```

No usar el contrato histórico `local-capture-context-v1` de readiness como sustituto.
`source_sha256` debe ser el de los bytes seleccionados. Guardar fuera de Git las
refs y claims privados. La CLI anterior `import_auctionator.py` sigue rechazando
341 sin binding completo; no se habilita un atajo por HTTP o watcher.

Salida 0: preflight válido/import confirmado, incluido duplicate. Salida 1:
bloqueo o fallo con mensaje saneado. Salida 2: sintaxis inválida. Un bloqueo
numérico devuelve reason `price_exceeds_persistence_int32`; errores de contexto,
archivo o persistencia no imprimen Lua, rutas privadas, credenciales ni traceback.

La comprobación de destino devuelve nombre, OID de base e identificador del cluster;
contrastar con el laboratorio provisionado. No comprueba el contenido de la captura.
El lector comprueba tracking 006 y el escritor exige además 005 antes del primer
INSERT. Si falta esquema, preparar **por separado sólo un laboratorio conocido**;
no ejecutar `migrate.py` sin destino explícito para resolver un error de ingestión.

| Error/estado | Acción operativa |
| --- | --- |
| invalid_capture_id | Elegir el SHA completo, en minúsculas, del directorio publicado |
| invalid_verified_context | Revisar localmente contrato, campos requeridos, refs, JSON duplicado y límite de 64 KiB |
| archive_integrity_failed | Conservar original/metadatos; comprobar publicación, archivos extra, marca de sólo lectura y corrupción; no editar hashes para hacerlos coincidir |
| capture_context_mismatch / capture_validation_failed | Revisar selector 341, codec, hash, mercados y procedencia; detenerse si no hay evidencia suficiente |
| price_exceeds_persistence_int32 | Mantener la captura completa en 5A; no filtrar items ni intentar importarla por otro contrato |
| Fallo de ingestión o lector | Verificar DSN, nombre/identidad efectivos, disponibilidad, tracking 005/006 y selectores; los detalles privados no se imprimen |
| pending o incomplete-* de 5A | Aún no es importable. Reintentar capture_auctionator.py según [5A.1](PHASE_5A1_LOCAL_CAPTURE.md), conservando opciones/original válido; no mover manualmente a captures ni borrar evidencia |

Si la respuesta de una importación se pierde, consultar estado/recibos o repetir
el mismo comando: puede agregar una recepción, pero reutiliza los hechos. Failed
puede existir sólo si el intento alcanzó SQL y la base permitió registrar el fallo;
un rechazo offline no genera recibo SQL ni consume secuencias.

## Lectores v2 disponibles

Biblioteca: `app.ingestion.local_readers.LocalEvidenceReader(connection_factory)`.
La CLI de lectura exige un DSN explícito por variable y no carga DATABASE_URL.
Abre la sesión en READ ONLY antes de consultar; la biblioteca usa snapshots
REPEATABLE READ / READ ONLY. No crea tablas ni aplica migraciones.

```powershell
.\.venv\Scripts\python.exe -B scripts\read_local_evidence.py markets --database-url-env AUCTIONATOR_LAB_DSN
$marketId = Read-Host 'ID económico elegido de markets'
.\.venv\Scripts\python.exe -B scripts\read_local_evidence.py states --market-id $marketId --database-url-env AUCTIONATOR_LAB_DSN
$exportId = Read-Host 'ID del estado elegido explícitamente'
.\.venv\Scripts\python.exe -B scripts\read_local_evidence.py state --export-id $exportId --database-url-env AUCTIONATOR_LAB_DSN
.\.venv\Scripts\python.exe -B scripts\read_local_evidence.py facts --export-id $exportId --market-id $marketId --database-url-env AUCTIONATOR_LAB_DSN
.\.venv\Scripts\python.exe -B scripts\read_local_evidence.py receipts --export-id $exportId --database-url-env AUCTIONATOR_LAB_DSN
```

| Lector | Resultado y límites |
| --- | --- |
| markets | Sólo identidades verificadas; `first_native_label` es representativa, no identidad económica |
| states(market_id) | Un registro por estado sellado que contiene esa economía; descubre mercados vacíos por manifest; receipt_count no multiplica hechos |
| state(export_id) | Hash/manifest completo, conteos del export completo y primer observador identificado como tal |
| facts(export_id,market_id) | l/h/a/m exactos, variantes y claves originales, índices/null; sin proyección, fallback implícito o unión a recepciones |
| receipts(export_id) | Run, observador, adquisición, recepción, hashes, contexto/metadata completos y transporte de cada recepción |

Las listas aceptan `--limit 1..1000` (default 100) y `--offset 0..2147483647`.
Orden estable por ID; facts por item/índice/campo. Recorrer páginas explícitamente.
El orden de IDs/recepción no determina el estado más reciente del mercado.
Un estado ajeno a la economía seleccionada, legacy v1 o inexistente se rechaza.
Los hechos con m siguen sin fecha. Los lectores devuelven evidencia privada,
incluidas refs/claims en state/receipts: no publicar su stdout. Precios persistidos
siguen en 32 bits; esta CLI Python no certifica transporte futuro de BIGINT a JS.
No se exponen endpoints nuevos ni se conecta esta biblioteca con frontend/3A/3B.
Los mercados vacíos se conservan cuando acompañan evidencia válida de otros
mercados; el decoder existente sigue rechazando una captura sin ningún hecho.

## Validación de laboratorio

Regresión focalizada: **74 tests nuevos aprobados**, distribuidos en 44 de
preflight/CLI offline, 14 de selectores/errores de lectura y 16 de integración
manual/lectores. Se comprobaron Lua/CBOR, extremos monetarios exactos, JSON
duplicado/excesivo, corrupción, selección publicada y ausencia de settings/SQL
en preflight mediante un proceso Python limpio.

La integración prueba importación repetida, observadores/originales equivalentes,
estados diferentes del mismo bucket, mercado vacío junto a otro poblado, rollback
después de la recepción, retry tras fallo y retry de deadlock. Comprueba que hechos
no se multiplican por recepción y que los lectores excluyen v1/003, paginan de
forma estable, rechazan otra economía y mantienen READ ONLY físicamente en SQL.
Un destino nuevo sin tablas se rechaza sin crear schema_migrations ni otra tabla.
El target protegido efectivo se rechaza también mediante alias de host.

Para repetir, seleccionar **únicamente un laboratorio propio, aislado y ya
preparado**, con nombre `_test` distinto de DATABASE_URL; no usar una base de tests
preexistente con datos que se quieran preservar. Desde backend:

```powershell
$env:TEST_DATABASE_URL = $env:AUCTIONATOR_LAB_DSN
$env:TRIAL_INTEGRATION_DATABASE_URL = $env:AUCTIONATOR_LAB_DSN
$env:TRIAL_INTEGRATION_DATABASE_NAME = $labName
Remove-Item Env:AUCTIONATOR_REAL_CAPTURE -ErrorAction SilentlyContinue
$testTemp = Join-Path ([IO.Path]::GetTempPath()) ('wow-5b2-tests-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -X utf8 -B -m pytest -q -p no:cacheprovider --basetemp $testTemp
# Focalizada: agregar los tres archivos test_manual_local_capture.py,
# test_local_readers.py y test_local_readers_integration.py de tests/.
```

La suite crea/migra schemas temporales exclusivamente en el laboratorio elegido.
Las pruebas de TrialDatabase requieren conexión directa y permisos para consultar
la identidad efectiva de PostgreSQL. Se ejecutaron fuera del sandbox del agente
por las ACL temporales de pytest en Windows; no se modificaron ACL del usuario.

La primera regresión amplia detectó dos errores de fixtures nuevos: una captura
enteramente vacía (rechazada correctamente por el decoder) y una aserción que
contaba recepciones de un hash compartido con otras pruebas. Se corrigieron el
fixture mixto y el aislamiento del hash del escenario. Sus 1064 aprobados, dos
fallos y un omitido son diagnóstico previo, no el resultado final.

Regresión final completa: **1069 recolectados, 1068 aprobados, 1 omitido, cero
fallos y cero integraciones excluidas**, en 251,67 segundos. Se preservaron los
995 casos publicados y se agregaron 74. Incluye persistencia, migraciones,
concurrencia, fallos/retries, guards, contratos, parsers, snapshots y motores
3A/3B existentes. Las pruebas nuevas pasaron también en la regresión focalizada.

Único omitido: `test_authentic_341_capture_offline`, por retirar explícitamente
AUCTIONATOR_REAL_CAPTURE. No ejecutados: frontend build/tests/live, uso del
cliente WoW, /reload real e importaciones auténticas; esas capas y datos no forman
parte del cambio autorizado. Avisos existentes: una deprecación Starlette/httpx
y dos warnings Pydantic esperados de fixtures con float rechazados por el guard.

Se creó un **contenedor PostgreSQL 16 separado**, sin volúmenes del proyecto ni
de desarrollo, ligado sólo a loopback. Laboratorio inicial:
`wow_5b2_1793029412658_test`; base nueva para el cierre:
`wow_5b2_final_1793030070512_test`. 001–006 se aplicaron con DSN
explícito únicamente después de verificar que esas bases nuevas estaban vacías
y separadas de la referencia protegida. No se usó el default de migrate.py,
no se editaron migraciones publicadas ni se migró un destino desconocido.
Los fixtures crearon/eliminaron sólo schemas propios y una base efímera vacía
de rechazo dentro del cluster de laboratorio.

Desarrollo se consultó exclusivamente en lectura para verificar su identidad y
comparar todas las filas de tablas public y last_value/is_called de sus secuencias.
El fingerprint antes/después de ambas regresiones completas fue idéntico:
`d43f8effd13e77eb2a69825f54847fe700e8b714d6f5b84e45eb9381ff0bdfef`.
La base de testing preexistente no fue seleccionada: TEST_DATABASE_URL y las
variables trial del proceso apuntaron a los laboratorios nuevos, sin editar .env.
No quedaron schemas temporales. El contenedor temporal se retiró al terminar;
el contenedor PostgreSQL existente siguió en ejecución.

Control final de la entrega inicial: ocho archivos Python parseados, enlaces locales y whitespace
comprobados, `git diff --check` aprobado. Doce archivos nuevos/modificados,
sin staging, commit ni push. HEAD conserva `d54fef88…`. Migraciones 001–006,
frontend, app/market, watcher y configuración persistente permanecen sin cambios.

## Bloqueos para datos auténticos y límites prelaunch

Siguen pendientes región técnica y procedencia auténticas completas, identidad
económica/reino o ámbito conectado, alcance real del AH y facción si corresponde.
Se requiere vincular esa evidencia privada a cada hash y a su fase real
stress_test/launch, sin reinterpretar muestras de stress como lanzamiento.
Build/addon en captura y productor efectivo del codec conservan incógnitas si
no hay evidencia independiente. No se fabrica timestamp nativo ni epoch.

Quedan pendientes primer `/reload` real con watcher y primera importación auténtica
manual revisada. No se abrieron capturas privadas ni se controló el cliente WoW.
Capturas auténticas con precios fuera de dominio siguen bloqueadas íntegramente;
su conservación local es útil aunque aún no puedan llegar a PostgreSQL.
El paso futuro a una base personal permanente requiere otra decisión operativa:
5B.2 sólo habilita laboratorios `_test`, nunca desarrollo ni destinos desconocidos.

El alcance técnico excluye sincronización, IA, predicciones, frontend, cambios de
Market Intelligence, backfill, migraciones nuevas y edición de 001–006. La entrega
inicial terminó sin commit/push; el cierre posterior autorizado se registra abajo.

## Archivos de la entrega

- `backend/app/local_capture/preflight.py`
- `backend/app/ingestion/local_readers.py`
- `backend/app/ingestion/local_lineage.py` (docstring actualizado al uso manual)
- `backend/scripts/ingest_local_capture.py`
- `backend/scripts/read_local_evidence.py`
- `backend/tests/test_manual_local_capture.py`
- `backend/tests/test_local_readers.py`
- `backend/tests/test_local_readers_integration.py`
- `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` y este informe.

## Auditoría final y cierre para publicación

Revisión focalizada del 26/10/2026 sobre los doce archivos anteriores, recibidos
sin staging en main y HEAD d54fef88ad5050955f6af53b6a483234700a043d. El fetch de
origin confirmó main sincronizado con esa base antes de preparar la publicación.
**Auditoría aprobada; sin bloqueos estructurales para publicar 5B.2.**

Se revisaron archivos completos y diferencias, límites de selección/rutas,
contratos y recálculo de hashes, revalidación previa al escritor, ownership de
conexiones por TrialDatabase, transacciones, política monetaria y lectura nativa.
No se encontraron bypasses nuevos, hechos duplicados por reimportación ni unión
de recibos a hechos. Los estados diferentes del mismo bucket conservan su
evidencia separada y no crean días. No se incluyen Lua privados, credenciales,
temporales o rutas personales fijadas en código. El cambio en local_lineage.py
actualiza sólo docstrings; los guards y la persistencia existentes se reutilizan.

La corrección de cierre es **documental**: se amplió la guía para identificar el
SHA publicado, preparar todos los claims explícitamente sin valores ficticios de
Forever, verificar el destino sin escritura y entender errores/pending. Se
comprobó la sintaxis de los seis bloques PowerShell y se ejecutó la receta de
selección/contexto/preflight/check-target/ingestión y las cinco vistas del lector
con un fixture sintético temporal. El sidecar generado pasó el contrato real y
preflight; el estado importado conservó sus tres hechos y una recepción.
No se añadieron funcionalidades, dependencias ni archivos fuera de los doce.

**Regresión de cierre: 321 aprobados, cero fallos, cero omitidos**, en 28,04
segundos. Los once módulos ejecutados fueron test_manual_local_capture,
test_local_readers, test_local_readers_integration, test_local_lineage,
test_local_lineage_integration, test_local_ingestion_readiness,
test_trial_database, test_trial_database_integration, test_341_persistence,
test_341_persistence_integration y test_native_exports. Incluye concurrencia,
rollback/reintentos, rechazo antes de secuencias, guards SQL/006 y separación de
economías/estados/recepciones. Dos warnings Pydantic esperados de fixtures con
float, rechazados antes del escritor. Sin cambio funcional, no se repitió la
regresión completa ya demostrada de 1068 aprobados y un opt-in auténtico omitido.
No se ejecutaron frontend/build/live, WoW ni pruebas auténticas.

Esta revisión usó otro contenedor PostgreSQL efímero con dos bases **nuevas**:
target y referencia protegida. DATABASE_URL/TEST_DATABASE_URL se reemplazaron sólo
en los procesos de prueba, sin editar .env. El launcher aplicó una whitelist de
host loopback, puerto del contenedor y nombres de laboratorio; registró 387
sesiones permitidas; no se efectuaron conexiones fuera de la whitelist. La referencia
protegida quedó vacía y sin secuencias. Se aplicaron 001–006 sólo al target nuevo
verificado vacío; no quedaron schemas temporales. El ensayo de la documentación
usó el mismo target y referencia, exclusivamente con el fixture sintético.
Desarrollo y la base de testing preexistente no se conectaron en este cierre.
El contenedor de cierre se retiró después de las validaciones; el PostgreSQL
preexistente siguió en ejecución.

Migraciones 001–006, frontend, watcher y app/market conservan sus bytes publicados.
El control final comprobó ocho archivos Python, 40 enlaces locales, whitespace,
ausencia de rutas personales/claves nuevas, revisión del índice y git diff --check.
La publicación autorizada usa un commit de estos doce archivos
con el mensaje `feat: add guarded local capture ingestion and evidence readers`
y push normal a main, sin force ni inicio de otra fase. El hash del commit y la
confirmación del push se informan al usuario después de ejecutar esas operaciones.

Pendiente: evidencia privada verificada y primera adquisición/importación
auténtica revisada; precios extremos siguen bloqueados. Para una fase posterior
se recomienda diseñar una vista de evidencia v2 de sólo lectura en el dashboard,
con mercado económico y export explícitos, hechos y recibos separados y sin
alimentar 3A/3B automáticamente. Esa siguiente fase no se implementa aquí.
