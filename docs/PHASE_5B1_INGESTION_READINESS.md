# Fase 5B.1: preparación segura de la ingestión local

**Cierre de 5B.1:** la auditoría final se registra en la sección 10. Las decisiones
de identidad y linaje aprobadas por el
usuario se implementan en la [sección 9](#9-actualización-5b11-identidad-y-linaje-persistente).
Las secciones 1–8 conservan el diagnóstico y los resultados de 5B.1 anteriores
a esa implementación; sus decisiones detenidas y ausencia de 006 son históricas.

Revisión: **24/10/2026**, America/Buenos_Aires. Base inspeccionada:
`e6145a814cf58b86e88270122da1dc121e2260a3`, rama `main`, inicialmente limpia.

**Veredicto: NEEDS DESIGN DECISION antes de 5B.2.** Las correcciones acotadas y
el contrato offline están preparados para revisión. No se implementó un
importador local: faltan decisiones de persistencia de identidad completa y
recepciones locales. Se elige **B: conservar precios extremos exclusivamente
como evidencia local**, con bloqueo explícito del archivo completo para ingestión.
No se amplían SQL, API, frontend ni los motores 3A/3B.

## 1. Flujo reconstruido y alcance de la auditoría

Se revisaron README, ARCHITECTURE, PHASE_5A1_LOCAL_CAPTURE,
PHASE_5A2_LOCAL_WATCHER, FIRST_REAL_AUCTIONATOR_VALIDATION y BETA_DATA_READINESS;
además, lectores, adaptadores, contratos, servicios, scripts, migraciones
001–005, consultas y pruebas relacionadas. Los resultados auténticos citados
pertenecen a esos informes anteriores. **En esta fase no se abrieron capturas
privadas, ni siquiera para una nueva validación offline.**

```text
Auctionator.lua elegido por el operador
  -> watcher: lectura estable, debounce, hash esperado
  -> capture_file: buffer acotado, CaptureAdapter.decode_bytes
  -> originales independientes + CaptureMetadata, fuera del proyecto
     [el flujo automático termina aquí]

Ruta de importación ya existente, independiente del watcher:
Lua -> AuctionatorAdapter.load/load_bytes
    -> PartialBatch (340) / Auctionator341Batch + NativeExportEvidence
    -> procedencia ligada a bytes y contexto para perfiles extendidos
    -> PartialIngestionService + TrialDatabase obligatorio para 341
    -> run, catálogo, mercados, export sellado, hechos, acumulado, vínculo
    -> PostgreSQL 003/004/005

Lectura analítica actual:
PostgreSQL -> MarketRepository -> series tipadas -> 3A -> 3B -> API -> React
             [contratos de lectura todavía limitados a 340]
```

El archivador no importa settings ni servicios SQL/HTTP. `decode_bytes()`
valida hechos sin fabricar región, dataset o fuente. `load_bytes()` vuelve a
construir observaciones desde diccionarios con el contrato SQL de 32 bits;
usar `CaptureAdapter.load_bytes()` tampoco habilita valores más amplios.

La CLI ordinaria importa 340 a `DATABASE_URL`; la extendida exige `--trial`,
selección explícita de destino y `--provenance-file`. HTTP sólo recibe
`PartialBatch` 340 normalizado, sin Lua, archivo local ni evidencia nativa.
Los scripts `import_snapshot`/`import_samples` pertenecen al contrato independiente
de snapshots completos. `migrate.py` conserva su default de desarrollo y **no
debe usarse como preparación automática de capturas**.

### Qué se conserva y qué no llega a SQL

| Nivel | Conservación | Límites/pérdidas |
| --- | --- | --- |
| Archivo 5A | Todos los bytes, SHA-256, tamaño, copia independiente, adquisición UTC | No autentica cliente, origen o reloj; polling puede perder estados intermedios |
| Metadato 5A | Hash económico global y por mercado, claves nativas, estructura/conteos, codec seleccionado, pendientes | `captured_at` es adquisición; `origin_id` opcional no es automáticamente `source_id` |
| Adaptador | l/h/a/m presentes, variantes completas, claves originales, tablas vacías en manifest, proyección con fallback explícito | Ignora otros globals como datos económicos; no conserva sus bytes en SQL |
| 003 | Extremos diarios acumulados y estados m sin fecha, referencias al primer/último import que cambió el valor | Reemplazar un extremo no conserva en esta tabla cada versión anterior |
| 004 | Cada estado contextual sellado, hechos nativos y recepciones separadas | No guarda el original Lua; `raw_reference` es una referencia, no un backup |
| 005 | Procedencia en manifest sellado, versión y transporte extendidos, stress_test separado | No agrega adquisición local, hashes económicos de 5A, reino/facción ni precios BIGINT |
| 3A/3B | Un punto por índice compatible; procedencia y métricas bajo demanda | No son scans completos ni una cronología de recepciones; 341 aún se rechaza |

No existe una unión persistida entre `CaptureMetadata` y `partial_import_runs`.
La ruta del Lua en `raw_reference` no conserva por sí sola hora de adquisición,
hash económico local, contexto completo ni garantía de disponibilidad del original.

## 2. Límites numéricos comprobados

| Dominio | Python/Pydantic | PostgreSQL / consumidores |
| --- | --- | --- |
| Precio local l/h/m | Entero estricto `0..9223372036854775807` (`2**63-1`) | Sólo evidencia local; no hay una columna monetaria BIGINT en 001–005 |
| Precio parcial a persistir | `PartialObservation.value`, `NativeFact.value`: `0..2147483647` | `partial_observations.value` y `partial_export_facts.value`: INTEGER, CHECK >= 0 |
| Disponibilidad a | Entero estricto `0..2147483647` también en modelos locales | Mismas columnas INTEGER; no se amplía al ampliar precios locales |
| Índice nativo | `scan_day`: `0..2147483647`; texto original ASCII de hasta 10 dígitos | INTEGER, CHECK >= 0, COALESCE(scan_day,-1) en identidad; nunca una fecha civil |
| ID externo / species / gear level | Clave normalizada: ID positivo <= 2147483647; nivel `0..2147483647` | ID externo es TEXT; regex SQL de hasta 10 dígitos no sustituye el validador semántico Python |
| Variantes | Clave completa `ID`, `g:ID:nivel`, `gr:ID:sufijo`, `p:speciesID`; sufijo opaco acotado | item_key TEXT única; no se reduce la variante al ID externo |
| PK/FK internas | Selectores positivos hasta `2**63-1` | BIGSERIAL / BIGINT; son identidades, no precios ni cantidades |
| Conteos | Máximo 200.000 observaciones/hechos y presupuesto estructural; ventanas de hasta 366 posiciones | Conteos INTEGER; COUNT SQL devuelve bigint; índices/paginación conservan sus límites |
| Snapshot completo 001 | Cinco campos estrictos `0..2147483647` | Precios, quantity_total y auction_count INTEGER con checks; contrato separado |

El límite superior SQL de valores proviene del **tipo INTEGER**, además del
CHECK inferior. 005 no modifica esos tipos. No hay NUMERIC para estos precios.
Índices y unicidades usan identidades, campos y buckets; el precio no forma
parte de la clave de observación diaria ni de la clave de hecho dentro de un export.

### Conversiones, operaciones y serialización

- Los `int` Python no desbordan a 32/64 bits. Lua entero se lee con `int`, CBOR
  con `int.from_bytes`; CBOR unsigned llega a `2**64-1` antes de la validación
  de dominio. Un literal Lua tiene límite de 32 caracteres. Valores por encima
  de `2**63-1` se rechazan localmente, sin saturación ni wraparound.
- `type(value) is int` en el adaptador y campos Pydantic estrictos excluyen
  bool, float, strings numéricos y negativos. Los decimales Lua se conservan
  como Decimal hasta rechazarse; CBOR rechaza floats. No se usa `int(precio)`
  para hacer pasar fracciones ni se atribuye a esto soporte de todo ModernAH.
- El servicio pasa enteros como parámetros psycopg, sin casts de precio a
  float; acumula mediante LEAST/GREATEST. Los casts `::integer`/`integer[]`
  encontrados en consultas corresponden a índices de buckets, no a precios.
  La proyección SQL usa COALESCE/UNION; no calcula un promedio SQL monetario.
- `series.build_points` revalida filas con `PartialObservation`/`NativeFact`;
  `BucketPoint` también limita precios/disponibilidad a 32 bits.
- 3A usa Decimal con precisión 40 y contexto propio para cálculos derivados;
  3B reutiliza ese contexto. `exact_ols_terms` usa enteros Python y comparaciones
  racionales exactas. No se encontró overflow de enteros Python ni conversión
  monetaria a float en esos motores. Esto no elimina sus restricciones de
  entrada ni certifica una ampliación de dominio o precisión derivada.
- `SeriesContext` admite `source_version=340` y datasets real/simulated;
  el repositorio acumulado exige runs 340, el export exige `(340,8,1)`, y el
  lector de manifest exige exactamente version/markets, sin provenance.
  **Incluso precios 341 pequeños siguen siendo incompatibles con 3A/3B.**
- JSON Python y el archivado conservan dígitos enteros exactos y hashes
  completos. Un consumidor JavaScript sólo garantiza enteros exactos hasta
  `2**53-1`; JSON.parse puede perder precisión antes de validar. React exige
  Number.isSafeInteger, sus contratos aún excluyen stress_test/341 y sus
  monedas usan BigInt a partir del valor recibido. Eso no recupera dígitos
  previamente perdidos. Los derivados Decimal viajan como strings.

### Decisión B y alternativas

Se mantiene exactitud local de 64 bits y rechazo íntegro por encima de 32 bits
en ingestión. `assess_local_capture` señala `price_exceeds_persistence_int32`
y cuenta **hechos nativos de precio** afectados, sin filtrar items. Un único
precio incompatible deja toda la captura como evidencia. No se recorta ni
se omite m, h o l para importar el resto. Tampoco se recalcula su hash sobre
un subconjunto.

Ampliar sólo columnas a BIGINT (A) trasladaría el fallo a contratos de lectura,
versiones, manifests y JSON, sin habilitar un camino seguro de extremo a extremo.
NUMERIC, escalar copper, redondear, saturar o aceptar únicamente hasta el máximo
seguro de JavaScript serían cambios de contrato sin resolver esas brechas.
Separar almacenamiento extremo SQL de análisis es una alternativa futura,
pero requiere revisar transporte y lectores: no se agrega una segunda tabla
de hechos ni una migración especulativa para esta fase.

**No hay migración 006.** No se editaron 001–005 ni se ejecutó ningún runner.

## 3. Incompatibilidad reproducida y corrección del servicio

Pydantic confía por defecto en instancias ya construidas. Se reprodujo con un
`CaptureObservation(value=2**63-1)` pasado como instancia a un `PartialBatch`
340. El batch conservaba la subclase y su valor ampliado. Antes del cambio,
`PartialIngestionService.import_batch` sólo revalidaba el batch extendido;
un resultado 340 sin evidencia nativa alcanzaba el escritor. La demostración
usó un escritor mock: **cero conexiones y cero INSERT reales**.

Ahora el servicio reconstruye **todos** los batches desde diccionarios con su
tipo 340/341 y usa ese resultado validado. También usa la evidencia nativa
revalidada para persistencia. La validación ocurre antes de conectar, del bucle
de retries y del registro failed; los datos inválidos no consumen secuencias.
No se cambian locks, SQL, transacciones ni política de retries.

`CaptureProvenance.source_id` rechaza además placeholders exactos como unknown,
PENDIENTE o todo. El archivo local puede seguir guardarse sin una identidad de
importación: esa libertad no se convierte en un default para persistir.
Los contratos legacy de fuente y hashes de evidencia válida se conservan.

## 4. Contrato de procedencia preparado, sin escritor

Nuevo módulo: [local_capture/readiness.py](../backend/app/local_capture/readiness.py).
`LocalCaptureContext` es un **candidato de sidecar privado** para futuras
ejecuciones. No lo lee la CLI actual, no se escribe al archivo 5A y no se añade
al manifest sellado v1 de 004/005. No hay endpoint, sincronizador ni lote SQL nuevo.

Requiere explícitamente:

- `contract=local-capture-context-v1`.
- `provenance`: CaptureProvenance existente con formato **341**, source_id,
  región técnica, dataset/fase, hash de bytes, todos los mercados/rulesets y
  refs revisadas de región/mercado/origen. Launch conserva el mapeo existente
  **dataset=real, capture_phase=launch**; `launch` no es un nuevo valor SQL.
- `serialized_codec`: null para tablas Lua o cbor-definite, concordante con
  la selección archivada. El productor puede seguir unverified; no se inventa
  LibCBOR ni C_EncodingUtil por decodificar correctamente.
- `market_identities`: exactamente las claves nativas de provenance, sin
  renombrar PvP. Cada entrada tiene un realm con EvidenceClaim, faction
  explícita (claim o null), auction_house_scope realm/faction y su ref.
  Scope faction exige facción verificada; scope realm exige evidencia de
  alcance compartido. Región/reino/facción desconocidos no forman un contexto
  importable: la captura permanece íntegra en 5A.

Las refs y claims son attestaciones del operador: validar presencia y coherencia
**no autentica su contenido**. Ni el idioma, país, timezone, nombre PvP, alias
origin_id o build instalado completan región, facción o sesión de captura.
Reino o facción no se extraen de un nombre mediante heurísticas.

`assess_local_capture(raw, metadata, context)` es una función pura: recibe bytes
ya leídos, revalida modelos anidados, decodifica, recalcula todos los hashes de
5A y compara metadatos completos, conteos, estructura, reglas y codec. Contrasta
el SHA-256 completo de provenance y los mercados reales del buffer. Una selección
341 explícita puede completar un selector local null; un selector archivado 340
contradictorio se rechaza. El marcador SIMULATED no permite contexto auténtico.

La salida conserva CaptureMetadata y contexto completos, sin precios convertidos;
indica compatibilidad **numérica** y bloqueos. Siempre devuelve evidence_only,
import_enabled=false y analytics_enabled=false. Un resultado numéricamente
compatible no certifica esquema, destino, identidad global ni autorización.
No devuelve PartialAdapterResult ni llama a PartialIngestionService. El módulo
no carga settings, psycopg, app.db ni servicios de persistencia.

### Tiempos y hashes con responsabilidades distintas

| Dato | Representación actual / requisito futuro |
| --- | --- |
| Adquisición local | CaptureMetadata.captured_at UTC, preservado como adquisición; no se modifica al evaluar ni deduplicar |
| Importación | partial_import_runs.imported_at, recepción SQL con default now(); no se fabrica durante preflight |
| Hora nativa del scan | null; no está disponible en el formato soportado y no se sustituye por adquisición, mtime o importación |
| Bucket 2485 | Índice opaco, base temporal unknown hasta evidencia separada; no se agrega epoch al sidecar preparado |
| source_sha256 / capture_id | SHA-256 de bytes completos, conservados íntegros; cada serialización distinta mantiene su original |
| market_sha256 / state_sha256 por mercado | Evidencia nativa canónica 5A, independiente de región/dataset/fuente/recepción |
| native.state_hash(batch) | Estado contextual 004: contexto, estructura, hechos y attestaciones; no es el hash 5A |
| result.evidence_hash | Estado normalizado con contexto utilizado para m; no equivale a ningún timestamp ni al hash de bytes |

La hora local y el alias no se pueden autenticar recalculando el hash económico;
se preservan como metadatos declarados del archivo privado. No son una firma.

## 5. Garantías existentes e histórico de dos capturas del mismo bucket

003 ya separa mercados por `(region,market_key,dataset)` y diarios por mercado,
variante, source_id/type, base temporal, scan_day y estadística. Los extremos se
combinan con LEAST para mínimo y GREATEST para máximo/disponibilidad. m permanece
sin fecha y usa identidad de estado normalizado; no se asigna al último bucket.

004 ya separa exportaciones de observaciones acumuladas: estado canónico único,
hechos por export/mercado/item/bucket/campo y recepciones append-only. Sellado,
conteo/coherencia l/h/a, contexto run/export y primer vínculo diferido se protegen
con triggers. Un export sellado no se modifica, elimina, trunca ni recibe hechos
nuevos. El servicio contrasta manifest y todos los hechos si reutiliza un hash;
un hash coincidente no autoriza sustituir evidencia distinta. No reconstruye
exports anteriores a 004. SQL no autentica el origen ni valida por sí solo toda
la estructura del manifest: contratos y servicio siguen siendo necesarios.

005 amplía etiquetas/dataset/procedencia y añade un guard de transporte sin
quitar los anteriores. No garantiza identidad de reino/facción ni una recepción
local completa. Los tres hashes anteriores cumplen funciones distintas y no se
debe reutilizar uno como sustituto de los otros.

Para los dos archivos PvP del bucket 2485 descritos en 5A:

1. Conservar ambos originales y sus SHA-256: evidencia de archivo independiente.
2. Contenido económico distinto implica dos estados nativos, incluso en el mismo
   índice. En una futura importación válida, 004 puede conservar dos exports
   contextuales sellados. Contenido equivalente reutiliza export_id, con otro
   run/vínculo de recepción; nunca se duplica el hecho dentro del mismo export.
3. 003 mantiene un único conjunto de extremos por identidad diaria. Por ejemplo,
   dos h sin l de 100 y 200 producen proyecciones por export de 100 y 200; el
   acumulado retiene mínimo 100 y mayor mínimo 200. Reimportar o recibir tarde
   un archivo no crea otro día ni establece cuál fue el último scan.
4. Son dos evidencias de estado, **no dos puntos temporales independientes**
   para tendencia. Por item/contexto hay un solo bucket 2485; m se excluye de
   métricas temporales. Recepciones no se unen a puntos para multiplicar muestras.

La disponibilidad máxima no es volumen vendido, número de subastas ni liquidez.
Más items no significan más posiciones históricas. Estrés y lanzamiento mantienen
mercados y estados separados; cambiar de fase no prueba una evolución de precios
de una misma economía. No se calculan predicciones ni se rebajan mínimos de muestra.

## 6. Decisiones de diseño detenidas para revisión

**Identidad completa:** dos reinos/facciones con igual región, dataset y clave
genérica PvP colisionarían en partial_markets. source_id separa observaciones,
pero no corrige la identidad global del mercado. El manifest v1 actual tampoco
incluye los nuevos MarketIdentity: cambiar sólo ese sidecar no cambia el hash
contextual 004. Una regresión sintética demuestra esta limitación y verifica que
el resultado siga bloqueado. No se reescriben claves ni se inventan regiones
compuestas como solución. Falta acordar una dimensión estable de alcance de
mercado y su representación/versionado, compatible con filas existentes sin
asignarles automáticamente un reino/facción no probado.

**Recepciones locales:** adquisición y hashes 5A pertenecen a cada captura/recepción,
no al estado económico compartido. Meterlos en structure_manifest rompería la
reutilización de estados equivalentes; editar un export existente violaría el
sellado. Revisar primero una extensión aditiva de partial_import_runs o un vínculo
append-only de recepción local, con idempotencia por captura **y contexto**,
sin crear otro almacén de hechos económicos. No se implementa ninguna alternativa.

**Lectura 341:** requiere una revisión separada de formatos/manifest/procedencia,
datasets y transporte exacto de valores, aun manteniendo los conceptos de 3A/3B.
No se quitan guards de versiones ni se envían datos auténticos al dashboard.

La política numérica B permite revisar estas decisiones sin una migración de
precios prematura. Una futura ampliación requerirá migración nueva transaccional,
comprobación de checks/lectores y pruebas exclusivamente en laboratorio aislado;
no puede editarse una migración publicada o backfillear identidad por suposición.

## 7. Validación de esta entrega

Pruebas nuevas: [test_local_ingestion_readiness.py](../backend/tests/test_local_ingestion_readiness.py).
Fixtures exclusivamente sintéticos: límites 0/32/53/64 bits Lua y CBOR, overflow,
cantidades/índices/IDs inválidos, variantes, metadatos obligatorios, regiones y
fases contradictorias, source IDs, integridad completa de hashes y conteos,
equivalencia/idempotencia de evaluación y hashes de export, dos estados del mismo
bucket, separación de contextos, adquisición sin timestamp nativo y rechazo antes
de conexión/retry/failed tanto en 340 como en 341. Se comprueba que un item extremo
no permita filtrar/importar silenciosamente el resto del archivo.

La regresión comparable del backend recolectó **944 casos: 795 aprobados,
1 omitido y 148 no ejecutados/deseleccionados**. Incluyó 80 casos nuevos y todas
las suites sin PostgreSQL: parser/adaptadores, exports, contratos, guard y startup
CLI, captura/watcher, estadísticas, ventanas, validación HTTP y señales 3A/3B.
Después se agregaron dos regresiones de identidad/archivo mixto; su ejecución
focalizada terminó con **82 aprobados** (incluye los 80 anteriores), sin fallos
y con el driver bloqueado. Total de casos distintos aprobados en esta entrega:
**797**. La colección actual contiene 946 casos: 797 comprobados sin PostgreSQL,
1 opt-in auténtico omitido y 148 integraciones no ejecutadas. No se volvió a
repetir la regresión amplia después de añadir esos dos tests; no cambió código
de producto después de la ejecución amplia.

El omitido es el opt-in auténtico `test_authentic_341_capture_offline`:
AUCTIONATOR_REAL_CAPTURE se retiró sólo del proceso de pruebas. Los 148 excluidos
requieren fixtures `isolated_database`, `test_database_url` o `lab`; no se les
atribuye aprobación actual. No se ejecutaron pruebas de idempotencia/transacciones
SQL, migraciones ni concurrencia PostgreSQL. Sus garantías se auditaron en código
y pruebas existentes, no se presentan como verificadas físicamente en esta fase.

Un hook temporal de colección filtró dependencias de fixtures de toda la colección
y bloqueó psycopg.connect: **0 intentos de conexión**. No se levantó FastAPI ni se
usaron endpoints de red. Los subprocesos de CLI prueban errores de configuración,
help y operación local con fixtures; no reciben una captura auténtica.

La primera ejecución dentro del sandbox obtuvo 657 aprobados, 1 omitido y 138
errores de setup por mkdir(0700) en Windows. El intento con directorios de pytest
de ACL heredada obtuvo 734 aprobados y 61 fallos de archivado por la misma
restricción al crear sus directorios privados; no se modificó el archivador para
hacerlo pasar. La ejecución final se hizo fuera del sandbox con los controles
offline y temporales nuevos; aprobó los 795 casos seleccionados. No se cambiaron
ACL de directorios existentes ni permisos del producto. Avisos: deprecación previa
Starlette/httpx y dos avisos Pydantic esperados de fixtures deliberadamente
corruptos con float; sus valores fueron rechazados antes del escritor.

Para repetir sólo la suite nueva, desde backend, sin PostgreSQL:

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m pytest -q -p no:cacheprovider tests/test_local_ingestion_readiness.py
```

No ejecutar toda la colección sin filtrar PostgreSQL: con configuración de tests
presente sus fixtures sí crean/migran schemas. Para la regresión amplia se usó
este launcher temporal (sin guardarlo en Git), con un directorio nuevo en Temp:

```python
import os
from pathlib import Path
from uuid import uuid4
import psycopg
import pytest

os.environ.pop("AUCTIONATOR_REAL_CAPTURE", None)
attempts = []
def forbid(*args, **kwargs):
    attempts.append(True)
    raise AssertionError("5B.1 prohibits PostgreSQL connections")
psycopg.connect = forbid

class Offline:
    def pytest_collection_modifyitems(self, config, items):
        excluded = [i for i in items if
                    {"isolated_database", "test_database_url", "lab"} & set(i.fixturenames)]
        items[:] = [i for i in items if i not in excluded]
        config.hook.pytest_deselected(items=excluded)
    def pytest_sessionfinish(self, session, exitstatus):
        print("PostgreSQL connection attempts:", len(attempts))
        if attempts:
            session.exitstatus = 1

root = Path(os.environ["TEMP"]) / ("wow-5b1-verified-tests-" + uuid4().hex)
raise SystemExit(pytest.main([
    "-q", "-p", "no:cacheprovider", "--basetemp", str(root), "--tb=short"
], plugins=[Offline()]))
```

No se repitieron frontend/build/live tests: el frontend y sus contratos no se
modificaron y los live tests requerirían servicios. No se ejecutó una prueba
con WoW, `/reload` real, watcher sobre archivos privados ni importación auténtica.

## 8. Preservación y requisitos antes de 5B.2

Se preservan las bases existentes por **ausencia de conexiones**: no se leyeron
ni escribieron desarrollo, producción, tests existentes o laboratorios. No hay
un nuevo snapshot físico de filas/secuencias que deba confundirse con los
controles históricos de otras fases. No se modifican .env, Settings globales,
servicios de Windows, archivos del juego, originales privados ni migraciones.
No se envían datos por red. No hubo commit, push ni cambios del índice Git.

Antes de 5B.2:

1. Revisar y resolver identidad completa y persistencia de recepción local;
   definir versionado e idempotencia sin romper los estados sellados existentes.
2. Completar evidencia técnica privada de región, mercado/alcance, origen y fuente
   para cada captura; conservar incógnitas de build/productor/tiempo como tales.
3. Mantener política B hasta revisar por separado dominio monetario, transporte
   exacto y lectores 341. No aceptar archivos parcialmente descartados.
4. Diseñar cualquier migración nueva como aditiva y reproducible, con preservación
   y rechazo sin consumo de secuencias comprobados en laboratorio autorizado.
5. Mantener TrialDatabase como único dueño de todas las conexiones extendidas,
   incluidos retry/failed; revalidar ambas identidades y 005 antes del primer run.
6. Implementar después el enlace explícito archivo/contexto/recepción; jamás
   usar el preflight como autorización de escritura, ni cambiar a 340/HTTP para
   sortear el guard. Sin automatización o importación auténtica en esta entrega.

Los cambios de diseño de esta sección quedan detenidos para revisión del usuario.

Control final: `git diff --check` aprobado; sintaxis Python, whitespace de archivos
nuevos y enlaces del informe comprobados. Siete archivos en el working tree:
cuatro modificados (README, ARCHITECTURE, capture_provenance, partial_service) y
tres nuevos (readiness, su suite y este informe). `main` sigue en el commit base;
índice sin cambios, sin commit ni push. Migraciones y frontend sin diferencias.

## 9. Actualización 5B.1.1: identidad y linaje persistente

Implementación del 24/10/2026 sobre los cambios locales de 5B.1, preservados.
Se mantienen los precios de 32 bits en persistencia y 64 bits sólo en el archivo.
No se modifica frontend, 3A/3B ni el watcher. Las decisiones A/B/C aprobadas se
implementan como un camino explícito de **persistencia de evidencia nativa**,
sin sincronización automática, CLI nueva o importación auténtica.

### Modelo mínimo elegido

Se reutilizan partial_markets, partial_items, partial_import_runs,
partial_exports, partial_export_facts y partial_export_imports. Sólo se agrega
una tabla de recepciones locales y una columna de identidad en mercados.
No hay tabla paralela de precios ni infraestructura multiusuario.

Un mercado verificado se identifica por el objeto canónico:

```json
{
  "version": 1,
  "dataset": "launch",
  "region": "synthetic-eu",
  "economy": "synthetic-realm-a",
  "auction_house_scope": "shared",
  "faction": null
}
```

Todos los valores anteriores son **sintéticos**, no metadatos confirmados de
Forever. `economy` es un identificador técnico estable y revisado del reino o
ámbito económico realmente compartido; no un alias de jugador ni una inferencia
desde PvP. Si varios reinos comparten una economía, se utiliza el identificador
verificado de ese ámbito, conservando el reino observado como claim separado.
No se deduce si Forever comparte economías o AH entre facciones.

`VerifiedEconomy` requiere claims/referencias para economía, reino conocido o
null explícito, facción económica o null explícito y alcance del AH con evidencia.
Scope shared exige faction=null; scope faction exige su facción verificada.
La facción del personaje no se usa para partir un AH compartido. Un reino puede
seguir desconocido cuando el ámbito económico técnico esté verificado por otra
evidencia; no se fabrica un nombre para satisfacer el contrato.

Región técnica sigue siendo explícita y verificada. En el perfil implementado
se requiere un identificador técnico no vacío: región desconocida bloquea el
camino. Si se demuestra un producto sin región técnica aplicable, se detiene
ese caso hasta documentar su namespace real; no se inventa unknown, PvP o una
región a partir del idioma/ubicación. Ningún test acredita la región real de
las capturas privadas.

Ni source_id, las refs de evidencia, hora de adquisición ni la clave nativa
forman parte de esta identidad económica. Dos observadores de esa economía
comparten market_id. Dos economías con clave PvP reciben IDs distintos.
Los datos nuevos usan **dataset=simulated, stress_test o launch** literalmente;
`real` permanece sólo para compatibilidad de los flujos anteriores. No se
reetiquetan retrospectivamente datos real ni stress_test como launch.

La columna market_key de un mercado verificado conserva la primera etiqueta
nativa recibida, como etiqueta representativa. Cada export/facto/recepción
conserva su clave nativa exacta; las etiquetas no se reescriben para resolver
colisiones. Las etiquetas externas requieren el mapping de ruleset explícito.
Dos aliases que pretendan representar la misma economía dentro de un único
archivo se rechazan hasta reconciliar la evidencia: no se fusionan facts
duplicados por heurística. Un ruleset contradictorio con una economía ya
persistida causa rollback, sin modificar el mercado o sus hechos anteriores.

### Captura, estado y recepción

- **Original:** sigue en el archivo privado 5A, independiente y sin alteraciones.
  SHA-256 identifica bytes completos. SQL no recibe el Lua ni datos auxiliares
  privados de configuración; raw_reference usa local-capture:<hash>.
- **Estado económico v2:** partial_exports.canonical_version=2. Su hash incluye
  identidades económicas verificadas por clave nativa, estructura nativa,
  hash económico 5A completo, versión de formato/base y base temporal unknown.
  Excluye observador, refs y tiempos de adquisición/recepción. La estructura
  conserva variantes, presencia l/h/a/m, tablas vacías, claves originales e
  índices. Los hechos se guardan una vez por estado en partial_export_facts.
- **Recepción:** cada run enlaza el estado mediante partial_export_imports y
  una fila append-only de partial_capture_receipts. La fila guarda ambos hashes
  completos, acquired_at, CaptureMetadata y VerifiedLocalContext íntegros.
  Cada observador conserva su source_id y todas sus attestaciones en su propia
  recepción, aun cuando comparte estado. La cabecera conserva sin modificaciones
  la procedencia de su primer observador, compatible con los controles de 005;
  no pretende describir al resto de observadores.

La identidad de estado v1, sus hashes y todos sus manifests sellados permanecen
intactos. El hash v2 describe la evidencia económica compartida; no se compara
como si fuera el hash v1 que incluía source_id/attestaciones. Al reutilizar v2
el servicio compara también estructura, contexto económico y todos los hechos,
sin sustituir la procedencia de la primera recepción.

Ejemplos sintéticos:

| Caso | Resultado |
| --- | --- |
| Dos observadores, misma economía, misma evidencia nativa | Un mercado, un export v2, un conjunto de hechos, dos runs/recepciones con procedencia independiente |
| Archivos distintos sólo por configuración | Hashes de archivo distintos; mismo estado v2 y hechos; ambos linajes conservados |
| Repetir el import con igual contexto | duplicate, mismo export y cero hechos nuevos; nueva recepción auditada, como en el flujo previo |
| PvP en dos economías distintas | Dos mercados y estados separados, aunque el hash económico local sea igual |
| Mismos nombres en stress_test y launch | Mercados/estados distintos por dataset, sin reinterpretar real legacy |
| h=100 y luego h=200, ambos bucket 2485 | Dos estados inmutables y sus recepciones; sigue existiendo un solo índice nativo, sin inventar dos días |

El camino local **no escribe partial_observations acumuladas de 003**. Persiste
hechos nativos compartidos y linaje; evita multiplicar una muestra por cada
observador y mantiene 341 fuera de los motores analíticos actuales. Devuelve
observations_changed=0 y native_facts_seen explícito; completed puede significar
estado nativo nuevo, duplicate significa estado reutilizado. Esta semántica
se documenta deliberadamente: no se descartan hechos ni se anuncia una serie
analítica nueva. La acumulación legacy sigue funcionando como antes.

Los lectores actuales conservan supuestos v1: el catálogo parcial parte del
acumulado 003 y el filtro source_id de history por export identifica al primer
observador de la cabecera. No se presentan como una API de consulta de todas
las recepciones v2; ese linaje se inspecciona en sus relaciones SQL. Adaptar esos
lectores y la exposición de recepciones queda pendiente de la siguiente fase,
sin cambiar ahora 3A/3B o el dashboard.

Acquired_at sigue siendo adquisición local; imported_at sigue siendo recepción
SQL y native_scan_timestamp permanece null. Un SHA de bytes puede tener varias
recepciones/adquisiciones declaradas: no es un ID universal de evento físico.
2485 permanece índice opaco, no fecha ni hora de scan. Ni a ni m se convierten
en volumen vendido, ventas o timestamps.

### Contrato y guard de escritura

[local_lineage.py](../backend/app/ingestion/local_lineage.py) implementa
VerifiedEconomy, VerifiedLocalContext (`contract=verified-local-capture-v1`),
LocalCaptureBinding y prepare_local_capture(raw, metadata, context). Se requieren
formato 341, dataset de ciclo de vida explícito, región, fuente, todos los mercados,
scope y refs revisadas, perfil/codec explícito y hashes concordantes.

El helper recibe bytes ya leídos, no abre archivos, carga settings ni escribe.
Recalcula la evidencia de 5A con CaptureAdapter; valida metadatos y bytes completos.
Un precio >2147483647 rechaza **toda** la preparación con causa
price_exceeds_persistence_int32; el original y valores de 64 bits permanecen intactos.
No se filtran items, campos o variantes para forzar aceptación.

El resultado sólo se puede escribir mediante PartialIngestionService con un
TrialDatabase real. El servicio vuelve a validar batches, native y binding,
contrasta hashes económicos y contexto, y exige 005 y 006 **antes del primer
INSERT/nextval**, también para failed. Un dataset launch sin binding se rechaza
antes de conectar. También se rechaza **cualquier escritura 341 sin binding**,
incluidos stress_test/simulated: quitar el vínculo no permite volver al escritor
legacy. Las filas v1 anteriores no cambian. HTTP conserva su contrato 340; la
CLI 341 no importa y devuelve un motivo fijo antes de conectar. Sigue permitiendo
check-target. La preparación/escritura revisada se ejerce por biblioteca con
TrialDatabase; integrar una CLI con archivo completo queda para otra fase.
No se añade un atajo a través del watcher.

La protección de base destino, transacción, retries y registro failed sigue
perteneciendo a TrialDatabase. Un error SQL por conflicto persistido revierte
datos de mercado y conserva failed en el laboratorio; sus secuencias pueden
avanzar. Entradas inválidas detectadas antes del escritor no cambian filas ni
secuencias. Ninguna referencia externa es autenticada automáticamente por el
software: los claims técnicos siguen requiriendo revisión del operador.

### Migración 006 y compatibilidad

[006_verified_local_lineage.sql](../backend/migrations/006_verified_local_lineage.sql):

1. Agrega economic_identity JSONB nullable a partial_markets. Un índice único
   parcial compara el objeto completo de mercados verificados, sin depender de
   una colisión de hash. Conserva otra unicidad parcial legacy por región/clave/
   dataset. Los registros anteriores quedan con economic_identity=NULL y no se
   fusionan con mercados verificados, aunque coincidan sus nombres.
2. Admite launch en los metadatos de 341, con identidad verificada y exports v2.
   Conserva real/simulated/stress_test anteriores. No modifica tipos monetarios,
   migraciones 001–005 ni filas existentes de hechos/observaciones.
3. Agrega partial_capture_receipts sin nuevas secuencias. Comprueba run/export,
   hashes de archivo/evidencia, adquisición y contexto económico; exige vínculo
   de recepción coincidente mediante constraint trigger diferido. Rechaza UPDATE,
   DELETE y TRUNCATE. La identidad verificada del mercado es inmutable y no se
   permite promover una fila legacy mediante UPDATE.
4. Mantiene sellado, coherencia, append-only y vínculos de 004/005. Sólo para
   canonical_version=2 permite un observador distinto de la cabecera, exigiendo
   su propia recepción validada. v1 sigue exigiendo el mismo source_id.

La migración se ejecuta transaccionalmente una sola vez con tracking existente;
una repetición del runner no vuelve a ejecutarla. No es un script DDL para lanzar
repetidamente sin tracking. Su aplicación requiere locks DDL y un destino
verificado, sin escritores concurrentes. Sólo se aplicó a laboratorios nuevos.

### Validación y condiciones operativas pendientes

**Veredicto 5B.1.1: READY FOR REVIEW.** El diseño aprobado queda implementado;
las decisiones detenidas en 5B.1 se resuelven para el perfil verificado descrito,
sin afirmar datos técnicos de Forever que todavía no se conocen.

Resultado final: **985 recolectados, 984 aprobados, 1 omitido, 0 fallos y
0 integraciones excluidas**. Se ejecutó la suite completa del backend, incluidas
las integraciones antes excluidas en 5B.1, migraciones, concurrencia, rollback,
retries/failed, guards, parser/codecs, snapshots completos y motores 3A/3B.
Los tests nuevos son 39: 23 casos de contrato/guard y 16 de persistencia/
migración SQL. Se conservaron los 82 tests de readiness de 5B.1.

La primera regresión completa, previa al cierre adicional del escritor 341,
aprobó 979 casos y omitió uno. Después se reforzó el guard de binding para todos
los datasets 341 y el transporte SQL, y se agregaron cinco casos. La suite
focalizada pasó 181 casos; la regresión final completa pasó los 984 anteriores.
Los tests de persistencia 341 se actualizaron para aportar el binding completo
y comprobar evidencia nativa sin acumulación; la CLI anterior ahora se prueba
como rechazo sin escritura. Los tests históricos de migración 004/005 conservan
su alcance original; el upgrade 006 tiene cobertura propia, sin editar SQL publicado.

El único omitido fue test_authentic_341_capture_offline: AUCTIONATOR_REAL_CAPTURE
se retiró del proceso de pruebas. No se abrieron/importaron originales privados.
Avisos: deprecación previa Starlette/httpx y dos avisos esperados Pydantic de
fixtures corruptos con float, rechazados antes del escritor. No se repitieron
frontend build/live o WoW: no se modificaron esas capas ni se usó el cliente real.

Para las pruebas se provisionaron únicamente bases nuevas de laboratorio:
target inicial wow_5b11_target_f946c79cdc_test, referencia protegida vacía
wow_5b11_protected_ae41121aba_test y target de revisión final
wow_5b11_final_149e8c3002_test. La segunda ejecución completa usó exclusivamente
los dos últimos: **1.444 sesiones del driver**, con whitelist de nombres/host
local y bloqueo defensivo del hash auténtico para INSERT de runs. La referencia
protegida siguió sin tablas. Los fixtures/schema temporales se limitaron a los
laboratorios; no se conectó desarrollo ni la base de tests preexistente.

Se usó postgres administrativo sólo para consultar capacidad de provisión y
crear esas bases nuevas, sin cambiar roles/permisos ni tablas de aplicación de
bases existentes. Las variables DATABASE_URL/TEST_DATABASE_URL de los procesos
de tests identificaron **referencias de laboratorio**, no cambiaron .env ni un
backend en ejecución. No se cambió la configuración persistente del proyecto.
Los tests se ejecutaron fuera del sandbox por las ACL privadas de Windows ya
documentadas, sin modificar ACL existentes ni el comportamiento del archivador.

Antes de aplicar la revisión final de 006 se preparó 001–005 en el target nuevo,
con fixtures históricos 340/341 sellados. La comparación de todas las columnas
anteriores de todas las tablas y de last_value/is_called de todas las secuencias
fue idéntica tras 006; sólo aparecieron la columna nullable y tabla nuevas,
vacía esta última. Una regresión independiente repite preservación/compatibilidad
en schema efímero y reimporta el export legacy con el mismo ID. Los mercados
previos conservaron economic_identity=NULL. Dos ejecuciones adicionales del
runner con DSN **explícito del laboratorio verificado** devolvieron cero pendientes,
preservando todas sus filas/secuencias. No se ejecutó el default de migrate.py.

Los laboratorios recibieron fixtures y sus secuencias sí avanzaron durante
imports, duplicados e intentos SQL revertidos. No se los presenta como bases
preservadas en conjunto. La preservación de desarrollo/tests anteriores se
sustenta en la ausencia de conexiones a ellas, no en un nuevo snapshot físico.

Estado Git de la entrega combinada 5B.1/5B.1.1: main continúa en
e6145a814cf58b86e88270122da1dc121e2260a3. Once archivos modificados y siete nuevos,
incluidos los siete cambios locales recibidos de 5B.1; sin staging, commit ni push.
001–005, frontend y market/3A/3B sin diferencias. Revisión final de sintaxis,
whitespace/enlaces y git diff --check forman parte del cierre.

La primera prueba con /reload real y la primera importación auténtica siguen
pendientes, al igual que la región y alcance real de las capturas privadas.
No se inicia automáticamente ningún proceso ni se autoriza esa importación
por aprobar fixtures o por disponer de un contrato válido.

## 10. Auditoría final y cierre de Fase 5B.1

Revisión del 24/10/2026, sobre el conjunto de **11 archivos modificados y siete
nuevos** respecto de e6145a8. La publicación en main fue autorizada explícitamente
por el usuario, condicionada a esta auditoría y sus regresiones. Se revisaron los
18 archivos completos, su alcance, ausencia de originales/credenciales/temporales,
compatibilidad legacy, contratos, transacciones, índices y guards SQL de 006.
Frontend, motores 3A/3B, watcher y migraciones publicadas 001–005 permanecen intactos.

### Hallazgo corregido antes de publicar

Se reprodujo una brecha de integridad referencial del linaje: aunque la recepción
era append-only, SQL permitía modificar source_id, source_hash o status del run
al que apuntaba, dejando contradictoria la recepción ya validada. Las mutaciones
del repro sintético se revirtieron. Una regresión nueva falló contra el esquema
anterior (no se lanzó el rechazo esperado), confirmando el defecto.

La **006 todavía inédita** agrega partial_capture_run_guard: para un run con
recepción local congela identidad, hash, referencia, fecha de recepción y conteos;
sólo permite finalizar como completed/duplicate con observations_changed=0.
El alta de recepción bloquea su run con FOR UPDATE para serializar su validación
con cambios concurrentes. Los runs legacy sin recepción local conservan su
comportamiento previo. No hay nuevas columnas, precios, tablas o funcionalidades
de 5B.2 en esta corrección.

Se agregaron nueve casos de mutación SQL del run y una prueba de fallo **después
de crear la recepción**: se revierten export/hechos/recepción, se conserva failed,
y el retry seguido de reimportación reutiliza un único estado sin duplicar hechos.
La regresión focalizada de contratos, bypass 340 y linaje pasó **131 casos**.

### Regresiones y publicación

**Auditoría final aprobada, sin bloqueos pendientes para publicar este alcance.**
La suite completa del código final recolectó **995 casos: 994 aprobados, uno
omitido, cero fallos y cero integraciones excluidas**, incluidos los diez casos
adicionales de esta auditoría. El omitido sigue siendo el opt-in de captura
auténtica, deshabilitado expresamente. No se abrieron archivos privados, usó WoW
ni ejecutó un /reload real. Frontend build/live no se ejecutaron: esas capas no
cambiaron. El check offline de contratos OpenAPI terminó sin drift ni intentos
de conexión a DB, sin regenerar archivos frontend. Persisten sólo la deprecación
anterior Starlette/httpx y dos warnings
Pydantic esperados de fixtures corruptos con float, rechazados antes del escritor.

La suite final usó únicamente wow_5b1_close_final_89d801a449_test y su referencia
protegida nueva/vacía wow_5b1_close_protected_6b287c83c9_test. El primer laboratorio
wow_5b1_close_target_1cf6eac127_test se limitó a reproducir la versión anterior y
la regresión roja. Las variables de selección sólo existieron en los procesos de
pruebas; no se modificaron .env o servidores de aplicación. El driver registró
**1.478 sesiones permitidas y cero intentos fuera de los laboratorios**; se bloqueó
defensivamente la creación de runs con el hash auténtico conocido. La referencia
protegida continuó sin tablas. Desarrollo, producción y tests preexistentes no
se consultaron ni migraron; postgres administrativo sólo provisionó bases nuevas.

Se repitió el upgrade 001–005 -> 006 con fixtures legacy 340 y 341 v1 sellados
en un schema efímero del laboratorio verificado. Coincidieron todos los hashes
de filas anteriores y last_value/is_called de todas las secuencias; la tabla
nueva quedó vacía y ambas identidades anteriores quedaron NULL. El reimport 340
reutilizó el export original. Dos ejecuciones del runner con el DSN explícito
del laboratorio final devolvieron cero pendientes, preservando todas sus filas
y secuencias. No se usó el destino por defecto de desarrollo. Los laboratorios
sí recibieron fixtures y avances de secuencias por imports y rollbacks, como es
esperable; no se afirma preservación global de sus datos de pruebas.

La revisión confirma: guard 340 reconstruido sin regresiones; toda escritura
341 exige contexto completo y TrialDatabase; hashes originales/económicos
conservados; precios fuera de rango rechazados sin filtrar ni escritura parcial;
dos observadores comparten economía; estados distintos del mismo bucket no crean
días nuevos; el camino local no actualiza 003 ni habilita 3A/3B. CLI 341 y
lectores v2 siguen pendientes. Los 18 archivos previstos contienen sólo fuente,
SQL, pruebas y documentación: sin Lua auténtico, credenciales, .env o temporales.
Sintaxis/whitespace/enlaces y git diff --check forman parte del control final.
Se comprobó origin/main sincronizado con la base publicada antes del commit;
la publicación autorizada usa push normal, sin force ni cambios de 5B.2.

No se comienza 5B.2. Su objetivo técnico siguiente es integrar explícitamente el
contrato completo de captura en una CLI manual protegida y preparar lectores de
recepciones/estados v2, manteniendo separación entre adquisición, recepción y
tiempo nativo. Esa tarea requiere otra ejecución y no habilita sincronización,
conexión del watcher a PostgreSQL o uso estadístico por 3A/3B.

Siguen pendientes contexto técnico auténtico verificado, primer /reload real con
watcher y primera importación auténtica. Los precios superiores al dominio de
ingestión permanecen exactos en el archivo local y bloquean la captura completa.
