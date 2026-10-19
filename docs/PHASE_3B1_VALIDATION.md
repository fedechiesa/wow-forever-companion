# Fase 3B.1 — Motor de señales estadísticas

Entrega del 2026-10-19 sobre HEAD `a4852586b71aa3be41a5692d22b91283cd66a7fa`.
Alcance: dos reglas backend bajo demanda, sin nombres de items, frontend, IA,
ranking global ni persistencia nueva. No se cambian ingestión, Auctionator,
migraciones, configuración PostgreSQL o datos simulados existentes. Ningún
SavedVariables auténtico se importa ni se usa como evidencia de validación.

## Arquitectura y reutilización

```text
GET /market/signals
  -> SignalsQuery: selectores/ventana de 3A + parámetros de reglas
  -> MarketSignalService
     -> MarketAnalysisService.analyze (una sola vez)
        -> contexto/repositorio/ventana/puntos/métricas/calidad de 3A
        -> una transacción READ ONLY, REPEATABLE READ
     -> evaluate_signals (puro; sin conexión ni escritura)
        -> evaluación de evidencia por regla
        -> desviación y tendencia
        -> explicaciones y contratos 3b1-v1
```

`signal_contracts.py` define parámetros, motivos y respuestas tipadas.
`signal_service.py` compone el servicio existente; `signals.py` evalúa reglas.
El router adapta HTTP usando el manejo de errores existente. No se incorpora
otro repositorio ni otro motor estadístico. Contexto, ventana, puntos, cobertura,
calidad y procedencia se conservan exactamente como los entrega 3A.

Tendencia reutiliza directamente las instancias `MetricValue` de pendiente,
primer/último precio y cambios de 3A. También se reutilizan sus conteos de
origen. Para la referencia se llama a `compute_metrics` de 3A con los puntos
anteriores al último, tomando su mediana. Este segundo recorrido tiene como
máximo 365 puntos y no agrega SQL ni otra implementación de mediana. Se conserva
la implementación 3A completa para evitar refactorizar sus contratos/cálculos.

## Definiciones matemáticas

Sean `(d_i, p_i)`, ordenados por índice real, los mínimos guardados no null de
la ventana. `n` cuenta buckets con precio, nunca imports, subastas o scans físicos.
Los ceros explícitos pertenecen a la muestra. Ausencias y `m` no se imputan.

### Desviación histórica

- Observado `P = p_n`: último mínimo **guardado por índice** en esta selección.
- Histórico `H = (p_1, ..., p_(n-1))`; referencia `R = median(H)`.
- Desviación con signo `D = P - R`, en copper.
- Magnitud absoluta `A = |D|`, en copper.
- Desviación porcentual con signo `Q = 100 * D / R`, sólo si `R != 0`.

Con evidencia suficiente, `Q <= -deviation_threshold_pct` produce
`below_reference`; `Q >= deviation_threshold_pct`, `above_reference`. El resto
produce `no_significant_deviation`. Los límites son inclusivos.

Se excluye siempre el último punto de la referencia; no se ofrece un parámetro
que cambie esa definición dentro de la misma versión. Así el precio evaluado
no desplaza su propio baseline. Contraejemplo simulado: `[1,2,3,100]` tiene
mediana anterior 2 y desviación 4900%; incluir 100 cambiaría la referencia a 2,5.
La mediana resiste extremos aislados mejor que la media, pero puede cambiar si
una parte importante de los buckets es extrema o tiene ausencias selectivas.

`R=0` deja `Q=null`, estado `undefined`, motivo `zero_reference`. Si además
`P=0`, la diferencia exacta cero permite clasificar ausencia de desviación,
siempre que pasen los demás requisitos. Si `P!=0`, la dirección es
`insufficient_evidence` con motivo estructurado `zero_reference`; no se inventa
infinito. `P=0, R>0` conserva una desviación válida de -100%.

### Tendencia histórica

Se reutilizan de 3A:

- `B = sum((d_i-mean(d))*(p_i-mean(p))) / sum((d_i-mean(d))^2)`.
- `C = p_n - p_1` y `T = 100*C/p_1` cuando `p_1 != 0`.

Con evidencia suficiente, hay dirección sólo si `B != 0`, `B` y `T` tienen el
mismo signo, `|T| >= trend_threshold_pct` y
`|B| >= min_trend_slope_copper_per_scan_index`. Signo positivo produce
`ascending`; negativo, `descending`. De otro modo, `no_significant_trend`.
Los límites de magnitud son inclusivos. No se etiqueta como ascendente sólo
porque el último precio supere al primero si la pendiente indica lo contrario.
Signos opuestos agregan `trend_direction_disagreement`.

Pendiente no calculable produce `unavailable_trend`. Primer precio cero y
cambio no cero producen `zero_baseline` e `insufficient_evidence`. Cambio entre
extremos cero permite una clasificación neutral sin inventar un porcentaje;
esto incluye la serie constante cero. Neutral no prueba estabilidad de los
valores interiores ni ausencia de movimientos importantes.

La unidad de `B` sigue siendo **copper/scan_index**, incluso con calendario
conocido. Se usan los índices originales, con sus huecos; nunca ordinales
compactados. No es una tasa diaria verificada, un pronóstico, un test de
significancia estadística ni una inferencia causal.

## Parámetros validados y defaults

| Parámetro | Default | Validación / finalidad |
|---|---:|---|
| min_history_observations | 7 | Entero 3..365; precios anteriores, exige al menos 8 precios totales por defecto |
| min_trend_observations | 7 | Entero 3..366; nunca permite tendencia con uno o dos precios |
| min_price_coverage | 0.8 | Decimal `0 < x <= 1`; precios / posiciones solicitadas |
| min_index_coverage | 0.5 | Decimal `0 < x <= 1`; precios / posiciones del intervalo de índices |
| deviation_threshold_pct | 20 | Decimal positivo; magnitud porcentual mínima de desviación |
| trend_threshold_pct | 10 | Decimal positivo; magnitud porcentual mínima del cambio entre extremos |
| min_trend_slope_copper_per_scan_index | 0 | Decimal no negativo; piso opcional por unidad de índice; pendiente cero nunca da dirección |
| max_latest_price_lag | 0 | Entero 0..2147483647; distancia máxima del último precio al ancla |
| require_native_l | false | Booleano; si true, todos los precios usados deben tener origen l |
| require_known_temporal_basis | false | Booleano; si true, unknown bloquea clasificación |

NaN, infinitos, parámetros extra y combinaciones inválidas de selección/ventana
se rechazan con 422 antes de consultar PostgreSQL. Los parámetros efectivos se
devuelven completos para reproducir cada resultado.

Siete es un piso operativo conservador, no una garantía de confianza. Exigir
80% de lo solicitado impide tratar una fracción pequeña de una ventana como
evidencia completa. El piso de 50% del intervalo detecta series dispersas que
podrían mostrar 100% sobre los buckets observados. 20%/10% son filtros iniciales
de magnitud legibles, no calibrados con nuestros samples; requieren revisión
con datos auténticos. El piso de pendiente cero evita imponer una escala de
copper arbitraria entre items; el filtro porcentual sigue activo. Son decisiones
de producto auditables y configurables, sin afirmación de optimalidad.

## Evidencia, ventanas y procedencia

Cada regla devuelve `evidence.status=sufficient|insufficient`, motivos tipados,
conteo usable, conteo anterior al último, dos ratios, distancia al ancla y
conteos l/h_fallback/unknown. Los motivos pueden coexistir; ninguno se oculta
porque otro haya fallado. Los números descriptivos disponibles se conservan
aunque la dirección esté bloqueada por evidencia insuficiente.

Se exige, por regla:

1. Muestra mínima aplicable.
2. `n / requested_position_count >= min_price_coverage`.
3. `n / index_span_position_count >= min_index_coverage`.
4. Último precio dentro de la distancia permitida al ancla.
5. Políticas de origen/base temporal, cuando se solicitan.
6. Baseline y cálculos necesarios definidos para una clasificación direccional.

Los denominadores vacíos son null/no_axis y fallan la condición. La ventana y
el ancla siguen las reglas de 3A, sin cambiarlas:

- `observed_buckets`: N posiciones solicitadas del mercado. Si se piden 30 y
  sólo hay ocho, 3A puede mostrar cobertura seleccionada 8/8=1; la nueva regla
  muestra `requested_price_ratio=8/30` y bloquea señal con defaults.
- El segundo ratio usa el intervalo inclusivo entre inicio/fin seleccionados,
  incluyendo índices que no aparecen en observed_buckets. Ocho precios en
  índices 10,20,...,80 tienen ratio seleccionado 1, pero ratio de intervalo 8/71.
- `index_range` y `calendar_days` conservan posiciones faltantes y la cobertura
  solicitada no las elimina. Calendario requiere base conocida y 7/14/30 días.
- La distancia al ancla se mide en índices, nunca en horas desde la recepción
  ni respecto de hoy. Un precio puede estar en el ancla y aun ser antiguo frente
  al mundo real; no se afirma actualidad del mercado.

`coverage` y `quality` son exactamente los de 3A. Los nuevos ratios no redefinen
`coverage.price_ratio`. `historical_observation_count` siempre cuenta precios
anteriores al último; tendencia utiliza `usable_observation_count` completo.

`accumulated` mantiene extremos de imports compatibles y origen desconocido;
no representa un único estado del addon. `export` mantiene exactamente un
estado sellado seleccionado por export_id y su proyección l/h_fallback.
Ambos modos pueden producir señales sobre sus propias semánticas con defaults,
con sus advertencias; `require_native_l=true` bloquea accumulated y exports
con fallback, sin disfrazarlos de l ni seleccionar otra muestra silenciosamente.

Base temporal desconocida permite reglas por índice y conserva `unknown_calendar`;
la política opcional puede bloquearlas. Se preservan mercado/región/dataset,
item con variante, fuente/tipo/base, modo/export y semántica del valor.
`provenance`, referencias por punto, hash del export, IDs de imports y recepción
permanecen visibles. Recepción, ID y reimportación nunca ordenan scans ni agregan
muestras. `m` se cuenta como evidencia excluida, no como precio actual.

## Endpoint y contrato

`GET /market/signals` acepta todos los selectores y ventanas de `/market/metrics`
y los diez parámetros anteriores como query params. No cambia endpoints
existentes. Errores: 404 contexto inexistente, 409 incoherencia, 422 consulta
inválida y 503 PostgreSQL no disponible, sin revelar detalles de conexión.
Contexto válido con ventana vacía devuelve 200 con insuficiencia explicada.

Respuesta `MarketSignalsResponse`:

- `analysis_version=3b1-v1`, `metrics_analysis_version=3a-v1`, precisión 40.
- Parámetros efectivos, contexto, ventana, puntos, coverage, quality y provenance.
- `price_deviation`: tipo/dirección, observado, mediana de referencia, diferencias
  con signo/absoluta/porcentual, evidencia y explicación legible.
- `historical_trend`: tipo/dirección, extremos, pendiente, cambios, evidencia y
  explicación legible.
- `warnings`: límites propios de las reglas. `quality.warnings` conserva los
  avisos de muestra/fuente/ventana de 3A; no son motivos automáticos de rechazo.

Cada número calculado reutiliza `MetricValue`: Decimal en Python y string fijo
en JSON, sin float, quantize ni exponentes. Los parámetros Decimal usan el mismo
formato fijo. La aritmética hereda explícitamente el contexto determinista de
3A: precisión 40, ROUND_HALF_EVEN, independiente del contexto del llamador.
"Sin pérdida" significa no introducir conversiones/recortes adicionales a esa
precisión de cálculo, no prometer representar exactamente decimales periódicos.

Ejemplo **exclusivamente simulado**, creado por los tests: ocho buckets 10..17,
precios `[100,100,100,100,100,100,100,80]`, mercado PvE de testing, item ficticio
123, source test-source y modo accumulated. Los IDs de mercado se obtienen de
la fixture aislada, no son IDs portables de desarrollo:

```text
GET /market/signals?market_id=<id_fixture>&item_key=123
  &source_id=test-source&source_type=simulated&temporal_basis=unknown
  &series_mode=accumulated&window_type=observed_buckets&size=8
```

Extracto ilustrativo; los campos MetricValue completos también incluyen unidad,
muestra, estado y límites de índices:

```json
{
  "analysis_version": "3b1-v1",
  "price_deviation": {
    "direction": "below_reference",
    "reference_method": "median_excluding_latest",
    "observed_price_copper": {"value": "80"},
    "reference_price_copper": {"value": "100"},
    "signed_deviation_copper": {"value": "-20"},
    "absolute_deviation_copper": {"value": "20"},
    "deviation_pct": {"value": "-20"},
    "evidence": {"status": "sufficient", "reasons": []}
  },
  "historical_trend": {"direction": "descending"}
}
```

Esto describe mínimos simulados, no confirma una oportunidad de compra.

## Contraejemplos y límites interpretativos

- `[0,...,0]`: diferencias/pendiente cero; neutral con porcentajes indefinidos.
- `[0,...,0,100]`: diferencias calculables, clasificación bloqueada por baseline
  cero; no se inventan porcentajes infinitos.
- 100 repetido siete veces seguido de 80/120: exactamente -20%/+20%, incluidos
  en el umbral. 81/119 quedan bajo el umbral de desviación.
- `[100,1000,900,800,700,600,500,120]`: cambio de extremos +20%, pero pendiente
  negativa; sin tendencia direccional, con advertencia de desacuerdo.
- Dos precios pueden dar un porcentaje enorme; ambas reglas siguen bloqueadas.
- Ocho precios densos frente a ocho índices muy dispersos: igual conteo,
  distinta pendiente y distinta suficiencia sobre el intervalo.
- Caída de disponibilidad máxima de 10000 a 0: no se usa para estas señales,
  no prueba ventas ni influye en la dirección.
- Mínimos 2147483647 frente a 2147483646: diferencia -1 exacta y porcentaje
  diminuto conservado en Decimal; umbral `1e-50` vuelve en notación fija.

La mediana y regresión operan sobre mínimos guardados sujetos a poda, selección
de muestras, extremos y asignación de bucket por sesión. Fallback h puede perder
mínimos y acumulados pueden ampliarse con imports posteriores. No hay inferencias
de demanda, ventas, volumen, liquidez, rentabilidad o recomendación automática.
La pendiente OLS es sensible a extremos; no se agrega regresión robusta ni
eliminación automática de outliers.
"Significativo" en los nombres de dirección significa alcanzar el umbral de
la regla; no es significancia estadística ni confianza probabilística.

## Validación ejecutada

Resultados:

| Ejecución | Resultado |
|---|---|
| Primera ejecución de los tres módulos nuevos | 86 passed |
| 3B.1 final (88 casos) y regresiones 3A (111 casos), siete módulos | **199 passed**, 75,58 s |
| Backend amplio, excluyendo integración PostgreSQL de trial | **478 passed**, 11 errores de preparación de temporales, 180,65 s |
| Repetición de los 11 casos CLI afectados, con temporales accesibles | **11 passed**, 7,20 s |
| Total de casos distintos cubiertos por la regresión amplia y su repetición | **489 aprobados** |
| OpenAPI servido y respuestas de ambos modos | Aprobado en pruebas HTTP puras e integración |
| Contratos OpenAPI existentes del frontend (`--check`) | OK, sin regenerar archivos |
| `git diff --check` y whitespace de los siete archivos nuevos | OK |

La ejecución amplia encontró un problema del entorno, no de aserciones:
`tmp_path` no podía recorrer directorios creados con permisos 0700 por Python
3.13 en Windows bajo el token del sandbox. Un basetemp nuevo por sí solo tampoco
lo resolvió. La repetición usa un wrapper transitorio de `os.mkdir` que hereda
los permisos normales **únicamente dentro de un nuevo árbol temporal UUID**.
Los 11 tests se ejecutaron completos, incluidos sus subprocesses CLI. No se
modifican tests existentes, código productivo, ACL de directorios previos o
configuración persistente para pasar la suite. El resto de la regresión amplia
ya había aprobado: no se presenta la primera corrida como una suite enteramente
verde ni se suman las 199 pruebas repetidas al total de 489.

Se excluyó explícitamente `test_trial_database_integration.py`: exige un
laboratorio provisionado y variables TRIAL_INTEGRATION_DATABASE_URL/NAME
autorizadas específicamente para ese laboratorio. Esta entrega no lo configura
ni reutiliza bases existentes para importar pruebas de trial. No forma parte
de los checks requeridos de 3B.1. Las pruebas unitarias de trial y sus 11 pruebas
de arranque CLI sí están incluidas en la cobertura ampliada.

Una advertencia preexistente de Starlette/httpx en las ejecuciones con TestClient;
no se cambia una dependencia para silenciarla.

Comandos principales, desde `backend` con TEST_DATABASE_URL dedicada ya configurada:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_market_signals.py tests/test_market_signals_validation.py tests/test_market_signals_integration.py tests/test_market_statistics.py tests/test_market_windows.py tests/test_market_validation.py tests/test_market_integration.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --ignore=tests/test_trial_database_integration.py
.\.venv\Scripts\python.exe -B ..\frontend\scripts\generate-api-contracts.py --check
git diff --check
```

Cobertura nueva: fórmulas y límites inclusivos, mediana sin el punto evaluado,
extremos, ceros/referencias cero, muestra 0/1/2 y pisos configurables, constantes,
pendiente ascendente/descendente/neutral y desacuerdo con extremos, huecos internos,
series densas/dispersas, cobertura exacta en el límite, ventana incompleta,
distancia al ancla, índices hasta 2147483647 y 366 puntos, origen y política l,
calendario conocido/desconocido, accumulated/export separados, reimports,
variantes/contextos, disponibilidad ajena a ventas, Decimal grande/fraccionario/
pequeño y contexto aritmético externo hostil. FastAPI valida parámetros, errores,
OpenAPI y respuestas reales PostgreSQL en esquemas aislados.

Las integraciones comprueban READ ONLY/REPEATABLE READ y un único análisis 3A
por request. Comparan byte a byte la respuesta de `/market/metrics` antes y
después de `/market/signals`, y verifican todas las tablas y secuencias de las
fixtures. Las regresiones 3A mantienen cobertura de descubrimiento, coherencia
de procedencia, calendarios y lectura repetible durante ingestión concurrente.

### Preservación de desarrollo

Antes de implementar se registraron, mediante transacción READ ONLY/REPEATABLE
READ, conteos y SHA-256 de filas `t::text` ordenadas en las 13 tablas de desarrollo,
y `last_value/is_called` de sus 11 secuencias. Comparación posterior idéntica;
no hubo importación, migración, update, reinicio o consumo de secuencias allí.

| Tablas | Filas antes/después |
|---|---:|
| schema_migrations | 4 |
| realms / items | 1 / 10 |
| auction_snapshots / auction_snapshot_items | 7 / 69 |
| import_runs | 10 |
| partial_markets / partial_items | 4 / 50 |
| partial_observations | 16.628 |
| partial_import_runs | 2 |
| partial_exports / partial_export_facts / partial_export_imports | 0 / 0 / 0 |

Las escrituras de integración se limitaron a la base dedicada cuyo nombre
termina en `_test`, distinta de desarrollo y validada por el guard existente.
Cada test crea/migra/elimina su esquema UUID con el fixture existente. Consulta
READ ONLY final: **cero esquemas test_ remanentes** en esa base. Los scripts y
fingerprints auxiliares están en temporales fuera del repositorio.

## Archivos y estado de entrega

Nuevos: `backend/app/market/signal_contracts.py`, `signal_service.py`, `signals.py`;
`backend/tests/test_market_signals.py`, `test_market_signals_validation.py`,
`test_market_signals_integration.py`; este informe.
Modificados: `backend/app/api/market.py`, README, ARCHITECTURE y ROADMAP.

No se modifican módulos de cálculo/selección/persistencia 3A, frontend, ingestión,
migraciones, dependencias, configuración o datasets. Sin commit ni push.
Git: HEAD permanece en el esperado; cuatro archivos existentes modificados y
siete nuevos, todos sin staging y dentro del alcance solicitado. No había
cambios ajenos al comenzar. Veredicto: **READY FOR REVIEW**.

Pendientes antes de validar con fuente real: SavedVariables auténticos de Forever,
ruta AH/codec nativo, reloj/base temporal, semántica de ceros, cobertura/poda,
fracciones ModernAH y revisión de umbrales en mercados reales. Los defaults no
demuestran idoneidad para trading. Integración UI, ranking comparable, alertas y
persistencia de señales quedan fuera de esta entrega.

## Correcciones finales tras auditoría focalizada — 2026-10-19

Esta sección actualiza el estado de la entrega inicial descrita arriba. La
auditoría encontró un HIGH de expansión Decimal y un MEDIUM de clasificación
por residuo de redondeo. Ambos se corrigen sin alterar las métricas públicas de
3A, contratos ajenos a 3B.1, frontend, ingestión, migraciones o datos. No hay
importaciones ni conexiones/escrituras PostgreSQL en esta validación final.

### HIGH: límites antes del formato fijo

La precisión del contexto Decimal limita aritmética, no `format(value, "f")`.
Los parámetros aceptaban exponentes compactos que podían convertirse en strings
enormes al devolverlos en la respuesta. Se agregan límites explícitos para los
cinco campos Decimal, tanto al validar como al serializar:

| Restricción | Límite |
|---|---|
| Texto de entrada por parámetro Decimal | Hasta 128 caracteres |
| Estimación conservadora de longitud fija, incluyendo signo y punto | Hasta 96 caracteres |
| Magnitud no cero mínima | `1e-64` |
| min_price_coverage / min_index_coverage | `1e-64 .. 1` |
| deviation_threshold_pct / trend_threshold_pct | `1e-64 .. 1e12` |
| min_trend_slope_copper_per_scan_index | Cero, o `1e-64 .. 2147483647` |

Los defaults permanecen iguales. El nuevo piso de configuración no es un
epsilon para las pendientes calculadas: no redondea ni convierte pendientes
pequeñas en cero. `1e-50` y los umbrales válidos con más de 40 dígitos siguen
admitidos dentro de estos límites. El tope porcentual 1e12 cubre incluso los
cambios posibles entre precios fuente enteros y referencias de mediana de medio
copper. El tope de pendiente cubre el máximo cambio de un precio fuente entre
índices distintos. Valores mayores no aportan umbrales útiles para este dominio.

El guard examina finitud, coeficiente y exponente sin generar formato fijo ni
usar normalize/quantize. Calcula una cota de longitud con enteros Python y
rechaza antes de formatear; también aplica una cota conservadora a ceros con
exponente enorme. La notación científica y la notación fija equivalentes pasan
si cumplen los límites; se conservan valor y ceros finales, sin normalización
silenciosa. Los ceros finales excesivos se rechazan aunque el valor numérico
sea equivalente a una representación corta.

Los errores usan mensajes constantes y conservan el input compacto. Los casos
HTTP con exponentes peligrosos devuelven 422 antes de llegar al servicio; sus
errores medidos tienen menos de 2048 bytes. También se protege el serializador
ante instancias construidas con model_construct/model_copy que omitan validación.
OpenAPI publica límites numéricos y la descripción de límites de representación.

Reproducción original corregida: `1e-50000`, `1e-1000000000` y exponentes
positivos enormes se rechazan sin expansión. Los tests interceptan la llamada
al formateador para verificar que las entradas peligrosas nunca lo alcanzan.
No se intentó generar cadenas de tamaño peligroso.

### MEDIUM: decisiones OLS exactas sin cambiar 3A

El cálculo descriptivo centrado de 3A puede dejar un residuo Decimal cuando la
covarianza exacta es cero. 3B.1 interpretaba cualquier residuo no cero como signo
de tendencia, porque el piso de pendiente por defecto es cero.

Se agrega exclusivamente el auxiliar `exact_ols_terms` en statistics.py. Para
los índices y precios enteros ya validados calcula, con enteros Python:

```text
N = n * sum(x_i * p_i) - sum(x_i) * sum(p_i)
D = n * sum(x_i * x_i) - sum(x_i)^2
```

Con al menos tres índices distintos, D es positivo. Se resta el primer índice
antes de sumar para reducir operandos; esa traslación conserva N y D. No hay
redondeo y el signo de N determina exactamente el signo de la pendiente. No
se aumenta la precisión ni se agrega un epsilon.

Las seis funciones existentes de 3A permanecen idénticas, incluido linear_slope.
La respuesta sigue mostrando su MetricValue descriptivo sin cambios. Las
decisiones de 3B y el warning de desacuerdo con los extremos usan el signo exacto.
Cuando N es cero la dirección es neutral y la explicación lo indica, aunque la
pendiente descriptiva muestre un residuo. Esto evita cambiar silenciosamente
la salida publicada de /market/metrics.

Para comparar el umbral de pendiente `t = a/b`, obtenido exactamente mediante
Decimal.as_integer_ratio, se evalúa `abs(N)*b >= a*D` con enteros. Así el límite
es inclusivo y respeta también umbrales con más dígitos que el contexto Decimal.
La condición sobre el cambio porcentual de extremos sigue reutilizando la
métrica de 3A y su precisión publicada. Se exigen N no cero, signo coherente con
ese cambio y los mismos requisitos de evidencia; no se habilitan señales por
carecer de observaciones, cobertura, origen requerido o precio cercano al ancla.

Contraejemplo original, índices 100..114:

```text
[100,299,103,117,92,80,94,117,153,97,114,161,150,169,130]
N/D exacto = 0/4200
MetricValue 3A conservado = 7.142857142857142857142857142857142857143e-40
Cambio entre extremos = +30%
Nueva dirección 3B = no_significant_trend
Evidencia = sufficient
```

El residuo anterior se muestra aquí en notación compacta para lectura; en JSON
continúa serializado como string fijo. La serie inversa `400-p_i` también
clasifica neutral. Al aumentar en uno el precio de la posición 8 y separar
índices por 140000000 se obtiene pendiente genuina `1/39200000000`; se mantiene
la dirección ascendente cuando la cobertura dispersa está permitida
explícitamente. Su reflejo conserva la dirección descendente. No se eliminan
pendientes verdaderas pequeñas por un epsilon arbitrario.

### Validación de las correcciones

**255 tests aprobados** en cinco módulos: test_market_signals.py,
test_market_signals_validation.py, test_market_statistics.py,
test_market_windows.py y test_market_validation.py. Incluyen las 153 pruebas
previas pertinentes y 102 casos de regresión nuevos. Una advertencia preexistente
Starlette/httpx; sin skips ni xfails. Se bloqueó psycopg.connect durante toda la
ejecución para garantizar que estas pruebas no acceden a PostgreSQL.

Los tests nuevos cubren los cinco parámetros, strings y Decimal directos,
exponentes extremos de ambos signos, ceros de exponente extremo, NaN/sNaN e
infinitos, límites exactos y valores inmediatamente fuera, notaciones equivalentes,
preservación de dígitos, errores acotados, serialización con validación omitida,
HTTP 422 antes del servicio y respuestas válidas contra OpenAPI. La cobertura
matemática incluye el contraejemplo, constantes, pendientes pequeñas de ambos
signos, índices dispersos, huecos, copper grande, ejes inválidos y umbrales
inclusivos con dígitos más allá de la precisión 40. Los tests previos conservan
la comprobación de signos opuestos entre pendiente y extremos.

Dos aserciones iniciales nuevas confundían igualdad de valor con igualdad de
exponente después de formatear `1e12` como string fijo. Se corrigieron para
comprobar el valor exacto serializado y la representación original en Python;
no se modificó el código productivo para acomodarlas.

Contraste independiente adicional: **360 series** de índices altos irregulares,
con numerador/denominador racional calculado aparte. Todas las decisiones de
dirección coinciden y el JSON completo de métricas 3A es idéntico al obtenido
con el código de HEAD. Comparación AST: las **seis funciones originales de 3A**
son idénticas; sólo se añadió el auxiliar. HTTP en memoria confirma neutralidad
del contraejemplo y respuesta /market/metrics idéntica antes/después de señales.
OpenAPI de respuestas nuevas y contratos existentes del frontend: OK, sin
regenerar archivos. `git diff --check`: OK.

No se reejecutaron suites enteras ni integraciones que importan fixtures o
escriben esquemas/bases. No hubo conexiones PostgreSQL ni importaciones, y por
tanto no hubo modificaciones a tablas, filas o secuencias en esta corrección.

Archivos tocados en esta corrección: signal_contracts.py, signals.py,
statistics.py, test_market_signals.py, test_market_signals_validation.py y este
informe. Los demás cambios de la entrega inicial se conservan. Estado acumulado:
cinco archivos existentes modificados y siete nuevos, sin staging; HEAD sigue
en a4852586b71aa3be41a5692d22b91283cd66a7fa. Sin commit ni push.

No se detectaron regresiones funcionales en las comprobaciones ejecutadas.
Continúan los límites de evidencia l/h_fallback y accumulated, la sensibilidad
OLS a outliers y los pendientes de datos auténticos. Accumulated admite revisión
de extremos por imports tardíos y no es un backtest inmutable ni un precio
actual garantizado. No se agregan inferencias de ventas, demanda o rentabilidad.

Veredicto final de estas correcciones: **READY TO COMMIT**.
