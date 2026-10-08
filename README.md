# WoW Forever Companion

WoW Forever Companion es un proyecto personal de portfolio y una herramienta pensada para acompanar el juego desde el lanzamiento de WoW Forever. El foco inicial es construir Market Intelligence para el Auction House: entender precios, volumen, tendencias y oportunidades de mercado a partir de snapshots historicos.

Auctionator 340 es la fuente candidata para observaciones parciales de precios y disponibilidad. Su integración se basa en código local inspeccionado y sigue pendiente de un SavedVariables real de Forever. Los snapshots completos de Fase 2 conservan su contrato independiente.

## Objetivo de v0.1

La v0.1 debe ser una primera version usable para validar el producto con datos simulados o importados desde archivos simples. No busca resolver todo el ecosistema de WoW Forever, sino demostrar que el nucleo de inteligencia de mercado funciona de punta a punta.

Alcance concreto:

- Definir un contrato comun para snapshots del Auction House.
- Ingerir datos simulados o archivos exportados en un formato controlado.
- Guardar historico de items, precios, volumen y snapshots.
- Consultar metricas basicas por item: precio minimo, precio medio, maximo, volumen, tendencia simple y volatilidad.
- Detectar oportunidades iniciales con reglas explicables.
- Preparar el backend para exponer herramientas consultables por un asistente de IA sobre datos propios.
- Proveer una interfaz simple para explorar items y ver senales de mercado.

Fuera de alcance para v0.1:

- Personajes, guild, roster, raid planner, profesiones completas o gear planning.
- Integracion definitiva con un addon especifico.
- Automatizacion compleja de compra/venta.
- Modelos predictivos avanzados.
- Optimizaciones prematuras de escala.

## Stack

- Frontend: React.
- Backend: Python + FastAPI.
- Database: PostgreSQL.
- Control de versiones: Git/GitHub.

La prioridad es mantener el sistema simple, explicable y facil de defender tecnicamente. Las abstracciones deben existir solo donde reducen acoplamiento real, especialmente alrededor de la fuente de datos del Auction House.

## Documentacion

- [Arquitectura](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)

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
http://127.0.0.1:5173/
```

El frontend muestra una pantalla tecnica minima y comprueba que el backend este disponible. El backend ya importa y consulta snapshots simulados de Fase 2; el frontend todavia no incluye una UI de Auction House.

### 5. Validaciones utiles

```powershell
# Backend vivo
Invoke-RestMethod http://127.0.0.1:8000/health

# Conexion backend -> PostgreSQL
Invoke-RestMethod http://127.0.0.1:8000/health/db

# Frontend compila
cd frontend
npm run build
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

Implementación con validación real de Forever todavía pendiente. No incluye Market Intelligence.
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

Para un archivo real, usar una identidad estable de cuenta/export y región explícita:

```powershell
.\.venv\Scripts\python.exe scripts\import_auctionator.py C:\ruta\Auctionator.lua --source-id cuenta-local-reloj-original --region wow-forever --dataset real
# Si la clave es realm/facción, agregar --market-map C:\ruta\markets.json
# Ejemplo de ese JSON: { "Everlook Alliance": "PvE" }, sólo si el ruleset está confirmado.
# Sólo para serialización LibCBOR verificada: --allow-libcbor
# Sólo con base temporal comprobada: --scan-day-zero "2020-01-01T00:00:00Z"
```

Sin base temporal se guarda el índice del addon; no se asume UTC ni la fecha de
importación como observación. No se anuncia soporte para el codec nativo del cliente.
El parser de literales Lua/LibCBOR aplica límites de tamaño/profundidad y no ejecuta código.

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

## Principio guia

Primero construir una base pequena que permita aprender con datos reales o simulados. Despues extender. El proyecto debe poder crecer hacia features de personajes, guilds o profesiones, pero la primera version debe concentrarse en el diferencial: inteligencia de mercado para el Auction House.
