# WoW Forever Companion

Catálogo prelaunch 5D.2: [uso y validación](docs/PHASE_5D2_ITEM_CATALOG.md).
Consulta manual puntual a AHledger, caché temporal separada de precios y nombres
en Evidencia launch; iconos con placeholder hasta autorización. Sin migraciones,
importación auténtica ni sincronización automática.

WoW Forever Companion es un proyecto personal de portfolio y una herramienta pensada para acompanar el juego desde el lanzamiento de WoW Forever. El foco inicial es construir Market Intelligence para el Auction House: analizar mínimos guardados, disponibilidad máxima, cambios y dispersión a partir de evidencia histórica. Las oportunidades pertenecen a una fase posterior.

Auctionator 340 y 341 aportan observaciones parciales de precios y disponibilidad. La compatibilidad offline de 341 se comprobó con un SavedVariables auténtico de la stress test del 21/10/2026: siete items en un único índice nativo, 2485. La persistencia está preparada y probada con fixtures en laboratorio, pero **todavía no se importaron capturas auténticas**. Siguen pendientes región técnica y procedencia completa; el build en el momento de captura y el productor efectivo del codec no están confirmados. Los snapshots completos de Fase 2 conservan su contrato independiente.

## Objetivo de v0.1

La v0.1 debe ser una primera version usable para validar el producto con datos simulados o importados desde archivos simples. No busca resolver todo el ecosistema de WoW Forever, sino demostrar que el nucleo de inteligencia de mercado funciona de punta a punta.

Alcance concreto:

- Mantener contratos independientes para snapshots completos y evidencia parcial.
- Ingerir datos simulados o archivos exportados en un formato controlado.
- Guardar históricos de items, snapshots y estadísticas parciales con procedencia.
- Consultar mínimos guardados, promedio/mediana de mínimos, cambios, dispersión, tendencia y disponibilidad máxima.
- Consultar señales estadísticas explicables en Fase 3B; su integración 3B.2 espera revisión visual. No confirman oportunidades de compra.
- Preparar el backend para exponer herramientas consultables por un asistente de IA sobre datos propios.
- Proveer una interfaz simple para explorar items y ver senales de mercado.

Fuera de alcance para v0.1:

- Personajes, guild, roster, raid planner, profesiones completas o gear planning.
- Integracion definitiva con un addon especifico.
- Automatizacion compleja de compra/venta.
- Modelos predictivos avanzados.
- Optimizaciones prematuras de escala.

## Stack

- Frontend: React + TypeScript + Vite, dashboard de Market Intelligence.
- Backend: Python + FastAPI.
- Database: PostgreSQL.
- Control de versiones: Git/GitHub.

La prioridad es mantener el sistema simple, explicable y facil de defender tecnicamente. Las abstracciones deben existir solo donde reducen acoplamiento real, especialmente alrededor de la fuente de datos del Auction House.

## Documentacion

- [Arquitectura](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Preparación segura de ingestión local 5B.1](docs/PHASE_5B1_INGESTION_READINESS.md):
  precios extremos sólo como evidencia local. La actualización 5B.1.1 prepara
  identidad económica y linaje persistente con migración 006, validados con
  fixtures en laboratorio. Sin sincronización ni importación auténtica.
- [Ingestión manual protegida y lectores v2 — 5B.2](docs/PHASE_5B2_MANUAL_INGESTION.md):
  preflight offline de capturas ya archivadas, contexto económico explícito,
  escritura sólo mediante TrialDatabase en laboratorios preparados con 006 y
  consulta independiente de estados, hechos y recepciones. Sin alimentar 3A/3B.
- [Consulta visual de evidencia v2 — 5C.1](docs/PHASE_5C1_EVIDENCE_DASHBOARD.md):
  sección **Evidencia de mercado**, con dataset, economía y estado explícitos,
  una fila por item/variante y detalles nativos desplegables, búsqueda por ID y
  recepciones secundarias. Sólo GET; sin importar ni sincronizar.
  Diseño aprobado visualmente. La validación usa fixtures sintéticos; datos
  auténticos siguen pendientes. La próxima etapa investigará y validará proveedores
  de nombres, IDs, iconos y metadatos reales, con recetas/profesiones como extensión
  futura; todavía no se implementa el catálogo.

La estructura propuesta del repositorio esta documentada en [Arquitectura](docs/ARCHITECTURE.md#estructura-propuesta-del-repositorio).

## Desarrollo local

### Requisitos

- Python 3.11 o superior.
- Node.js 20 o superior.
- npm.
- PostgreSQL local, o Docker con Docker Compose para levantar solo la base de datos.

Docker se usa unicamente como opcion simple para PostgreSQL local. El frontend y el backend corren directamente en la maquina de desarrollo.

### 1. Configurar variables de entorno

Desde la raiz del repo:

```powershell
Copy-Item .env.example .env
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
```

Los archivos `.env` locales estan ignorados por Git. Los valores incluidos son defaults de desarrollo y pueden ajustarse segun tu instalacion local.

### 2. Levantar PostgreSQL

Opcion con Docker:

```powershell
docker compose up -d postgres
```

Opcion sin Docker:

1. Instalar PostgreSQL localmente.
2. Crear una base `wow_forever_companion`.
3. Crear un usuario `wow` con password `wow_dev_password`, o ajustar `backend\.env`.
4. Verificar que `DATABASE_URL` apunte a tu instancia local.

La comprobacion del backend esta disponible en:

```text
GET http://127.0.0.1:8000/health/db
```

### 3. Levantar el backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Health check:

```text
GET http://127.0.0.1:8000/health
```

### 4. Levantar el frontend

En otra terminal:

```powershell
cd frontend
npm install
npm run dev
```

La app queda disponible en:

```text
http://localhost:5173/
```

El dashboard de Fases 4A/4A.1 usa el flujo **mercado → item → resultados**.
Elegí un mercado disponible y un item: su histórico, métricas, disponibilidad
y calidad se cargan automáticamente. Un único historial `accumulated` compatible
se selecciona de forma segura; si hay varias fuentes o bases posibles, la app
pide elegir un historial. Ninguna exportación se selecciona automáticamente.

**Opciones avanzadas**, cerrada al inicio, conserva dataset, fuente, modo,
base temporal, exportación y todas las ventanas de análisis anteriores.
Los filtros compatibles se conservan al cambiar de item. Los incompatibles
se restablecen con aviso visible, sin mezclar contextos.
Al cambiar de mercado, el item seleccionado se conserva si el nuevo catálogo
lo incluye; en caso contrario se limpia con aviso y se pide elegir otro.

`VITE_API_BASE_URL` configura la URL pública del backend en tiempo de build
(default `http://localhost:8000`); nunca debe contener secretos. FastAPI permite
por defecto el origen `http://localhost:5173`: usar `127.0.0.1` en la barra del
navegador requiere agregar ese origen en `FRONTEND_ORIGINS` del `.env` local del
backend y reiniciarlo. Vite fija puerto 5173 para evitar un cambio de origen
silencioso. Para preview/otro despliegue, configurar su origen explícitamente.

### 5. Validaciones utiles

```powershell
# Backend vivo
Invoke-RestMethod http://127.0.0.1:8000/health

# Conexion backend -> PostgreSQL
Invoke-RestMethod http://127.0.0.1:8000/health/db

# Frontend compila
cd frontend
npm run build

# Precisión, contratos, ventanas, paginación y componentes (sin DB)
npm test

# Integración de lectura: requiere FastAPI y PvE simulado ya almacenado
npm run test:live
```

### 6. Ejecutar migraciones

Desde `backend`:

```powershell
.\.venv\Scripts\python.exe scripts\migrate.py
```

El runner usa SQL plano desde `backend/migrations/`, crea `schema_migrations` si hace falta, ejecuta solo migraciones pendientes y registra las aplicadas.
Las migraciones aplicadas no se editan: los cambios de esquema se agregan en archivos incrementales. Ejecutar un solo runner a la vez; no incorpora coordinacion entre procesos concurrentes.

### 7. Importar snapshots simulados

Desde `backend`, para cargar todos los snapshots de ejemplo en `data/samples/`:

```powershell
.\.venv\Scripts\python.exe scripts\import_samples.py
```

Para importar un archivo puntual:

```powershell
.\.venv\Scripts\python.exe scripts\import_snapshot.py ..\data\samples\snapshot_001.json
```

Tambien se puede importar enviando JSON directo al backend, desde la raiz del repositorio:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/imports/snapshots `
  -ContentType application/json `
  -InFile data\samples\snapshot_001.json
```

### 8. Consultas principales de Fase 2

```powershell
# Buscar items
$items = Invoke-RestMethod "http://127.0.0.1:8000/items?search=Lotus"
$itemId = $items[0].id

# Listar snapshots e identificar el mercado
$snapshots = Invoke-RestMethod "http://127.0.0.1:8000/snapshots"
$realmId = $snapshots[0].realm_id

# Consultar un item
Invoke-RestMethod "http://127.0.0.1:8000/items/$itemId"

# Consultar historico de un item
Invoke-RestMethod "http://127.0.0.1:8000/items/$itemId/history?realm_id=$realmId"

# Listar snapshots importados
Invoke-RestMethod "http://127.0.0.1:8000/snapshots?realm=Everlook&region=wow-forever"

# Listar importaciones
Invoke-RestMethod "http://127.0.0.1:8000/imports"
```

Pipeline de ingestion implementado en Fase 2:

```text
JSON simulado
  -> FileAdapter
  -> NormalizedSnapshot
  -> validacion Pydantic
  -> IngestionService
  -> PostgreSQL
  -> endpoints de consulta historica
```

La Fase 2 guarda snapshots agregados por item. Todavia no calcula tendencias, volatilidad, oportunidades ni recomendaciones.

Tablas actuales: `schema_migrations`, `realms`, `items`, `auction_snapshots`, `auction_snapshot_items` e `import_runs`. Los siete JSON de `data/samples/` contienen diez items distintos y 69 observaciones en total. Incluyen variaciones de precio y volumen, cambio de nombre/calidad y desaparicion/reaparicion de un item; son exclusivamente datos simulados.

Reglas del pipeline:

- Precios y cantidades: enteros estrictos entre 0 y 2147483647; floats, booleans y valores fuera de rango se rechazan con 422 por HTTP.
- `captured_at` e `imported_at`, si se proporciona, requieren zona horaria y se normalizan a UTC.
- Un realm se identifica por `realm_id`, con nombre y region visibles en snapshots e historicos. Regiones vacias o con solo espacios se normalizan a NULL en entrada; PostgreSQL rechaza valores no normalizados.
- Los filtros aceptan `realm_id` o `realm` mas `region`. Un nombre ambiguo devuelve 422; un selector inexistente devuelve 404. `region=` selecciona region NULL. El historico sin selector solo se permite cuando hay un unico realm; `/snapshots` sin filtro lista mercados identificados.
- La unicidad de un snapshot depende de `(realm_id, source_type, captured_at)` o `source_hash`. Reimportaciones secuenciales y concurrentes devuelven `duplicate` con el ID original y cero items importados. Dos imports concurrentes nuevos terminan como `completed` y `duplicate`.
- `source_hash` es SHA-256 de los bytes originales para archivos y de JSON con claves ordenadas para HTTP. Pueden diferir entre transportes; la identidad relacional sigue evitando duplicados. La primera importacion conserva sus datos incluso si otro payload usa la misma identidad.
- `external_item_id` es global. Cambios de nombre/calidad actualizan el catalogo sin cambiar `items.id` ni los agregados historicos.
- `import_runs` registra intentos que alcanzaron ingestion/persistencia: completed, duplicate o failed. Errores de lectura, parsing y validacion previos quedan fuera. Un fallo de persistencia revierte los datos de mercado y registra failed en una transaccion separada; si PostgreSQL no esta disponible, tampoco puede garantizarse ese registro.

### 9. Ejecutar tests en un entorno aislado

Desde `backend`, instalar las dependencias de desarrollo y definir explicitamente una base separada:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:TEST_DATABASE_URL = "postgresql://wow:wow_dev_password@localhost:5432/wow_forever_companion_test"
.\.venv\Scripts\python.exe scripts\setup_test_database.py
.\.venv\Scripts\python.exe -m pytest -q
```

Adaptar las credenciales/host al PostgreSQL local. Tambien se puede definir `TEST_DATABASE_URL` en `backend/.env`, siempre ignorado por Git. El script crea la base de testing si no existe y aplica sus migraciones; necesita permisos para crearla.

La suite exige un nombre terminado en `_test`, diferente del nombre de la base de desarrollo. Sin configuracion explicita, o si apunta a desarrollo, se niega a preparar el entorno. Cada test de integracion crea un esquema aleatorio, aplica las migraciones alli y elimina solamente ese esquema. No borra ni reinicia tablas o secuencias de desarrollo; tampoco limpia tablas compartidas del entorno de testing. Los tests unitarios y de validacion HTTP pueden ejecutarse sin base con `pytest tests/test_file_adapter.py tests/test_import_validation.py`.

## Supuestos pendientes de validar

- Cual sera la fuente real de datos del Auction House.
- Frecuencia posible de actualizacion de snapshots.
- Campos disponibles por item, subasta y realm.
- Si existira una API confiable o si dependeremos de exports de addons.
- Como se identificaran items de forma estable en WoW Forever.
- Si habra restricciones legales, tecnicas o de terminos de uso para obtener datos.

## Fase 2.5: Auctionator y mercado fresh simulado

La etapa original se validó con simulación. La integración 341 posterior tiene
compatibilidad offline auténtica comprobada y persistencia protegida preparada
para revisión de trial. No se importaron sus capturas a PostgreSQL.
La [investigación de Auctionator 340](docs/AUCTIONATOR_340.md) detalla evidencia,
formatos soportados y límites. El addon ofrece mínimos diarios, mayor mínimo diario,
disponibilidad máxima y último mínimo sin fecha. No ofrece ventas, promedio de
publicaciones ni cantidad de subastas en esta base de precios.

Desde `backend`, aplicar la migración incremental y generar/importar datos:

```powershell
.\.venv\Scripts\python.exe scripts\migrate.py
.\.venv\Scripts\python.exe scripts\generate_fresh_market.py
.\.venv\Scripts\python.exe scripts\import_auctionator.py ..\data\imports\fresh\Auctionator.lua --source-id fresh-seed-340 --region simulation --dataset simulated
# Repetir el último comando reutiliza export_id, devuelve duplicate y cero cambios.
```

El generador usa seed 340, 50 items ficticios, 30 días y cuatro mercados
PvE/PvP/HC/RP. Produce 16.628 estadísticas (16.428 diarias y 200 últimos mínimos
sin fecha), no 16.628 subastas. Perfiles: materiales abundantes, demanda creciente,
oferta escasa, volatilidad temprana que se estabiliza, aparición tardía y días sin
observación. Los IDs y nombres son **FICTIONAL** y todos los precios/disponibilidades
son **SIMULATED**. Los tres archivos generados (Lua, catálogo y contexto) quedan
en `data/imports/fresh/`, ignorados por Git. Opciones: `--seed`, `--days`, `--items`,
`--markets` y `--output`. No se representan ventas ni auction_count.

Para los antecedentes de capturas auténticas 341, ver [la validación real](docs/FIRST_REAL_AUCTIONATOR_VALIDATION.md)
y [el procedimiento histórico de trial](docs/BETA_DATA_READINESS.md#14-persistencia-341-con-procedencia-verificada-y-destino-trial).
El procedimiento manual vigente es [5B.2](docs/PHASE_5B2_MANUAL_INGESTION.md):
captura publicada de 5A, contexto verificado completo y laboratorio preparado
con 006. `import_auctionator.py` sigue bloqueando 341 sin ese enlace; usar
`ingest_local_capture.py preflight|ingest`. No se autoriza todavía una importación auténtica.
Para CBOR serializado se exige el perfil explícito `cbor-definite`. Las migraciones
005/006, la procedencia vinculada al hash, la identidad económica explícita y
el destino TrialDatabase verificado son obligatorios. La stress
test usa un dataset independiente `stress_test`; no representa el lanzamiento.
No completar la región por idioma, ubicación o nombre PvP.

Sin base temporal se guarda el índice del addon; no se asume UTC ni la fecha de
importación como observación: 2485 no equivale directamente a una fecha civil.
Se admite el subconjunto CBOR acotado comprobado en 341, sin atribuirle un productor
confirmado ni anunciar soporte completo de toda serialización nativa del cliente.
Los lectores Lua/CBOR aplican límites de tamaño/profundidad/tipos y no ejecutan código.

Consultas, con el backend iniciado:

```powershell
$markets = Invoke-RestMethod http://127.0.0.1:8000/partial/markets
$marketId = ($markets | Where-Object { $_.market_key -eq 'PvE' -and $_.dataset -eq 'simulated' -and $_.region -eq 'simulation' }).id
Invoke-RestMethod "http://127.0.0.1:8000/partial/items?market_id=$marketId"
Invoke-RestMethod "http://127.0.0.1:8000/partial/history?market_id=$marketId&item_key=1900000000&source_id=fresh-seed-340"
Invoke-RestMethod http://127.0.0.1:8000/partial/imports
```

El histórico exige mercado, item_key y source_id; `temporal_basis` selecciona una
serie con base conocida (default `unknown`). Acepta `start_day`, `end_day`, `limit`
y `offset`. Los últimos mínimos sin fecha aparecen después de los días; un filtro
de días los excluye. `/partial/items` acepta limit/offset; `/partial/imports` acepta
limit. `POST /partial/imports` acepta el contrato JSON `PartialBatch`, no Lua ni paths
locales. Las importaciones Lua se hacen por CLI.

Los datos parciales usan las cuatro tablas de 003 y tres tablas de evidencia de 004,
con un catálogo sin nombres inventados.
Mercados reales y simulados tienen identidades separadas. Las tablas y endpoints de
snapshots completos permanecen independientes.

Pruebas: usar la misma base dedicada y setup de la sección 9; luego ejecutar toda
la suite con `python -m pytest -q -p no:cacheprovider`. Para parser/simulador sin DB:
`python -m pytest tests/test_auctionator.py -q -p no:cacheprovider`.
El [informe de validación](docs/PHASE_25_VALIDATION.md) registra resultados físicos,
idempotencia y preservación de Fase 2.

### Hardening tras auditoría adversarial

El importador ordena globalmente locks de items, después mercados y después
observaciones; valida la coherencia min/max contra los datos persistidos antes de
commit y reintenta sólo deadlocks 40P01 (máximo tres intentos). Claves literales
PvE/PvP/HC/RP deben coincidir con su ruleset; los mappings sólo resuelven claves
externas. Los límites se aplican durante construcción y con un presupuesto
compartido de parsing Lua/CBOR. El marcador SIMULATED se reconoce con BOM o
whitespace inicial, como protección contra errores de importación.

ModernAH puede generar precios fraccionarios por división buyout/cantidad. El
contrato de Fase 2.5 los **rechaza explícitamente sin redondear**; no debe afirmarse
compatibilidad con todos los precios legítimos del addon. El índice diario se fija
al cargar la sesión del addon y no se recalcula por scan.

La tabla 003 conserva extremos acumulados entre imports. La 004 agrega
`partial_exports`, `partial_export_facts` y `partial_export_imports`: campos nativos
l/h/a/m, estructura y vínculos de recepción, sin guardar el Lua completo. No hace
backfill ni reconstruye exports anteriores. Una primera importación con evidencia
nueva puede devolver completed con cero cambios acumulados.

El CLI devuelve `export_id`, `evidence_status` (created/reused) y `native_facts_seen`.
Agregar `&export_id=ID` a `/partial/history` consulta exclusivamente ese export;
el mínimo indica `minimum_origin=l` o `h_fallback`. Sin export_id sigue consultando
el acumulado. `value_semantics` distingue ambos y los estados normalizados sin
fecha. `/partial/imports` enlaza las recepciones; el POST normalizado anterior sigue
funcionando con `evidence_status=unavailable` porque no conserva estructura nativa.
Archivos antiguos no sustituyen un supuesto último estado observado; imported_at
es recepción. Contenido idéntico reutiliza evidencia, registrando cada intento.

Los triggers protegen hechos/cabeceras sellados y vínculos frente a modificaciones
accidentales mediante SQL; la estructura y su proyección se validan en el servicio.
Ver [evidencia por exportación](docs/PHASE_25_EXPORT_EVIDENCE.md) y el
[informe de hardening](docs/PHASE_25_HARDENING.md) para hallazgos, regresiones y pendientes.

## Fase 3A: Market Intelligence descriptivo

El motor consulta PostgreSQL en transacciones `READ ONLY, REPEATABLE READ` y no
modifica observaciones, exports, imports ni secuencias. No agrega migraciones ni
dependencias. Fase 3B (oportunidades), frontend, IA y predicciones permanecen fuera
de esta entrega. [Definiciones y validación](docs/PHASE_3A_VALIDATION.md).

Dos modos obligatorios e independientes:

- `accumulated`: extremos de `partial_observations`, nunca el supuesto estado
  más reciente del addon. El origen nativo del mínimo es `unknown`.
- `export`: exactamente un `export_id` sellado. Proyecta `l`, o `h` si falta `l`,
  indicando `minimum_origin=l|h_fallback`; disponibilidad solamente desde `a`.

Ambos seleccionan mercado, item/variante completa, source_id, source_type y base
temporal. Dataset/región provienen del mercado y se devuelven explícitamente.
Fuentes, versiones, bases y modos no se fusionan. La 004 puede estar vacía:
`accumulated` sigue funcionando, sin reconstruir evidencia nativa. `m` queda
excluido porque no tiene fecha; recepción e IDs no establecen cronología de scans.

Endpoints nuevos:

- `GET /market/series?market_id=...&item_key=...`: contextos disponibles, modos,
  bases y exports explícitos. Acepta `series_mode`, `limit` (1..100) y `offset`.
  El orden de paginación no es cronología de observación.
- `GET /market/metrics`: contexto, ventana, puntos, métricas, cobertura,
  referencias de evidencia y advertencias. Los derivados Decimal se serializan
  como strings decimales en notación fija (sin exponentes), con precisión de
  cálculo 40 y ROUND_HALF_EVEN, sin redondear a copper entero. El contexto de
  cálculo es independiente del redondeo y los traps del llamador Python.

Ejemplo con el mercado simulado ya almacenado, sin importar archivos:

```powershell
$markets = Invoke-RestMethod http://127.0.0.1:8000/partial/markets
$marketId = ($markets | Where-Object { $_.market_key -eq 'PvE' -and $_.dataset -eq 'simulated' -and $_.region -eq 'simulation' }).id
Invoke-RestMethod "http://127.0.0.1:8000/market/series?market_id=$marketId&item_key=1900000000"
$query = "market_id=$marketId&item_key=1900000000&source_id=fresh-seed-340&source_type=simulated&temporal_basis=unknown&series_mode=accumulated"
Invoke-RestMethod "http://127.0.0.1:8000/market/metrics?$query&window_type=observed_buckets&size=30"
Invoke-RestMethod "http://127.0.0.1:8000/market/metrics?$query&window_type=index_range&start_day=2500&end_day=2529"
```

En modo `export`, reemplazar `series_mode=accumulated` por `series_mode=export`
y agregar `export_id=...` de un contexto descubierto. No elegir el export por
una supuesta hora de scan.

Ventanas, con máximo 366 posiciones y ancla del mercado/contexto:

- `observed_buckets&size=N`: últimos N índices observados del mercado, no N
  registros del item ni N días calendario. Puede devolver menos de N.
- `index_range&start_day=A&end_day=B`: rango inclusivo, con huecos explícitos.
- `calendar_days&days=7|14|30`: requiere `temporal_basis` ISO con timezone
  comprobada. Opcional `end_day`; por defecto termina en el último bucket del
  mercado. Son buckets nominales de 86400 segundos del reloj del addon; una
  sesión puede seguir escribiendo en el índice anterior. No implica actualidad.

La base conocida se envía con URL encoding (por ejemplo, `+` como `%2B`); también
se acepta el sufijo `Z`. No se asignan fechas a una base desconocida. Un calendario
fuera de rango devuelve 422; los mismos índices siguen disponibles por rango.

Las métricas describen mínimos **guardados**, no el precio medio o máximo de todas
las subastas. Desviación muestral y CV son dispersión de niveles, no volatilidad
de retornos. Disponibilidad es un máximo por bucket: no se suma como ventas o
volumen. Ausencias son null; cero requiere evidencia explícita.

La cobertura divide buckets del item con dato por posiciones seleccionadas;
en `observed_buckets` el denominador contiene solamente los buckets seleccionados
del mercado. Los huecos entre índices se cuentan aparte. Muestras menores de
siete precios generan una advertencia, sin otorgar confianza estadística al
alcanzar siete. Los estados de cálculo son `ok`, `no_data`, `insufficient_data`
y `undefined`, con motivo y valor null cuando corresponde.

Errores: 422 para selección/ventana inválida, 404 para contexto inexistente,
409 para evidencia incoherente y 503 para base no disponible. Un manifest
malformado de un export seleccionado devuelve 409; el descubrimiento no lo
interpreta como indisponibilidad ni afecta items sin relación con ese export.
Los tests usan
exclusivamente la base dedicada y esquemas aleatorios descritos en la sección 9.
La compatibilidad con SavedVariables auténticos, fracciones ModernAH y codec
nativo sigue pendiente; no se amplió el alcance del parser.

## Fase 3B.1: señales estadísticas backend

`GET /market/signals` acepta los mismos selectores y ventanas de `/market/metrics`,
más parámetros validados de reglas. Devuelve desviación del último mínimo
guardado respecto de la mediana de los anteriores y tendencia histórica basada
en pendiente y cambio de 3A. Las direcciones requieren evidencia suficiente;
si falta, la respuesta incluye motivos estructurados y conserva los cálculos
descriptivos disponibles. No son oportunidades de compra confirmadas.

Defaults: siete precios anteriores para desviación, siete precios para tendencia,
80% de cobertura sobre posiciones solicitadas, 50% sobre el intervalo de índices,
precio en el ancla, desviación de al menos 20% y cambio de tendencia de al menos
10% con pendiente del mismo signo. Origen `l` y base temporal conocida pueden
exigirse mediante parámetros; por defecto, su ausencia conserva advertencias.
Decimal sigue como string decimal fijo, con precisión de cálculo 40.
Sin cambios de frontend, ingestión, datos, migraciones o endpoints existentes.
Fórmulas, configuración, ejemplos simulados, pruebas y limitaciones en
[PHASE_3B1_VALIDATION.md](docs/PHASE_3B1_VALIDATION.md).

## Fases 4A y 4A.1: dashboard React

- Diseño oscuro responsive, acentos dorados/bronce, tipografías del sistema y
  gráfico SVG local. Sin nuevas dependencias de runtime ni assets externos.
  Las pruebas de App montado usan jsdom 26.1.0 como dependencia de desarrollo,
  junto al runner Node y React DOM existentes.
- Catálogo paginado de `/partial/items` y búsqueda local por ID/variante sobre
  todos los items cargados. La API parcial no provee nombres; no se inventan.
- Dataset y mercado/región explícitos desde `/partial/markets`; contextos
  paginados desde `/market/series`. Ningún export se elige automáticamente;
  recepción e ID no se usan como cronología de observación.
- Exploración principal: mercado e item, con resultados automáticos. Dataset
  filtra la lista de mercados desde Opciones avanzadas; al inicio se muestran
  todos los mercados con región, reglas y SIMULATED/REAL diferenciados.
- Se prioriza el único contexto accumulated compatible, o una elección explícita
  previa que siga siendo válida. Varios accumulated entre fuentes/bases exigen
  elección; incluso un único export necesita selección explícita. Un default
  automático no se convierte en una preferencia de fuente para futuros items.
- `/market/metrics` proporciona puntos, promedio/mediana de mínimos, variación,
  pendiente, disponibilidad, cobertura, advertencias y procedencia. React no
  recalcula estadísticas. Gráfico por índices reales, con cortes en ausencias
  y saltos; ceros explícitos conservados. Tabla accesible con referencias.
- Ventanas: 1..366 buckets observados, rango inclusivo de hasta 366 índices,
  o 7/14/30 días con base temporal verificada. Ancla opcional por índice;
  el default pertenece al mercado/contexto, no a hoy. La consulta inicial solicita
  30 buckets observados, también con base conocida; menos datos conservan los
  avisos de cobertura. Los controles avanzados permiten cambiar esta ventana.
  El rango inicial termina en el último índice y ocupa como máximo 366 posiciones;
  un rango explícito mayor se rechaza con aviso, sin recortarlo.
- Mouse/touch inspeccionan el punto más cercano en el SVG, con desempate por
  índice menor; teclado y tabla conservan acceso a cada bucket. El eje vertical
  utiliza etiquetas copper enteras distintas incluso con precios cero/constantes.
- Los Decimal siguen siendo strings. Las abreviaturas con `…` indican
  truncamiento y se despliega el valor completo. La conversión oro/plata/cobre
  usa BigInt y conserva todas las fracciones de copper de la respuesta.
- Loading, reintento de conexión, vacíos y contexto inválido/incoherente.
  Las peticiones se cancelan al cambiar selección y sus resultados anteriores
  se ocultan. SIMULATED permanece visible en dataset y resultados.

Los contratos de respuesta del motor se generan desde OpenAPI, con tipos y
validación runtime. `/partial` no declara modelos de respuesta en OpenAPI:
sus tipos se basan en SQL/migración 003 y respuestas reales inspeccionadas.
Para comprobar o regenerar contratos, desde `frontend`:

```powershell
..\backend\.venv\Scripts\python.exe scripts\generate-api-contracts.py --check
# Después de un cambio intencional de API, regenerar sin --check.
```

Flujo con los datos existentes: `PvE · simulation · SIMULATED` → item
`1900000000` → resultados automáticos. Internamente se conserva fuente
`fresh-seed-340 · simulated`, modo `accumulated`, base `unknown` y 30 buckets.
Opciones avanzadas permite reproducir las consultas técnicas de 4A; no hay
botón obligatorio de consulta. Los cambios válidos actualizan los resultados
automáticamente, con debounce de 200 ms y cancelación de respuestas obsoletas.
No hay importación ni modificación de datos desde el dashboard o `test:live`.
Para otra URL de prueba: definir `TEST_API_BASE_URL` (no cambia la URL de Vite).

Validación original: [PHASE_4A_VALIDATION.md](docs/PHASE_4A_VALIDATION.md).
Simplificación y validación actual: [PHASE_4A1_VALIDATION.md](docs/PHASE_4A1_VALIDATION.md).
La integración de señales 3B.2 está implementada y espera revisión visual; rankings,
IA y alertas siguen pendientes. El diseño 4A/4A.1 fue aprobado
en revisión visual manual. Las pruebas montadas verifican eventos y efectos en
jsdom; no sustituyen el layout de un navegador o las pruebas en un dispositivo touch.

### Fase 3B.2: señales en el análisis del item

Debajo del gráfico, **Señales del histórico** muestra desviación frente a la mediana
anterior y tendencia histórica, con dirección, magnitud, explicación y evidencia
por regla. Se distinguen resultados neutros, evidencia insuficiente y ausencia de
precios. Las bajadas y subidas usan el mismo estilo neutral. Los motivos estructurados,
valores exactos, procedencia y parámetros efectivos siguen accesibles.

`/market/signals` usa exactamente la consulta de `/market/metrics`, incluidos item
con variante, fuente, base temporal, modo/export y ventana. Los parámetros estadísticos
quedan en sus defaults validados del backend. Las señales tienen carga, cancelación
y reintento independientes: su error conserva gráfico y métricas. Si las lecturas
no coinciden en contexto, ventana o evidencia, se ocultan las señales y se ofrece
recargar ambas consultas. No se modifican backend, ingestión ni PostgreSQL.

Datos de desarrollo **SIMULATED**; accumulated puede revisarse por imports posteriores
y export representa un estado sellado seleccionado. Ninguno garantiza precio actual,
ventas, demanda o rentabilidad. Implementación, pruebas y pendiente de captura real:
[PHASE_3B2_VALIDATION.md](docs/PHASE_3B2_VALIDATION.md).

## Fase 5A — Local Capture Companion

**5A.1 implementada:** núcleo manual en `backend/app/local_capture` y CLI
`backend/scripts/capture_auctionator.py`. Reutiliza el parser offline existente,
valida una lectura estable y archiva originales independientes y metadatos de
sólo lectura. No necesita PostgreSQL ni configuración `.env`.

Desde la raíz, después de `/reload` o salida normal y una vez terminada la escritura:

```powershell
$auctionatorFile = 'D:\WoW\WTF\Account\MI_CUENTA\SavedVariables\Auctionator.lua'
.\backend\.venv\Scripts\python.exe -B .\backend\scripts\capture_auctionator.py `
  $auctionatorFile --source-version 341 --serialized-codec cbor-definite
```

El destino predeterminado es `%LOCALAPPDATA%\WoWForeverCompanion\local-capture`.
`--destination` permite otro directorio privado; cualquier ruta dentro de este
proyecto se rechaza mediante código, sin depender de `.gitignore`.
La versión seleccionada no es una detección del addon; Lua sin serializar no
requiere codec. No se infieren región, dataset, build ni fechas desde buckets.

Mismos bytes reutilizan la captura por SHA-256. Un archivo distinto con mercado
canónico equivalente conserva su propia evidencia sin crear otro estado
económico. Cambios nativos `l/h/a/m` y estructura se identifican por separado,
con hashes por mercado. La hora UTC es adquisición local, no hora del scan.
Contrato, recuperación, privacidad, límites y pruebas:
[PHASE_5A1_LOCAL_CAPTURE.md](docs/PHASE_5A1_LOCAL_CAPTURE.md).

**5A.2 implementada:** watcher por polling de una ruta configurable,
con debounce, estabilización, reintentos acotados y salida con Ctrl+C. Invoca el
mismo núcleo 5A.1; no requiere un servicio de Windows ni envía datos al backend.
Desde la raíz, ingresar el SavedVariables **real** dentro de `WTF` de Forever:

```powershell
$foreverSavedVariables = Read-Host 'Ruta completa de Auctionator.lua real dentro de WTF'
.\backend\.venv\Scripts\python.exe -X utf8 -B .\backend\scripts\watch_auctionator.py `
  $foreverSavedVariables --source-version 341 --serialized-codec cbor-definite
```

La carpeta de copias históricas no es el origen en vivo. Las simulaciones usan
un archivo temporal independiente y un archivo de capturas separado; ninguna
ruta personal está fijada en el programa. El directorio padre del origen debe
existir, aunque el archivo puede aparecer después. Configuración, mensajes,
límites y resultados en [PHASE_5A2_LOCAL_WATCHER.md](docs/PHASE_5A2_LOCAL_WATCHER.md).
Detener con **Ctrl+C** en esa terminal. El polling puede perder estados intermedios;
la estabilidad del archivo no prueba el fin de un escaneo. La primera prueba
con un **`/reload` real de WoW Forever sigue pendiente**.
La validación final de 5A.1 incluyó dos capturas auténticas y fixtures sintéticos
para comprobar cambios de configuración sin cambios de mercado.

El archivador conserva precios enteros exactos hasta `2**63-1` (64 bits con signo).
La ingestión actual mantiene su límite de `2**31-1` (32 bits); cantidades e índices
locales también conservan ese límite. Compatibilizar precios de 64 bits con los
contratos de API y persistencia queda pendiente antes de una futura sincronización.

Después se estudiarán sincronización autenticada con backend, histórico y
análisis económico reales, estacionalidad semanal y posibles modelos predictivos.
El objetivo de dos a cuatro escaneos diarios es **manual**, sin automatización
dentro del juego. Las capturas auténticas siguen fuera de Git y no se importaron
durante esta entrega.

## Principio guia

Primero construir una base pequena que permita aprender con datos reales o simulados. Despues extender. El proyecto debe poder crecer hacia features de personajes, guilds o profesiones, pero la primera version debe concentrarse en el diferencial: inteligencia de mercado para el Auction House.
