# Investigación del catálogo auténtico de items

Fecha de consulta: **2026-10-15** (America/Buenos_Aires). Base local inspeccionada: `85bd0e127b142aadfdce2ba73a552039c0067c94`, rama `main`, árbol limpio al comenzar.

**Recomendación: CONDITIONAL GO.** El diseño permite un catálogo independiente y una prueba de diez materiales. Antes de implementar una carga real necesitamos una muestra propia verificable y una base de reutilización documentada, o un export con autorización explícita del proveedor. La web sirve hoy como referencia para contrastar; no se ha acreditado permiso para replicar su base. Ninguna evidencia consultada confirma estos datos para el lanzamiento.

**Validación práctica de fuente (2026-10-15): NEEDS MANUAL VALIDATION.** Se confirmó la ruta de captura/exportación en código, pero no se recibió un SavedVariables auténtico ni se comprobó el cliente del usuario. No hace falta esperar técnicamente al lanzamiento: hace falta acceso a una beta compatible y validar la captura, o un archivo auténtico previo con procedencia. Procedimiento y criterios concretos en la sección 11.

Este documento es investigación y propuesta. No se ejecutaron importaciones, migraciones, scripts de addons, instalaciones ni consultas a PostgreSQL. No se modificaron backend, frontend, datos ni otros documentos; no hubo commit ni push.

## 1. Fuentes, método y límites de acceso

Se consultaron páginas públicas mediante la herramienta web y archivos puntuales de ForeverTome mediante el conector de GitHub. Se leyeron código, SQL, contratos, fixtures y documentación del proyecto local. No se clonaron bases, recorrieron alfabetos completos, enumeraron IDs del juego ni probaron endpoints privados o rutas de API supuestas. Las fichas consultadas son una muestra manual acotada.

| Fuente | Enlace y alcance comprobado |
| --- | --- |
| Índice de items | [warcraftforever.games/items](https://warcraftforever.games/items): descripción del origen beta y navegación pública |
| Ficha de referencia | [273902](https://warcraftforever.games/items/273902): campos descriptivos, tooltip, build y marca de confirmación |
| Navegación alfabética | [A, página 1](https://warcraftforever.games/items/browse/a/1): listado HTML con fichas e imágenes |
| Materiales y contexto profesional | [Mining](https://warcraftforever.games/professions/mining), [Herbalism](https://warcraftforever.games/professions/herbalism) y las diez fichas de la sección 8 |
| Procedencia y condiciones declaradas por el sitio | [FAQ](https://warcraftforever.games/guides/faq), sección This site |
| Origen de precios del sitio | [Guía Auction House](https://warcraftforever.games/guides/auction-house): información del proveedor, no contrato de nuestra ingestión |
| ForeverTome | [Repositorio](https://github.com/Skold177/ForeverTome), inspeccionado también a una revisión fija, indicada abajo |

ForeverTome: la consulta de `commits/main` devolvió **`1c92db983b4668cc408ae5e7b4873b4b1086f734`**. Se leyeron a ese ref README, LICENSE, manifest, lector de items, perfil de compatibilidad, generador y documentación/esquema de catálogo. Enlaces reproducibles:

- [README](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/README.md).
- [LICENSE](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/LICENSE), blob `d159169d1050894d3ea3b98e1c965c4058208fe1`.
- [ForeverTome.toc](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/ForeverTome/ForeverTome.toc).
- [Loot.lua, lector de metadatos](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/ForeverTome/Loot.lua#L170), blob `de98efedd9f9011d63ea42bef20f1e9e8953f4c2`.
- [Compatibility.lua](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/ForeverTome/Compatibility.lua#L3), blob `cf9ff8b5a61801ef014bb6fe5655dc8c2290057e`.
- [build_catalog.py](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/tools/build_catalog.py), blob `d5e13090ae912203ee8585872b54df162576a91a`.
- [Formato de catálogo](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/docs/website-catalog.md), [cobertura](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/docs/database-coverage.md), [evidencia del cliente](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/docs/implementation-client.md).
- [Esquema de categorías](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/schemas/catalog-category-v1.schema.json), blob `cdd664fcf67b361748670b07aaac090497aafdde`.

**Límites:** la herramienta web devuelve representaciones de páginas, algunas con caché de días/semanas; la fecha de consulta no prueba una actualización del contenido ese día. Hubo errores de caché/503 para varias fichas, el raw de GitHub y LICENSE; el conector permitió verificar los archivos de GitHub después. Los intentos de HTTP desde la terminal fallaron con `WinError 10061`. Por lo tanto hubo acceso a Internet mediante herramientas, pero no un acceso HTTP general operativo desde el shell.

No se pudieron leer [robots.txt](https://warcraftforever.games/robots.txt) ni [sitemap.xml](https://warcraftforever.games/sitemap.xml) con la herramienta web. Eso no demuestra ni ausencia del archivo ni prohibición del sitio. No se investigaron solicitudes internas de JavaScript, autenticación ni límites efectivos. No se intentó sortear ninguna restricción. Las conclusiones negativas de este informe significan **no encontrado/verificado en este alcance**, nunca inexistencia demostrada.

## 2. Evidencia de warcraftforever.games

### 2.1 Campos realmente visibles

El [índice](https://warcraftforever.games/items) identifica el contenido como extracción del cliente beta, anuncia 21.787 entradas y permite navegación por inicial. Ese total es una afirmación del sitio, no un conteo independiente. El [listado A](https://warcraftforever.games/items/browse/a/1) expone enlaces a fichas e imágenes; también presenta nombres repetidos. Un nombre no identifica un item. El menú de idiomas no prueba que los nombres del juego estén traducidos en todos ellos.

| Campo | Evidencia puntual | Límite de la verificación |
| --- | --- | --- |
| ID y nombre | [273902: Wildstalker's Spaulders](https://warcraftforever.games/items/273902) | El ID está en la ficha y URL; no se deduce por nombre |
| Calidad | Esa ficha indica Epic | Etiqueta visible; no se verificó una codificación numérica pública |
| Categoría y slot | Armor, Shoulder; tooltip Mail | Etiquetas; no se verificaron IDs de clase/subclase del sitio |
| Niveles | Item Level 61; Requires Level 60 | Son dos campos distintos; pueden faltar en otros items |
| Build | `1.60.1.69893` y marca `tooltip confirmed in-game` | Confirmación declarada por el sitio, sin evidencia cruda propia ni equivalencia con lanzamiento |
| Otros | Bind on equip, armadura 294, conjunto/efectos y precio de venta | Muestra de tooltip, no esquema garantizado para todo el catálogo |
| Icono | Enlace de imagen en esa ficha | Referencia externa; no se verificaron bytes, licencia ni disponibilidad futura |
| Materiales | [2770](https://warcraftforever.games/items/2770): Trade Goods, Common, nivel 10, stack 20, build `1.60.1.70009` | No generalizar el build a las demás fichas |

El href de imagen de 273902 apunta a `https://wowforever-media.fly.storage.tigris.dev/icons/large/inv_shoulder_l_mail_raidhunterhyjalc60_d_01.jpg`. Su apertura falló por caché. Se comprobó la referencia que publica la ficha, no la entrega del recurso. No debe convertirse en una URL de recurso propio del Companion.

Hay builds distintos dentro del sitio: [Mining](https://warcraftforever.games/professions/mining) declara `1.60.1.70205`, mientras las fichas de la muestra incluyen `69893` y `70009`. Una versión de página de profesión no acredita que cada item haya sido revalidado en ese build.

### 2.2 API, exports y automatización

No se encontró documentación de una API pública de catálogo, contrato estable, cuotas, export oficial de items ni dataset acompañado de autorización de reutilización. Se revisaron índice, fichas, navegación, FAQ y búsquedas específicas de API/export/licencia/términos en el dominio. No se puede afirmar que no existan acuerdos o interfaces adicionales.

La [guía de Auction House](https://warcraftforever.games/guides/auction-house) atribuye sus precios a scans propios de beta mediante addon y afirma que no proceden de una API. Esto se refiere a sus datos de subasta; **no prueba** que el sitio carezca de API de items, ni autoriza reutilizar sus precios. No se importó ninguno.

La ruta comprobada para consultar items es HTML público. Sin un export acordado, extraer automáticamente un catálogo desde esas páginas sería scraping; utilizar endpoints internos no documentados agregaría una dependencia sin contrato. Ninguna de esas vías quedó aprobada para este proyecto. No se infirió una API a partir del funcionamiento del buscador.

### 2.3 Beta, observación y lanzamiento

Conviene separar dos dimensiones: **canal/build** y **tipo de evidencia**. Una observación en juego puede seguir siendo beta; la palabra real en nuestro dataset tampoco significa lanzamiento.

| Evidencia | Lo que permite afirmar | Lo que no permite afirmar |
| --- | --- | --- |
| Tabla extraída de beta | El proveedor identifica un registro en ese cliente | Que el servidor lo entregue, sea comerciable o conserve atributos al lanzamiento |
| Tooltip confirmado según la ficha | El sitio declara una lectura en juego | Validación propia, de todos los campos o en todos los builds |
| Observaciones de juego publicadas | [Copper Ore](https://warcraftforever.games/items/2770) atribuye recolección/botín a ForeverLog y advierte sobre muestras beta | Que sean capturas de ForeverTome, tasas universales o datos de lanzamiento |
| Captura propia con export y contexto | Podemos auditar campos efectivamente observados | Catálogo completo, atributos faltantes o garantía de continuidad entre builds |
| Confirmación de lanzamiento | Requeriría evidencia específica del canal/build de lanzamiento | No se obtuvo en esta investigación |

ForeverLog y ForeverTome son nombres distintos en las fuentes. No se verificó que sean el mismo software ni que compartan datasets. El sitio se declara fan site no oficial en su [FAQ](https://warcraftforever.games/guides/faq); sus afirmaciones no sustituyen confirmación del editor del juego.

## 3. ForeverTome: utilidad y garantías comprobadas

El [manifest](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/ForeverTome/ForeverTome.toc) declara versión `0.3.0`, Interface `16001` y SavedVariables `ForeverTomeDB`. El [perfil](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/ForeverTome/Compatibility.lua#L3) lee build y locale y reconoce específicamente `1.60.1 / 69893`; no debe habilitarse para otro build cambiando sólo el TOC. Sus capacidades siguen etiquetadas `wf_unverified` en código.

El [lector de items](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/ForeverTome/Loot.lua#L170) prepara: `item_id`, `requested_link`, `link`, `name`, `quality`, `item_level`, `minimum_level`, `item_type`, `subtype`, `stack_size`, `equip_location`, `icon_id`/`icon_path`, `sell_price_copper`, `class_id`, `subclass_id`, `bind_type`, `expansion_id`, `set_id`, `crafting_reagent` y `description`. Son campos del código, opcionales según lectura; no una muestra real capturada por nosotros. Un identificador/ruta de icono del cliente necesita un resolvedor de recursos y no implica bytes ni una URL pública, como advierte el [generador](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/tools/build_catalog.py#L149).

La [documentación del cliente](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/docs/implementation-client.md) declara validación en juego de ciertos flujos anteriores de quests/loot/persistencia. Los detalles nuevos de items, tooltips y otros colectores todavía requieren validación nativa. Tests offline y llamadas presentes en código no prueban permiso ni funcionamiento del cliente. No se ejecutó el addon, no se inspeccionó un cliente instalado ni se obtuvo un SavedVariables auténtico durante esta tarea.

La [ruta documentada](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/docs/website-catalog.md) guarda mediante `/reload` o logout y convierte una copia local con `tools/build_catalog.py`. El resultado `forevertome.website-catalog`, schema 1, contiene contexto, procedencia, entidades y registros. Preserva links exactos como variantes, referencias a evidencia y el flag `synthetic`. Es staging local: no requiere subir datos a un sitio ni ofrece por sí mismo una API alojada. Son instrucciones investigadas, no comandos ejecutados aquí.

La [proyección acumulada](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/docs/database-coverage.md) documenta `history.json`, `database.json`, `items.json` y vistas de recetas, entre otras. Mantiene hechos por campo, razones de ausencia, conflictos y claves delimitadas por producto/build/locale. Una referencia sin metadatos puede existir. Para combinar varios archivos se deben comprobar sus identidades de export/historia; una categoría no es todo el juego. No se descargó un dataset de jugadores ni se verificó cobertura completa.

**Conclusión técnica:** sí ofrece un mecanismo útil para construir un catálogo desde observaciones propias, con adaptador independiente. No entrega un catálogo completo de lanzamiento ni una equivalencia directa entre sus links y las claves de Auctionator. Para el MVP basta un export de una sesión; el watcher y las proyecciones acumuladas pueden esperar.

## 4. Licencias, restricciones e incertidumbres de reutilización

| Componente | Qué se verificó | Decisión para el proyecto |
| --- | --- | --- |
| Base del fan site | No se halló licencia de base ni permiso de réplica/export en las páginas revisadas | Conservar enlaces y notas mínimas de investigación; no republicar su base ni convertir esta muestra en un seed de producción |
| Condiciones del sitio | FAQ explica procedencia, privacidad y carácter no oficial | No equivale a términos de extracción o redistribución; pedir condiciones concretas si se desea una importación |
| Robots/límites | No verificables con el acceso disponible | Antes de automatizar, obtener reglas y límites; robots accesible tampoco sería una licencia |
| Código de ForeverTome | LICENSE completo es GNU GPL versión 2; GitHub lo identifica GPL-2.0 | Uso/modificación/distribución sujetos a esa licencia. Si se distribuye código derivado, preservar avisos y cumplir obligaciones de fuente/licencia aplicables |
| Output de ForeverTome | GPL sección 0 distingue ejecución del programa de la cobertura de su resultado | No asumir que todo JSON generado es GPL ni que la GPL concede derechos sobre datos/arte del juego |
| Iconos, textos y datos del juego | No se verificó permiso general de redistribución de esos recursos | Mantener procedencia y estado de derechos separados; imágenes y tooltips extensos quedan fuera del MVP publicable |
| Datos de colaboradores | No se recibió muestra ni autorización de un colaborador | Solicitar cesión/permiso de uso adecuado al alcance y retirar datos personales antes de conservar o publicar |

Estas decisiones se apoyan en el [LICENSE inspeccionado](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/LICENSE) y el [FAQ del proveedor](https://warcraftforever.games/guides/faq). El FAQ dice usar artwork bajo una política de fan content, pero no se verificó esa política ni su aplicación a nuestro proyecto. No se afirma una conclusión jurídica general sobre nombres, IDs o derechos de base de datos.

El alcance de lo legítimamente reutilizable debe quedar registrado por fuente y por tipo de contenido: permiso para metadatos no implica permiso para descargar/hospedar iconos. Para observaciones propias, registrar los hechos técnicos mínimos cuya conservación esté permitida por las condiciones aplicables del juego; obtener esa comprobación antes de un catálogo público. Publicidad del sitio, atribución, pequeño tamaño o uso de un addon abierto no sustituyen una autorización necesaria.

Si se solicita acceso al fan site, acordar: campos, muestra/export y frecuencia; versión/build/locale; uso interno frente a redistribución y uso comercial; atribución; derechos de imágenes; límites de consultas/cache; correcciones y retirada. No se contactó al mantenedor durante esta tarea.

## 5. Arquitectura local e identidad histórica

### 5.1 Dos circuitos existentes

| Circuito / archivo inspeccionado | Estado actual | Consecuencia |
| --- | --- | --- |
| [Migración 001](../backend/migrations/001_create_phase_2_tables.sql), [ingestión completa](../backend/app/ingestion/service.py) | `items.id` es PK interna; `external_item_id` TEXT es único global; nombre/calidad obligatorios. El upsert reemplaza nombre/calidad actuales | No usar esta tabla como nuevo catálogo auténtico: no tiene producto/build/locale/procedencia por campo y ya contiene simulación |
| [Samples Fase 2](../data/samples/snapshot_001.json) y restantes `snapshot_*.json` | Fuente `simulated`; contienen nombres/IDs conocidos, incluso `2770 / Copper Ore`. Simulan cambios de nombre/calidad | Coincidir con un ID auténtico no vuelve auténtico al sample ni a su histórico |
| [Migración 003](../backend/migrations/003_create_partial_observations.sql) | `partial_items`: PK interna, `item_key` único global, `external_item_id`, `key_kind`; sin nombre/calidad | Es identidad de evidencia parcial/variante, no una definición descriptiva del juego |
| Misma migración | Mercado único por `(region, market_key, dataset)`, con ruleset; dataset real/simulated | La separación de dataset está en mercado/observación, no en `partial_items` |
| [Servicio parcial](../backend/app/ingestion/partial_service.py) | Obtiene items por clave global y persiste observaciones con contexto de fuente/mercado | Agregar una FK global desde `partial_items` al catálogo podría etiquetar también simulaciones que compartan clave |
| [Migración 004](../backend/migrations/004_create_partial_export_evidence.sql) | Exports sellados y hechos nativos append-only; guardan también identidades originales y manifest | No reescribir claves, facts, hashes ni evidencias para incorporar nombres |
| [Simulador fresh](../backend/app/ingestion/fresh_simulator.py) | IDs desde `1900000000`, nombres `FICTIONAL material NN`, flag `fictional` en su catálogo generado | No mapearlos a items reales por orden, perfil económico ni semejanza de nombres |

No se inspeccionó el contenido de PostgreSQL. Estas conclusiones describen código, esquema versionado y archivos de ejemplo, no certifican qué filas están cargadas actualmente.

### 5.2 API y React

- [GET /items](../backend/app/api/items.py) busca con `ILIKE` por nombre o `external_item_id` en la tabla de Fase 2; `/{item_id}` e histórico usan la PK interna, no el ID del juego. El límite se acota a 1–100. No consulta `partial_items`.
- [GET /partial/items](../backend/app/api/partial.py) exige `market_id`, usa `limit/offset` (máximo 100 por página), lista claves con observaciones de ese mercado y no ofrece búsqueda por nombre.
- [Cliente React](../frontend/src/api/client.ts) carga todas esas páginas. [App.tsx](../frontend/src/App.tsx) filtra localmente por `item_key`, `external_item_id` y `key_kind`; no usa el buscador de Fase 2.
- [ItemList](../frontend/src/features/market/ItemList.tsx) muestra `Item {item_key}`, tipo e ID. Ya admite `getLabel`; selección y keys dependen de la clave completa. [MarketResults](../frontend/src/features/market/MarketResults.tsx) también titula con `context.item_key` y muestra SIMULATED.
- [Contratos parciales de React](../frontend/src/api/contracts.ts) sólo incluyen identidad, sin nombres/iconos. `/partial` carece de modelos de respuesta OpenAPI explícitos. Los contratos de métricas se derivan de [market/contracts.py](../backend/app/market/contracts.py), con [tipos generados](../frontend/src/api/generated.ts) y [esquemas runtime](../frontend/src/api/response-schemas.json). Cualquier extensión futura debe mantenerlos sincronizados.

La revisión de [ARCHITECTURE](ARCHITECTURE.md), [AUCTIONATOR_340](AUCTIONATOR_340.md), [ROADMAP](ROADMAP.md), [validación 4A](PHASE_4A_VALIDATION.md), [validación 4A.1](PHASE_4A1_VALIDATION.md) y [README](../README.md) concuerda con separar snapshots completos de evidencia parcial y conservar fallback por clave. La validación auténtica de Auctionator en Forever sigue pendiente. No es indispensable cambiar esos documentos para registrar esta investigación.

## 6. Modelo y arquitectura propuestos

Los nombres siguientes son conceptos de diseño, no tablas ni contratos implementados. Evitar renombrar/reutilizar `items` o `partial_items` para otro significado.

### 6.1 Identidad, revisiones y evidencia

| Concepto | Datos mínimos propuestos | Regla |
| --- | --- | --- |
| `catalog_item` | PK interna propia, `product`, `content_namespace`, `game_item_id` auténtico | Unicidad por producto/namespace/ID. Beta y lanzamiento no comparten namespace sin una política de continuidad acreditada |
| `catalog_revision` | Item, versión de cliente, build textual, canal beta/release/unknown, revisión de catálogo | Atributos pertenecen a un build; build ausente queda null/unknown, nunca se inventa |
| `catalog_name` | Revisión, texto, locale observado, fuente del nombre, indicador original/localizado | No convertir el idioma de la web en locale de cliente confirmado; no generar traducciones oficiales |
| Afirmaciones descriptivas | Calidad raw y normalizada, categoría raw, class/subclass IDs si existen, item level y required level separados | Valores opcionales con evidencia por campo; nunca completar calidad o categoría por familiaridad con Classic |
| `catalog_source` / adquisición | URL o referencia de export, tipo de fuente, versión del extractor/addon, fecha de obtención UTC, fecha de observación si existe, hash, permisos/licencia y alcance | `acquired_at` no sustituye `observed_at`; URL sin hash no acredita un snapshot reproducible |
| `catalog_icon_ref` | Tipo `client_file_id`, `client_path`, `external_url` o `managed_asset`; valor, proveedor, build y estado de derechos/disponibilidad | Referencia externa no implica recurso administrado. Sólo un asset autorizado y almacenado recibe URL propia |
| `market_catalog_binding` | Contexto de mercado/fuente, clave exacta o identidad legacy, item base, revisión/namespace aplicable, estado y evidencia de asociación | Enlace explícito contextual; no FK descriptiva global desde `partial_items` |

La unicidad de afirmaciones debe incluir fuente y alcance: dos proveedores pueden discrepar en un mismo build/locale. Una revisión puede contener candidatos por campo y una proyección de lectura seleccionada con regla/versionado de resolución. Para diez items alcanza una estructura sencilla con candidatos/procedencia; no hace falta un sistema genérico de ontologías.

Estados de verificación propuestos: `reference_only`, `provider_reported`, `observed`, `corroborated`, `disputed`, `rejected`. Registrar método y responsable/evidencia de la decisión. Ninguno implica lanzamiento: `release_channel` es independiente. La marca de confirmación del fan site se guarda como afirmación de proveedor, no como observación nuestra. `synthetic` y el estado de permisos también son dimensiones independientes.

Ausencia: null y motivo (`not_provided`, `not_observed`, `unavailable`, `restricted`, `unsupported_build`). No confundir false, cero, vacío legible y desconocido. Un conflicto conserva todos los candidatos, sus builds/locales/fechas, y puede dejar la proyección sin valor. No aplicar “última fuente importada gana”. Los atributos observados en tooltips de una variante/personaje no se promueven automáticamente a atributos universales del item base.

### 6.2 Enriquecimiento sin tocar históricos

```text
Export autorizado / observaciones propias
  -> adaptador de catálogo -> staging y validación -> catálogo versionado
                                                      |
Identidad de mercado + procedencia -> resolver binding --+
  -> respuesta descriptiva opcional -> React (nombre o fallback por clave)

Auctionator -> evidencia parcial -> series/métricas existentes
```

Resolver una asociación requiere: fuente real verificada, producto/namespace identificado, tipo de entidad compatible y build conocido o compatibilidad explícita revisada. `dataset=real` es necesario para los mercados actuales, pero es una declaración de ingestión: por sí solo no certifica producto ni build. Si falta evidencia, devolver `unresolved` o `build_unknown`, conservar la clave y ofrecer, como máximo, una referencia candidata claramente identificada.

La asociación debe estar delimitada al menos por mercado y procedencia de serie/import. No basta `partial_items.id`: es compartido. El mismo ID numérico puede aparecer en un mercado simulado, otro producto o una especie de mascota. Para Fase 2, conservar todas las filas e identidades legacy y no asociarlas automáticamente; una futura ingestión real completa requeriría antes resolver su unicidad global por ID. Esa ingestión queda fuera del MVP.

Una respuesta futura de enriquecimiento puede contener `base_item_ref`, `display_name`, `display_locale`, `verification_status`, `build_status`, `catalog_revision_id`, `source_ref` e icono opcional. Debe distinguir nombre del item base de nombre exacto de variante. Recomendación inicial: endpoint adicional de enriquecimiento por lote y contexto, sin cambiar ingestión ni cálculos de mercado. Las rutas concretas quedan para la implementación. El catálogo general puede listar items sin mercado; la lista de un mercado sigue incluyendo únicamente sus items observados.

### 6.3 Versiones y futuro Profession Planner

Un cambio entre builds agrega una revisión; no sobrescribe la anterior, cambia IDs internos históricos ni modifica exports. Mismo ID y nombre distinto no obliga a crear un item nuevo si la continuidad está probada. Si hay reutilización del ID o cambia la línea de contenido, abrir otro namespace/identidad y mantener relación de sucesión revisada. Un ID ausente de un export parcial no significa eliminado del juego.

Para un histórico sin build de observación no se debe mostrar un tooltip nuevo como si describiera el item de aquel momento. Una etiqueta de referencia actual podría mostrarse con esa limitación; la consulta reproducible debe identificar la revisión de catálogo usada. Una serie acumulada que cruza builds no se divide retroactivamente inventando límites: conservarla y señalar que su compatibilidad de contenido es desconocida. Futuras importaciones pueden adjuntar contexto verificable sin alterar la clave nativa.

Recetas: modelar después identidad propia de receta/profesión, build, fuentes, outputs e ingredientes con cantidad, slots/alternativas y condiciones. Referenciar items base auténticos, y variantes sólo cuando la receta exponga requisitos específicos. Mantener ingredientes sin resolver. No deducir receta por nombre del producto, ni equiparar recipe ID, spell ID e item ID. El catálogo puede existir sin precio y una receta sin histórico de mercado; para costes se seleccionará explícitamente mercado y serie compatibles. La fuente profesional observada no acredita todas las recetas del servidor.

## 7. Relación con Auctionator y riesgos de compatibilidad

La evidencia local reproducible está en [normalize_item_key](../backend/app/ingestion/auctionator_keys.py), [contrato parcial](../backend/app/ingestion/partial_contracts.py), [contratos de series](../backend/app/market/contracts.py) y [AUCTIONATOR_340](AUCTIONATOR_340.md). Los siguientes son formatos, no afirmaciones de que exista un item particular con esos atributos:

| Forma nativa | Interpretación actual | Enriquecimiento permitido |
| --- | --- | --- |
| `ID` | Item básico | Resolver item base en producto/namespace confirmado |
| `g:ID:nivel` | Variante por gear level | Puede compartir nombre base; mantener clave/nivel y serie separados |
| `gr:ID:sufijo` | Variante por sufijo | Conservar sufijo opaco y clave completa; nombre base no identifica el sufijo |
| `p:speciesID` | Especie de mascota | No buscar `speciesID` en `catalog_item.game_item_id`; futuro catálogo de especies separado |

`external_item_id` contiene el componente numérico también en mascotas; su nombre actual no garantiza que represente un item del juego. Ni `items.id` ni `partial_items.id` son IDs auténticos. Un link exacto de ForeverTome puede contener más información que una DBKey de Auctionator: no son intercambiables ni forman una relación uno-a-uno. Cualquier conversor futuro requerirá evidencia del build y del algoritmo del addon; el MVP no lo necesita.

La identidad de una serie conserva `market_id`, `item_key` completa, `source_id`, `source_type`, `temporal_basis`, `series_mode` y `export_id` cuando corresponde. Añadir un nombre no puede agrupar por ID base ni cambiar esos selectores. No compartir caché de enriquecimiento por ID numérico solamente.

`source_version=340` identifica el formato de Auctionator seleccionado por el operador/parser y `database_version=8` el formato de su base; ninguno es el build del cliente. Los contratos actuales de mercado no aportan un build del juego verificable. Tampoco una región o un `source_id` introducidos por el operador lo certifican: esa evidencia deberá adjuntarse y revisarse por separado para resolver el catálogo.

Semántica que debe permanecer: `l`/fallback de `h` representan mínimo diario guardado; `h`, mayor mínimo; `a`, disponibilidad máxima; `m`, último mínimo sin fecha verificable. La proyección de un export y los extremos acumulados son distintos. Nombres/builds del catálogo no aportan timestamps de scans, ventas, promedio de listings ni volumen vendido. No insertar metadatos en manifests/hash de exports anteriores.

| Riesgo | Control propuesto |
| --- | --- |
| Colisión simulación/real, incluida la de `2770` en samples legacy | Ningún binding auténtico para históricos simulados; prueba negativa con el mismo número en ambos contextos |
| Colisión de producto/canal/build | Namespace y contexto explícitos; desconocido bloquea confirmación automática |
| Mezclar variantes o mascotas | Resolver según `key_kind`; conservar claves completas y entidad distinta para especies |
| Perfil ForeverTome 69893 frente a fichas 70009 y profesión 70205 | Validar el cliente instalado; no extender allowlist por analogía |
| Localización incompleta y nombres duplicados | Identidad por ID/contexto; fallback de idioma explícito sin traducir IDs |
| Scraping frágil o sin autorización | Export acordado o capturas propias; sin dependencia de APIs internas |
| Icono remoto caído, cambiado o sin permiso | Placeholder; no descarga/hotlink por defecto ni promesa de disponibilidad |
| Conflictos o cambios de atributos | Revisiones y evidencia por campo; resolución auditable |
| HTML/links no confiables | Renderizar nombres como texto React; no `dangerouslySetInnerHTML`; validar esquemas/URLs |
| Catálogo ausente o lento | Métricas conservan su identidad y funcionamiento; enriquecimiento opcional y cancelable |

## 8. Diseño del MVP: diez materiales verificados como referencia

La muestra se concentra en minería, materiales y productos intermedios. Todas las filas siguientes se leyeron en sus fichas públicas: nombre, ID, calidad, categoría Trade Goods, item level, stack y build. **Verificadas como publicación del proveedor, no como captura propia ni confirmación del lanzamiento.** Se eligió conservar aquí sólo los campos necesarios para revisar la selección; no es un dataset autorizado para importar.

| ID | Nombre publicado / fuente individual | Calidad publicada | Item level | Build de la ficha |
| --- | --- | --- | --- | --- |
| 2770 | [Copper Ore](https://warcraftforever.games/items/2770) | Common | 10 | 1.60.1.70009 |
| 2771 | [Tin Ore](https://warcraftforever.games/items/2771) | Common | 20 | 1.60.1.70009 |
| 2835 | [Rough Stone](https://warcraftforever.games/items/2835) | Common | 5 | 1.60.1.70009 |
| 2838 | [Heavy Stone](https://warcraftforever.games/items/2838) | Common | 25 | 1.60.1.69893 |
| 2840 | [Copper Bar](https://warcraftforever.games/items/2840) | Common | 10 | 1.60.1.70009 |
| 2841 | [Bronze Bar](https://warcraftforever.games/items/2841) | Common | 20 | 1.60.1.70009 |
| 3576 | [Tin Bar](https://warcraftforever.games/items/3576) | Common | 20 | 1.60.1.70009 |
| 3857 | [Coal](https://warcraftforever.games/items/3857) | Common | 30 | 1.60.1.69893 |
| 12365 | [Dense Stone](https://warcraftforever.games/items/12365) | Common | 45 | 1.60.1.69893 |
| 249426 | [Pitchblende](https://warcraftforever.games/items/249426) | Uncommon | 60 | 1.60.1.70009 |

[Mining](https://warcraftforever.games/professions/mining) vincula estos materiales con recetas, incluido Pitchblende para Azerothium Bar. No se incorporan cantidades/requisitos de esas recetas al MVP. No asumir que todos los materiales están disponibles en el nivel accesible del cliente, que sean comerciables ni que deban aparecer en nuestro AH. Si no se pueden observar diez de ellos, documentar cobertura y completar la prueba únicamente con sustitutos cuyo ID/nombre se verifiquen realmente; no rellenar valores.

Se intentaron también fichas de Iron Ore (`2772`), Mithril Ore (`3858`), Thorium Ore (`10620`), Heavy Thorium Ore (`248815`), Heavy Thorium Bar (`251291`), Silver Bar (`2842`), Silver Ore (`2775`) y Gold Ore (`2776`). Se pudo seguir su enlace desde Mining, pero las fichas fallaron en la herramienta. No se atribuyen calidad, nivel ni build a esos candidatos; quedan fuera de la muestra validada.

### 8.1 Obtención verificable y conservación

1. **Resolver origen y derechos.** Elegir un export de muestra autorizado por el proveedor o capturas propias dentro de las condiciones aplicables del cliente. No iniciar scraping. Documentar permiso/condiciones para metadatos y, separadamente, imágenes. La muestra publicada arriba sólo orienta la selección.
2. **Comprobar el build real.** Con ForeverTome, usar versión/revisión fijada y perfil compatible. Si el cliente difiere de 69893, conseguir soporte revisado y validado o elegir otra fuente; no intentar activar lecturas restringidas. No se requiere datamining masivo.
3. **Observar jugando normalmente.** Abrir bolsas/tooltips o fuentes accesibles de los materiales disponibles. Guardar una sesión y exportar una copia mediante la herramienta documentada. Comprobar `synthetic=false`, producto, build, locale, IDs, links y motivos de ausencia. Un flag false solo no prueba autenticidad: revisar la captura y su procedencia.
4. **Revisar el pequeño export.** Contrastar cada ID/nombre con su evidencia propia y, si está permitido, con una ficha pública. Mantener cualquier desacuerdo en revisión. Conservar hash, versión del generador, referencia de sesión/observación, alcance de permisos y fecha; retirar rutas de cuenta e información personal. Los exports reales quedan fuera de Git.
5. **Limitar campos.** Primera proyección: producto/namespace, ID, nombre y locale realmente conocidos, build/canal, fuente, fechas, estado de verificación y derechos. Calidad opcional. Icono sólo como referencia opcional; placeholder en UI. Categoría/niveles/recetas pueden esperar. No copiar tooltips completos ni archivos de imagen sin permiso.
6. **Mantener catálogo sin mercado.** No crear precios, imports, observaciones ni filas de mercado para demostrar nombres. Cuando llegue un SavedVariables auténtico de Auctionator, validar su contexto y asociar por identidad base comprobada conservando `item_key`. Si no existe mercado real compatible, la pantalla de catálogo puede mostrar el item sin precio/histórico.

### 8.2 React y búsqueda

En una etapa posterior, proporcionar a `ItemList.getLabel` el nombre aprobado para ese contexto; usar `Item {item_key}` si no existe binding, falla la carga o hay conflicto. `MarketResults` debe usar la misma resolución. Mantener ID, clave completa y atributos de variante visibles aunque varias filas compartan nombre base. Un resultado simulado conserva etiqueta SIMULATED y fallback ficticio; no recibe icono/nombre del catálogo real por coincidir el número.

La búsqueda local podrá incluir nombre localizado y nombre original observado además de ID/tipo/clave, con fallback de idioma explícito. No modificar la selección ni sus parámetros al cambiar un nombre. La clave de caché debe incluir contexto de mercado/procedencia, locale y revisión de catálogo. Una respuesta tardía del catálogo anterior no puede etiquetar el nuevo mercado. Para un catálogo general futuro, ofrecer búsqueda paginada de catálogo en backend, separada de la búsqueda legacy y de descubrimiento de series.

### 8.3 Pruebas que corresponderían al implementar

| Área | Casos de aceptación |
| --- | --- |
| Identidad | Item real por ID/contexto; mismo número en namespace distinto; `p:ID` no resuelve como item; variantes conservan selección y series distintas |
| Simulación | `1900000000` continúa ficticio; sample legacy `2770` no se enriquece; una `partial_items` compartida por real/simulated no filtra identidad auténtica al simulado |
| Procedencia | Rechazar muestra sintética para catálogo observado; build/producto ausentes no se completan; fechas de adquisición y observación distintas; import idempotente por contenido/contexto |
| Campos y conflictos | Nombre sin calidad; ceros/false; locale sin traducir; campos restringidos; conflicto mismo build/locale no sobrescribe; variante contextual no redefine base |
| Builds | Cambio de nombre/calidad crea revisión; falta de item en export parcial no lo elimina; build desconocido del mercado no se deduce de la fecha de importación |
| Histórico | Enriquecer no cambia conteos, valores, claves, hashes, manifests ni resultados de métricas de una selección idéntica; export y acumulado conservan diferencias |
| Contratos/UI | Runtime schema y tipos acordes; nombre y fallback; búsquedas por nombre/ID; error/ausencia de catálogo; icono fallido; texto hostil escapado; respuestas tardías canceladas; SIMULATED visible |
| Recetas futuras | Ingredientes sin resolver, cantidades y alternativas preservadas por build; ningún precio inventado |

Extender, cuando corresponda, las suites existentes de Auctionator/native exports, integración parcial/mercado y componentes React. La integración futura debe usar `TEST_DATABASE_URL` y el aislamiento ya documentado, nunca desarrollo. No ejecutar tests live o de BD para esta tarea sólo documental. Las pruebas offline no sustituyen una validación manual del addon y de los diez registros en el cliente soportado.

## 9. Comparación de alternativas y plan por etapas

| Alternativa | Ventaja | Bloqueo/límite actual | Evaluación |
| --- | --- | --- | --- |
| Referencia manual del fan site | Fichas utilizables para contrastar IDs y detectar cambios | Permisos de réplica no acreditados, mezcla de builds, HTML sin contrato | Útil para investigación; no elegir como dependencia de ingestión |
| API/export acordado con mantenedor | Podría aportar esquema, versiones y condiciones claras | No se obtuvo API documentada ni acuerdo | Preferible si se consigue autorización suficiente |
| Observaciones propias con ForeverTome | Evidencia auditable y límites explícitos; export local y variantes | Muestra propia pendiente, perfil 69893 y validación nativa pendiente de ciertos campos; derechos de contenido independientes | Ruta técnica recomendada para piloto condicionado |
| Scraping o API interna no documentada | Acceso técnico potencial | No acredita derechos, límites ni estabilidad | NO GO en el estado actual |
| Dataset de otra rama de WoW / Classic | Puede ser conocido o fácil de obtener | No prueba identidad/atributos de Forever ni reutilización permitida | No usar como fuente autoritativa o relleno silencioso |

| Etapa futura | Resultado y condición de salida |
| --- | --- |
| 0. Cerrar evidencia y permisos | Muestra autorizada o propia, condiciones de uso registradas, build/producto/locale verificables y perfil de captura válido. Sin esto no cargar catálogo auténtico |
| 1. Contrato y staging offline | Acordar namespaces, campos mínimos, estados y revisión; adaptar sólo diez registros con procedencia. Validación y revisión de conflictos, sin tocar registros de mercado |
| 2. Catálogo independiente | Implementación aditiva en una tarea posterior: persistencia propia, carga idempotente y consulta paginada/por lote. Cero backfill descriptivo en históricos simulados |
| 3. Bindings y UI | Enriquecimiento opcional por contexto; nombres/fallback, variante e ID visibles, contratos sincronizados; pruebas de colisión y cancelación |
| 4. Mercado auténtico | Obtener y validar Auctionator real con reglas AH, codec, reloj y producto/build; crear asociaciones comprobadas. Conservar carencias y semántica de la fuente |
| 5. Expansión controlada | Sólo tras el piloto: más items, política de cambios entre builds, recursos de iconos autorizados y relaciones de recetas/materiales |

Separar catálogo y mercado permite realizar las etapas de descripción antes de contar con precios reales, pero no permite presentar la simulación existente como mercado de esos items. La incorporación al catálogo no cierra por sí sola la validación real pendiente de la Fase 6 del roadmap.

## 10. Recomendación final y pendientes

**CONDITIONAL GO para el piloto; no comenzar todavía la carga/integración real.** Hay evidencia suficiente para definir arquitectura e identificar diez candidatos sin inventar IDs. La ruta recomendada es generar una muestra propia pequeña mediante un perfil de ForeverTome validado, o conseguir un export autorizado con contrato y permisos claros. No hace falta otra base masiva: hace falta esa muestra y acreditar su uso antes de implementar el catálogo auténtico. La réplica automatizada del fan site permanece NO GO sin condiciones verificadas.

**Comprobado:** fichas públicas con IDs/nombres/calidad/build y referencias de iconos; diez materiales con campos publicados; coexistencia de builds beta; licencia GPL v2 y código/export de ForeverTome a ref fijo; modelo y contratos locales; colisiones de identidad posibles y una coincidencia concreta en samples legacy. Los datos web son afirmaciones de proveedor, no mediciones propias del juego.

**Sin confirmar:** API/export público autorizado del sitio, licencia de su base/iconos, reglas de automatización, bytes de imágenes y traducciones de nombres; datos definitivos de lanzamiento; funcionamiento de todas las lecturas nuevas de ForeverTome en el cliente actual; permisos aplicables a publicar el contenido capturado; muestra propia de diez items; SavedVariables auténtico y correspondencia de variantes/contexto de Auctionator en Forever. Tampoco se auditó el contenido actual de PostgreSQL.

**Alcance del cambio:** únicamente `docs/ITEM_CATALOG_RESEARCH.md`, nuevo y sin versionar hasta decisión posterior del usuario. No fue necesario actualizar ROADMAP, ARCHITECTURE ni README: este informe registra una propuesta condicionada, sin cambiar el estado de implementación. Validación de esta entrega: revisión de referencias locales, formato/diff y estado Git; sin ejecutar suites ni tocar BD. HEAD permanece en el commit inicial indicado; sin commit ni push.

## 11. Validación práctica de la fuente: procedimiento para obtener la muestra

### 11.1 Resultado y alcance de la segunda inspección

**NEEDS MANUAL VALIDATION.** No hay todavía una muestra propia de 10–20 items aceptada. Se leyó íntegramente este informe y se volvió a consultar la rama pública `main` de ForeverTome: sigue en `1c92db983b4668cc408ae5e7b4873b4b1086f734`. El código y los documentos no cambiaron respecto de la revisión anterior; los hallazgos nuevos provienen de revisar el flujo de captura, comandos, estados y generación con más detalle. No se descargaron bases, ejecutaron herramientas del addon ni instalaron componentes. No se inspeccionaron instalaciones del juego ni cuentas del usuario.

Evidencia adicional, siempre al ref fijo anterior:

| Referencia | Archivo y evidencia puntual |
| --- | --- |
| P1 | [Compatibility.lua, líneas 3–43](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/ForeverTome/Compatibility.lua#L3): identidad del cliente, comparación exacta de build y capacidades |
| P2 | [Inventory.lua, líneas 15–31 y 97–168](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/ForeverTome/Inventory.lua#L15): snapshots de almacenamiento y solicitudes de metadatos; eventos que los activan |
| P3 | [Loot.lua, líneas 170–203 y 254–376](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/ForeverTome/Loot.lua#L170): campos básicos, `item.metadata`, pendientes, timeout y links. Blob `de98efedd9f9011d63ea42bef20f1e9e8953f4c2` |
| P4 | [Bootstrap.lua, líneas 30–81](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/ForeverTome/Bootstrap.lua#L30): comportamiento real de `/ft dump`, `/ft export` y `/ft status` |
| P5 | [Core.lua, líneas 673–688](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/ForeverTome/Core.lua#L673): sesión con cliente, producto, addon, perfil y capacidades; aviso en build no soportado |
| P6 | [build_catalog.py, líneas 50–53, 95–159 y 209–234](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/tools/build_catalog.py#L95): contexto, hash, formato y export de un archivo nuevo |
| P7 | [export_saved_variables.py, líneas 377–399 y 448–469](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/tools/export_saved_variables.py#L377): parser de datos, lectura estable y formatos JSON/JSONL; SQLite es opcional |
| P8 | [catalog_entities.py, líneas 85–217](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/tools/catalog_entities.py#L85): identidad por contexto/tipo/ID, hechos, display y variantes por link exacto |
| P9 | [Plan de validación WF](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/docs/04-validation/wf-test-plan.md): identidad medida y casos de persistencia, caché e inventario; es un plan con casos no ejecutados |

El árbol de archivos del repositorio se pudo consultar sin truncamiento. Se identificó `LICENSE`; no se encontró un archivo separado de licencia de datos por nombre ni una licencia específica del output en los documentos revisados. Esto no demuestra que no exista otra declaración o acuerdo. No se encontró ni descargó una muestra real distribuida y autorizada que permita marcar SAMPLE AVAILABLE.

### 11.2 Compatibilidad y posibilidad de capturar en beta

El addon es **0.3.0**, con TOC Interface **16001**. Su condición de soporte es `client.version == "1.60.1"` y `client.build == "69893"` (P1). Lee además `WOW_PROJECT_ID`, locale, fecha de build e interface. En ese perfil registra producto `WF`; en otro, `UNKNOWN`, y restringe la captura a lifecycle. El build reconocido activa las rutas, pero las capacidades siguen declaradas `wf_unverified`: habilitación técnica y validación en juego son cosas diferentes.

| Situación real del usuario | Siguiente paso viable |
| --- | --- |
| Acceso jugable a beta `1.60.1.69893` | Hacer el ensayo de dos items y luego ampliar a 10–20. No hay un requisito del exportador de esperar al lanzamiento |
| Beta jugable con otro build | Esta revisión no acredita captura de items. Obtener soporte revisado del mantenedor o una muestra previa/colaborador con build soportado. No cambiar TOC, allowlist ni etiquetas para forzar compatibilidad |
| SavedVariables auténtico ya guardado de un build soportado | Se puede exportar offline, sin cliente activo. Verificar origen, sesión y campos; no reconstruir detalles que nunca se capturaron |
| Sin acceso jugable ni archivo auténtico | Solicitar una captura acotada a un colaborador o un export autorizado al mantenedor. Esperar al lanzamiento sólo ayudaría si después existe acceso y un perfil compatible; no lo garantiza |

No se verificó que hoy pueda iniciarse sesión en ese build ni que el usuario tenga acceso a la beta. Una instalación antigua presente en disco no basta. Las fichas del sitio con builds más nuevos tampoco acreditan compatibilidad del addon. No hay motivo para preferir datos de lanzamiento si el objetivo inmediato es probar un catálogo **etiquetado beta**; para describir lanzamiento habrá que volver a observarlo allí.

### 11.3 Qué activa la captura y qué se puede esperar del export

P2 muestra que la entrada al mundo y `BAG_UPDATE_DELAYED` programan lecturas del almacenamiento accesible. Cada item legible dispara `FT.RequestItem(item_id, link, observation_id)`. `/ft dump` fuerza una nueva revisión de almacenamiento mediante `FT_CATALOG`; también inicia otros colectores, por lo que **no es un comando para capturar sólo diez items**. El flujo de bolsas de P3 también solicita metadatos de los IDs/links presentes en el baseline. Mirar un tooltip, por sí solo, no es una garantía de captura; para el ensayo conviene tener los materiales físicamente en las bolsas.

P3 emite `item.metadata` cuando dispone de nombre y metadatos legibles. Si no resuelve, puede emitir `item.metadata_unresolved` con motivo, incluso timeout. La espera está limitada a 15 segundos por solicitud, con hasta tres lecturas de detalles; la UI de status **sólo informa pendientes de spells**, no una cola pendiente de items. Esperar un margen antes de guardar es una medida práctica, no una prueba de éxito: el archivo exportado es lo que se revisa.

`/ft save` y `/ft export` **sólo imprimen instrucciones**. La escritura al disco la realiza el cliente mediante `/reload` o salida normal. No generan JSON ni envían datos. La ubicación esperada es la carpeta de producto del cliente, `WTF/Account/<cuenta>/SavedVariables/ForeverTome.lua`; debe comprobarse el archivo creado, sin inferir la ruta de la instalación del autor.

| Salida | Forma y uso en esta prueba |
| --- | --- |
| SavedVariables original | Lua de datos con `ForeverTomeDB`, `schema_version=1`, `synthetic`, sesiones y observaciones. Conservar copia íntegra privada; no ejecutar el Lua |
| Export crudo con `export_saved_variables.py` | JSON por defecto; JSONL mediante `--format jsonl`. Conserva la evidencia normalizada. No hace falta SQLite ni usar `--sqlite` |
| Export recomendado con `build_catalog.py` | Un JSON `format="forevertome.website-catalog"`, `schemaVersion=1`, `generatorVersion="0.3.0"`; incluye `source`, `contexts`, `sessions`, `catalog`, `transactions`, `observations` y `summary` |
| Exporter de escritorio | Alternativa documentada que genera también historia y vistas acumuladas; no necesario para una captura puntual. La estructura de `items.json` no es la de `catalog.items` del JSON puntual |

El export puntual calcula `source.sha256` sobre los bytes de la copia original y deriva `exportId` incluyendo formato, schema y versión del generador. Conserva `source.synthetic`; **acepta tanto true como false**. Que el comando termine bien no certifica autenticidad ni diez items descriptivos. El hash prueba integridad/comparación de bytes, no firma del cliente ni autoría de la captura (P6–P7).

### 11.4 Procedimiento manual mínimo, sin importar nada

Estos son pasos para el usuario en una sesión posterior. No se ejecutaron aquí. Elegir una carpeta privada nueva **fuera de este proyecto y fuera de Git**. No hace falta comprar materiales, capturar precios, abrir Auctionator ni preparar una base de datos.

1. **Comprobar el cliente antes de instalar.** Con acceso normal al juego, anotar producto seleccionado en el launcher, fecha y resultados de los comandos de identidad documentados en P9:

   ```text
   /dump GetBuildInfo()
   /dump WOW_PROJECT_ID
   /dump GetLocale()
   ```

   Guardar la salida o una captura acotada sin datos personales. Debe corresponder al producto Forever beta y al build soportado. Si esos comandos no funcionan o no se puede confirmar la identidad, registrar el fallo y no afirmar compatibilidad. No usar dumps amplios de memoria o datos sociales.

2. **Preparar una revisión reproducible del addon.** Obtener el código fuente de la revisión fijada en este informe en una carpeta separada; guardar su SHA. La [instalación manual documentada](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/README.md#install-and-record) consiste en copiar la subcarpeta `ForeverTome` a `Interface/AddOns/ForeverTome` del producto correcto. Preservar cualquier instalación/grabación previa; no ejecutar `/ft clear confirm`. Iniciar completamente el cliente y activar el addon. El instalador de escritorio descarga `main` al actualizar, así que no es la vía preferida para mantener el ref fijo. No se instaló ni descargó ese ejecutable en esta tarea.

3. **Ensayo de dos items.** Entrar con uno o dos materiales distintos ya disponibles en las bolsas y verificar `/ft status`. Debe informar `recording` y perfil `forever-beta-69893-source-v1`, sin bloqueo o pausa. Si está pausado, `/ft resume`. Ejecutar una vez `/ft dump`. Revisar visualmente nombre y link de esos objetos en el cliente. Esperar unos 20 segundos y hasta que los scans indicados estén idle; este margen cubre el timeout declarado de items pero no garantiza que se hayan resuelto. Salir normalmente del juego para obtener un guardado estable. Si faltan datos, no fabricar una lectura; revisar el export y registrar el caso.

4. **Comprobar guardado y persistencia.** Con el cliente cerrado, localizar el SavedVariables real y copiarlo a una carpeta privada nueva. Confirmar tamaño/fecha y conservar el original. Tras ese respaldo, iniciar y salir normalmente otra vez; comprobar que las observaciones anteriores siguen presentes y que se agregó la sesión correspondiente. Si no restaura, detener la ampliación y conservar ambas copias como evidencia del fallo. No instalar reparaciones de SavedVariables ni editar el guardado como parte de esta prueba.

5. **Exportar la copia offline.** Usar Python 3.10 o superior y los archivos fuente de la misma revisión. No se necesita Lua para ejecutar este exportador Python. En PowerShell, adaptar las rutas de ejemplo; `$ftSource` es la raíz del repositorio externo y `$sampleDir` la carpeta privada que ya contiene la copia `ForeverTome.lua`:

   ```powershell
   $ftSource = 'C:\ruta\ForeverTome-revision-fijada'
   $sampleDir = 'C:\ruta\muestra-privada-01'
   py -3 --version
   Set-Location -LiteralPath $ftSource
   Get-FileHash -LiteralPath "$sampleDir\ForeverTome.lua" -Algorithm SHA256
   py -3 tools/build_catalog.py "$sampleDir\ForeverTome.lua" --output "$sampleDir\catalog-01.json"
   ```

   El archivo de salida debe ser nuevo; el exportador se niega a sobrescribirlo y no modifica la entrada. No usar `--sqlite`, watcher ni opciones de instalación. Un error de parser, schema, lectura o referencias se conserva como resultado fallido; no modificar el original para que pase.

6. **Validar los dos items antes de ampliar.** Inspeccionar el JSON de sólo lectura y aplicar los criterios de 11.5. Comandos de exploración, sin escritura ni importación:

   ```powershell
   $packet = Get-Content -Raw -LiteralPath "$sampleDir\catalog-01.json" | ConvertFrom-Json
   $packet | Select-Object format, schemaVersion, generatorVersion
   $packet.source
   $packet.contexts | Select-Object id, product, client
   $packet.catalog.items | Select-Object nativeId, key, contextId, displaySourceId,
     @{Name='observedName'; Expression={$_.display.name}}
   $packet.observations | Where-Object type -eq 'item.metadata' |
     Select-Object id, contextId, sessionId, data, missingFields
   ```

7. **Ampliar a 10–20 IDs base distintos.** Si el ensayo y la persistencia funcionan, repetir con materiales accesibles jugando normalmente, usando la lista de la sección 8 sólo como orientación. No es obligatorio conseguir materiales de alto nivel. No asignar a sustitutos IDs recordados de Classic: obtenerlos de los links/registros del propio cliente. Mantener los originales y generar `catalog-02.json` con destino nuevo. El conteo se hace sobre los IDs aceptados en un mismo contexto, no sobre stacks, variantes, sesiones ni el total de entidades del export.

8. **Conservar un paquete privado de revisión.** Copia original, JSON íntegro, hashes, revisión del addon/exportador, identidad medida del cliente, fecha, pasos seguidos y una lista de los 10–20 IDs seleccionados con su resultado de validación. Mantener las referencias de sesión/observación y los registros relacionados. No recortar a mano el JSON ni borrar fuentes para obtener exactamente diez filas: se seleccionan los items a revisar y se conserva el contexto completo. No subir el paquete a Git, al fan site ni a nuestro backend.

### 11.5 Criterios para aceptar cada item y el conjunto

| Comprobación | Aceptación / resultado si falta |
| --- | --- |
| Origen | Captura propia o de colaborador identificado para la revisión, con pasos y contexto medidos; `source.synthetic=false` necesario pero insuficiente |
| Cliente/contexto | `contexts[].product=WF`, cliente `version=1.60.1`, `build=69893`, locale y sesión coherentes con la medición; otra versión no hereda compatibilidad |
| Evidencia descriptiva | Registro `item.metadata` legible con `data.item_id` y `data.name`, no sólo referencia desde receta/inventario o `item.metadata_unresolved` |
| Identidad | `nativeId` coincide con `data.item_id`; el componente `item:ID` del link legible coincide. Si no hay link suficiente para verificar, dejar el caso pendiente para esta primera muestra |
| Nombre | Contrastar el nombre capturado con el mostrado por el cliente en ese locale. La ficha web es corroboración opcional, no condición ni sustituto |
| Cadena de procedencia | `key`, `contextId`, `sourceIds`, `displaySourceId`, sesión y registro descriptivo resolubles. El `display` es una selección representativa; inspeccionar `details` y `facts` ante contradicciones |
| Variantes | Conservar `requested_link`, `link` resuelto, `variants[].link`, clave y `sourceIds` sin normalización destructiva. Si links difieren, revisar; no asumir que la variante solicitada y la resuelta son equivalentes |
| Atributos opcionales | Calidad, niveles, categorías e iconos sólo si fueron leídos. Metadatos básicos válidos pueden aceptarse aunque stats/tooltip estén unavailable; conservar el motivo |
| Tiempo | Mantener observación de servidor si existe, tiempo transcurrido y orden de sesión. La fecha de copia/exportación no sustituye la de observación |
| Integridad | SHA-256 de la copia coincide con `source.sha256` ignorando mayúsculas/minúsculas; export sin errores y referencias completas. No prueba autenticidad criptográfica del juego |
| Cobertura | 10–20 IDs base distintos con resultado aceptado en el contexto elegido; anotar descartes y pendientes. Dos variantes del mismo ID no cuentan como dos items base |

P8 construye la clave de entidad con contexto, tipo e ID y la de variante con el hash del link exacto. Esas claves no son DBKeys de Auctionator. Para este ensayo no se genera ninguna correspondencia ni se asocia a los IDs ficticios existentes. Tampoco observar un material en bolsas acredita dónde se obtuvo: el canal `observed_storage_only` no demuestra compra, loot o recolección. Separar **origen de la evidencia** de **origen de adquisición del objeto**; el segundo puede seguir desconocido.

No basta con que `summary.catalogCounts.items` sea mayor o igual a diez: puede contar entidades sin descripción. No se exige que iconos o stats funcionen para validar ID/nombre/build, y un campo ausente nunca se rellena con datos del fan site o de otra rama. Si un nombre o atributo discrepa, conservar ambos hechos y excluir ese campo de la proyección aprobada hasta revisarlo.

### 11.6 Código, datos producidos e iconos: permisos separados

- **Código:** se volvió a leer el [LICENSE GPL v2](https://github.com/Skold177/ForeverTome/blob/1c92db983b4668cc408ae5e7b4873b4b1086f734/LICENSE). Permite usar el programa bajo sus condiciones; modificaciones y distribución de código tienen obligaciones propias. Ejecutarlo localmente para exportar no significa incorporar su código a nuestra aplicación.
- **Datos producidos:** no se verificó una licencia específica del conjunto de observaciones generado. La sección 0 de GPL no convierte automáticamente cualquier salida en obra GPL, ni concede permisos sobre contenido de terceros. Ser autor de la grabación no elimina condiciones del juego. Obtener la captura y revisarla localmente no equivale a autorizar su publicación como dataset. Para un colaborador, registrar permiso para el uso/revisión acordado y confirmar por separado cualquier redistribución.
- **Iconos:** el export contiene IDs/rutas de archivo cuando son legibles, no imágenes ni una licencia para extraerlas, hospedarlas o enlazarlas desde otro proveedor. La muestra se puede validar con ID/nombre/build y conservar la referencia opcional; la publicación de imágenes queda pendiente de derechos/resolvedor. No descargar iconos para este ensayo.

No se añade un requisito de conseguir permiso del fan site para capturar datos propios: esa fuente sólo necesita autorizar el uso de su contenido si elegimos reutilizarlo. Los permisos sobre cliente/datos/arte y sobre grabaciones de colaboradores siguen siendo cuestiones separadas.

### 11.7 Siguiente paso y criterio de cambio de veredicto

**Acción inmediata del usuario:** comprobar acceso jugable y enviar sólo los resultados textuales de `GetBuildInfo()`, `WOW_PROJECT_ID`, `GetLocale()` y si ya existe un SavedVariables propio. No hace falta compartir rutas de cuenta ni el archivo completo para decidir compatibilidad. Si el build coincide, seguir primero el ensayo de dos items; si pasa, ampliar a diez. Si ya hay un archivo auténtico, la ruta offline permite comenzar por su export y revisión sin volver a entrar al juego.

El veredicto pasa a **SAMPLE AVAILABLE** cuando existe el paquete real con 10–20 IDs aceptados y procedencia revisada; no significa autorización automática para publicarlo. Pasa a **SAMPLE BLOCKED** si se confirma que no hay acceso/archivo/colaborador viable, o que el único cliente disponible es incompatible y no hay perfil validado. En ese caso la solicitud concreta al mantenedor/colaborador es una grabación pequeña de materiales con build/locale, SavedVariables o export íntegro con fuentes, revisión del generador y permiso de uso especificado. No solicitar una base completa.

Con la evidencia disponible al cerrar esta revisión, se mantiene **NEEDS MANUAL VALIDATION**: la ruta técnica existe, pero faltan la identidad medida del cliente del usuario y la captura auténtica. Esperar al lanzamiento no resuelve por sí mismo esos puntos. La recomendación general sigue en CONDITIONAL GO y no se ha iniciado implementación, importación ni modificación de datos.
