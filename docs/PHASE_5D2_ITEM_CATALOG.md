# Fase 5D.2 — Catálogo mínimo de metadatos

28/10/2026, America/Buenos_Aires. Base publicada `fb9ca648`.
**Cierre técnico aprobado para publicación**, con placeholder para iconos y caché sólo vigente.
La documentación pendiente de 5D.1 y ROADMAP se preservó y se actualizó con el
cierre. La entrega inicial quedó sin staging, commit ni push; el usuario autorizó
después su revisión y publicación en main. No se consultó ni modificó PostgreSQL, no se
importaron capturas auténticas y no se pobló un catálogo con datos ficticios.

## Alcance y procedencia

AHledger es el único adaptador activo. La respuesta pública por ID se comprobó
en 5D.1 para 2589, 2770, 2447 y 4604. En esta fase se releyeron sólo las páginas
de condiciones; no se repitieron esas consultas ni se descargaron imágenes.
Las pruebas nuevas utilizan respuestas sintéticas reducidas mediante servidor
HTTP en loopback, nunca la API pública durante tests/CI.

Se integran nombre, calidad y categoría/subclase devueltos por el proveedor,
producto solicitado, URL de consulta, fecha propia de adquisición y atribución.
Idioma y build siguen null: un nombre inglés no verifica enUS; un build global
publicado o la fecha HTTP no acredita la compatibilidad de una captura. La UI
advierte esa limitación. No se importan vendorSell, precios, estimaciones de ventas
ni métricas económicas aunque estén presentes en el JSON.

Sólo items simples de `launch` reciben nombres por su ID exacto. `g:`, `s:` y
`p:` mantienen identidades y etiquetas propias; no se infiere su nombre desde el
item base o desde otra especie. Simulated y stress_test tampoco se resuelven con
este catálogo auténtico. El catálogo fresh de 50 items y la tabla items de Fase 2
no intervienen. El frontend no cambia agrupación ni cálculos de hechos nativos.

La restricción a launch es una decisión conservadora de este MVP: las claves
numéricas de los fixtures no prueban identidad auténtica y pueden colisionar con
IDs reales. Cambiar desde launch a simulated/stress_test oculta inmediatamente los
metadatos anteriores y no consulta el catálogo. Launch tampoco autentica una
captura: sólo habilita esta asociación descriptiva opcional, con procedencia visible.

## Arquitectura y contrato

```text
CLI manual (1–4 IDs) → AHledgerClient → GET AHledger por ID
                                  → caché JSON temporal, máximo 128 registros
React Evidencia launch → GET /catalog/items → sólo caché local vigente
                     → asociación descriptiva por ID simple, sin modificar hechos
```

Se revisaron `items`, `partial_items`, contratos v2 y catálogo simulado: ninguno
registra procedencia/build/idioma suficiente para reutilizarlo como catálogo real.
Se evitan tablas y migraciones. `app/catalog.py` es independiente de React,
PostgreSQL e ingestión. Cada archivo sólo guarda una proyección validada, no el
cuerpo completo del proveedor. Escritura por reemplazo y lock de consultas;
dos CLI simultáneas no duplican solicitudes. No hay cron, watcher ni sincronización.

`CatalogItem` tiene product=forever, entity_kind=item, item_id entero estricto,
name, language nullable, quality/category/subclass nullable, build nullable,
compatibility=provider_product_only, icon_ref nullable, icon_permission,
provider, source_url, attribution_url, fetched_at y expires_at (epoch UTC).
Valores ausentes siguen null; no se asignan códigos de calidad inventados.
El origen corresponde al registro completo; no se mezclan campos de dos fuentes.
ForeverDB está representado en el contrato y fixtures para probar atribución
alternativa; no existe adaptador, autorización, importador ni fallback automático
hacia su API. Eso no acredita permiso de uso real de ForeverDB.

`GET /catalog/items` responde `contract=5d2-v1` y hasta 128 registros vigentes;
rechaza query params y no tiene métodos de escritura. No conecta a SQL ni al
proveedor. Responde `Cache-Control: no-store` para impedir una segunda caché que
extienda el TTL. Archivo corrupto, vencido o con identidad discordante: se omite;
directorio no accesible: 503 saneado. Cache ausente: lista vacía.
Tipos y esquemas frontend se generan desde OpenAPI como los de evidencia.

## Condiciones, atribución e imágenes

Revalidados el 28/10: [terms](https://ahledger.com/terms) y
[developers](https://ahledger.com/developers). Permiten API personal/comercial
con enlace a AHledger junto a los datos, sin revender el feed o atribuirse el scan,
y exigen respetar caché. Se conserva attribution.url con sus campaign tags; nunca
se inserta el HTML recibido. Se validan protocolo HTTPS y host del proveedor.
Cuando falta ese bloque, se usa el enlace de crédito genérico a AHledger.

La caché temporal es la interpretación operativa de estos términos; no hubo
concesión individual ni contacto externo. Se exige Cache-Control max-age positivo;
TTL máximo 300s, descontando Age y antigüedad Date. Sin headers válidos, con
no-cache/no-store, vencido o contradictorio: no se almacena ni muestra el resultado.
No se sirve stale en errores u offline. Los archivos vencidos se eliminan al
siguiente almacenamiento; no se versionan ni se crea archivo histórico.
El render de un mercado consultado funciona sin conexión a AHledger durante el
TTL. Más allá de ese permiso, los IDs conservan la vista usable. Persistencia
duradera/offline sin caducidad requiere decisión y aclaración del proveedor.

No se obtuvo permiso aplicable de iconos de Blizzard: el adaptador descarta
`icon` sin solicitarlo. Se muestra ◇ como placeholder local. La UI sólo admite
un futuro icon_ref bajo `/assets/catalog/` y marcado authorized; ningún asset se
incluye en esta entrega y no hay switch que autorice URLs de Blizzard. Si una
imagen local autorizada falla, vuelve al placeholder conservando nombre y precio.
Los tests prueban esa ruta con un recurso ficticio sin descargar imágenes.

## Límites y errores

- Una petición GET por lookup faltante; sin redirects, autenticación ni retry.
- Socket timeout 5s y presupuesto de lectura 10s comprobado entre bloques (una
  lectura bloqueante puede consumir hasta el timeout adicional del socket).
- Respuesta máxima 65.536 bytes; nombre 256 caracteres; validación de tipos,
  ID exacto, producto contradictorio, controles, enlaces y claves JSON duplicadas.
- 404 devuelve ausente; 400/403/5xx/JSON inválido fallan explícitamente sin datos
  parciales. 429/503 o 5xx con Retry-After guardan cooldown para próximas CLI.
  Se admite Retry-After en segundos/fecha HTTP; si falta o es inválido se usa 60s.
- Separación mínima de solicitudes 2s persistida entre procesos; CLI secuencial
  hasta cuatro IDs explícitos, espera 2,1s entre ellos y se detiene al primer error.
  No se intenta agotar la cuota publicada de 300/min/dirección.
  **Cuatro IDs es sólo el límite por invocación de la CLI manual actual**, no una
  cuota de AHledger ni la capacidad definitiva del producto. El cliente hace una
  consulta por ID y la caché puede reunir hasta 128 registros vigentes de consultas
  manuales separadas; esto tampoco define la capacidad futura del catálogo.
- Lock existente impide otra consulta. Si un proceso se interrumpe, revisar que
  haya terminado antes de retirar únicamente `lookup.lock` del directorio elegido.
  Un cooldown local corrupto falla cerrado y pide revisar retry-after.txt.
- Caché de hasta 128 registros; al llenarse no crece automáticamente. No pretende
  cubrir el catálogo completo ni ser un servicio multiusuario público.

## Procedimiento de uso

No cambia la configuración de bases ni requiere migrar. Desde la raíz:

```powershell
# Usa data/imports/item-catalog por defecto, ignorado por Git.
.\backend\.venv\Scripts\python.exe -B backend/scripts/lookup_item_catalog.py 2589 2770
```

Ejecutar sólo para IDs concretos necesarios, sin bucles de enumeración.
Para otra ubicación, establecer `ITEM_CATALOG_CACHE_DIR` como variable del proceso
en la consola del CLI **y** del backend antes de iniciarlos. Esta variable se lee
del entorno del proceso, no del .env. No modificar .env de desarrollo para probar.
El backend y la CLI deben apuntar al mismo directorio privado.

En Evidencia: elegir launch → economía → estado explícitos. Los items simples con
metadatos vigentes muestran nombre, ID secundario, proveedor enlazado e incertidumbre
de idioma/build. Buscar por nombre, ID o clave completa. Si se consulta el catálogo
con la vista ya abierta, volver a seleccionar el estado para recargar la caché
local. La caducidad retira nombres automáticamente, sin red al proveedor; para
renovar, repetir manualmente la CLI y volver a seleccionar el estado.
Sin catálogo, API local caída, nombre inválido o caché vencida: `Item ID`;
mascotas: `Especie ID`. Precio, disponibilidad y detalles permanecen consultables.

## Validación inicial y archivos

Frontend: **148 tests aprobados** (82 lógica/contratos, 36 dashboard histórico,
30 evidencia, incluidos ocho nuevos de catálogo), `npm run build` aprobado y
generación OpenAPI `--check` sin drift. Vite se ejecutó fuera del sandbox por
EPERM al iniciar subprocesos. Pytest también requirió temporales fuera del sandbox
por WinError 5; los fixtures HTTP permanecen en loopback.

Backend: **334 tests aprobados**, cero fallos, 19,74s; regresión focalizada de
catálogo, API de evidencia y 3A/3B. Suites ejecutadas: test_item_catalog.py,
test_evidence_api.py, test_market_statistics.py, test_market_windows.py,
test_market_signals.py, test_market_validation.py y test_market_signals_validation.py.
Cubre HTTP 400/403/404/429/500/503, JSON inválido/duplicado,
contradicciones, opcionales ausentes, recursos/timeout, TTL/Age/Date/no-store,
cooldown persistido, lock/capacidad, fuente alternativa, imágenes autorizadas y
fallback, variantes/especies, búsqueda y preservación de hechos/precios.
Advertencia preexistente de Starlette/httpx; sin nueva dependencia.
`git diff --check` aprobado, índice vacío y esquemas anteriores de evidencia y
3A/3B comparados con HEAD: idénticos. La CLI se comprobó con --help y tests de
límites/errores, sin ejecutar consultas públicas de items.

La regresión backend bloquea psycopg.connect en el proceso; no se habilitan
fixtures de integración ni accesos a desarrollo. El responsive se verifica por
DOM/CSS de las tarjetas ya aprobadas en 5C.1; no sustituye una nueva revisión
visual en navegador. No se afirma QA visual nuevo ni prueba en el cliente real.

Archivos de implementación: backend/app/catalog.py, backend/app/api/catalog.py,
backend/scripts/lookup_item_catalog.py, backend/app/main.py y backend/.env.example.
Pruebas: backend/tests/test_item_catalog.py y frontend/tests/evidence.test.mjs.
Frontend: api/catalog.ts, contracts.ts, generated.ts, response-schemas.json,
features/evidence/EvidenceDashboard.tsx, EvidenceItemsTable.tsx y styles.css;
scripts/generate-api-contracts.py y tsconfig.test.json.
Documentación: README, ARCHITECTURE, ROADMAP, informe 5D.1 y este informe.

Pendientes de lanzamiento independientes: primera captura auténtica y su identidad
económica, codec/reloj/build compatibles y primera importación manual revisada.
Este catálogo no cierra esos pendientes ni cambia el veredicto de 5B/5C sobre ellos.

Estado Git de la entrega inicial: HEAD `fb9ca648c26c1e28fa7f0cf96ee63bcce2799b20`,
14 archivos modificados y 7 sin seguimiento (incluye la investigación 5D.1
recibida como pendiente). Índice sin cambios; sin commit/push. No se sembraron
registros reales ni se guardaron imágenes. El catálogo comienza vacío y se
consulta con el procedimiento manual anterior.

## Revisión formal y cierre para publicación — 28/10/2026

El usuario autorizó commit/push a main tras la revisión. Se preservaron los 21
archivos pendientes, incluidos el informe 5D.1 y los cambios previos de ROADMAP.
La única corrección de comportamiento impide que AHledgerClient reutilice una
entrada cacheada de ForeverDB como si procediera de AHledger. Una consulta explícita
a AHledger sólo reutiliza su propia fuente; no se añade adaptador ni sincronización.

| Control | Resultado comprobado |
| --- | --- |
| TTL y consultas | El header real registrado en 5D.1 es public, max-age=300. 300s es un techo conservador, no una frecuencia de polling. Se respetan TTL menores, Age/Date y no-store/no-cache. Tests montados verifican que expirar no genera requests locales ni remotos. |
| Metadatos frente a hechos | Proyección descriptiva separada, atribución por fila y sin campos económicos; precios, hechos, motores y esquemas anteriores permanecen iguales. |
| Dataset | Sólo launch habilita nombres. Los fixtures ficticios pueden compartir números con items reales; cambios a simulated/stress_test ocultan nombres inmediatamente y no consultan catálogo. |
| Cuatro IDs | Límite exclusivo de la invocación manual actual; no describe una cuota del proveedor ni la capacidad definitiva del producto. |
| Iconos | Campo remoto descartado, sin GET de imágenes ni assets distribuidos. Placeholder hasta autorización acreditada; ruta de imagen local futura cubierta sólo con fixtures. |
| Fallback | Caché ausente, vencida, inválida o API local fallida conserva Item ID y evidencia consultable; variantes y especies siguen separadas. |
| Atribución | Enlace visible a AHledger junto al nombre, campaign tags conservados; no se utiliza HTML remoto ni se atribuyen datos a otro proveedor. |
| Contenido Git | Lista explícita de 21 archivos de código/tests/documentación; sin .env, tokens/claves detectados, imágenes, cachés, capturas o cuerpos completos de respuestas. Las proyecciones reducidas de investigación y fixtures sintéticos sí forman parte de la entrega. |

Validación final: **337 tests backend aprobados** en 21,07s y **149 frontend**
(82 + 36 + 31); build de producción correcto. Se añadieron regresiones para fuente
cacheada alternativa, TTL menores y caducidad sin polling, y se amplió el cambio
launch → stress_test/simulated. OpenAPI --check y git diff --check aprobados;
esquemas anteriores de evidencia/3A/3B idénticos a la base publicada. Una advertencia
preexistente Starlette/httpx. Sin PostgreSQL (conexiones bloqueadas en la regresión),
consultas públicas nuevas, capturas auténticas o cambios adicionales de UI.

La publicación de esta fase precede a una actualización documental separada del
roadmap para priorizar PRELAUNCH READINESS CHECK. Esa etapa no comienza en este
cierre: watcher, preflight, identidad económica, límites, ingestión protegida y
consulta v2 siguen pendientes de su validación específica. Permisos de iconos,
offline más allá del TTL y build/idioma por item conservan sus limitaciones.
