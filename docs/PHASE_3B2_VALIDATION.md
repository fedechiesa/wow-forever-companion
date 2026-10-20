# Fase 3B.2 — Señales de mercado en el dashboard

Implementación del 2026-10-20 sobre `3f8859a` (3B.1 publicada). El usuario confirmó
la aprobación visual de la presentación g/s/c y solicitó el ajuste final de copper
indivisible, documentado al final. Estado vigente: **READY FOR UX REVIEW** para ese
ajuste, sin cerrar la fase ni publicar cambios. Las políticas y veredictos de las
entregas anteriores se conservan como registro histórico y quedan actualizados
por la última sección.

## Alcance y componentes

Se mantiene el flujo Mercado → Item → gráfico, métricas y señales automáticas.
No hay rediseño, pantalla separada, rankings, alertas, Profession Planner,
dependencias nuevas, nombres de items ni iconos inventados. Opciones avanzadas
permanece inicialmente cerrada.

Nuevos:

- `frontend/src/features/market/MarketSignals.tsx`: sección integrada y dos tarjetas,
  estados independientes, explicaciones, motivos y detalles de evidencia/valores.
- `frontend/src/features/market/signals.ts`: etiquetas españolas de direcciones,
  motivos y advertencias; comparación de contexto, ventana y evidencia.
- Este informe.

Modificados:

- `App.tsx`: consulta independiente de señales con los mismos parámetros y debounce.
- `MarketResults.tsx`: espacio para señales inmediatamente después del gráfico.
- `api/client.ts`, `api/backend.ts`, `api/contracts.ts`: cliente GET y validación runtime.
- `scripts/generate-api-contracts.py`, `api/generated.ts`, `api/response-schemas.json`:
  incorporación del modelo real `MarketSignalsResponse` y sus dependencias al
  generador frontend existente, sin modificar el contrato del servidor.
- `styles.css`: sección y tarjetas con colores, tipografía y disclosures existentes;
  dos columnas en escritorio amplio y una en anchos menores.
- `tests/app.test.mjs`, `tests/live.test.mjs`, `tsconfig.test.json`: cobertura focalizada.
- README y ROADMAP: estado, alcance y pendiente visual.

Se reutilizan `StatusPanel`, `MetricCard`, `ExactValue`, `useResource`, el scheduler,
la resolución de contexto y la query de métricas. Backend, contratos Python,
ingestión, migraciones, configuración, dependencias y datasets no se modifican.

## Integración, contrato y coherencia

Se inspeccionaron componentes, cliente, schemas, scheduler, estados y el informe
3B.1 antes de implementar. El router real declara `GET /market/signals` con
`SignalsQuery` y `MarketSignalsResponse`; el generador importa `app.openapi()`
sin conectar a PostgreSQL. Los nuevos contratos runtime se generan desde esos
schemas. También se probaron respuestas HTTP reales del backend local.

Métricas y señales reciben exactamente `plan.params`: mercado (y su dataset),
clave completa del item/variante, fuente/tipo, base temporal, modo, export_id
cuando corresponde y todos los parámetros de ventana/ancla. No se ofrecen
controles estadísticos adicionales: los parámetros omitidos usan los defaults
validados del backend y la UI conserva los parámetros efectivos devueltos.

Defaults verificados vía HTTP: 7 precios anteriores para desviación, 7 precios
para tendencia, coberturas `0.8`/`0.5`, umbrales `20`/`10`, piso de pendiente `0`,
distancia máxima al ancla 0, sin exigir l nativo o calendario conocido.

Ambas consultas se programan con debounce de 200 ms. La clave contiene la
consulta completa y su contador de reintento. `useResource` oculta inmediatamente
resultados de otra clave, cancela con AbortController y evita publicar éxitos o
errores tardíos incluso si el fetcher ignora la cancelación. Se mantiene la
supresión de solicitudes duplicadas por replay de React StrictMode.

Además de comprobar la identidad solicitada, antes de mostrar señales junto al
análisis se comparan íntegramente `context`, `window`, `points`, `coverage`,
`quality` y `provenance`. El orden de las propiedades no altera la comparación.
Esto detecta también imports entre dos transacciones GET independientes. Ante
diferencias se conservan gráfico/métricas, se ocultan las clasificaciones y se
ofrece recargar ambas consultas. No se promete atomicidad entre endpoints ni se
crea un snapshot persistente.

## Direcciones, estados y semántica

Desviación distingue `below_reference`, `above_reference`,
`no_significant_deviation` e `insufficient_evidence`. Tendencia distingue
`ascending`, `descending`, `no_significant_trend` e `insufficient_evidence`.
La UI utiliza la clasificación del motor: no la reconstruye desde el signo
de un porcentaje o una pendiente descriptiva con posibles residuos Decimal.

Se muestran magnitudes porcentuales y, en detalles cerrados, precios de
referencia/extremos, diferencia monetaria, magnitud absoluta y pendiente. Cada
regla conserva una explicación legible en español y la original del motor
accesible en detalles. La evidencia muestra suficiencia, conteos y todos los
motivos estructurados traducidos con sus códigos visibles. Ratios, distancia al
ancla y conteos l/h_fallback/unknown permanecen accesibles en detalles.

| Estado | Comportamiento |
|---|---|
| Loading de señales | Sección con `aria-busy` y estado de carga; análisis disponible |
| Error HTTP/red/contrato | Error local y reintento exclusivo de señales |
| Ventana sin precios | Mensaje de ausencia y ambas reglas insuficientes con motivos |
| Evidencia insuficiente | No se muestra dirección clasificable; conserva valores descriptivos |
| Neutral | Etiquetas específicas por regla; no prueba estabilidad de precios interiores |
| Cambios rápidos | Oculta el contexto anterior y cancela/descarta respuestas obsoletas |
| Evidencia divergente | Oculta señales y ofrece recargar métricas y señales |

Todas las direcciones comparten el mismo estilo neutral; no hay semáforo de
compra/venta. El aviso SIMULATED queda visible junto a las señales. Se aclara que
son mínimos históricos guardados, sujetos a cobertura/poda, y no oferta actual,
ventas, demanda, volumen vendido, liquidez o rentabilidad. Los umbrales son reglas
de magnitud, no significancia estadística ni confianza probabilística.

Accumulated reúne extremos de imports compatibles y puede revisarse con imports
posteriores: no es una reconstrucción histórica inmutable ni un estado único.
Export corresponde al estado sellado explícitamente elegido, con posible fallback
h. La procedencia 3A y las referencias por bucket siguen disponibles. Los índices
sin base temporal verificada no se convierten en días transcurridos; la pendiente
siempre se expresa en copper/índice.

Los valores monetarios y estadísticos Decimal permanecen como strings; no hay
aritmética económica ni conversión nueva a Number. Se reutiliza la presentación
exacta existente (BigInt para monedas y strings para fracciones), truncamiento
marcado con `…`, title y disclosure del valor completo. Cero no equivale a null;
un porcentaje indefinido no se convierte en cero o infinito.

## Validación ejecutada

| Check | Resultado |
|---|---|
| `npm test` | **74 aprobados**: 42 de funciones/componentes existentes y 32 montados |
| `npm run test:live` | **6 aprobados**: 4 regresiones existentes y 2 integraciones de señales |
| `npm run build` | TypeScript y Vite producción aprobados |
| Generador OpenAPI `--check` | OK |
| `git diff --check` | OK |

Se agregan 22 casos montados. Incluyen las ocho direcciones, evidencia suficiente
e insuficiente, los diez códigos de motivo, ausencia de precios, cero, porcentajes
indefinidos, fracciones diminutas y valor Decimal exacto, rechazo de Decimal
numérico/dirección inválida, mismos parámetros para ambos endpoints, variante,
fuente, exportaciones 41/42 explícitas, base temporal conocida, ventana calendario,
cancelación por item/mercado/ventana, éxito y error fuera de orden, error parcial
503 y de contrato, reintento sin refetch de métricas, preservación de los mismos
nodos de gráfico/métricas y coherencia de las seis partes del snapshot.
Accesibilidad básica: encabezados asociados por aria-labelledby, aria-busy,
roles de estado/alerta, controles nativos y disclosures operables; no es una
auditoría completa con lector de pantalla.

Las 6 integraciones usan exclusivamente GET sobre datos existentes de desarrollo.
PvE / item `1900000000` / fuente `fresh-seed-340` / accumulated / unknown / 30
buckets conserva promedio `72.06666666666666666666666666666666666667`, mediana
`69.5` y cobertura 30/30. Desviación `-18.57142857142857142857142857142857142857`
clasifica `no_significant_deviation`, tendencia `descending`, evidencia suficiente
para ambas reglas. Se comprueba igualdad de evidencia entre endpoints y respuesta
de métricas idéntica antes/después. También vacío, 404 y 422.

Una primera prueba nueva falló por alias entre campos MetricValue de la fixture
JavaScript; se corrigió la fixture para reproducir objetos independientes de JSON
HTTP. No se alteró código productivo para acomodar ese fallo. El primer build en
sandbox encontró `spawn EPERM` al iniciar esbuild; el mismo comando autorizado
fuera de esa restricción pasó. No se modificaron dependencias o configuración.

No se ejecutan suites backend que crean/importan/eliminan esquemas de integración,
para respetar la restricción de no alterar PostgreSQL. No se ejecutan imports,
migraciones, POST, UPDATE, DDL o consumos de secuencias. No se afirma una auditoría
de hashes de la base: las verificaciones realizadas son de solo lectura.

## Captura real, limitaciones y pendiente

Se inició FastAPI local en `127.0.0.1:8000` y Vite en `localhost:5173` para la revisión.
El control de navegador no encontró superficies disponibles. Se intentó la
habilidad computer-use con Chrome de Windows; Computer Use se detuvo porque no
pudo determinar con suficiente certeza la URL actual del navegador para aplicar
su política. Se interrumpió la automatización visual, sin intentar eludir ese
bloqueo. **No se obtuvo una captura real ni se presenta un mock como captura.**

Pendiente antes de cerrar: abrir el dashboard, seleccionar PvE e item 1900000000,
revisar y capturar gráfico más señales, inspeccionar ancho reducido y obtener la
aprobación UX del usuario. El layout responsive se implementa en CSS, pero jsdom
no lo dibuja: no hay validación visual de escritorio/móvil en esta entrega.

Continúa pendiente el primer archivo auténtico de Auctionator Forever, esperado
para intentar su obtención el 2026-10-21. Los datos y umbrales actuales no validan
comportamiento real ni oportunidades de trading. Exports/calendario se cubren con
fixtures sintéticas; desarrollo no contiene exportaciones para integración real.
No se incorporan reglas nuevas, persistencia de señales o garantías de snapshot
atómico entre endpoints.

## Git y veredicto

HEAD permanece en `3f8859a`; el árbol estaba limpio al comenzar. Todos los cambios
de esta fase son frontend, README, ROADMAP y este informe, sin staging. Backend,
migraciones, ingestión y datasets sin cambios. Sin commit ni push.

Veredicto: **NOT READY FOR UX REVIEW**. Implementación y checks automatizados
aprobados; falta entregar la captura real solicitada y realizar la revisión
visual. La fase no se considera cerrada.

## Mejora de presentación — moneda WoW (2026-10-20)

Esta mejora se realiza sobre la integración 3B.2 local anterior, conservando sus
cambios sin staging. El alcance es exclusivamente visual: no cambia ninguna
respuesta API, fórmula, clasificación, magnitud de señal, selección, ventana o
estado de carga/error. Tampoco oculta métricas ni reordena el contenido.

### Utilidad y componentes

Nuevos `frontend/src/features/market/currency.ts` y
`frontend/src/components/MoneyValue.tsx`. La utilidad ofrece:

- `splitCopper`: valida y separa signo, oro, plata, cobre y fracción con strings y
  BigInt. Retiene el string original, incluidos signo, ceros iniciales y finales.
- `presentCopper` / `formatCopper`: tokens por denominación y texto compacto g/s/c,
  omitiendo denominaciones enteras en cero. Cero completo se muestra como `0c`.
- `formatCopperAxis`: etiquetas SVG en una única denominación, con todos los
  decimales necesarios para expresar exactamente cada tick entero.

Equivalencias: 1g = 10.000 copper, 1s = 100 copper. Los precios observados nativos
ya llegan como enteros seguros según el contrato; únicamente esos enteros pueden
entrar como Number. Un número fraccionario, inseguro, NaN o infinito se rechaza.
Las métricas derivadas siempre conservan su Decimal string; no se convierten a
Number ni se recalculan económicamente. Texto inválido produce un error controlado.

`MoneyValue` muestra indicadores circulares CSS de oro, plata y cobre, con letras
g/s/c, nombre accesible y signo único para todo el monto. Los indicadores son
decorativos y no dependen de recursos externos. Las denominaciones pueden pasar
a otra línea; valores largos tienen ajuste de texto. La pendiente conserva
`/ índice` junto a las denominaciones y en el nombre accesible: es una tasa,
no un precio absoluto ni una tasa diaria.

Componentes existentes actualizados:

- `MetricCard.tsx`: solo `copper` y `copper/scan_index` pasan a MoneyValue. Esto
  alcanza promedios, medianas, extremos, dispersión monetaria, cambios absolutos
  y los montos dentro de las señales, sin editar la lógica de MarketSignals.
- `PriceChart.tsx`: detalle interactivo con monedas y valor exacto expandible;
  título y nombre accesible del punto con g/s/c y copper original. El detalle
  sigue disponible por foco, teclado, puntero y toque, sin depender de hover.
- `MarketResults.tsx`: montos de la tabla de precios con monedas y detalle exacto.
- `format.ts`: la conversión textual completa existente reutiliza splitCopper.
- `chart.ts`: margen izquierdo de 112 en lugar de 82 unidades SVG para las
  etiquetas monetarias. Se conserva el extremo derecho, puntos, escala económica,
  huecos, interacción y gráfico SVG existente.
- `styles.css`: tipografía, puntos de denominación y ajustes de tamaño para
  tarjetas, tabla, señales y detalle del gráfico, siguiendo el tema aprobado.
- `tests/market.test.mjs` y `tests/app.test.mjs`: cobertura focalizada.

No cambian porcentajes, cantidades disponibles, índices, buckets, cobertura,
coeficientes adimensionales ni parámetros técnicos, incluido el parámetro de
umbral de pendiente. El formato de ese parámetro sigue siendo el Decimal original
del motor; no es una tarjeta de monto. Los cambios previos de contratos frontend
pertenecen a 3B.2 y se conservan sin modificaciones en esta mejora.

### Política de precisión y ejemplos

Internamente copper proporciona una unidad única para comparar y calcular sin
mezclar denominaciones. Los derivados usan Decimal del backend para conservar
fracciones. Oro/plata/cobre es solamente una representación visual equivalente.

Los montos enteros se descomponen exactamente, sin aproximación. Si el Decimal
tiene fracción, esta se mantiene en la denominación cobre. La lectura principal
conserva hasta dos dígitos fraccionarios; si el string contiene más dígitos, los
restantes se abrevian con `…`, sin redondear ni trasladar fracciones a una moneda
entera. Se muestra «Fracción de cobre · vista abreviada». Incluso si los dígitos
restantes son ceros se marca la abreviación, conservando la representación original.

**Todos los montos**, incluidos los enteros, tienen un `<details>` nativo con
«Ver valor exacto en copper» o «Ver valor exacto · sin redondeo». Se puede enfocar
y abrir por teclado o tocar en móvil. El detalle contiene el string original
completo en copper (punto decimal de la API, sin normalizar) y su conversión
completa en palabras. El original nunca se sobrescribe. Un negativo diminuto
puede verse como `−0,00…c`: el signo y los dígitos completos siguen accesibles;
no se afirma que el monto sea cero.

| Antes, lectura principal | Ahora, lectura principal |
|---|---|
| 45 c | 45c |
| 1000 c | 10s |
| 85490 c | 8g 54s 90c |
| 1102045 c | 110g 20s 45c |
| 0 c | 0c |
| −1600 c | −16s |
| Mediana 69,5 c | 69,5c |
| Promedio 72,06… c | 72,06…c + aviso de fracción abreviada + Decimal completo |
| Pendiente −1600,5 c / índice | −16s 0,5c / índice |
| Variación −18,57… % | −18,57… % (sin conversión) |

En el eje vertical se usa una denominación por etiqueta para ahorrar espacio:
85490 copper se etiqueta `8,549g`, exactamente; 101 copper, `1,01s`. Los ticks
continúan siendo enteros de copper diferentes, incluso entre 9999/10000/10001.
No se redondean a monedas enteras ni se eliminan diferencias pequeñas. El punto
permite consultar su precio con denominaciones completas y el entero original.

### Pruebas, Git y revisión visual

- `npm test`: **101 aprobados** (65 de funciones/componentes y 36 montados), sin
  skips. Se agregan 27 casos a los 74 de 3B.2: 23 de conversión/render y 4 montados.
- Casos: 0, 1, 45, 99, 100, 9999, 10000, importes con tres denominaciones,
  negativos, montos mucho mayores que Number.MAX_SAFE_INTEGER como strings,
  ceros finales, valores exactos, fracciones de promedio/mediana, fracciones muy
  pequeñas, errores controlados y ticks distintos en los límites de denominación.
- Render: nombre accesible, indicadores decorativos, disclosure con foco y
  apertura, exactitud en copper, tooltip/detalle por foco/toque, tabla y señales.
  Se comprueba que no se muta el JSON de señales, que sus direcciones se conservan
  y que porcentajes, cobertura, disponibilidad, índices y parámetros no usan monedas.
- `npm run build`: TypeScript + Vite producción aprobados (51 módulos).
- `npm run test:live`: **6 aprobados**, exclusivamente GET sobre el backend local
  y los datos simulados existentes; métricas y señales exactas sin cambios.
- `git diff --check`: OK. Sin dependencias nuevas ni cambios de backend,
  contratos API, ingestión, migraciones o PostgreSQL en esta mejora.

La primera corrida encontró un selector demasiado amplio en un test nuevo:
buscaba monedas entre todos los descendientes de la tarjeta de señal, incluidos
sus montos, al comprobar que el porcentaje no usara monedas. Se acotó el selector
al valor porcentual; no se cambió la implementación para acomodar la prueba.

Estado acumulado: rama `main`, HEAD `3f8859a`, 19 archivos modificados y 5 nuevos,
incluyendo la entrega 3B.2 anterior. Los 17 archivos previos se conservan; esta
mejora añade siete rutas al conjunto de cambios. Sin staging, commit o push.

Se volvió a intentar la revisión visual: el navegador Chrome no está disponible
en el control de navegador y Computer Use de Windows se detuvo al no poder
verificar con certeza su URL actual. No se continuó esa automatización. No hay
captura real nueva, verificación de layout ni aprobación visual implícita; los
tests jsdom no sustituyen esa revisión. El frontend y backend local siguen
respondiendo en `http://localhost:5173/` y `http://127.0.0.1:8000`.

Pendiente: revisar visualmente tarjetas, detalles de señal, tooltip, tabla y eje
en escritorio y ancho reducido; en los datos actuales predominan precios menores
a 1s, por lo que los montos grandes se verifican con fixtures sintéticas. Datos
auténticos y revisión con lector de pantalla/dispositivos físicos siguen pendientes.

Veredicto de esta mejora: **NOT READY FOR UX REVIEW**, por falta de captura y
verificación visual real. Implementación y validación automatizada aprobadas.
La Fase 3B.2 continúa abierta, sin cambios Git publicados.

## Ajuste final — copper indivisible (2026-10-20)

El usuario confirmó que la presentación g/s/c anterior fue aprobada visualmente.
Esta sección reemplaza su política de monedas fraccionarias y el bloqueo de
revisión registrado anteriormente. No se rediseña el dashboard ni se considera
cerrada o publicada la fase; queda por revisar este ajuste semántico final.

### Política vigente

La unidad monetaria mínima es **1 copper**. Toda lectura principal en g/s/c
utiliza denominaciones enteras, conservando los indicadores CSS, texto accesible,
signos, estilos responsive y detalle nativo de valor exacto.

- **Observados:** `MoneyValue`, `presentCopper` y `formatCopper` usan por defecto
  la política `observed`, que rechaza fracciones de copper distintas de cero.
  No se transforma un precio observado inválido en una moneda válida. Se aceptan
  representaciones matemáticamente enteras como `5.000` sin aproximación. Los
  precios numéricos siguen requiriendo enteros seguros, como exige el contrato.
- **Derivados:** las tarjetas de estadísticas monetarias usan explícitamente la
  política `derived`. Si hay fracción no nula, solo la presentación se redondea
  a copper entero mediante **ROUND_HALF_UP**. Se examina el primer dígito
  fraccionario y se suma una unidad BigInt a la magnitud si es al menos 5; después
  se conserva el signo. No se usa Number, Math.round, parseFloat ni aritmética
  binaria para ese redondeo. Los acarreos a plata/oro son exactos.
- **Aproximación visible:** un monto derivado redondeado lleva `≈`, nombre
  accesible «aproximadamente» y aviso «Redondeo visual a 1 copper · ROUND_HALF_UP».
  Un Decimal con fracción compuesta solo por ceros no necesita redondeo ni `≈`.
  Un monto diminuto puede mostrarse `≈ 0c` o `≈ −0c`; se conserva su signo y el
  original no nulo en el detalle, sin afirmar que el resultado matemático sea cero.
- **Exactitud accesible:** todos los montos conservan el string original íntegro
  en «Ver valor exacto» mediante `<details>` operable con teclado o tacto. Se
  elimina la segunda conversión del detalle a monedas fraccionarias: allí se
  muestra el Decimal técnico original en copper, sin normalizar ni redondear.
- **Pendiente:** `copper/scan_index` se muestra como decimal técnico con todos sus
  dígitos y la unidad `copper / índice`, además del detalle original. No se convierte
  a monedas ni se redondea a cero una pendiente pequeña. No lleva `≈` porque no
  se ha aproximado. La presentación no decide el signo o la clasificación de señal.
- **Eje SVG:** usa denominaciones enteras exactas. Si una etiqueta completa supera
  14 caracteres, utiliza el entero original en copper para respetar el margen
  existente y distinguir ticks cercanos. No hay redondeo de precios ni de ticks.
- Porcentajes, disponibilidad, cobertura, índices, coeficientes y parámetros
  estadísticos mantienen su presentación previa.

| Decimal recibido | Lectura principal |
|---|---|
| 85490 | 8g 54s 90c |
| 5 | 5c |
| 5.5 | ≈ 6c |
| 10.4 | ≈ 10c |
| -15.5 | ≈ −16c |
| 10000.5 | ≈ 1g 1c |
| 0 | 0c |
| -0.00000000000000000001, monto derivado | ≈ −0c, original exacto en detalle |
| -0.00000000000000000001, pendiente | −0,00000000000000000001 copper / índice |

Los ejemplos fraccionarios de monto requieren política `derived`; no son precios
observados válidos. Internamente se sigue calculando en copper/Decimal. Esta
conversión es exclusivamente de presentación y no cambia resultados económicos.

### Cambios y validación

Archivos de este ajuste: `currency.ts`, `MoneyValue.tsx`, `MetricCard.tsx`,
`MarketResults.tsx`, `MarketSignals.tsx`, `styles.css`, `tests/market.test.mjs`,
`tests/app.test.mjs` y este informe. Se etiquetan explícitamente como observados
los mínimos nativos, extremos y último precio de señales/métricas. Medianas,
promedios, diferencias, magnitudes y dispersión monetaria permanecen derivados.
PriceChart y la tabla mantienen la política observada por defecto, sin cambiar
su selección, geometría o interacción. Se reutilizan componentes y estilos.

| Verificación | Resultado |
|---|---|
| `npm test` | **118 aprobados**: 82 de funciones/componentes y 36 montados |
| `npm run test:live` | **6 aprobados**, exclusivamente GET |
| `npm run build` | TypeScript + Vite producción OK |
| `git diff --check` | OK |

Se agregan 17 casos y se actualizan los de la política anterior. Cobertura:
enteros, fracciones positivas/negativas, empates y valores inmediatamente antes
de la mitad con muchos dígitos, acarreos, fracciones diminutas, montos mayores
que Number.MAX_SAFE_INTEGER, ceros decimales, ROUND_HALF_UP simétrico sobre la
magnitud y acceso al Decimal original. Se comprueban MetricCard, MarketSignals,
PriceChart, detalle por teclado/toque y ausencia de mutación del JSON. Los
precios observados fraccionarios se rechazan, nunca se redondean para dibujarlos.

La integración conserva promedio
`72.06666666666666666666666666666666666667`, mediana `69.5`, desviación
`-18.57142857142857142857142857142857142857`, dirección de desviación
`no_significant_deviation` y tendencia `descending` en PvE / item 1900000000.
Los dos primeros valores se leen ahora `≈ 72c` y `≈ 70c`; los resultados
estadísticos, evidencia y clasificaciones originales permanecen idénticos.

No hay cambios nuevos en backend, contratos API, estadísticas, ingestión,
migraciones, configuración o datos. PostgreSQL solo se consulta mediante las
integraciones GET existentes. No se instala ninguna dependencia.

Git acumulado conserva rama `main`, HEAD `3f8859a`, **19 archivos modificados y
5 nuevos** (incluidos los cambios locales anteriores de 3B.2), sin staging,
commit ni push. Este ajuste no añade rutas al conjunto de cambios pendiente.

Veredicto vigente: **READY FOR UX REVIEW** del ajuste de copper indivisible.
La aprobación visual previa corresponde al diseño anterior; no se presenta como
aprobación implícita de esta corrección ni se cierra la fase. Continúan los límites
de datos simulados, exports/calendario con fixtures y pruebas físicas pendientes.
