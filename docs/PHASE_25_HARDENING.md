# Hardening de Fase 2.5 — informe

Este informe conserva la pasada inicial de hardening (194 tests). La decisión
arquitectónica del hallazgo 4 fue aprobada posteriormente y se implementó en 004;
el estado actual y su validación están en
[PHASE_25_EXPORT_EVIDENCE.md](PHASE_25_EXPORT_EVIDENCE.md). Las referencias abajo a
una decisión pendiente o a ausencia de 004 describen aquella ejecución histórica.

2026-10-08. Alcance exclusivo: los siete hallazgos comunicados de la auditoría
adversarial. Sin Fase 3, funcionalidades de producto, commit ni push. Desarrollo
se usó sólo para lectura y comparación; todas las escrituras de validación fueron
en esquemas aislados de `wow_forever_companion_test`.

**Veredicto: NOT READY TO COMMIT.** Se corrigieron los mecanismos independientes,
pero faltan los payloads exactos de la auditoría y una decisión arquitectónica para
el hallazgo 4. Se preguntaron ambos puntos y no se asumió una respuesta. Se detuvo
ese rediseño como exige la instrucción del usuario; no se creó una migración 004.

## 1. Correcciones por hallazgo

| Hallazgo | Corrección / estado | Regresión |
| --- | --- | --- |
| 1. Deadlock con items compartidos y mercados distintos | Todos los items por item_key global; todos los mercados; todas las observaciones. Locks FOR UPDATE hasta commit. Máximo tres intentos de transacción completa, sólo SQLSTATE 40P01. Falta comparar los batches exactos originales. | Control negativo SQL real 40P01; mismos batches construidos completan con items nuevos/existentes; reimportación duplicate; retries y agotamiento |
| 2. Rulesets literales inconsistentes | Pydantic exige que PvE/PvP/HC/RP coincidan con su ruleset. El adapter rechaza cualquier mapping de clave literal, incluso si coincide; sólo se mapean claves externas. | Los cuatro rulesets en Lua y HTTP; mapping externo válido y conflicto con mercado externo persistido |
| 3. Estadísticas contradictorias entre batches | Los locks de items protegen también estadísticas todavía ausentes. Se valida el par min/max persistido dentro de la transacción, después de todos los cambios. La combinación contradictoria revierte todo el batch y registra failed. | Low/high separados en ambos órdenes, carreras coherentes/contradictorias y rollback de otros items del batch |
| 4. Extremos acumulados distintos de GetPriceHistory | Discrepancia confirmada y documentada. Rediseño detenido pendiente de decidir evidencia inmutable por export y tratamiento del acumulado. No se falsifica ni reconstruye evidencia previa. | Pendiente de implementar y probar la alternativa elegida |
| 5. Fracciones ModernAH legítimas | Confirmada división buyout/count en fuente auténtica. Se mantiene rechazo explícito sin redondeo; tokens decimales Lua se leen con Decimal. CBOR float sigue sin soporte. | Literales 100.5, 1/3 serializado y notación exponencial; CBOR 1.5; exponente corrupto |
| 6. Marcador simulado con BOM/whitespace | Se comparte normalización de prefijo entre lector y detector. Error de dataset antes de parsing; imports simulated siguen funcionando con esos prefijos. | Cinco prefijos con/sin BOM, whitespace o ambos |
| 7. Límites tardíos / decoders independientes | Se limita antes de construir cada observación. Presupuesto de un millón de nodos compartido entre Lua y todos los CBOR. Un contenedor CBOR incompatible con el presupuesto falla al leer su cabecera. | Contador de objetos construidos; rechazo de cabecera sin hijos; presupuesto compartido entre diez strings; Lua implícito y profundidad |

Archivos cambiados en esta pasada: adapter, contratos parciales, lectores, servicio
parcial, test de integración existente y documentación README/ARCHITECTURE/ROADMAP/
AUCTIONATOR_340/PHASE_25_VALIDATION. Archivos nuevos de esta pasada:
`tests/test_hardening_parser.py`, `tests/test_hardening_integration.py`,
`tests/fixtures/deadlock_reconstruction.json` y este informe.

## 2. Decisiones de semántica de precios

`Source_ModernAH/FullScan/Mixins/Frame.lua:GetInfo` divide buyout por cantidad, sin
floor. Los precios fraccionarios pueden ser legítimos. El contrato INTEGER actual
los rechaza y no debe anunciar compatibilidad con todos los exports del addon.
No se altera disponibilidad ni índice temporal, que continúan siendo enteros estrictos.

Un racional numerador/denominador con columnas NUMERIC sin escala fija sería una
representación candidata. La base agregada no conserva los operandos buyout/count
y el resultado ya pasó por aritmética del cliente. Guardar el literal Decimal sería
exacto respecto del texto exportado, pero no prueba el precio racional original;
guardar un racional de IEEE754 tendría otra semántica y requiere justificar el codec.
Se mantiene la alternativa de rechazo explícito autorizada en el hallazgo 5,
sin introducir floats binarios ni un redondeo silencioso en la importación.

Para el hallazgo 4, el caso comprobado es:

| Evidencia | l | h | minSeen de GetPriceHistory | Mínimo acumulado actual |
| --- | --- | ---: | ---: | ---: |
| Export A | ausente | 100 | 100 | 100 |
| Export B | ausente | 200 | 200 | 100 |

El adapter refleja B correctamente, pero 003 conserva LEAST entre imports. No hay
timestamp de export para demostrar que el último archivo importado sea el estado
observado más reciente; la procedencia de importación y la de observación difieren.

Alternativas planteadas al usuario:

1. Recomendada: conservar los acumulados existentes, etiquetar su semántica y
   agregar evidencia inmutable de cada nuevo export con origen l/fallback h.
   Consultar un export identificado explícitamente; no reconstruir exports anteriores.
2. Guardar sólo evidencia por export hacia adelante, conservando los acumulados
   originales como legado separado y sin reinterpretarlos como estado del addon.

Ambas requieren decidir el contrato de persistencia/consulta y una 004 incremental.
Esta parte se detuvo por el pedido explícito de detener decisiones arquitectónicas
importantes y explicar alternativas. Ninguna de las dos se implementó sin respuesta.

## 3. Migraciones

No se agregaron ni ejecutaron migraciones nuevas en esta pasada. Los hashes de
001, 002 y 003 antes/después son idénticos. No se modificaron tablas o filas de
desarrollo. La eventual 004 sólo se definirá tras resolver el hallazgo 4; no hará
backfill de evidencia de exports que no está disponible.

## 4. Tests ejecutados

Suite final, después del último cambio: **194 passed**, una advertencia de dependencia,
20,76 segundos. Incluye los 165 tests anteriores y 29 casos nuevos de hardening.

```powershell
# Desde backend, con TEST_DATABASE_URL dedicada configurada explícitamente:
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

El módulo de concurrencia/históricos/retries se ejecutó además con trazas:
**11 passed**. Parser y regresiones de prefijos/budgets/fracciones se ejecutaron
durante implementación; la suite final incluye también el caso adicional de
exponente decimal corrupto. La advertencia corresponde a Starlette/httpx TestClient
y no hubo tests omitidos ni xfails.

Hubo dos fallos iniciales en el nuevo test de concurrencia: su barrera de arranque
seguía instalada durante la reimportación secuencial y esperaba un segundo hilo
inexistente. Se restauraron los hooks antes de esa fase y se reejecutó el módulo
y la suite. Esos fallos no fueron errores de persistencia ni se contaron como passed.

## 5. Reproducción de concurrencia

Los payloads originales no están en el repositorio ni fueron incluidos en el pedido.
El fixture se declara **construido a partir de la descripción del hallazgo**, no
obtenido de la auditoría ni de SavedVariables auténticos:

- Batch A: HC/item 911 y RP/item 910.
- Batch B: PvE/item 910 y PvP/item 911.
- Cada item tiene daily_minimum y daily_highest_minimum del mismo día. Mercados
  distintos y items compartidos hacen invertir el orden del catálogo anterior.

El control negativo ejecuta el SQL anterior intercalado por mercado en dos conexiones
reales de PostgreSQL. Una barrera después del primer item garantiza la inversión:
un resultado `committed` y un error **40P01 real**, sin mock del error SQL.

Después de la corrección, los dos imports arrancan concurrentemente con estas trazas:

```text
A: item 910 -> item 911 -> market HC  -> market RP
B: item 910 -> item 911 -> market PvE -> market PvP
```

Resultados: `completed/completed`, ocho estadísticas físicas y ningún failed;
reimportaciones `duplicate/duplicate`. Se verificaron tanto items nuevos como
preexistentes. Retry no disimula el caso corregido: las trazas de cada hilo contienen
una sola fase de items seguida de mercados; no aparecen intentos extra. El test separado de retries inyecta
40P01 después de escribir el catálogo para comprobar rollback, máximo tres intentos
y un único failed final cuando se agotan.

**No se afirma haber reproducido exactamente los batches de la auditoría.** Falta
recibirlos y agregarlos como regresión explícita antes de cerrar el hallazgo 1.

## 6. Integridad de históricos

Se comprobaron mínimo=200 y máximo=100 en batches separados, en ambos órdenes:
el primero confirma sólo el dato conocido; el segundo se rechaza con CheckViolation
y rollback completo. No se inventa la estadística ausente para evitar el conflicto.
En concurrencia contradictoria, un batch completa y otro rechaza; nunca confirman
ambos valores. Con mínimo=80/máximo=100, ambos completan coherentemente.

El test de rollback agrega otro item válido al batch contradictorio y confirma que
tampoco queda su catálogo ni observación. Los extremos válidos de imports anteriores
se mantienen; los tests anteriores de stale import siguen pasando. Fuentes, región,
mercado, variantes y base temporal continúan separados.

La protección de coherencia es transaccional en el servicio, no un constraint
interfila añadido a PostgreSQL. SQL manual o versiones antiguas del importador
quedan fuera del contrato protegido. La persistencia por export sigue pendiente;
los acumulados no se anuncian como GetPriceHistory del último export.

## 7. Preservación de datos existentes

Comparación SHA-256 de todas las filas ordenadas por PK, antes y después de la
suite completa, con conexiones de desarrollo en modo READ ONLY:

| Tabla | Filas antes/después | Hash |
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
| schema_migrations | 3 | idéntico |

Las nueve secuencias de desarrollo también son idénticas. Los originales de Fase 2
y Fase 2.5 no recibieron imports, updates, deletes ni reinicios. `/snapshots` sigue
devolviendo siete snapshots; las consultas de los cuatro mercados parciales
existentes siguen devolviendo 91 estadísticas del item ficticio de control, sin mezcla.

Testing exige un nombre terminado en `_test` distinto del de desarrollo y aplica
migraciones en un esquema aleatorio por test. Tras terminar la suite se confirmó
que no quedaron esquemas `test_*`. Evidencia local ignorada:
`data/imports/hardening_before.json` y `data/imports/hardening_after.json`.

## 8. Riesgos pendientes de un SavedVariables real

Se consultó la fuente auténtica externa de Auctionator 340, especialmente DB,
ModernAH FullScan, Variables y LibCBOR. No se modificó ni copió el addon. Ningún
fixture usado aquí es un SavedVariables real de Forever; tampoco se verificaron
los codecs nativos C_EncodingUtil ni sus extensiones.

El índice daysSinceZero se fija al cargar el módulo y se reutiliza durante la
sesión: cruzar medianoche no garantiza cambiar de bucket. La base temporal del
cliente no está en el export; m tampoco tiene timestamp. Deben conservarse esos
límites al interpretar fechas, orden de exports y equivalencia del histórico.
ModernAH admite fracciones que el contrato actual rechaza. El marcador simulado
con BOM/whitespace es una protección contra errores, sin autenticidad criptográfica.

## 9. Estado Git

Cambios locales de Fase 2.5 y hardening sin commit ni push. `git diff --check`
sin errores y comprobación de whitespace también para archivos no trackeados.
Migraciones 001/002/003 sin cambios de bytes. No se añadieron entornos, secretos,
builds, evidencia local data/imports ni el addon externo al conjunto versionable.
No se hicieron optimizaciones extensas: el coste fila por fila permanece como
mejora posterior; las fases de locks y la validación adicional corrigen integridad.

## 10. Veredicto y trabajo detenido

**NOT READY TO COMMIT.** Faltan:

1. Los dos batches originales y su procedimiento de sincronización, para demostrar
   la reproducción exacta exigida, además del mecanismo ya reproducido/corregido.
2. La decisión entre las alternativas del hallazgo 4 y su implementación 004,
   tests de ambas semánticas y verificación sin reinterpretar evidencia previa.

Se completaron y validaron las correcciones independientes. La limitación sobre
precios fraccionarios queda explícita, con tests, conforme a la alternativa de
rechazo autorizada. Fase 2.5 sigue pendiente de SavedVariables auténtico y Fase 3
no se inició.
