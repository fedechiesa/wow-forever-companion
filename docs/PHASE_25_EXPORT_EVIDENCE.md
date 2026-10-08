# Fase 2.5 — evidencia nativa por exportación

Entrega del 2026-10-08. Decisión arquitectónica aprobada: separar la evidencia
inmutable de cada estado exportado de los acumulados de la aplicación. Sin Fase 3,
commit ni push. Sin SavedVariables auténticos de Forever; los ejemplos y tests
usan fixtures construidos y datos simulados.

La 004 está implementada, validada en testing aislado y aplicada a desarrollo.
**Veredicto global: NOT READY TO COMMIT.** La implementación de evidencia pasó
todos sus checks; sigue pendiente recibir los dos batches originales de la
auditoría para cerrar su exigencia de reproducción exacta del deadlock. La
regresión construida reproduce y corrige el mecanismo, pero no se presenta como
aquellos payloads. La decisión pendiente del hallazgo 4 ya quedó resuelta.

## 1. Implementación

- `app/ingestion/native_exports.py`: contratos de hechos y estructura, validación
  de identidad/coherencia, hash canónico v1 y proyección GetPriceHistory.
- Adapter Auctionator: conserva campos nativos, claves originales y presencia de
  tablas, incluidos items/mercados vacíos. Los límites se aplican durante construcción.
- Servicio: evidencia y acumulados confirman juntos; se conserva el orden global
  de locks, la validación diaria persistida y los retries acotados de 40P01.
- Contrato de resultado: export_id, evidence_status y native_facts_seen; el contador
  observations_changed sigue refiriéndose a cambios del acumulado.
- `/partial/history?export_id=...`: sólo el estado de ese export. Sin export_id
  conserva la consulta acumulada. `/partial/imports` expone los vínculos.
- El POST normalizado anterior conserva compatibilidad y declara evidencia
  unavailable. No se reconstruyen campos nativos desde sus estadísticas.

## 2. Estructura SQL final

SQL completo: [004_create_partial_export_evidence.sql](../backend/migrations/004_create_partial_export_evidence.sql).

| Tabla | Contenido y restricciones principales |
| --- | --- |
| partial_exports | Contexto fuente/versión/dataset/región/base temporal; hash canónico y versión únicos; manifest JSONB sin precios; cantidad de hechos; primer import; sealed |
| partial_export_facts | FK a export, mercado e item; copias de identidad; claves originales; campo l/h/a/m; índice temporal opcional; valor INTEGER; identidad única por export/mercado/item/día/campo |
| partial_export_imports | Un vínculo por import; FK a export; formato decodificado y versión del decoder; índice por export/import |

El manifest tiene versión 1, mercados con ruleset/realm_version y sus items con
identidades originales/normalizadas y fields_present. Conserva `a` ausente frente
a `a={}`; una disponibilidad cero tiene un hecho explícito. Las tablas l/h son
obligatorias en el formato soportado; sus entradas por día pueden estar ausentes.
Un item vacío y un mercado vacío no desaparecen de la evidencia de un export
aceptado. Se sigue rechazando un batch completamente sin estadísticas.

Los hechos guardan sólo valores nativos presentes. El nombre de estadística se
obtiene del mapping verificado l/minimum, h/highest_minimum, a/max_available,
m/last_minimum. No se guarda Lua completo ni se duplican precios en el manifest.
Las copias de identidad permiten consultar evidencia aunque cambie el catálogo.

## 3. Integridad y triggers

PK/FK/UNIQUE/CHECK cubren identidad, rango INTEGER, fecha ausente de m y coherencia
entre clave literal y ruleset. Pydantic/servicio validan estructura, normalización,
colisiones de claves y equivalencia exacta entre hechos y batch proyectado.

Tres funciones de trigger, instaladas mediante siete triggers de fila/statement:

1. `partial_guard_export`: sólo permite crear una cabecera sin sellar y luego
   sellarla sin cambiar otros atributos. Al sellar valida conteo, existencia del h
   para l/a, igualdad de clave de día y l <= h. Rechaza modificaciones posteriores,
   DELETE y TRUNCATE.
2. `partial_guard_export_child`: hechos/vínculos son append-only. INSERT de hechos
   bloquea la cabecera y rechaza exports sellados. INSERT de vínculos exige
   cabecera sellada y contexto de import coincidente; rechaza UPDATE/DELETE/TRUNCATE.
3. `partial_require_sealed_export`: constraint trigger diferido por cabecera nueva,
   que exige sellado y vínculo con first_import_id al commit.

Son indispensables para proteger modificaciones accidentales fuera del servicio:
un CHECK/FK no puede prohibir UPDATE de un valor válido ni anexar hechos a un
export sellado. El chequeo diferido evita confirmar una construcción incompleta.
No hay triggers de estructura JSON, estadísticas derivadas o validación por cada
hecho al commit. El manifest y las identidades completas se validan en el servicio;
no se afirma que SQL arbitrario construya evidencia auténtica. Administradores
que desactiven los guards quedan fuera de la protección.

## 4. Semántica e idempotencia

`export_id` identifica un estado de evidencia. El hash incluye contexto, claves
originales, valores y presencia/estructura, pero excluye ruta, recepción, codec,
whitespace y IDs locales. Se compara también el contenido persistido al reutilizar
una identidad, para rechazar colisiones/incoherencias. El hash normalizado anterior
de m permanece sin cambios para preservar su identidad acumulada.

Cada recepción tiene su import_run y vínculo, con hash de entrada y referencia.
Contenido idéntico comparte export_id; no permite probar eventos físicos distintos
de exportación. Un nuevo estado puede dar completed con cero cambios acumulados.
Reimportar ese estado da duplicate/reused y conserva otro vínculo de recepción.

GetPriceHistory se proyecta por export: minimum = l si existe, o h si falta;
highest_minimum = h; disponibilidad sólo cuando hay a; m sin día. El mínimo declara
minimum_origin=l/h_fallback y source_fact_id referencia el hecho utilizado. No se
materializa un l ficticio. value_semantics distingue export_projection,
accumulated_extreme y undated_normalized_state. No se implementan métricas de Fase 3.

Exports distintos del mismo día permanecen separados. Archivos recibidos fuera
de orden preservan sus propios valores; no reemplazan un supuesto último observado.
Pueden ampliar extremos acumulados, y sus ausencias no borran acumulados anteriores.
first_received_at/imported_at son recepción, nunca fecha del scan.

## 5. Migración ejecutada

Primero se ejecutó la suite completa contra `_test`, con schemas aleatorios que
aplican 001–004. El test específico de upgrade comenzó con 001–003, siete
snapshots de muestras y 16.628 observaciones simuladas importadas dos veces por
el contrato anterior sin evidencia nativa. Comprobó hashes/cantidades/secuencias
antes y después de 004, tablas nuevas vacías y reejecución del runner sin pendientes.

Sólo en ese test, una reimportación posterior guardó 15.731 hechos nativos con
cero cambios en las 16.628 observaciones. Es una recepción nueva; no vinculó los
imports anteriores ni inventó timestamps. La diferencia de conteos son mínimos
proyectados por fallback, que no deben duplicarse como hechos l.

Luego se ejecutó en desarrollo `scripts/migrate.py`:

```text
Applied migration: 004_create_partial_export_evidence.sql
No pending migrations.  # segunda ejecución
```

001–003 conservaron hashes idénticos. En desarrollo sólo se agregó el esquema de
004 y su registro: cero filas en las tres tablas nuevas; sin imports adicionales,
backfill, modificaciones de observaciones originales o secuencias antiguas.

## 6. Tests realmente ejecutados

Suite final: **232 passed**, una advertencia Starlette/httpx, **145,47 segundos**.
Incluye los 194 anteriores y 38 nuevos. Sin skips ni xfails.

```powershell
# Desde backend, TEST_DATABASE_URL explícita dedicada, distinta de desarrollo:
.\.venv\Scripts\python.exe -m pytest -q -s -p no:cacheprovider
```

Los tres módulos nuevos son test_native_exports.py, test_export_integration.py y
test_export_migration.py. Cubren ausencia/presencia de l, a ausente/vacío/cero,
claves originales, tablas vacías, límites tempranos, equivalencia Lua/LibCBOR,
dos exports del mismo día, recepción tardía, reimportación, imports concurrentes,
separación de contexto, protección SQL, coherencia al sellar, rollback y retries
después del sellado. La suite anterior verifica Fase 2, identidad de mercados y
coherencia entre batches normalizados.

Ejecuciones intermedias: 82 unitarios existentes; 24 de integración anteriores;
34 nuevos antes del test de upgrade; suite de 229 antes de las últimas regresiones;
47 casos focalizados de parser/evidencia/hardening. La cifra final corresponde
exclusivamente a la última suite. No se atribuyen resultados a ejecuciones inexistentes.

## 7. Consultas físicas PostgreSQL

Ejecutadas en schemas aislados de testing, con fixtures construidos, sin mocks
de persistencia. No son exports reales de Forever. IDs locales del caso A→B:

```sql
SELECT export_id, native_field, scan_day, value
FROM partial_export_facts
ORDER BY export_id, native_field;
```

| export_id | native_field | scan_day | value |
| ---: | --- | ---: | ---: |
| 1 | h | 2500 | 100 |
| 1 | m | NULL | 100 |
| 2 | h | 2500 | 200 |
| 2 | m | NULL | 200 |

```sql
SELECT scan_day, statistic, value
FROM partial_observations
WHERE scan_day = 2500
ORDER BY statistic;
```

| scan_day | statistic | value |
| ---: | --- | ---: |
| 2500 | daily_highest_minimum | 200 |
| 2500 | daily_minimum | 100 |

La API contra ese PostgreSQL devuelve mínimo 100 para export 1 y 200 para export
2, con h_fallback; el acumulado devuelve 100. Invertir recepción conserva los
mismos estados y extremos, sin inferir cuál fue observado más tarde.

## 8. Concurrencia y rollback

Imports nativos idénticos: un completed/created y un duplicate/reused, mismo
export_id, una cabecera y dos vínculos. Distintos valores compartiendo item:
completed/created ambos, dos estados. Reimportaciones posteriores: duplicate.
Items 910/911 compartidos entre HC/RP y PvE/PvP también completaron con dos exports.

El control negativo anterior volvió a producir un 40P01 real con SQL intercalado
por mercado. Las regresiones corregidas mantuvieron item 910→911 antes de mercados,
con items nuevos y existentes. Son batches reconstruidos, no originales recibidos
de la auditoría. Retries inyectados tras sellar demostraron rollback de toda la
evidencia y un solo failed al agotar tres intentos.

Errores después de hechos, durante acumulación y antes del vínculo revierten
catálogos, observaciones, cabeceras, hechos y vínculos; sólo queda el failed final.
Errores de SQL manual también revierten su transacción. No quedan schemas test_*.

## 9. Preservación de desarrollo

Comparaciones mediante conexiones READ ONLY antes/después:

| Tabla | Filas antes/después | SHA-256 |
| --- | ---: | --- |
| realms | 1 | idéntico |
| items | 10 | idéntico |
| auction_snapshots | 7 | idéntico |
| auction_snapshot_items | 69 | idéntico |
| import_runs | 10 | idéntico |
| partial_markets | 4 | idéntico |
| partial_items | 50 | idéntico |
| partial_observations | 16.628 | idéntico |
| partial_import_runs | 2 | idéntico |

Hash de partial_observations (filas PostgreSQL t::text por PK, JSON hasheado):
`ebb3f3a4e95766faa8af25b8633155652a7de83b3c008325bba0a6d6947393c9`.
Las nueve secuencias anteriores están idénticas. Se agregaron dos secuencias
vacías de 004. schema_migrations pasa de tres a cuatro registros, como corresponde.

TestClient sobre desarrollo con default_transaction_read_only=on confirmó siete
snapshots y 91 estadísticas del item ficticio de control en cada mercado parcial.
Los imports 1/2 conservan completed/duplicate y export_id NULL/unavailable.

Evidencia local ignorada: data/imports/export004_before.json,
export004_pre_migration.json, export004_after.json, export004_dev_queries.json y
export004_suite.txt. Los hashes de los cinco archivos de referencia comprobados
permanecen idénticos; no se modificó/copió el addon.

## 10. Límites y Git

Pendientes de SavedVariables auténticos: ruta AH de Forever, codec nativo
C_EncodingUtil, contexto de reloj, cobertura y poda reales. Fracciones ModernAH
siguen rechazadas explícitamente, sin floats binarios ni redondeos. daysSinceZero
se fija al cargar el módulo del addon; cruzar medianoche puede mantener el bucket.
No se deducen scans desde recepción, m ni filesystem mtime. El marcador simulado
protege errores de etiquetado, sin autenticar datos criptográficamente.

Cambios locales sin commit ni push. Nuevos de esta última parte: 004,
native_exports.py, tres módulos de tests y este informe. Se actualizaron adapter,
servicio, contratos, API y README/ARCHITECTURE/ROADMAP/AUCTIONATOR_340; informes
anteriores referencian esta entrega sin reemplazar su evidencia histórica.
No se modificaron dependencias, frontend, Fase 2 o migraciones 001–003.
git diff --check y chequeo adicional de whitespace de archivos nuevos sin errores.
Los artefactos locales, entornos, builds y cachés están ignorados; git status
--ignored advirtió permisos del caché pytest previo, que la suite deshabilitó.
No se hicieron optimizaciones extensas; el coste fila por fila permanece pendiente.
