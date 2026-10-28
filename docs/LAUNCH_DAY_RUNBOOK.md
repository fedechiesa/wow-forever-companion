# Manual de lanzamiento — WoW Forever Companion

Fecha de preparación: 28/10/2026. Objetivo comunicado: 04/11/2026.
Base ensayada: `911633c3ed191b50881276001e60049e744f0123`.
[Resultados del ensayo sintético](PHASE_6_PRELAUNCH_READINESS.md).

La prioridad es **conservar originales y no mezclar economías/datasets**.
Archivar no requiere PostgreSQL, FastAPI, React ni AHledger. La ingestión es
manual y requiere preflight, contexto revisado y un destino TrialDatabase separado.
Este documento no autoriza importar capturas auténticas ni escribir en desarrollo.

## Qué se puede hacer hoy y qué queda condicionado

| Hoy, con fixtures | Lanzamiento: requiere verificación/autorización |
| --- | --- |
| Comprobar dependencias, ensayar watcher sobre un archivo temporal, crear un lab nuevo, migrar sólo ese lab, importar fixtures y consultar v2 | Elegir la instalación/WTF reales, comprobar primer `/reload`, identificar región/economía/alcance/origen, preparar contexto auténtico y autorizar su primera importación |
| Probar fallos, deduplicación, rollback, backup y fallback a IDs | No trasladar ningún valor `synthetic`, contexto de prueba o DSN de ejemplo a capturas auténticas |

**Intervenciones manuales:** elegir archivo y archivo de capturas; iniciar/detener
watcher; ejecutar scan y `/reload` en WoW; comprobar publicación; revisar cada
contexto y hash; verificar destino; ejecutar ingestión; seleccionar dataset,
economía y estado; hacer backup. No hay tarea programada, ingestión desde UI ni sync.

Todos los comandos parten de la raíz del repositorio salvo indicación contraria.
Usar consolas separadas para watcher, ingestión, API y React. No transcribir
valores privados, DSNs ni salida de los lectores privados a Git/issues/chat.

## 1. Dependencias y control inicial — hoy

```powershell
git status --short
git rev-parse HEAD
$python = (Resolve-Path .\backend\.venv\Scripts\python.exe).Path
& $python --version
& $python -B -c "import fastapi, uvicorn, psycopg, pydantic, pytest; print('Python dependencies OK')"
node --version
npm --version
docker version --format '{{.Server.Version}}'
docker image inspect postgres:16-alpine --format '{{.Id}}'
& $python -B backend/scripts/watch_auctionator.py --help
& $python -B backend/scripts/ingest_local_capture.py --help
& $python -B backend/scripts/read_local_evidence.py --help
```

Ensayo comprobado con Python 3.13, Node 20 y PostgreSQL 16. La ausencia de Docker
o frontend **no impide archivar**. Si faltan dependencias, prepararlas antes del
primer día: venv del backend con `pip install -e '.[dev]'` desde backend y
`npm ci` desde frontend, usando los manifiestos publicados. No reinstalar ni
actualizar versiones mientras hay una captura en curso.

No ejecutar `scripts/migrate.py` sin destino explícito: su default es DATABASE_URL.
No arrancar/recrear el PostgreSQL de compose para este ensayo; podría ser desarrollo.

## 2. PostgreSQL nuevo de laboratorio — hoy, sólo fixtures

Este bloque crea un contenedor **nuevo**, puerto exclusivo loopback y contraseña
aleatoria de ensayo. No utiliza el contenedor de desarrollo. Conservar estas
variables en esta consola privada; no imprimirlas ni guardarlas en el repositorio.

```powershell
$labContainer = 'wow-prelaunch-' + [guid]::NewGuid().ToString('N').Substring(0,12)
$labUser = 'wow_lab'
$labPassword = [guid]::NewGuid().ToString('N')
$labRoot = Join-Path $env:TEMP ('wow-prelaunch-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $labRoot) { throw 'El directorio debe ser nuevo' }
New-Item -ItemType Directory -Path $labRoot | Out-Null
$labEnvFile = Join-Path $labRoot 'postgres.env'
[IO.File]::WriteAllText($labEnvFile, "POSTGRES_USER=$labUser`nPOSTGRES_PASSWORD=$labPassword`nPOSTGRES_DB=postgres`n", [Text.UTF8Encoding]::new($false))
docker run -d --name $labContainer --label wow-companion-purpose=prelaunch-readiness `
  -p 127.0.0.1::5432 --env-file $labEnvFile postgres:16-alpine
if ($LASTEXITCODE -ne 0) { throw 'No se creó el laboratorio' }
$labBinding = docker port $labContainer 5432/tcp
$labPort = [int](($labBinding -split ':')[-1])
docker exec $labContainer pg_isready -U $labUser -d postgres
# Si aún inicia: esperar unos segundos y repetir pg_isready, sin importar todavía.
```

Crear dos bases nuevas: destino y referencia protegida vacía. DATABASE_URL para
la **consola de ingestión** debe ser esa referencia, nunca desarrollo ni el target.
No usar una base de tests preexistente como destino de preparación.

```powershell
$labName = 'wow_prelaunch_' + [guid]::NewGuid().ToString('N').Substring(0,12) + '_test'
$referenceName = 'wow_reference_' + [guid]::NewGuid().ToString('N').Substring(0,12) + '_test'
docker exec $labContainer createdb -U $labUser $referenceName
if ($LASTEXITCODE -ne 0) { throw 'Referencia no creada' }
docker exec $labContainer createdb -U $labUser $labName
if ($LASTEXITCODE -ne 0) { throw 'Destino no creado' }
$env:DATABASE_URL = "host=127.0.0.1 port=$labPort dbname=$referenceName user=$labUser password=$labPassword"
$env:AUCTIONATOR_LAB_DSN = "host=127.0.0.1 port=$labPort dbname=$labName user=$labUser password=$labPassword"
docker exec $labContainer psql -U $labUser -d $labName -Atc "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
docker exec $labContainer psql -U $labUser -d $labName -Atc "SELECT count(*) FROM pg_sequences WHERE schemaname='public'"
# Ambos deben devolver 0. Si no: detenerse, no migrar ese destino.
& $python -B -c "import os,sys; sys.path.insert(0,'backend'); from scripts.migrate import run_migrations; print(run_migrations(os.environ['AUCTIONATOR_LAB_DSN']))"
if ($LASTEXITCODE -ne 0) { throw 'Migración del laboratorio falló' }
docker exec $labContainer psql -U $labUser -d $labName -Atc 'SELECT id FROM schema_migrations ORDER BY id'
# Deben estar las seis migraciones 001–006, sin editar sus archivos.
& $python -B backend/scripts/import_auctionator.py --trial --check-target `
  --database-url-env AUCTIONATOR_LAB_DSN --expected-database $labName
if ($LASTEXITCODE -ne 0) { throw 'Destino no verificado' }
```

No inyectar opciones de routing PostgreSQL por PGSERVICE/PGHOST/PGPORT/PGOPTIONS.
TrialDatabase las rechaza; usar una consola limpia con host, port, dbname y user
explícitos. No quitar guards ni conectar desarrollo para sortear un bloqueo.
La referencia nueva sustituye desarrollo **sólo para este ensayo autorizado**.

Para repetir el ensayo automático completo con otro lab **nuevo y vacío**:

```powershell
$env:PRELAUNCH_INTEGRATION_DATABASE_URL = $env:AUCTIONATOR_LAB_DSN
$env:PRELAUNCH_PROTECTED_DATABASE_URL = $env:DATABASE_URL
$env:PRELAUNCH_INTEGRATION_DATABASE_NAME = $labName
$env:PRELAUNCH_ARTIFACTS_DIR = Join-Path $labRoot 'rehearsal'
$pytestRoot = Join-Path $env:TEMP ('wow-readiness-tests-' + [guid]::NewGuid().ToString('N'))
Push-Location backend
try {
  & $python -X utf8 -B -m pytest -q -s -p no:cacheprovider --basetemp=$pytestRoot tests/test_prelaunch_readiness.py
  if ($LASTEXITCODE -ne 0) { throw 'Ensayo incompleto: conservar resultados y revisar' }
} finally { Pop-Location }
```

El test crea sólo archivos sintéticos, inicia el watcher real, prepara sidecars
simulated, usa las CLI publicadas y escribe un `latest.json` fuera del proyecto.
Exige destino sin exports; para repetir desde cero crear otro destino, no borrar
evidencia del anterior. No suministrar archivos o contextos auténticos al test.

## 3. Elegir WTF e iniciar watcher — lanzamiento, condicionado

**Pendientes:** identificar la instalación que se usará, la cuenta SavedVariables
correcta y observar su primer `/reload`. No se supone disponible WoW hoy. No
buscar una copia histórica ni un backup como sustituto del origen vivo.

```powershell
$sourceFile = Read-Host 'Ruta completa de Auctionator.lua en el WTF real revisado'
$privateArchive = Read-Host 'Directorio PRIVADO de capturas, fuera del proyecto y de WTF'
if ([IO.Path]::GetFileName($sourceFile) -ine 'Auctionator.lua') { throw 'Revisar archivo elegido' }
if (-not (Test-Path -LiteralPath (Split-Path -Parent $sourceFile) -PathType Container)) { throw 'Padre del origen inexistente' }
$watchArgs = @($sourceFile, '--destination', $privateArchive)
# Añadir sólo lo comprobado. No declarar una versión por estar instalada hoy.
$verifiedVersion = Read-Host 'Versión del perfil seleccionado: 340, 341 o vacío si desconocida'
if ($verifiedVersion) {
  if ($verifiedVersion -notin @('340','341')) { throw 'Versión no soportada' }
  $watchArgs += @('--source-version', $verifiedVersion)
}
$codecProfile = Read-Host 'Perfil del formato: lua o cbor-definite'
if ($codecProfile -eq 'cbor-definite') { $watchArgs += @('--serialized-codec','cbor-definite') }
elseif ($codecProfile -ne 'lua') { throw 'Formato no verificado: detenerse' }
& $python -X utf8 -B backend/scripts/watch_auctionator.py @watchArgs
```

El proceso es foreground; detenerlo con **Ctrl+C** en esa consola. No se instala
como servicio ni queda autoarranque. El default observa cada 2s y exige 4s de
estabilidad, además del debounce de 2s; durante el ensayo se usaron tiempos cortos.
Si el archivo aún no existe pero su padre sí, espera a que aparezca.

En WoW: scan y `/reload` manuales o salida normal; esperar el mensaje de captura
archivada antes de provocar otro guardado. Repetir el mismo estado debe indicar
idéntico/sin cambios. Reiniciar con la misma ruta/destino conserva la deduplicación.
El watcher no puede recuperar estados que WoW nunca guardó, ni garantizar estados
intermedios sobrescritos entre sondeos o antes de estabilizarse. Nunca prometer
captura de cada cambio intradiario. Backend o catálogo caídos no detienen el archivo.

## 4. Comprobar publicación, capture-id y hashes

Usar otra consola, con `$privateArchive` elegido en privado. El ID de 12 caracteres
del mensaje de watcher es sólo una abreviatura: seleccionar el SHA completo.

```powershell
Get-ChildItem -LiteralPath (Join-Path $privateArchive 'captures') -Directory |
  ForEach-Object { Get-Content -LiteralPath (Join-Path $_.FullName 'metadata.json') -Raw -Encoding UTF8 | ConvertFrom-Json } |
  Select-Object capture_id, source_sha256, market_sha256, captured_at, source_bytes, item_count, native_fact_count
$captureId = Read-Host 'SHA-256 COMPLETO de la captura publicada elegida'
if ($captureId -cnotmatch '^[0-9a-f]{64}$') { throw 'ID incompleto o inválido' }
$captureDirectory = Join-Path (Join-Path $privateArchive 'captures') $captureId
$originalFile = Join-Path $captureDirectory 'Auctionator.lua'
$metadata = Get-Content -LiteralPath (Join-Path $captureDirectory 'metadata.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$originalHash = (Get-FileHash -LiteralPath $originalFile -Algorithm SHA256).Hash.ToLowerInvariant()
if ($originalHash -cne $captureId -or $metadata.source_sha256 -cne $captureId -or $metadata.capture_id -cne $captureId) { throw 'Integridad inconsistente: no importar' }
```

La publicación válida está en `captures/<SHA>/{Auctionator.lua,metadata.json}`.
`pending` conserva intentos no publicados y nunca se importa directamente. No
editar originales/metadatos, quitar sólo lectura ni reconstruir fechas desde mtime.
`captured_at` es adquisición de copia; no fecha de precios ni hora del scan.
El hash de bytes, el hash económico local y el state hash con contexto son distintos.

## 5. Contexto, preflight y destino — importación manual condicionada

Primero revisar evidencia auténtica de región técnica, economía o ámbito conectado,
reglas, alcance shared/faction, facción si corresponde, origen y dataset/fase.
`PvP` no identifica un reino/región; desconocer facción no prueba shared. El formato
de ingestión local debe estar verificado como 341. Build y productor del codec no
confirmados permanecen desconocidos; no inventar sus claims.

Preparar el JSON privado `verified-local-capture-v1` usando la receta completa de
[5B.2, contexto](PHASE_5B2_MANUAL_INGESTION.md#identificar-la-captura-y-preparar-el-contexto).
Solicita cada claim y su evidence_ref, cubre todos los mercados y usa el hash
elegido. Nunca copiar el JSON del ensayo: sus datos son sólo `simulated`.
Stress_test y launch conservan fase/dataset separados; `real` legacy no es launch.

En la **consola de ingestión**, seleccionar explícitamente referencia y laboratorio
autorizados. En el ensayo son las dos bases nuevas del paso 2; para datos auténticos
la pareja debe revisarse y autorizarse antes. No cambiar una referencia por otra
para conseguir importar en el mismo destino que debería estar protegido.

```powershell
$contextFile = Read-Host 'Ruta del sidecar privado revisado para ESTE capture-id'
& $python -X utf8 -B backend/scripts/ingest_local_capture.py preflight `
  --archive $privateArchive --capture-id $captureId --context-file $contextFile
if ($LASTEXITCODE -ne 0) { throw 'Preflight bloqueado: conservar original, no importar' }
# import_performed=false, target_verified=false: preflight es totalmente offline.
& $python -B backend/scripts/import_auctionator.py --trial --check-target `
  --database-url-env AUCTIONATOR_LAB_DSN --expected-database $labName
if ($LASTEXITCODE -ne 0) { throw 'Destino no verificado: no importar' }
& $python -B backend/scripts/read_local_evidence.py markets --database-url-env AUCTIONATOR_LAB_DSN
if ($LASTEXITCODE -ne 0) { throw 'Tracking 006/destino no disponible: no importar' }
# SÓLO con autorización, claims revisados, preflight y target válidos:
& $python -X utf8 -B backend/scripts/ingest_local_capture.py ingest `
  --archive $privateArchive --capture-id $captureId --context-file $contextFile `
  --database-url-env AUCTIONATOR_LAB_DSN --expected-database $labName
if ($LASTEXITCODE -ne 0) { throw 'Importación no confirmada: verificar recibos antes de repetir' }
```

La ruta publicada sigue siendo **TrialDatabase**, destino explícito terminado en
`_test`, host/port/dbname/user y dos identidades físicas distintas. No existe en
esta fase un flujo autorizado hacia desarrollo o una base de producción ordinaria.
Si no hay pareja autorizada o contexto suficiente, **seguir archivando sin importar**.
Cada repetición válida crea otro recibo y reutiliza estado/hechos; no añade un día.

## 6. FastAPI, React y consulta v2 — hoy contra lab; lanzamiento sólo destino revisado

En una consola nueva de **sólo lectura HTTP**, configurar DATABASE_URL como el
**target**. No reutilizar esa consola para importar: dejaría target=protegida y
TrialDatabase lo bloqueará. No editar los `.env` de desarrollo.

```powershell
$env:DATABASE_URL = Read-Host 'DSN privado del TARGET autorizado de lectura'
$env:FRONTEND_ORIGINS = 'http://127.0.0.1:5179'
& $python -B -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Si el puerto está ocupado, elegir otro explícitamente y usarlo en todas las URLs.
En otra consola, desde la raíz:

```powershell
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8001'
Push-Location frontend
try { npm run dev -- --host 127.0.0.1 --port 5179 --strictPort }
finally { Pop-Location }
```

Verificar GET y CORS sin mostrar metadatos privados:

```powershell
$api = 'http://127.0.0.1:8001'
Invoke-RestMethod "$api/health"
$marketPage = Invoke-RestMethod "$api/evidence/v2/markets?dataset=simulated"
$marketPage.items | Select-Object id, dataset, economy, region
$marketId = Read-Host 'ID de economía elegida EXPLÍCITAMENTE'
$states = Invoke-RestMethod "$api/evidence/v2/markets/$marketId/states?dataset=simulated"
$states.items | Select-Object id, state_hash, native_fact_count, receipt_count
$stateId = Read-Host 'ID de estado elegido EXPLÍCITAMENTE'
Invoke-RestMethod "$api/evidence/v2/markets/$marketId/states/$stateId/facts?dataset=simulated"
Invoke-RestMethod "$api/evidence/v2/markets/$marketId/states/$stateId/receipts?dataset=simulated"
$cors = Invoke-WebRequest "$api/evidence/v2/markets?dataset=simulated" -Headers @{Origin='http://127.0.0.1:5179'} -UseBasicParsing
if ($cors.Headers['Access-Control-Allow-Origin'] -ne 'http://127.0.0.1:5179') { throw 'Origen CORS no coincide' }
```

Estos comandos usan **simulated para el lab**; cambiar a launch sólo para contexto
auténtico revisado e importado con esa fase. No reasignar fixtures a launch para
conseguir nombres. En `http://127.0.0.1:5179`: Evidencia → dataset → economía → estado.
Comprobar precio guardado, null/cero, detalles nativos, recibos, procedencia y
búsqueda por ID. No se usan métricas 3A/3B ni acumulados 003 como estados v2.
La CLI privada adicional acepta `markets`, `states`, `state`, `facts`, `receipts`:

```powershell
& $python -B backend/scripts/read_local_evidence.py states --market-id $marketId --database-url-env AUCTIONATOR_LAB_DSN
& $python -B backend/scripts/read_local_evidence.py facts --market-id $marketId --export-id $stateId --database-url-env AUCTIONATOR_LAB_DSN
& $python -B backend/scripts/read_local_evidence.py receipts --export-id $stateId --database-url-env AUCTIONATOR_LAB_DSN
```

`capture_context` y referencias privadas sólo están en el lector privado; no
publicar su salida. La API web permite únicamente sus proyecciones públicas.

Catálogo opcional: [5D.2](PHASE_5D2_ITEM_CATALOG.md). AHledger sólo se consulta
manualmente por IDs concretos; render y caducidad no lo consultan. Nombres sólo
para IDs simples launch con procedencia vigente y atribución junto al nombre;
idioma/build pueden seguir desconocidos. Sin conexión o tras TTL (máximo 300s):
Item ID, con hechos/precios intactos. Cuatro IDs es límite de la CLI actual por
invocación. No habilitar iconos remotos ni descargar/redistribuir sin permiso.

## 7. Backup verificado del archivo local — hoy sobre fixture; lanzamiento en privado

Detener watcher con Ctrl+C antes del backup. Elegir un destino nuevo externo al
repositorio, al archivo y a WTF, preferiblemente en otro volumen privado. Copiar
todo el árbol, incluidos `pending`; no mover ni borrar el original. Esto respalda
el archivo local, **no PostgreSQL**. La recuperación económica empieza por los
originales y sus contextos; conservar aparte también los sidecars revisados.

```powershell
$privateArchive = (Get-Item -LiteralPath $privateArchive).FullName.TrimEnd('\')
$backupRoot = Read-Host 'Destino NUEVO del backup privado en otro volumen'
$backupRoot = [IO.Path]::GetFullPath($backupRoot).TrimEnd('\')
$repoRoot = (Resolve-Path .).Path.TrimEnd('\')
foreach ($boundary in @($privateArchive,$repoRoot)) {
  if ($backupRoot -ieq $boundary -or $backupRoot.StartsWith($boundary + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Backup debe quedar fuera del archivo y del repositorio' }
}
if (Test-Path -LiteralPath $backupRoot) { throw 'No sobrescribir un backup existente' }
Copy-Item -LiteralPath $privateArchive -Destination $backupRoot -Recurse -Force -ErrorAction Stop
$backupFailures = 0
Get-ChildItem -LiteralPath $privateArchive -Recurse -File -Force | ForEach-Object {
  $relative = $_.FullName.Substring($privateArchive.Length).TrimStart('\')
  $copy = Join-Path $backupRoot $relative
  if (-not (Test-Path -LiteralPath $copy -PathType Leaf)) { $backupFailures++ }
  elseif ((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash -cne (Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash) { $backupFailures++ }
}
if ($backupFailures) { throw 'Backup no verificado: conservar origen y revisar' }
'Backup verificado; no se modificaron originales'
```

Tras reiniciar watcher, comprobar el archivo idéntico y continuar. Un backup en
el mismo disco sirve para el ensayo, pero no protege contra pérdida del volumen.
No se probó en esta entrega recuperación de desastre de un disco real ni pg_restore.

## 8. Recuperación de errores

| Situación | Acción operativa |
| --- | --- |
| Ruta ausente/incorrecta | Revisar instalación y cuenta en privado. Si padre existe, watcher espera; no crear una identidad falsa ni apuntar un backup como origen vivo. |
| Escritura parcial/archivo ocupado | Esperar estabilidad. Windows puede negar un escritor mientras se valida la copia. No cambiar permisos para forzar acceso. |
| Disco lleno/archive_error | Detener nuevos guardados si es posible, conservar origen/pending, liberar o preparar almacenamiento privado y reintentar con los mismos parámetros. Nunca borrar capturas para silenciar el error. |
| Captura inválida, >16 MiB, cantidad/índice fuera de rango o precio >2**63-1 | No hay publicación válida garantizada. Conservar el original bruto en privado y escalar compatibilidad; no truncar ni debilitar guards. |
| Precio entre 2**31 y 2**63-1 | Archivo válido local; `price_exceeds_persistence_int32` bloquea captura completa para SQL. Continuar archivando; no retirar sólo los items caros. |
| Contexto/hash/codec no coincide | No importar. Revisar ese capture-id y su evidencia. No editar metadatos archivados para que coincidan. |
| Target/protegida iguales, nombre incorrecto, 006 ausente, credenciales caídas | Detener ingestión. Revisar la pareja autorizada en la consola correcta. No migrar automáticamente un destino desconocido. |
| Timeout/fallo durante importación | Verificar hechos y recibos antes de repetir. El ensayo confirmó rollback de evidencia y un audit failed; secuencias pueden dejar huecos sin corrupción. |
| API/frontend/DB caídos | Watcher sigue archivando. Reiniciar lectores por separado; no convertir recepción SQL en fecha de precios. |
| AHledger caído/429/TTL vencido | Mantener IDs; no afecta archivo ni hechos. Honrar Retry-After; no polling ni bucles de consulta. |

Parada normal de API/React: Ctrl+C en sus consolas. Para pausar sólo el contenedor
creado en el paso 2: `docker stop $labContainer`; reanudarlo: `docker start $labContainer`
y comprobar pg_isready. No usar `docker compose down -v`, no borrar volúmenes ni
eliminar bases para repetir un ensayo. No se activan servicios permanentes.

## 9. Comprobar privacidad en Git

```powershell
git status --short --untracked-files=all
git diff --stat
git diff --cached --name-only
git ls-files -- '*.lua' '.env' 'backend/.env' 'frontend/.env' 'data/imports/*'
git check-ignore data/imports/item-catalog/2589.json backend/.env frontend/.env
git diff --check
```

`git ls-files '*.lua'` incluye fixtures sintéticos ya versionados: revisarlos por
nombre, no confundirlos con capturas reales. No debe aparecer ningún SavedVariables
auténtico, caché privada, contexto, credencial ni archivo de runtime. El archivo de
capturas y backups deben quedar **fuera** del repositorio, aun si una carpeta estuviera
ignorada. Revisar explícitamente cualquier archivo antes de staging; no hacer
`git add .` al operar. El ensayo se entregó inicialmente sin staging, commit ni
push; su publicación posterior fue autorizada sólo para pruebas y documentación
de Fase 6, sin archivos privados ni permiso de importar capturas auténticas.
