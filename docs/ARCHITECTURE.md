# Arquitectura

## Vision general

WoW Forever Companion se organiza alrededor de un nucleo de Market Intelligence para el Auction House. La aplicacion debe poder cambiar la fuente de datos sin reescribir el analisis, la base de datos ni la experiencia de usuario.

Arquitectura propuesta:

```text
Auction House data source
        |
        v
Ingestion adapter
        |
        v
Normalized full snapshot / partial evidence
        |
        v
Backend API + domain services
        |
        v
PostgreSQL
        |
        v
React UI / AI assistant tools
```

La parte más importante es el límite entre adaptadores y contratos normalizados.
Snapshots completos y evidencia parcial tienen contratos independientes:
Auctionator no debe fabricar campos de un snapshot completo. Market Intelligence
consume series tipadas cuya semántica, fuente y base temporal se mantienen visibles.

## Decisiones iniciales

- El backend sera la fuente de verdad del dominio.
- PostgreSQL guardara snapshots historicos y metricas derivables.
- React consumira endpoints del backend; no debe conocer detalles de la fuente de datos.
- La ingestion sera modular: cada fuente tendra un adaptador propio.
- Las oportunidades de mercado empezaran como reglas simples y auditables.
- El asistente de IA no consultara datos crudos directamente; usara herramientas del backend con consultas controladas.

## Decisiones tecnicas de Fase 1

- El frontend se inicializa con React, TypeScript y Vite para mantener una configuracion moderna y pequena.
- El backend se inicializa con FastAPI, `pydantic-settings` para configuracion y `psycopg` para comprobar conexion con PostgreSQL.
- PostgreSQL se prepara para desarrollo local mediante `compose.yaml`, sin dockerizar frontend ni backend.
- La configuracion local usa archivos `.env` ignorados por Git y archivos `.env.example` versionables.
- La Fase 1 establecio la conexion basica; las tablas de dominio se incorporaron en Fase 2.
- La comunicacion minima frontend -> backend usa `GET /health`.
- La comprobacion minima backend -> PostgreSQL usa `GET /health/db`.

## Decisiones tecnicas de Fase 2

- Las migraciones usan SQL plano y un runner minimo con `psycopg`; no hay ORM ni Alembic todavia.
- `external_item_id` es el identificador estable global de item para Fase 2.
- Los snapshots duplicados se detectan por `source_hash` o por `realm_id`, `source_type` y `captured_at`.
- Si un item conserva `external_item_id` pero cambia `name` o `quality`, se actualiza el catalogo actual sin duplicar el item ni reescribir historicos.
- `POST /imports/snapshots` recibe JSON directo; no hay multipart/upload HTTP todavia.
- `import_runs` registra intentos que alcanzaron ingestion/persistencia, completados, duplicados o fallidos. Errores previos de HTTP parsing, Pydantic o lectura/parseo de FileAdapter quedan fuera de esta trazabilidad.
- Los precios se almacenan como enteros en copper.
- La persistencia de Fase 2 guarda agregados por item dentro de cada snapshot, no subastas individuales.

### Integridad, transacciones e identidad

Tablas implementadas: `schema_migrations`, `realms`, `items`, `auction_snapshots`, `auction_snapshot_items`, `import_runs`. Las PK/FK, checks y restricciones de unicidad viven en PostgreSQL; Pydantic valida primero el contrato de entrada.

Los cinco campos numericos de los agregados exigen enteros estrictos en `0..2147483647`. Ambos timestamps de entrada requieren timezone y se normalizan a UTC. El adapter no persiste datos ni calcula metricas.

La identidad de realm es `(name, region)`, con `region` nullable y unicidad mediante `COALESCE(region, '')`. Pydantic recorta region y convierte vacios a NULL. La migracion incremental `002_normalize_realm_regions.sql` normaliza datos previos y agrega un check que rechaza regiones vacias o no recortadas en PostgreSQL. Si normalizar datos existentes produce un conflicto de unicidad, la migracion falla y se revierte; no fusiona mercados silenciosamente.

El servicio obtiene/crea realms con `INSERT ... ON CONFLICT DO NOTHING` y lookup con la misma semantica del indice. Los snapshots usan tambien `ON CONFLICT DO NOTHING`; tras un conflicto concurrente, una nueva consulta bajo READ COMMITTED recupera el ID original. Los constraints permanecen como garantia final. Items, snapshot, agregados y registro completed/duplicate se confirman dentro de la misma transaccion. Un fallo de PostgreSQL revierte la importacion antes de intentar registrar failed con otra conexion/transaccion; si la base no responde, ese registro puede no existir.

SHA-256 representa los bytes de un archivo, o JSON serializado con claves ordenadas en HTTP; no es un hash universal del modelo normalizado. La identidad relacional cubre reimportaciones equivalentes con distinta serializacion. El primer snapshot importado prevalece: un payload posterior con igual identidad se considera duplicate y no reescribe precios.

Los endpoints existentes de snapshots e historicos exponen `realm_id`, nombre y region. Aceptan `realm_id` o nombre/region; rechazan nombres ambiguos con 422 y selectores inexistentes con 404. Region vacia en el filtro identifica NULL. El historico sin selector requiere un unico realm, evitando mezclar mercados; listar snapshots sin filtro conserva la identidad de cada registro.

### Migraciones y tests

Las migraciones SQL pendientes y su registro en `schema_migrations` son transaccionales. El runner es local y se ejecuta por un solo operador a la vez; no coordina ejecuciones paralelas. Los cambios posteriores usan nuevas migraciones, sin modificar una ya aplicada.

La integracion usa una base separada configurada explicitamente con `TEST_DATABASE_URL`, cuyo nombre termina en `_test` y difiere del de desarrollo. `scripts/setup_test_database.py` la prepara y migra. Cada test crea un esquema propio y configura `search_path` exclusivamente alli, migra ese esquema y lo elimina al finalizar. No hay limpieza por nombres o prefijos de items en desarrollo. La suite incluye concurrencia real con dos conexiones/solicitudes, mercados homonimos, lectura fisica de JSON, limites numericos, timezone y rollback intermedio.

## Decisiones técnicas de Fase 2.5

Auctionator aporta evidencia parcial, por lo que no se fuerza al contrato de
snapshots completos ni se calculan campos faltantes. Flujo agregado:

```text
SavedVariables Lua / LibCBOR confirmado
  -> lector de literales con límites
  -> AuctionatorAdapter (sin PostgreSQL)
  -> NativeExportEvidence + PartialBatch / PartialObservation (Pydantic)
  -> PartialIngestionService
  -> partial_markets / partial_items / partial_observations / partial_import_runs
  -> partial_exports / partial_export_facts / partial_export_imports
  -> /partial/markets, /partial/items, /partial/history, /partial/imports
```

`003_create_partial_observations.sql` agrega cuatro tablas; no modifica las tablas
de Fase 2. El catálogo parcial conserva item_key, ID y tipo; nombres/calidad
permanecen desconocidos. Pet species, gear level y sufijos tienen claves propias
y no se fusionan con el item básico. Región y source_id son contexto explícito
del operador. El dataset forma parte de la identidad del mercado y separa real de
simulado aun con la misma región/clave. Las claves realm/facción necesitan mapping
de ruleset confirmado y se preservan literalmente.

Una observación contiene una estadística y un valor entero, un scan_day opcional,
mercado/item y procedencia. Se representa mínimo diario almacenado, mayor mínimo
diario, disponibilidad máxima o último mínimo. Nunca promedio, ventas o
auction_count. Días y disponibilidad ausentes no se completan. La base temporal
puede ser desconocida; la fecha de importación no se convierte en fecha del scan.

La identidad diaria incluye mercado, item con variante, fuente, base temporal,
índice diario y estadística. Una lectura importada extiende los extremos por
LEAST/GREATEST como acumulación de la aplicación; un archivo viejo no los reduce. El último mínimo
no tiene fecha y se conserva por hash del estado normalizado del export. El hash
normalizado tolera orden/whitespace/transporte; cada intento además guarda el hash
de origen, versión y referencia. Las observaciones enlazan primer/último import
que cambió su valor. Los intentos sin cambios ni evidencia nueva registran duplicate; los fallos SQL
revierten el batch antes de intentar registrar failed con una nueva transacción.
El hardening adquiere primero todos los locks de items en orden global de item_key,
luego todos los mercados, evidencia nativa, observaciones y vínculo de recepción. Los locks cubren también
estadísticas todavía ausentes, de modo que dos batches parciales concurrentes no
pueden confirmar un par mínimo/máximo contradictorio. Se valida la combinación
persistida antes de commit y un fallo revierte el batch completo. Sólo deadlocks
40P01 admiten dos retries de transacción entera, sin registrar failed intermedios.

La 004 separa tres niveles: hechos nativos inmutables l/h/a/m por export; extremos
acumulados en 003; proyección explícita de GetPriceHistory por export_id. No hay
métricas de Fase 3. Un l ausente no se materializa como hecho: sólo la proyección
usa h y marca minimum_origin=h_fallback. Identidades originales, presencia de
campos y tablas vacías se preservan en hechos/manifest; las identidades de hechos
son copias independientes de cambios posteriores del catálogo.

El hash canónico v1 incluye contexto, estructura y hechos, excluyendo recepción,
ruta, serialización y IDs locales. No reemplaza el hash normalizado anterior de m.
Un estado idéntico comparte export_id con distintos vínculos a import_runs; esto
no demuestra que sea el mismo evento físico de exportación. No se asigna orden
de observación a archivos recibidos tarde. La 004 deja vacías sus tablas y no
atribuye evidencia ficticia a los 16.628 registros anteriores.

Construcción, sellado, acumulación y vínculo confirman en una transacción. Dos
funciones guardan cabecera e hijos frente a cambios, borrados, TRUNCATE y anexado
a hechos sellados; un constraint trigger diferido exige sellado y primer vínculo
al commit. Conteo y coherencia l/h/a se comprueban al sellar. La validación del
manifest, identidades y proyección pertenece al contrato/servicio, sin triggers
de estructura JSON ni métricas. SQL de administradores que desactiven las
protecciones queda fuera de la garantía. Ver [detalle](PHASE_25_EXPORT_EVIDENCE.md).

Los nuevos tests PostgreSQL reutilizan la base `_test` y un esquema aleatorio por
test. Las tablas, datos y secuencias de desarrollo no se usan para limpiar tests.
La importación simulada en desarrollo es una acción de validación explícita y
permanece en tablas/mercados separados de snapshots y de evidencia real.

El simulador usa PRNG local con seed fija y reproduce actualización de campos del
addon para tres lecturas sintéticas por día observado. Exporta un Lua y dos JSON
auxiliares; no genera subastas individuales. Items, precios y disponibilidades son
explícitamente ficticios/simulados. No agrega análisis ni señales de Fase 3.

Ver [evidencia y límites de Auctionator 340](AUCTIONATOR_340.md): siguen pendientes
un SavedVariables real, selección de ruta AH de Forever y el codec nativo de
C_EncodingUtil. Sólo LibCBOR inspeccionado se selecciona explícitamente para strings
serializados. No se carga ni ejecuta el addon o el Lua importado.

ModernAH divide buyout por cantidad y admite fracciones: se mantiene rechazo
explícito, sin escala o redondeo inventados. Los decimales Lua se leen como Decimal
y se rechazan antes de persistencia. Los límites de parsing son compartidos con
todos los decoders CBOR; el límite de observaciones se comprueba durante construcción.
La detección del marcador simulado tolera BOM/whitespace, sin garantizar autenticidad.

## Modulos principales

### Frontend

Responsabilidades:

- Explorar items.
- Mostrar metricas historicas basicas.
- Mostrar oportunidades detectadas.
- Permitir subir o seleccionar datasets simulados en etapas tempranas.
- Consultar al asistente cuando exista la capa de herramientas.

No debe:

- Parsear formatos especificos de addons.
- Implementar reglas de negocio criticas.
- Calcular metricas historicas como fuente de verdad.

### Backend API

Responsabilidades:

- Exponer endpoints para items, snapshots, metricas y oportunidades.
- Validar datos antes de persistirlos.
- Orquestar servicios de ingestion y analisis.
- Exponer herramientas seguras para el asistente de IA.

### Ingestion

Responsabilidades:

- Recibir datos desde una fuente concreta.
- Parsear el formato original.
- Normalizar los datos al contrato interno.
- Registrar errores de importacion y datos incompletos.

Adaptadores previstos:

- `simulated`: datos generados para desarrollo.
- `file_import`: CSV/JSON controlado.
- `auctionator`: adapter 340 implementado para los formatos verificados; compatibilidad con SavedVariables auténticos pendiente.
- `api`: futuro adaptador si existe una API util.

### Market Intelligence

Responsabilidades:

- Calcular estadisticas por item y ventana temporal.
- Detectar tendencias simples.
- Medir dispersión de niveles de mínimos guardados, no volatilidad de retornos.
- Describir disponibilidad máxima, cobertura, muestra y procedencia.
- Evaluar señales históricas explicables en Fase 3B.1; ranking y oportunidades globales pendientes.
- Calcular márgenes de crafting solamente en etapas futuras con fuentes adicionales.

En v0.1 se priorizan reglas explicables sobre modelos avanzados.

### AI tools

Responsabilidades futuras:

- Permitir preguntas sobre nuestros datos.
- Traducir consultas del usuario en llamadas controladas al backend.
- Responder con evidencia: item, rango temporal, snapshot y metricas utilizadas.

Ejemplos futuros:

- "Que items bajaron fuerte en las ultimas 24 horas?"
- "Que materiales tienen mayor volatilidad esta semana?"
- "Hay oportunidades de compra por debajo de la media historica?"

## Estructura propuesta del repositorio

Estructura objetivo para cuando se inicialice el proyecto:

```text
wow-forever-companion/
  README.md
  docs/
    ARCHITECTURE.md
    ROADMAP.md
  compose.yaml
  backend/
    app/
      api/
      core/
      db/
      ingestion/
        adapters/
      market/
      ai_tools/
    tests/
  frontend/
    src/
      components/
      pages/
      api/
      features/
        market/
  data/
    samples/
    imports/
  scripts/
```

Responsabilidades previstas:

- `backend/app/api`: endpoints HTTP.
- `backend/app/core`: configuracion y utilidades compartidas.
- `backend/app/db`: modelos, migraciones y acceso a datos.
- `backend/app/ingestion`: contrato normalizado y flujo de importacion.
- `backend/app/ingestion/adapters`: adaptadores por fuente de datos.
- `backend/app/market`: calculo de metricas y oportunidades.
- `backend/app/ai_tools`: herramientas controladas para consultas asistidas por IA.
- `frontend/src/features/market`: pantallas y estado de Market Intelligence.
- `data/samples`: datasets simulados versionables.
- `data/imports`: archivos locales importados, normalmente no versionables.
- `scripts`: comandos auxiliares simples.
- `compose.yaml`: PostgreSQL local para desarrollo.

La Fase 1 implementó el esqueleto técnico. Fases 2/2.5 implementan ingestión,
persistencia y consultas históricas. `market` implementa Fases 3A y 3B.1;
`ai_tools` permanece vacío.

## Modelo de datos inicial

Modelo conceptual para v0.1:

### `realms`

Representa el servidor o mercado observado.

Campos iniciales:

- `id`
- `name`
- `region`
- `created_at`

### `items`

Catalogo normalizado de items.

Campos iniciales:

- `id`
- `external_item_id`
- `name`
- `quality`
- `item_class`
- `item_subclass`
- `created_at`

`external_item_id` debe ser estable si la fuente lo provee. Si no existe, se debera definir una estrategia temporal y marcarla como pendiente de validacion.

### `auction_snapshots`

Representa una captura del Auction House para un realm y una fuente.

Campos iniciales:

- `id`
- `realm_id`
- `source_type`
- `source_version`
- `captured_at`
- `imported_at`
- `raw_reference`

### `auction_snapshot_items`

Agregado por item dentro de un snapshot. En v0.1 conviene guardar datos agregados antes que cada subasta individual, salvo que la fuente real obligue a conservar granularidad completa.

Campos iniciales:

- `id`
- `snapshot_id`
- `item_id`
- `min_buyout`
- `avg_buyout`
- `max_buyout`
- `quantity_total`
- `auction_count`

### Métricas de Fase 3A

Se calculan bajo demanda; no existe una tabla `market_metrics` ni una migración
de análisis. Identidad: mercado (región/dataset), item/variante, source_id,
source_type, temporal_basis y modo; `export_id` adicional en modo export.
No se incluyen `volume_total`, promedio de subastas ni máximo global.
Contratos, fórmulas y validación en [PHASE_3A_VALIDATION.md](PHASE_3A_VALIDATION.md).

### `market_opportunities`

Propuesta futura de persistencia de oportunidades, no implementada. Fase 3B.1
evalúa señales bajo demanda sin esta tabla, scores ni ranking entre mercados.

Campos iniciales:

- `id`
- `realm_id`
- `item_id`
- `detected_at`
- `opportunity_type`
- `score`
- `reason`
- `reference_price`
- `current_price`
- `status`

## Market Intelligence implementado en Fase 3A

```text
/market/series, /market/metrics
  -> market/contracts.py (identidades y ventanas explícitas)
  -> market/service.py (READ ONLY, REPEATABLE READ)
  -> market/repository.py (SQL parametrizado; contextos/versiones/procedencia)
  -> market/windows.py (eje del mercado, máximo 366 posiciones)
  -> market/series.py (valores, ausencias, l/h_fallback y referencias)
  -> market/statistics.py (funciones puras, Decimal precisión 40)
  -> market/quality.py (cobertura y advertencias, sin score de confianza)
  -> contratos de respuesta para React y futuras herramientas
```

`market/errors.py` separa selección inexistente (404), incoherencia (409) y
ventana imposible (422); errores PostgreSQL se exponen como 503 sin detalles de
credenciales. `api/market.py` adapta HTTP; no calcula métricas ni hace imports.

Fase 3B.1 agrega `GET /market/signals` con los mismos selectores y ventanas.
`signal_service.py` obtiene exactamente un resultado de `MarketAnalysisService`
y lo entrega a `signals.py`, evaluador puro sin SQL. `signal_contracts.py`
valida parámetros y publica resultados versionados `3b1-v1`. Se reutilizan
pendiente, cambios, cobertura, calidad y procedencia de 3A; la referencia de
desviación reutiliza su mediana sobre los puntos anteriores al último.
Muestra mínima, cobertura solicitada y del intervalo de índices, distancia al
ancla y políticas opcionales de origen/base temporal condicionan las señales.
Regla, suficiencia de evidencia y advertencias se exponen por separado.
No se persisten resultados ni se convierten en ventas, predicciones o compras
confirmadas. Fórmulas, defaults y validación:
[PHASE_3B1_VALIDATION.md](PHASE_3B1_VALIDATION.md).

Los dos proveedores son independientes. `accumulated` lee 003 y declara origen
del mínimo desconocido. `export` lee hechos de un único estado sellado, usa
identidades copiadas/manifest y proyecta l o h; un a ausente no se completa. Los
vínculos de recepción no se unen a los puntos: reimports no multiplican muestras.
La 004 vacía no impide analizar 003. Ningún proveedor consulta snapshots de Fase 2.

Cada punto representa una posición de la ventana. En rangos se mantienen posiciones
sin evidencia; en buckets observados se conservan los índices originales. Las
métricas excluyen nulls y `m`, retienen ceros explícitos y muestran sus propios
extremos observados. La pendiente usa scan_day, no orden de filas/recepciones.
Base conocida permite convertir intervalos nominales de 86400 segundos, nunca
timestamps de scans individuales. Ventanas calendario requieren base comprobada
y fechas representables; su ancla no es necesariamente hoy.

Las respuestas contienen `analysis_version=3a-v1`, contexto, ventana resuelta,
puntos, métricas con estado/unidad/muestra, cobertura, calidad y procedencia.
Los valores fuente son enteros y los derivados strings Decimal en notación fija,
incluidos cambios negativos. El esquema OpenAPI conserva el patrón decimal sin
exponentes. El contexto de cálculo fija precisión 40 y ROUND_HALF_EVEN sin heredar
traps externos. No se redondea silenciosamente a copper ni se devuelve NaN/Infinity.
Mediana/promedio dan el mismo peso a cada bucket con precio. Disponibilidad no es
volumen transaccionado. Dispersión de niveles no es volatilidad de retornos.

## Dashboard implementado en Fases 4A y 4A.1

React + TypeScript + Vite consulta `GET /partial/markets`, `GET /partial/items`,
`GET /market/series` y `GET /market/metrics`. El flujo principal es mercado →
item → resultados automáticos; las opciones avanzadas conservan los filtros
compatibles de dataset, fuente, modo, base temporal y ventana. Un único contexto
accumulated compatible puede elegirse automáticamente; los contextos ambiguos
y todas las exportaciones requieren selección explícita, sin ordenar observaciones
por fecha de recepción. La ventana inicial usa 30 buckets observados del mercado.

El acceso HTTP y la validación de respuestas viven en `frontend/src/api`; la
selección de contexto, transformación y presentación en `frontend/src/features/market`.
Las métricas provienen de FastAPI, sin duplicar cálculos estadísticos en React.
Las peticiones canceladas no pueden publicar respuestas obsoletas. La URL pública
del backend se configura mediante `VITE_API_BASE_URL`, sin secretos en el bundle.

Los Decimal conservan sus strings y la conversión de moneda usa BigInt. El gráfico
SVG conserva huecos y ceros, permite inspección con pointer y teclado y ofrece
tabla accesible. La interfaz muestra mínimos históricos guardados, disponibilidad
máxima, cobertura, advertencias y SIMULATED cuando corresponde; no los interpreta
como precios actuales ni ventas. Los índices sin base verificada no se muestran
como fechas calendario. No se implementan oportunidades, carga de archivos ni IA
en estas fases. La validación con SavedVariables auténticos de Forever sigue pendiente.

Ver [validación de 4A](PHASE_4A_VALIDATION.md) y
[simplificación y correcciones de 4A.1](PHASE_4A1_VALIDATION.md).

## Captura local manual de Fase 5A.1

`backend/app/local_capture` y `backend/scripts/capture_auctionator.py` incorporan
el núcleo local sin observador automático ni nuevas dependencias. No importan
configuración de la aplicación, persistencia ni servicios HTTP. Reutilizan
`AuctionatorAdapter.decode_bytes()` para validar evidencia nativa sin fabricar
región, dataset o identidad de importación. `load_bytes()` mantiene los contratos
anteriores del importador.

`local_capture/decoder.py` admite precios enteros locales de 0 a `2**63-1`,
manteniendo cantidades e índices en 0 a `2**31-1`. Los modelos de ingestión
conservan el límite de 32 bits y se revalidan al construir un batch. Antes de
sincronizar deberá resolverse explícitamente la compatibilidad entre precios
locales de 64 bits, contratos de API y almacenamiento; 5A.1 no amplía ingestión.

```text
Ruta SavedVariables -> lectura estable acotada -> validación Lua/CBOR existente
  -> SHA-256 de bytes + hashes canónicos de evidencia por mercado
  -> pending/<hash>/{Auctionator.lua,metadata.json}
  -> verificación + publicación por rename -> captures/<hash>/
```

El archivo original y el metadato son copias independientes de sólo lectura,
fuera del proyecto por defecto y obligatoriamente fuera de él al configurar el
destino. No se usa sólo `.gitignore` como protección. Un lock de SO serializa
publicaciones; los fallos posteriores conservan evidencia pendiente recuperable.
Cada hash completo distinto conserva su original, incluso si el mercado ya era
conocido. Hashes canónicos por mercado permiten separar evidencia de archivo y
novedad de estado sin crear puntos económicos desde cambios de configuración.
La hora de adquisición UTC no es hora de scan; los buckets siguen siendo índices.

5A.2 agrega `local_capture/watcher.py` y `scripts/watch_auctionator.py`: polling
de una ruta elegida, SHA-256 por inspección, espera de estabilidad y reintentos
con pausa de recuperación. El observador no parsea Lua ni decide deduplicación:
invoca `capture_file()` con un hash esperado restrictivo para rechazar cambios
entre observación y captura. Un reinicio reutiliza el archivo persistido de 5A.1.
Origen de juego, simulación con copias y archivo de capturas tienen ubicaciones
independientes; no se fija una ruta personal ni se descubre el cliente recorriendo
discos. CLI en primer plano, sin servicio ni conexiones con PostgreSQL/3A/3B.
El polling puede perder estados intermedios y la estabilidad física no confirma
el fin de un escaneo del juego. La primera prueba con un `/reload` real de
WoW Forever sigue pendiente; la validación realizada usó simulaciones externas.

Contrato y archivado: [PHASE_5A1_LOCAL_CAPTURE.md](PHASE_5A1_LOCAL_CAPTURE.md).
Observación, configuración y límites: [PHASE_5A2_LOCAL_WATCHER.md](PHASE_5A2_LOCAL_WATCHER.md).

5B.1 agrega `local_capture/readiness.py`, un contrato de contexto y evaluación
offline que recalcula hashes y exige procedencia e identidad de mercado explícitas.
Su resultado siempre es evidencia local, sin habilitar un escritor. Precios por
encima de `2**31-1` bloquean la captura completa para ingestión; se mantienen exactos
en el archivo de 64 bits. El servicio revalida todos los batches desde diccionarios
antes de conectar, incluyendo 340 y subclases locales. No se amplían SQL ni 3A/3B.
La auditoría identificó que faltaban adquisición/hashes locales y una identidad
completa para claves genéricas; 5B.1.1 resuelve ambos puntos como se explica abajo.
No se introduce otra tabla de hechos.
Auditoría, alternativas y pruebas: [PHASE_5B1_INGESTION_READINESS.md](PHASE_5B1_INGESTION_READINESS.md).

5B.1.1 implementa las decisiones aprobadas mediante `ingestion/local_lineage.py`
y la migración **006**. `partial_markets.economic_identity` identifica dataset,
región técnica, ámbito económico estable y alcance compartido/facción, separando
observador y clave nativa. La unicidad JSONB compara la identidad completa;
las filas legacy conservan NULL y su unicidad previa, sin backfill de procedencia.
`partial_exports` v2 comparte estados/hechos entre observadores; las attestaciones
de cada uno, adquisición y hashes completos quedan en `partial_capture_receipts`,
append-only y enlazada a run/export. La cabecera mantiene su primer observador.
006 también congela la procedencia del run que ya tiene una recepción local,
permitiendo sólo su finalización completed/duplicate con cero cambios en 003.
El nuevo flujo conserva hechos nativos, sin poblar el acumulado 003 ni alimentar
3A/3B. Datasets nuevos simulated/stress_test/launch no reinterpretan real legacy.
Toda escritura 341 exige binding local verificado, 005/006 y TrialDatabase;
quitar el binding no permite volver al importador anterior. La CLI 341 queda
bloqueada para importación hasta integrar el contrato completo; check-target
mantiene su comprobación de identidad sin escritura. 340 permanece compatible.
No hay sincronización, cambios del watcher ni importaciones auténticas. Detalles,
ejemplos y límites en la sección 9 del informe 5B.1.

## Contrato de snapshot completo de Fase 2

El adaptador de snapshots completos produce una estructura equivalente a:

```json
{
  "realm": "Example Realm",
  "source_type": "simulated",
  "source_version": "0.1",
  "captured_at": "2026-10-05T00:00:00Z",
  "items": [
    {
      "external_item_id": "12345",
      "name": "Copper Ore",
      "quality": "common",
      "min_buyout": 120,
      "avg_buyout": 150,
      "max_buyout": 220,
      "quantity_total": 430,
      "auction_count": 37
    }
  ]
}
```

Los precios deben guardarse como enteros en la unidad minima disponible, por ejemplo copper, para evitar errores de punto flotante.

## Flujo de ingestion

1. La fuente entrega un snapshot o export.
2. El adaptador correspondiente parsea el formato original.
3. El adaptador valida campos obligatorios.
4. El adaptador convierte los datos al contrato normalizado.
5. El backend persiste `realms`, `items`, `auction_snapshots` y `auction_snapshot_items`.
6. Los endpoints de consulta leen items, snapshots, importaciones e historicos desde PostgreSQL.
7. En fases posteriores, Market Intelligence podra calcular metricas y oportunidades sobre estos historicos.

## Reglas iniciales de oportunidades

Para v0.1, las reglas deben ser simples:

- Precio actual por debajo de un porcentaje configurable de la media historica.
- Evidencia y cobertura suficientes; disponibilidad máxima no demuestra ventas o liquidez.
- Caida brusca respecto de snapshots recientes.
- Alta volatilidad marcada como riesgo, no necesariamente como oportunidad.

Cada oportunidad debe incluir una razon legible para poder defenderla.

## Riesgos tecnicos

### Fuente de datos del Auction House

Es el mayor riesgo del proyecto. Todavia no sabemos si existira API, si un addon exportara datos suficientes, que granularidad tendremos ni con que frecuencia podremos actualizar.

Mitigacion:

- Disenar adaptadores intercambiables.
- Trabajar primero con contrato normalizado.
- Mantener datasets simulados.
- Documentar cada supuesto de la fuente real.

### Identidad de items

Si no hay IDs estables, comparar historicos puede ser fragil.

Mitigacion:

- Preferir `external_item_id` cuando exista.
- Evitar depender solo del nombre.
- Registrar la fuente y version del dato.

### Calidad y frecuencia de snapshots

Snapshots incompletos o poco frecuentes pueden producir metricas enganadoras.

Mitigacion:

- Guardar `captured_at` solo cuando la fuente lo aporta; `imported_at` es recepción.
- Mostrar disponibilidad máxima, buckets con dato, cobertura y procedencia.
- No generar oportunidades cuando la muestra sea insuficiente.

### Complejidad prematura

El proyecto puede crecer hacia muchas areas de WoW.

Mitigacion:

- Mantener v0.1 centrada en Market Intelligence.
- Posponer personajes, guilds, raids y gear planning.
- Evitar microservicios y pipelines complejos al inicio.

## Cosas que no deberiamos construir todavia

- Integraciones definitivas con addons sin validar formato real.
- Prediccion avanzada de precios.
- Optimizacion automatica de trading.
- Sistema completo de profesiones.
- Gestion de personajes.
- Guild roster.
- Raid planner.
- Gear planner.
- Autenticacion compleja.
- Multi-tenant o roles avanzados.
- Infraestructura cloud elaborada.
