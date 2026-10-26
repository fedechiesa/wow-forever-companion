# Fase 5C.1 — Consulta visual de evidencia v2

**Diseño aprobado visualmente por el usuario.** Cierre técnico y publicación
autorizados, conservando el diseño sin modificaciones adicionales.
Base: `335e4342984432befd76fad2198a5b6a56f2873c`, main inicialmente limpio.
Se revisaron README, ARCHITECTURE, ROADMAP y 5B.1/5B.2, lectores, contratos,
identidad/linaje, API, React, estilos y suites existentes. No se importaron
capturas auténticas ni se conectó desarrollo durante las validaciones.
Las entregas iniciales terminaron sin staging, commit o push. El cierre posterior
autorizado se registra al final. No se inicia otra fase.

## Arquitectura

```text
App → selector de sección → EvidenceDashboard
  → dataset → economía → estado (siempre elegidos explícitamente)
  → api/evidence.ts → cliente GET compartido, timeout y validación runtime
  → /evidence/v2 → contratos públicos Pydantic cerrados
  → LocalEvidenceReader.web_* → READ ONLY / REPEATABLE READ / tracking 006
  → mercados verificados + estados sellados + hechos / recibos por separado
```

El lector privado y su CLI conservan sus contratos anteriores. Las proyecciones
web reutilizan su snapshot, validación de mercado y pertenencia estado/economía;
seleccionan columnas públicas en SQL, no descargan linaje completo para filtrarlo
en React. No hay migraciones nuevas ni modificaciones de 001–006. No hay caminos
de escritura, ingestion service o TrialDatabase dentro del flujo HTTP nuevo.
TrialDatabase se utiliza sólo para preparar fixtures en el laboratorio.

La única corrección de integración legacy es filtrar economic_identity no nula
de GET /partial/markets. Ese endpoint enumeraba también mercados v2 que el cliente
3A/3B no soporta. Se mantiene su catálogo legacy, sin mezclar los nuevos estados;
no cambian fórmulas, métricas, señales ni archivos de app/market.

## Endpoints y contratos

Todos requieren dataset explícito `simulated|stress_test|launch`. `real` legacy
no se reinterpreta como launch. IDs de entrada: enteros positivos hasta `2**63-1`;
IDs de respuesta: strings decimales para preservar BIGINT en JavaScript.

| GET | Respuesta |
| --- | --- |
| /evidence/v2/markets | Economías verificadas del dataset, región, alcance/facción y primera etiqueta nativa representativa |
| /evidence/v2/markets/{market_id}/states | Estados sellados v2 que contienen esa economía, etiqueta exacta de ese estado, conteos y rango de adquisiciones declaradas |
| /evidence/v2/markets/{market_id}/states/{export_id}/facts | Filas completas por item/variante y bucket; l/h/a/m y mínimo proyectado con origen explícito |
| /evidence/v2/markets/{market_id}/states/{export_id}/receipts | ID, adquisición, recepción SQL, completed/duplicate, hash de bytes, formato y estado del productor/build |

Todas las listas aceptan limit=1..100 y offset=0..2147483647. Defaults: mercados
y estados 50, hechos 100, recibos 20. La respuesta incluye contract=5c1-v1,
dataset, limit, offset, has_more y los IDs de contexto aplicables. Se pide una fila
extra en SQL para has_more, sin contar ni descargar páginas restantes. Se rechazan
parámetros desconocidos o repetidos. No existen POST/PUT/PATCH/DELETE del flujo.

Mercado/dataset contradictorio, estado ajeno o v1: 404. Parámetros inválidos: 422.
Datos que no cumplen el contrato público o etiquetas con aspecto de rutas/datos
privados: 409. Base no disponible/esquema sin preparar: 503. Errores saneados,
sin mensajes del driver, SQL, paths ni contexto privado. La API no migra un destino.

No se serializan structure_manifest, archive_metadata, capture_context, source_id,
observer_source_id, origin_id, raw_reference, nombres de cuenta ni refs de evidencia.
Los campos de identidad solicitados son identificadores públicos del mercado por
contrato: el operador debe revisarlos y no usar datos personales como etiquetas.
Se bloquean formas evidentes de rutas/cuentas; el software no puede autenticar
el significado de una palabra arbitraria introducida como nombre de economía.
Tampoco transforma claims del operador en una autenticación criptográfica.

Se mantienen los permisos/CORS de la aplicación personal. No se añade un sistema
de autenticación ni autorización por usuario: no se presenta como un servicio
multiusuario público. Cada conexión del nuevo lector entra en transacción READ
ONLY antes de consultar. Las respuestas públicas usan allowlist y validación
Pydantic extra=forbid; un campo inesperado no pasa silenciosamente al navegador.

## Experiencia visual

La navegación **Análisis histórico / Evidencia de mercado** conserva el dashboard
anterior como sección inicial. Entrar en evidencia no realiza ninguna selección
automática. El usuario elige dataset, economía y estado en ese orden; no hay
"último scan" inferido por ID o recepción. Cada lista tiene paginación explícita.

La identidad y el badge del dataset permanecen visibles. La tabla principal tiene
una fila por item/variante y muestra último mínimo guardado, mínimo histórico o
fallback, disponibilidad y avisos breves de datos ausentes. Conserva IDs/variantes
sin inventar nombres. Los buckets, l/h/a/m, origen, valores exactos y conteos quedan
en detalles desplegables. Tiene caption y encabezados de columna/fila; en mobile
las filas pasan a tarjetas con etiquetas. Los selectores usan labels, los errores
son alertas y las cargas/vacíos tienen mensajes y retry.

Procedencia y recibos son un details/summary secundario; se consultan sólo al
abrirlo. No se expone el sidecar ni una ruta local. Se distingue adquisición de
recepción SQL y se declara qué metadatos de cliente/codec siguen no confirmados.
MoneyValue conserva el formato oro/plata/cobre y el detalle exacto de copper.
Los ceros son datos; ausencia se muestra como Sin dato, sin completar con cero.

useResource cancela cada petición al cambiar selección/página o desmontar la
vista y oculta respuestas antiguas por clave inmediatamente. El cliente comprueba
dataset/market/export de la respuesta. Cambiar dataset o economía limpia estado,
hechos y recibos; cambiar estado reinicia sus páginas y cierra la procedencia.
Un retry conserva la selección explícita. No se solicitan series, métricas o
señales para evidencia v2, ni se añaden gráficos temporales.

## Semántica de los campos

| Campo | Interpretación |
| --- | --- |
| economy / region / alcance / faction | Identidad económica verificada para persistencia; shared usa faction=null, sin deducir la facción del personaje |
| native_label | Etiqueta original en el estado; la del listado de mercados representa sólo la primera etiqueta recibida |
| first_acquired_at / last_acquired_at | Extremos de adquisición local declarada entre recibos del estado, no cronología de scans |
| acquired_at | Hora de copia/adquisición de esa captura |
| received_at | Hora de recepción en PostgreSQL, no hora del precio |
| scan_day | Índice nativo; null para m. 2485 no se convierte en fecha civil |
| native_l | Mínimo histórico nativo del bucket |
| native_h | Mayor mínimo guardado del bucket; no el precio máximo de todas las subastas |
| minimum_copper / minimum_origin | l si existe, incluso cero; de otro modo h con h_fallback. No se fusiona con otro estado |
| native_m | Último mínimo guardado sin fecha nativa; fila independiente, nunca precio vigente confirmado |
| native_a | Disponibilidad máxima observada, en unidades; no ventas, liquidez ni número de subastas |
| item_count | Estructuras de item/variante de la economía seleccionada, incluidas las vacías |
| native_fact_count | Hechos presentes de la economía seleccionada; cada fila de tabla informa sus propios campos presentes |
| receipt_count | Recepciones del estado completo; no cantidad de muestras temporales |

La agrupación SQL de l/h/a/m ocurre **antes de paginar**; una página no puede
separar l de h y crear un fallback falso. El m permanece en su fila sin bucket.
Hechos no se unen con recibos; dos recepciones del mismo estado no duplican filas.
La membresía se comprueba por identidad del manifest, incluso para mercados vacíos
de una captura con otros mercados poblados. Un archivo sin ningún hecho sigue
siendo rechazado por el decoder existente.

Puede concluirse qué evidencia nativa quedó preservada en un estado concreto y
qué recibos la vinculan a capturas. No puede concluirse oferta disponible ahora,
ventas, evolución intradiaria exacta, fecha de cada precio o rentabilidad. Varios
estados del bucket 2485 conservan varias evidencias de **un mismo índice**, no una
serie de días. El rango de adquisición tampoco determina cuál fue el último scan.

## Pruebas y preview sintético

Backend final: **1111 aprobados, 1 omitido, cero fallos**, 1112 recolectados, en
262,27 segundos. Los 43 nuevos son 34 de contratos/API y nueve de PostgreSQL.
Incluyen privacidad de metadatos, BIGINT exacto, filtros/datasets, paginación por
bucket completo, cero/fallback, m sin fecha, mercados vacíos, reimports/estados,
separación legacy, read-only físico y fingerprint de filas/secuencias del lab.
La primera focalizada detectó un fixture del test legacy conectado a la referencia
vacía; se corrigió para usar el target, antes de la regresión final completa.

Frontend de la entrega inicial: **128 aprobados**, incluidos diez nuevos casos de evidencia montada
con jsdom, selección, vacíos, cambios de contexto, cancelación obsoleta, loading,
error/retry, moneda, variantes sin nombres, tiempos y accesibilidad básica.
`npm run build` aprobado; OpenAPI generado y `--check` sin drift. Vite/tests se
ejecutaron fuera del sandbox por el bloqueo EPERM de subprocesos en Windows.

El único omitido backend es el opt-in auténtico del parser, deshabilitado al
retirar AUCTIONATOR_REAL_CAPTURE. No se ejecutó npm run test:live legado: requiere
series 340 simuladas en un servidor que esta preview v2 no contiene. En cambio,
se verificaron GET reales de mercados/estados/hechos/recibos, dataset vacío y CORS
contra FastAPI local y el laboratorio nuevo.

Todas las conexiones del launcher de regresión se restringieron por whitelist a
un contenedor PostgreSQL nuevo, loopback y nombres de laboratorio: **1719 sesiones**.
Referencia protegida nueva sin tablas/secuencias, idéntica antes/después. No se
conectaron desarrollo ni la base de tests preexistente. Sólo se aplicaron 001–006
en destinos nuevos conocidos/verificados vacíos; ningún endpoint hace DDL.
Persisten los tres avisos previos: Starlette/httpx y dos fixtures Pydantic inválidos.

Preview dejada para revisión del usuario: **http://localhost:5174**. FastAPI local
en 8001 apunta exclusivamente a otra base nueva de laboratorio con fixtures, sin
editar .env. Elegir **Evidencia de mercado → simulated → Economia sintetica PvP**
y cualquiera de sus dos estados. Hay tres variantes de item: la API conserva seis
filas item/bucket y el ajuste UX presenta tres filas principales, con dos recibos
en el primer estado; ambos estados usan 2485.
stress_test contiene otro fixture separado; launch está vacío. No hay datos
auténticos. El contenedor y ambos servidores de preview son temporales.

**Límite de QA visual inicial:** Browser Use no expuso navegadores y Computer Use agotó
la autorización de Chrome. No se pudo verificar screenshot/layout real ni el
responsive en un navegador. Las pruebas DOM y el CSS responsive no sustituyen
esa revisión. El usuario confirmó después el funcionamiento del primer preview y
pidió la simplificación UX registrada abajo. Tras revisarla, aprobó expresamente
tabla, moneda compacta, búsqueda y desplegables. El control automatizado responsive
sigue limitado a DOM/CSS; la aprobación visual la aporta el usuario.

Para repetir las pruebas en otro entorno, usar únicamente laboratorios propios
preparados con 001–006, nunca desarrollo. Desde backend, configurar en ese proceso
DATABASE_URL como referencia protegida distinta, TEST_DATABASE_URL y
TRIAL_INTEGRATION_DATABASE_URL como target y TRIAL_INTEGRATION_DATABASE_NAME con
su nombre exacto terminado en _test. Después:

```powershell
Remove-Item Env:AUCTIONATOR_REAL_CAPTURE -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_evidence_api.py tests/test_evidence_api_integration.py
# Desde frontend:
npm test
npm run build
```

Los fixtures de integración escriben sólo datos sintéticos en ese lab y dejan
sus estados public disponibles para inspección; no reinician una base existente.
Para verlos, iniciar un proceso FastAPI con DATABASE_URL apuntando a ese target de
lectura y FRONTEND_ORIGINS concordante con el origen del frontend. Configurar
VITE_API_BASE_URL para ese backend antes de iniciar Vite. No reutilizar ese cambio
de DATABASE_URL como referencia protegida de una ingestión hacia el mismo target:
la CLI debe conservar una referencia separada, como exige 5B.2.

## Datos auténticos, límites y estado de entrega

Siguen pendientes procedencia e identidad auténticas verificadas, región técnica,
economía/reino conectado, alcance del AH/facción, primer /reload y primera
importación auténtica revisada. Builds/productor/tiempo no confirmados conservan
su incertidumbre. Las etiquetas públicas de mercado requieren revisión humana.
Precios >2147483647 siguen bloqueando la captura completa para ingestión;
el archivo 5A los conserva hasta 2**63-1. No se amplían columnas, transporte o
análisis para esos extremos. Esta vista sólo consulta estados ya persistidos.

El alcance excluye sincronización, carga/importación desde UI, predicciones,
cambios 3A/3B y migraciones nuevas. La revisión visual del usuario está aprobada;
el cierre autoriza commit/push exclusivamente de 5C.1, sin iniciar la siguiente etapa.

## Archivos y control final

Veinticinco archivos nuevos/modificados recibidos para este cierre, con HEAD en la
base publicada antes de la publicación autorizada:

- Backend: app/api/evidence.py, app/api/partial.py, app/ingestion/local_readers.py,
  app/main.py, tests/test_evidence_api.py y tests/test_evidence_api_integration.py.
- Frontend: src/features/evidence/EvidenceDashboard.tsx, src/api/evidence.ts,
  src/App.tsx, src/styles.css, src/api/client.ts, src/api/contracts.ts,
  src/api/generated.ts, src/api/response-schemas.json, src/components/MoneyValue.tsx,
  src/features/evidence/items.ts y src/features/evidence/EvidenceItemsTable.tsx.
- Verificación frontend: scripts/generate-api-contracts.py, scripts/test.mjs,
  tests/evidence.test.mjs y tsconfig.test.json.
- Documentación: README.md, docs/ARCHITECTURE.md, docs/ROADMAP.md y este informe.

Control de la entrega inicial aprobado: siete archivos Python parseados, 42 enlaces locales,
whitespace y git diff --check. Los veinte esquemas analíticos OpenAPI anteriores
son idénticos; sólo se agregan contratos de evidencia. Migraciones 001–006,
app/market, watcher, captura local y los escritores conservan sus bytes publicados.
No se añadieron dependencias, capturas, .env, credenciales o temporales al proyecto.

## Ajuste UX anterior al commit

Se preservó todo el workspace recibido de 5C.1. No hay cambios adicionales en
backend/endpoints/contratos, ingestión, migraciones, watcher ni 3A/3B.

- Una fila principal por item_key completa. m se reúne con la evidencia del mismo
  item/variante en el mismo estado/contexto; no se asigna a ningún bucket. Si hay
  un bucket, se muestra su mínimo y disponibilidad. Si hay varios, se muestra
  el número de registros y se consulta cada uno por separado en el desplegable:
  no se calcula un nuevo extremo, no se elige el mayor índice como último dato y
  no se mezclan disponibilidad y precio de buckets distintos.
- Se carga el estado completo por páginas GET de 100 antes de agrupar. Se validan
  offsets, avance, duplicados y conteo de hechos; se mantiene el presupuesto de
  200.000 hechos del parser. Una carga parcial falla explícitamente, no muestra un
  item incompleto. Cada petición se cancela y se descarta al cambiar contexto.
  El estado sellado mantiene hechos/conteos inmutables entre páginas.
- Búsqueda por ID o clave/variante completa sobre todos los items cargados;
  paginación visual de 25 items, independiente de las páginas de transporte.
  No se consulta GET /items ni una fuente externa para resolver nombres.
- Bucket, l/h/a/m, origen y copper exactos en detalles por item, montados al
  abrirlos. Hash del estado, etiqueta/reglas, conteos, recibos y procedencia en
  información avanzada. Se ocultan controles de paginación sin otra página.
- MoneyValue agrega compact como opción de presentación; su default y las
  funciones monetarias no cambian. La fila principal sólo muestra oro/plata/cobre,
  en línea; el detalle conserva el original en copper. Los estilos se limitan a
  Evidencia para no alterar la presentación del dashboard histórico. Null sigue
  siendo Sin dato; cero sigue siendo un valor explícito. En <=760px la fila se
  convierte en una tarjeta etiquetada, con denominaciones sin apilarlas.

### Investigación local de nombres

Se revisaron esquema/contratos, GET /items, samples, generador fresh, archivos de
catálogo del workspace y [la investigación previa](ITEM_CATALOG_RESEARCH.md).
Se encontró data/imports/fresh/catalog.json, con **50 entradas**, todas con
fictional=true y nombres FICTIONAL. No se leyó ningún SavedVariables auténtico ni
se usaron esos nombres como catálogo real. La tabla items de Fase 2 contiene
samples y no acredita producto/build/locale/procedencia por nombre; partial_items
y EvidenceFact no ofrecen nombres ni bindings verificados.

No existe un catálogo verificado reutilizable **en los circuitos locales
inspeccionados para v2**. Esto no afirma que no pueda haber un export privado en
otra ubicación. Se mantiene Item ID (o Especie ID para p:) y variante, sin cruzar
IDs con samples ni inventar etiquetas. El catálogo real pequeño y sus bindings
contextuales quedan como tarea prelaunch independiente en ROADMAP. Sin scraper,
integración externa, datos de juego nuevos ni catálogo completo en este ajuste.

La tabla presenta items con hechos. item_count puede incluir estructuras vacías
cuyas claves no expone el contrato de hechos; no se crean filas/IDs para completar
ese conteo. En estados grandes, cargar todas las páginas puede demorar; la carga
es cancelable y acotada, y el detalle cerrado no monta todos los registros en DOM.
Una futura paginación por item en servidor requeriría otra revisión, no se añade
un endpoint para facilitar este ajuste.

### Validación del ajuste UX

**140 tests frontend aprobados**: 82 de contratos/moneda/lógica compartida, 36 de
componentes/dashboard histórico y 22 de evidencia. Los doce casos adicionales
cubren agrupación, null/cero, variantes, múltiples buckets, item cruzando páginas,
paginas incompletas/repetidas, cancelación, filtros/paginación visual, moneda
compacta y estructura responsive. Se mantienen pruebas de loading/error/retry,
nombres ausentes, accesibilidad y respuestas obsoletas. `npm run build` aprobado.

No se repitieron las 1111 aprobaciones backend de la entrega anterior: este ajuste
no cambió sus archivos ni contratos. No hubo pruebas SQL ni escrituras nuevas en
PostgreSQL; se reutiliza el preview sintético existente mediante GET. Sin tests
auténticos ni npm run test:live legacy. El preview http://localhost:5174 se actualizó
por Vite y el usuario aprobó después su diseño, sin pedir más modificaciones visuales.

## Próxima etapa documentada, todavía no implementada

Investigar y validar proveedores de **nombres, IDs, iconos y metadatos reales de
WoW Forever**. Partir de la investigación existente, sin asumir que una referencia
histórica siga disponible o sea compatible: comprobar origen, producto/namespace,
build/canal, locale, cobertura, calidad, permisos/condiciones de reutilización y
una muestra verificable. Diferenciar metadatos de la disponibilidad/derechos de
iconos y mantener el binding a mercado/variante explícito. No reutilizar nombres
ficticios ni resolver mascotas como items por coincidencia de número.

Dejar abierta la posibilidad futura de **recetas y profesiones** con sus propias
identidades, fuentes, ingredientes/resultados y compatibilidad verificada. No
inferir esas relaciones desde precios o nombres. Esta entrega sólo documenta
la próxima investigación: no añade catálogo, scraping, integraciones externas,
recetas, profesiones, iconos descargados ni funcionalidades nuevas.

## Cierre técnico y publicación autorizada

**Auditoría aprobada, sin bloqueos para publicar 5C.1.** El usuario aprobó
expresamente la tabla simplificada, precios compactos, búsqueda y desplegables,
y pidió conservar ese diseño. En el cierre no se modificó código ni estilo:
sólo se actualizó documentación y se repitieron las comprobaciones pertinentes.

Se revisaron los veinticinco archivos completos/diffs, incluidos contratos
generados y tests. El flujo v2 mantiene cuatro GET, respuesta pública cerrada,
IDs exactos, paginación y validación de contexto. El lector mantiene READ ONLY /
REPEATABLE READ; los hechos no se multiplican por recibos ni se usan como series
3A/3B. El selector legacy excluye identidades v2. No se incluye Lua privado,
catálogo fresh, .env, credenciales, temporales, archivos de juego o build artifacts.
Los nombres/rutas con centinelas de los tests son exclusivamente fixtures sintéticos.

Validación repetida durante el cierre:

- **233 tests backend aprobados, cero fallos y cero omitidos**, en 30,38 segundos:
  test_evidence_api, test_evidence_api_integration, test_local_readers,
  test_local_readers_integration, test_partial_integration, test_market_validation
  y test_market_signals_validation. Cubre permisos de sólo lectura reales,
  privacidad, separación de datasets/legacy, paginación, recibos/estados y
  regresiones de validación 3A/3B.
- **140 tests frontend aprobados, cero fallos:** 82 de contratos/moneda/lógica,
  36 de componentes/dashboard histórico y 22 de evidencia, incluida la UX aprobada.
- **Build de producción aprobado**, contratos OpenAPI sin drift, sintaxis,
  enlaces locales, whitespace y git diff --check comprobados. Los veinte esquemas
  analíticos publicados y los bytes de migraciones 001–006 permanecen idénticos.

La regresión SQL usó un contenedor nuevo separado del preview y de desarrollo,
con target y referencia protegida nuevos. El tracking 001–006 se preparó sólo
en el target conocido y verificado vacío. El launcher registró **333 sesiones**
permitidas y cero conexiones fuera de su whitelist; la referencia protegida
continuó sin tablas/secuencias y no quedaron schemas temporales. No se conectaron
desarrollo ni tests preexistentes; no se modificaron .env o permisos del usuario.
El contenedor de cierre se retiró tras la validación.

No se repitió innecesariamente la suite backend completa previa de 1111 aprobados
y un opt-in auténtico omitido: el código funcional no cambió durante el cierre.
No se usaron capturas auténticas, el cliente WoW, catálogo externo o scraping;
no se ejecutó test:live legado, cuyos requisitos siguen documentados arriba.

Antes de publicar se comprobó main/origin/main sincronizado en la base
335e4342984432befd76fad2198a5b6a56f2873c. La publicación autorizada comprende
exclusivamente estos veinticinco archivos en un commit descriptivo y push normal
a main, sin force. El hash final, resultado remoto y árbol limpio se confirman
al usuario después de ejecutar la publicación. La investigación de proveedores
es la próxima etapa documentada; no se implementa dentro de este cierre.
