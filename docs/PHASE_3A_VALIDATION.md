# Fase 3A — Market Intelligence descriptivo

Entrega del 2026-10-13. Alcance: análisis de evidencia parcial existente, sin
Fase 3B, frontend, oportunidades, predicciones, ML, agentes o herramientas de IA.
No se modifican migraciones 001–004 ni se agregan dependencias o tablas.

## Arquitectura y archivos

Nuevos módulos en `backend/app/market/`: `contracts.py`, `errors.py`,
`repository.py`, `series.py`, `windows.py`, `statistics.py`, `quality.py` y
`service.py`. Router nuevo `backend/app/api/market.py`; registro en `app/main.py`.
Tests nuevos: `test_market_statistics.py`, `test_market_windows.py`,
`test_market_validation.py` y `test_market_integration.py`.
README, ARCHITECTURE y ROADMAP documentan la implementación y separan 3A/3B.

El servicio inicia una transacción `READ ONLY, REPEATABLE READ` antes del primer
SELECT. SQL parametrizado resuelve contexto, eje del mercado y evidencia;
funciones puras arman ventanas/puntos, calculan métricas y diagnósticos.
La validación de procedencia incluye los contextos de primer/último import del
acumulado, versiones 340/8 y el primer vínculo del export sellado.
Incoherencias de identidad, mínimos/máximos, alias de día o manifest se rechazan.

## Fuentes y procedencia

- `accumulated`: 003, extremos acumulados entre imports compatibles. Nunca se
  presenta como último estado del addon; origen l/h desconocido.
- `export`: hechos de exactamente un estado sellado, con identidades copiadas
  y manifest. Mínimo l si existe, de lo contrario h; origen l/h_fallback explícito.
- La 004 vacía no bloquea acumulados ni se rellena/reconstruye durante consultas.
- Mercado (región/clave/dataset), item completo, source_id/type, base y modo son
  identidades independientes. No se unen fuentes ni versiones incompatibles.
- Recepciones e IDs no establecen cronología de scans. Vínculos repetidos no
  multiplican puntos. m se cuenta aparte por contexto del item y se excluye.
- Los puntos referencian IDs de observaciones o hechos. En acumulados enlazan
  primer/último import que creó/cambió el valor, no la última recepción.
- `selected_daily_row_count` cuenta filas nativas/acumuladas de la ventana,
  sin duplicar h al proyectarlo como mínimo. La muestra estadística cuenta buckets.

## Ventanas y cobertura

`observed_buckets` selecciona los últimos N índices distintos del mercado/contexto,
antes de filtrar el item. Un rango `index_range` incluye ambos límites y conserva
posiciones sin evidencia. `calendar_days` requiere base conocida con timezone y
7/14/30 posiciones consecutivas representables. Máximo 366 posiciones; rangos
mayores se rechazan, no se truncan.

El ancla por defecto es el último bucket del mercado; puede fijarse con end_day.
No es el último precio del item ni la fecha de hoy. Una base ISO se normaliza a
UTC para seleccionar la misma identidad almacenada; unknown no se convierte.
Cada comienzo derivado es base + índice * 86400 segundos, no un timestamp de scan.
Los buckets están sujetos al índice fijo por sesión; no se garantizan días civiles
del cliente o scans dentro del intervalo correspondiente. Calendario fuera de
rango devuelve 422; ventanas por índice conservan el índice y bucket_start null.

Cobertura de precio/disponibilidad = buckets con ese dato / posiciones seleccionadas.
En buckets observados el denominador excluye índices sin evidencia del mercado;
el tamaño del intervalo de índices y sus huecos se devuelven por separado.
En rangos y días el denominador incluye todas las posiciones, aun sin evidencia.
Con eje vacío la cobertura es null/no_axis; con eje y cero datos es cero.
La cobertura no mide porcentaje del mercado capturado. Ausencias no distinguen
poda, falta de scans, falta de imports o falta del item; nunca se imputan como cero.

## Definiciones exactas

Sean p los mínimos guardados no null, d sus índices y n su cantidad. Cada bucket
tiene el mismo peso, sin ponderar por scans/imports/disponibilidad desconocidos.

| Campo | Fórmula / significado | Muestra y excepciones |
|---|---|---|
| minimum_copper | min(p) | n>=1; sin dato null/no_data |
| mean_daily_minimum_copper | sum(p)/n | n>=1; no es promedio de subastas |
| median_daily_minimum_copper | central ordenado; promedio de dos centrales si n par | n>=1; puede ser fraccionaria |
| first/last_minimum_copper | Primer/último precio por índice | n>=1; sus índices son explícitos |
| price_change_copper | último - primero | n>=2; no se divide por la cantidad de días |
| price_change_pct | 100*(último-primero)/primero | n>=2; baseline cero => null/zero_baseline |
| minimum_stddev_copper | sqrt(sum((p-mean)^2)/(n-1)) | n>=2; desviación muestral de niveles |
| minimum_cv_pct | 100*stddev/mean | n>=2; mean cero => null/zero_mean |
| trend_copper_per_scan_index | sum((d-dmean)*(p-pmean))/sum((d-dmean)^2) | n>=3; eje degenerado/duplicado => null/invalid_axis |
| first/last_max_available | Extremos cronológicos de valores a explícitos | al menos 1 disponibilidad; índices propios |
| availability_change_units | a_último-a_primero | al menos 2 disponibilidades |
| availability_change_pct | 100*(a_último-a_primero)/a_primero | al menos 2; baseline cero => null/zero_baseline |

Derivados calculados en contexto Decimal explícito de precisión 40 y ROUND_HALF_EVEN,
independiente del contexto del llamador, y serializados como strings en notación
decimal fija sin exponentes. No hay escala fija ni conversión silenciosa a copper entero. Valores fuente
son enteros estrictos. No se devuelve NaN o Infinity. Estados: ok, no_data,
insufficient_data, undefined; los tres últimos incluyen motivo y valor null.

Limitaciones: mínimos guardados no garantizan el mínimo de todos los scans;
fallback h puede perder un mínimo anterior. Acumulados pueden ampliarse con imports
posteriores. Mediana/promedio describen solamente buckets con dato, sujetos a
ausencias selectivas. Desviación/CV incluyen tendencias: no son retornos diarios
ni volatilidad intradía. La pendiente no es una predicción o prueba de significancia.
a es un máximo por bucket, no necesariamente simultáneo al mínimo; no se suma
como ventas, demanda, liquidez o volumen transaccionado.

## Calidad y contratos

Las respuestas incluyen contexto, ventana resuelta, puntos (null explícitos),
métricas con unidad/muestra/estado, cobertura, referencias de evidencia y warnings.
`analysis_version=3a-v1` identifica estas definiciones. No se persisten métricas.

Los diagnósticos distinguen dataset simulado, calendario desconocido/no representable,
muestra menor de siete, ventana incompleta, huecos del eje, ausencias por métrica,
extremos observados interiores, cero explícito, origen desconocido, fallback h y
evidencias sin fecha excluidas. Siete es un umbral de presentación, no garantía
de confiabilidad. No hay score global o estimación de autenticidad/cobertura real.
El manifest distingue a ausente frente a presente sin hechos; 003 declara unknown.

GET /market/series requiere market_id e item_key normalizada; permite filtrar modo
y paginar limit 1..100/offset. Lista contextos con límites, presencia y recepción
separada. Su orden declarado no es cronología del mercado.

GET /market/metrics requiere market_id, item_key, source_id, source_type,
temporal_basis, series_mode y window_type. accumulated prohíbe export_id;
export lo exige. observed_buckets requiere size; index_range start_day/end_day;
calendar_days days=7/14/30. Parámetros extra/incompatibles devuelven 422.
Contexto inexistente =>404; incoherente=>409; PostgreSQL no disponible=>503.
Un contexto válido sin datos en la ventana devuelve 200 con métricas no_data.
Un manifest malformado de un export seleccionado devuelve 409. En descubrimiento,
el recorrido JSON comprueba tipos antes de expandir arrays; un export corrupto
sin relación con el mercado/item consultado no impide listar contextos válidos.

## Validación ejecutada

Docker Desktop inicialmente detenido; PostgreSQL no respondía. Después del inicio
por el usuario, `docker compose ps` confirmó el contenedor existente saludable y
la conexión PostgreSQL respondió. backend/.env no existía: se creó ignorado con
TEST_DATABASE_URL solamente, usando la conexión local y la base existente
wow_forever_companion_test. DATABASE_URL no se sobrescribió.

Se ejecutó el procedimiento documentado `scripts/setup_test_database.py`: aplicó
la 004 pendiente exclusivamente en la base de testing existente. Cada integración
crea/migra/elimina su propio esquema aleatorio según conftest.py. No se recreó o
limpió desarrollo ni se importaron nuevos datos allí.

Ejecuciones focalizadas: **64 tests puros/HTTP aprobados**, **16 tests nuevos de
integración aprobados**. Suite completa: **312 passed**, 205,35 segundos, sin
skips/xfails. Una advertencia existente de Starlette sobre httpx en TestClient;
no se cambió una dependencia para silenciarla.

```powershell
# Desde backend, TEST_DATABASE_URL dedicada configurada:
.\.venv\Scripts\python.exe -B scripts/setup_test_database.py
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

Casos cubiertos: fórmulas manuales; muestras 0/1/2; bases cero; desviación muestral;
precisión fraccionaria; huecos reales en pendiente; calendarios/bases/overflow;
errores HTTP; ejes incoherentes; a ausente/vacío/cero y l/h_fallback; variantes;
fuentes/regiones/datasets/modos separados; estados exportados distintos;
reimports; catálogo mutable frente a identidades copiadas; restricciones READ ONLY;
lectura repetible durante ingestión concurrente; simulación de 16.628 filas con
004 vacía y preservación de Fase 2.

## Consulta real sin mocks

TestClient ejecutó los endpoints con el servicio y las conexiones PostgreSQL reales
de desarrollo, en READ ONLY. No hubo mocks de persistencia ni imports. Mercado PvE
simulado, región simulation, ID local 2; item ficticio 1900000000.

```text
GET /market/metrics?market_id=2&item_key=1900000000
  &source_id=fresh-seed-340&source_type=simulated&temporal_basis=unknown
  &series_mode=accumulated&window_type=observed_buckets&size=30
```

Respuesta real 200, resumida (los campos value son strings en el JSON completo):

| Resultado | Valor |
|---|---|
| Índices / cantidad de precios | 2500..2529 / 30 |
| Mínimo guardado | 55 copper |
| Promedio | 72.06666666666666666666666666666666666667 copper |
| Mediana | 69.5 copper |
| Primer / último mínimo | 73 / 57 copper |
| Cambio absoluto | -16 copper |
| Cambio porcentual | -21.91780821917808219178082191780821917808 % |
| Desviación muestral | 13.34149175687826052755057208186855364448 copper |
| CV | 18.51270826578852062102299548825423724951 % |
| Pendiente | -0.9890989988876529477196885428253615127920 copper/scan_index |
| Primera / última disponibilidad máxima | 377 / 914 unidades |
| Cambio disponibilidad | 537 unidades |
| Cobertura precio / disponibilidad | 1 / 1 |
| Filas diarias / evidencia sin fecha excluida | 90 / 1 |

Contraste independiente con SELECTs de valores crudos y Fraction, sin usar las
funciones estadísticas del motor: sum(p)=2162, n=30; promedio=1081/15;
mediana=139/2; cambio=57-73=-16; porcentaje=100*(-16)/73;
pendiente=(n*sum(d*p)-sum(d)*sum(p))/(n*sum(d*d)-sum(d)^2)=-4446/4495.
Se compararon automáticamente contra Decimal con tolerancia 1e-33.

La consulta /market/series devolvió solo modo accumulated: las tablas nativas
seguían vacías. Todos los bucket_start eran null y el origen del mínimo unknown.
Esto verifica el escenario real requerido sin asignarle un calendario ficticio.

## Evidencia local y preservación

Artefactos ignorados en data/imports/: phase3a_before.json y phase3a_after.json
(hashes/conteos/secuencias), phase3a_real_response.json (respuesta completa)
y phase3a_discovery.json.
Los artefactos no se incorporan a Git. Ningún archivo SavedVariables auténtico
fue utilizado. Fracciones ModernAH, codec nativo, ruta de AH, reloj, cobertura
y poda reales siguen pendientes de validación; no se amplió el parser.

Comparación final READ ONLY antes/después: los fingerprints de las 13 tablas
revisadas y las 11 secuencias de desarrollo son idénticos. Métodos: filas t::text
ordenadas por PK, JSON de dict_rows y SHA-256; secuencias last_value/is_called.

| Tabla | Filas antes/después |
|---|---:|
| schema_migrations | 4 |
| realms / items | 1 / 10 |
| auction_snapshots / auction_snapshot_items | 7 / 69 |
| import_runs | 10 |
| partial_markets / partial_items | 4 / 50 |
| partial_observations | 16.628 |
| partial_import_runs | 2 |
| partial_exports / partial_export_facts / partial_export_imports | 0 / 0 / 0 |

Hash de partial_observations con el método anterior, idéntico antes/después:
`15c385c9d27180da5509850e53362842642619bb4b097a21eb068b078c38024c`.
No quedaron esquemas temporales test_ en la base dedicada. No hubo migraciones,
imports, updates o reinicios de secuencias en desarrollo.

Git: cuatro archivos existentes modificados (README, ARCHITECTURE, ROADMAP y
app/main.py), catorce archivos nuevos (ocho módulos de market, router, cuatro
módulos de tests e informe). backend/.env y evidencia local permanecen ignorados.
No se hizo commit ni push. Veredicto de la entrega inicial: **READY FOR AUDIT**.

## Hardening final tras auditoría adversarial — 2026-10-13

Se corrigieron los tres hallazgos MEDIUM y el LOW dentro de Fase 3A. Sin nuevas
funcionalidades, migraciones, dependencias, caché global, commit o push.

1. `MetricValue.value` conserva el patrón Decimal publicado por OpenAPI y usa
   `format(value, "f")` exclusivamente al serializar JSON. Cero, exponentes
   pequeños, negativos y muchos decimales preservan el valor sin quantize ni float.
   En Python el contrato sigue entregando Decimal; null sigue siendo null.
2. El descubrimiento obtiene acumulados y exports mediante consultas por lotes.
   Las consultas individuales reutilizan esas mismas validaciones. Se conservan
   contexto de mercado/fuente/base, primer y último import, recepción del export,
   identidades copiadas, presencia de campos, l/h/a y límites del eje.
   Los joins de procedencia apuntan a claves únicas y no multiplican hechos.
3. El manifest valida explícitamente objeto, versión entera, arrays, formas,
   identidades únicas y límite estructural antes de interpretarlo. El SQL protege
   cada jsonb_array_elements con CASE/jsonb_typeof. Un export incoherente incluido
   en la selección devuelve 409, incluso si sus hechos faltan del manifest.
   Un export corrupto sin relación con el mercado/item pedido no bloquea el
   descubrimiento; consultas directas de otros exports válidos siguen disponibles.
4. Estadísticas y cobertura utilizan un Context nuevo con precisión 40,
   ROUND_HALF_EVEN, límites explícitos y traps controlados. No heredan rounding,
   traps, límites o flags externos, ni modifican el estado del llamador.

### Rendimiento SQL verificado

Consultas de lectura por petición, excluyendo SET TRANSACTION en ambas mediciones:

| Series exportadas de la página | Antes de hardening | Después |
|---:|---:|---:|
| 1 | 9 | 5 |
| 10 | 72 | 5 |
| 100 | 702 | 5 |

Acumulados: 4 consultas para páginas de 1/10/100 contextos. Páginas con ambos
proveedores: máximo 7, sin crecimiento por cada contexto. Los límites, offset,
has_more y el orden previo se conservan; también se probaron 100 contextos de
un item vacío presente solamente en manifests. Los tiempos locales observados para páginas
de 100 fueron 0,1204 s en export, 0,1003 s en accumulated y 0,1371 s en mixtas.
El costo de leer/validar filas y manifests todavía depende del tamaño de la
evidencia; el presupuesto acota viajes SQL, no garantiza latencia constante.

### Regresiones y validación final

Se agregaron **31 casos de test** en los tres archivos existentes
test_market_statistics.py, test_market_validation.py y test_market_integration.py.
Incluyen notación fija y preservación de dígitos, contexto externo hostil,
respuestas completas de ambos endpoints contra el OpenAPI servido, presupuesto
SQL 1/10/100, manifests malformados, hechos incompatibles y primer/último import.
El comprobador de OpenAPI usa Python estándar, resuelve referencias y comprueba
los keywords emitidos por estos contratos; falla ante keywords desconocidos.
También demuestra que el esquema rechaza la respuesta anterior con "0E-39".

Se ejecutaron primero 72 tests puros/HTTP, 37 integraciones y luego 10 regresiones
focalizadas que incluyeron los dos casos adicionales de procedencia acumulada.
La primera suite completa detectó una aserción errónea del test nuevo: exigía
flags externos vacíos en lugar de conservar los preexistentes. Se corrigió el
test, se repitieron los 72 tests puros/HTTP y se ejecutó nuevamente toda la suite.
Resultado final: **343 passed**, **247,20 segundos**, sin skips/xfails; una
advertencia preexistente Starlette/httpx. No se alteró código productivo para
borrar flags del llamador ni silenciar esa advertencia.

Contraste independiente posterior al hardening: **864 comparaciones** sobre
**108 series controladas y 12 series simuladas existentes**, usando Fraction y
Decimal de 90 dígitos. Error relativo máximo 4,95e-39, por debajo de 1e-36.
Las 12 respuestas reales de desarrollo también cumplieron el OpenAPI servido.
Ventanas, separación de fuentes/modos, idempotencia, READ ONLY/REPEATABLE READ,
concurrencia y las APIs anteriores quedaron cubiertas por la suite completa.

Comparación READ ONLY antes/después del hardening: conteos y hashes de filas
(MD5 de t::text ordenado) idénticos en las **13 tablas de desarrollo**, incluyendo
las **16.628 observaciones simuladas** y las tres tablas nativas todavía vacías.
Las **11 secuencias** conservaron sus valores de pg_sequences, y los SHA-256 de
las **migraciones 001–004** son idénticos. Sin schemas test_ remanentes en la base
dedicada. Toda escritura de pruebas se ejecutó allí, en schemas UUID aislados;
desarrollo sólo recibió lecturas. DATABASE_URL y TEST_DATABASE_URL no se cambiaron.

Archivos ajustados en este hardening: market/contracts.py, repository.py,
statistics.py y quality.py; los tres módulos de tests indicados; README,
ARCHITECTURE y este informe por el formato JSON y el comportamiento HTTP públicos.
Sin hallazgos pendientes de los cuatro auditados. SavedVariables auténticos,
fracciones ModernAH, codec y los demás límites de Auctionator permanecen como
pendientes conocidos; los timeouts operativos no forman parte de estas correcciones.

Veredicto final: **READY TO COMMIT**. No se hizo commit ni push.
