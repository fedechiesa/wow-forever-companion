# Informe de entrega — Fase 2.5

Este informe conserva la evidencia de la entrega inicial. La auditoría posterior
detectó límites de concurrencia y de equivalencia de la persistencia con el addon;
el estado actualizado y los pendientes están en
[PHASE_25_HARDENING.md](PHASE_25_HARDENING.md) y la posterior separación de evidencia
en [PHASE_25_EXPORT_EVIDENCE.md](PHASE_25_EXPORT_EVIDENCE.md). Los 165 tests citados abajo corresponden
a aquella ejecución inicial, no a la suite de hardening.

Validación ejecutada el 2026-10-08 en `wow-forever-companion`, Windows/PowerShell,
Python 3.13.3 y PostgreSQL del contenedor existente `wow-forever-companion-postgres`.
Implementación validada con fixtures y datos simulados. **Pendiente de SavedVariables
real de Forever; Fase 2.5 no se declara completa.** No se implementó Fase 3.

## 1. Archivos creados y modificados

Modificados:

- `backend/app/main.py`: registro del router parcial, sin alterar rutas de Fase 2.
- `README.md`: comandos de generación/importación/consultas/tests y alcance real.
- `docs/ARCHITECTURE.md`: contrato parcial y persistencia independiente.
- `docs/ROADMAP.md`: Fase 2.5 con validación real pendiente.

Creados:

- `backend/app/ingestion/saved_variables.py`: lectores seguros Lua y CBOR.
- `backend/app/ingestion/auctionator_keys.py`: normalización de claves comprobadas.
- `backend/app/ingestion/adapters/auctionator.py`: adapter sin PostgreSQL y procedencia.
- `backend/app/ingestion/partial_contracts.py`: contratos Pydantic independientes.
- `backend/app/ingestion/partial_service.py`: importación atómica, extrema e imports.
- `backend/app/ingestion/fresh_simulator.py`: generador determinista y writer de fixtures.
- `backend/app/api/partial.py`: endpoints mínimos, sin CRUD ni análisis de mercado.
- `backend/migrations/003_create_partial_observations.sql`.
- `backend/scripts/generate_fresh_market.py` y `backend/scripts/import_auctionator.py`.
- `backend/tests/fixtures/auctionator_v8.lua`: fixture representativo, no export real.
- `backend/tests/test_auctionator.py` y `backend/tests/test_partial_integration.py`.
- `docs/AUCTIONATOR_340.md` y este informe.

Artefactos locales ignorados: `data/imports/fresh/{Auctionator.lua,catalog.json,context.json}`,
`data/imports/phase2_before.json` y `data/imports/phase25_verification.json`.
No se copió código del addon, no se modificó la referencia externa, ni se agregó
la distribución a Git. No se modificaron dependencias, frontend o migraciones 001/002.

## 2. Migración

Se aplicó `003_create_partial_observations.sql` en desarrollo y testing. Agrega
`partial_markets`, `partial_items`, `partial_observations`, `partial_import_runs`,
con PK/FK, checks, índices e identidad única de observación. No modifica ninguna
tabla de snapshots completos. El runner conserva el registro de 001 y 002.

## 3. Contratos y modelo

`PartialObservation`: mercado exacto/ruleset, item_key, ID, tipo de clave,
statistic, value y scan_day opcional. `PartialBatch`: fuente/tipo/versión, dataset,
región, base temporal opcional y observaciones. `PartialImportResult`: import_id,
status y cantidades vistas/cambiadas. Import time pertenece al registro persistido
y lo genera PostgreSQL. Nombre/calidad permanecen desconocidos en el catálogo parcial.

Estadísticas: `daily_minimum`, `daily_highest_minimum`, `daily_max_available`,
`last_minimum`. Enteros estrictos `0..2147483647`; timezone obligatoria si se proporciona
base temporal. `last_minimum` siempre queda sin scan_day. Se preservan variantes y
namespace de pet species. No se incorporan ventas, promedio, máximo global ni auction_count.

## 4. Formatos soportados

SavedVariables de literales Lua y base global v8; tablas de realm/item; CBOR de
mercado o item de la ruta LibCBOR inspeccionada, con selección explícita del operador.
Se soporta un subconjunto definido y limitado de CBOR, incluyendo tablas vacías
codificadas como arrays. Hay pruebas de decimal escapes, bytes binarios, nesting,
claves, rechazo de code execution, CBOR truncado y formatos no soportados.

El [documento de evidencia](AUCTIONATOR_340.md) enumera archivos inspeccionados,
hashes, estructuras, semántica de h/l/a/m y limitaciones precisas del parser.

## 5. Pendientes de confirmar

Un export auténtico de Auctionator 340 en Forever 1.60.1, ruta ModernAH/LegacyAH,
claves efectivas de mercado, base temporal del cliente, tamaño/cobertura/poda real
y serialización nativa C_EncodingUtil. La versión del addon y región no se deducen
del archivo de precios. No se afirma soporte del codec nativo ni se asignan fechas
ficticias a los índices o al último mínimo.

## 6. Simulación generada

Seed 340; 50 IDs/nombres explícitamente **FICTIONAL**; 30 días simulados, índices
2500..2529; cuatro mercados PvE/PvP/HC/RP. Todos los valores económicos son
**SIMULATED**, no precios históricos de Forever.

Se generaron 16.628 estadísticas: 16.428 diarias y 200 últimos mínimos sin fecha.
Cada mercado contiene 4.157 estadísticas, 50 items y 30 días con datos a nivel
de mercado. Hay items con aparición tardía y días sin observación; no todos tienen
30 días. Incluye abundancia de leveleo, demanda creciente, escasez, volatilidad
temprana que disminuye, aparición tardía, ausencias y disponibilidad cambiante.
El generador reproduce el orden de actualizaciones SetPrice, incluido l disperso.

SHA-256 del Lua generado:
`9198770df3b394f401af110737d82dcc0c54a9d317a69f38564291ae2dd81e27`.
Se verificó reproducibilidad con seed idéntica y cambio de resultado con otra seed.

## 7. Importaciones ejecutadas

En la base de desarrollo existente, exclusivamente en tablas parciales:

| Import ID | Estado | Vistas | Cambiadas |
| --- | --- | ---: | ---: |
| 1 | completed | 16.628 | 16.628 |
| 2 | duplicate | 16.628 | 0 |

Ambos imports comparten el SHA-256 anterior, source_id `fresh-seed-340`, región
`simulation`, dataset `simulated`, source_type `simulated`, versión `340`, DB v8.
Conteo físico final: **16.628** filas, sin duplicación. No se importaron datos
reales de Forever. Los fixtures real/simulated de tests sólo viven en esquemas aislados.

## 8. Ejemplo físico de PostgreSQL

Resultado de `/partial/history?market_id=2&item_key=1900000000&source_id=fresh-seed-340`
consultado con TestClient contra la base de desarrollo, sin mock de persistencia:

| Mercado | Día | Estadística | Valor |
| --- | ---: | --- | ---: |
| PvE | 2500 | daily_minimum | 73 copper |
| PvE | 2500 | daily_highest_minimum | 134 copper |
| PvE | 2500 | daily_max_available | 377 unidades disponibles |

Dataset simulated; item ficticio; temporal_basis unknown; day_start NULL;
first_import_id y last_import_id 1. Esta consulta devuelve 91 filas: 90 estadísticas
de 30 días y un último mínimo sin fecha. No son ventas ni subastas individuales.

Consulta SQL equivalente:

```sql
SELECT m.market_key, i.item_key, o.scan_day, o.statistic, o.value
FROM partial_observations o
JOIN partial_markets m ON m.id = o.market_id
JOIN partial_items i ON i.id = o.item_id
WHERE m.region = 'simulation' AND m.dataset = 'simulated'
  AND m.market_key = 'PvE' AND i.item_key = '1900000000'
  AND o.source_id = 'fresh-seed-340' AND o.temporal_basis = 'unknown'
ORDER BY o.scan_day NULLS LAST, o.statistic, o.id;
```

## 9. Tests ejecutados

Suite final: **165 passed**, 15,13 segundos. Incluye los 88 tests anteriores y
77 nuevos. Ejecución: `python -m pytest -q -p no:cacheprovider`, con
TEST_DATABASE_URL explícita terminada en `_test` y distinta de desarrollo.
Parser/simulador/validación parcial aislados: **64 passed**.

Se ejecutaron pruebas reales de PostgreSQL: repetición y concurrencia, rollback
intermedio y registro failed, fuentes/regiones/bases temporales, evolución y
no regresión de extremos diarios, constraints SQL, timestamps, separación de
mercados/datasets, variantes, histórico ordenado, import HTTP y preservación de
Fase 2. Se verificó ausencia de esquemas `test_*` sobrantes al finalizar.

Una advertencia de dependencia: Starlette indica deprecación del uso actual de
httpx en TestClient. No hubo tests omitidos, fallidos ni resultados atribuidos a
ejecuciones que no ocurrieron. El primer ensayo unitario tuvo una advertencia de
permisos de caché pytest; la suite final deshabilita ese caché.

## 10. Idempotencia y separación

Reimportación física: 16.628 filas antes/después, 0 cambios en import 2.
Prueba concurrente: un completed y un duplicate. El mismo contenido normalizado
via archivo/HTTP también devuelve duplicate. Cambios de orden/whitespace no alteran
la identidad de evidencia sin fecha; los hashes de bytes preservan cada procedencia.

Consultas HTTP verificadas para los cuatro mercados, sin mezclas:

| Market ID local | Mercado | Estadísticas | Items | Días | Mínimo día 2500 item ficticio 1900000000 |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | HC | 4.157 | 50 | 30 | 136 |
| 2 | PvE | 4.157 | 50 | 30 | 73 |
| 3 | PvP | 4.157 | 50 | 30 | 148 |
| 4 | RP | 4.157 | 50 | 30 | 127 |

Los IDs son locales, no se hardcodean en la API. Los tests importan real y simulated
con la misma clave/región y demuestran que resultan ocho identidades independientes.
Otro source_id, región o base temporal tampoco fusiona series.

Se compararon hashes SHA-256 de todas las filas (orden por PK) y conteos antes y
después de migraciones, importaciones y suite:

| Tabla de Fase 2 | Filas antes/después | Resultado |
| --- | ---: | --- |
| realms | 1 | Hash idéntico |
| items | 10 | Hash idéntico |
| auction_snapshots | 7 | Hash idéntico |
| auction_snapshot_items | 69 | Hash idéntico |
| import_runs | 10 | Hash idéntico |

Sus cinco secuencias también permanecen idénticas (realms 31, items 159,
auction_snapshots 52, auction_snapshot_items 159, import_runs 60).
La API de Fase 2 sigue devolviendo los siete snapshots.

## 11. Estado de Git

Cambios locales sin commit ni push. Sólo código, documentación, migración nueva
y fixture representativo. `git diff --check` sin errores; comprobación adicional
de whitespace para archivos nuevos. No aparecen entornos, secretos, builds,
data/imports ni código de referencia en el conjunto versionable. No se modificaron
001/002 ni se añadió el addon al repositorio.

## 12. Problemas y decisiones

- Docker Desktop estaba detenido y el contenedor PostgreSQL existente estaba
  parado. Se iniciaron Docker Desktop y ese contenedor, conservando su volumen;
  no se recreó, borró ni reinicializó la base.
- La referencia externa era legible; no hubo bloqueo del parser por sandbox.
- Los días dependen de un reloj no guardado: conservar índices y admitir una
  base explícita evita asignar fechas injustificadas.
- m no tiene timestamp: se conserva por estado del export sin fecha observada.
- ModernAH y LegacyAH identifican mercados de distinta forma: se conserva la
  clave exacta y se exige mapping para claves sin ruleset explícito.
- La base de precios carece de catálogo completo: se eligieron IDs/nombres
  ficticios marcados para el simulador, sin presentarlos como items reales verificados.
- Los extremos diarios son mutables durante un día: se acumulan según la semántica
  del addon y las lecturas viejas no regresan valores. Se traza primer/último import;
  no se agrega un historial de revisiones ni análisis de tendencias de Fase 3.
- C_EncodingUtil no está implementado en la referencia: su codec permanece pendiente
  y no se presenta el subconjunto LibCBOR como soporte nativo verificado.

Los comandos reproducibles están en README y el detalle de evidencia en
[AUCTIONATOR_340.md](AUCTIONATOR_340.md).
