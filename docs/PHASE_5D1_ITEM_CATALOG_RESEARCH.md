# Fase 5D.1 — Investigación técnica de catálogo real

**Actualización de cierre, 28/10/2026:** investigación cerrada para el MVP de
metadatos puntuales con AHledger. Se conserva debajo el informe original y su
veredicto del 26/10. La decisión y los límites nuevos figuran en §8 y en
[5D.2](PHASE_5D2_ITEM_CATALOG.md); no se declara resuelta la licencia de iconos.

Consulta: **26/10/2026**, America/Buenos_Aires. Base inspeccionada:
`fb9ca648c26c1e28fa7f0cf96ee63bcce2799b20`, `main`, árbol inicialmente limpio.

**Veredicto: NEEDS ACCESS / FURTHER RESEARCH.** Se demostró factibilidad parcial:
AHledger entregó metadatos JSON de los cuatro IDs, cuatro iconos fueron accesibles
y una receta devolvió ingredientes y cantidades. Eso permite diseñar un adaptador,
pero todavía no acreditar compatibilidad por build/idioma ni derechos de uso de
iconos para una integración de producción. ForeverDB es una alternativa documentada
con mejor contexto de versión, pendiente de autorización y pruebas reales.

Entrega exclusivamente documental. No se implementó catálogo, importador,
sincronización, calculador, endpoint ni UI. No se abrió PostgreSQL, importaron
capturas, cambiaron migraciones o ejecutaron addons/binarios descargados. No se
inició sesión, solicitaron claves, otorgaron permisos ni enviaron mensajes a terceros.
Sin commit ni push.

## 1. Método y significado de las etiquetas

- **VERIFICADO POR RESPUESTA REAL:** HTTP observado o contenido público leído;
  se indica si es JSON, HTML o imagen. No significa validación propia en el juego.
- **DOCUMENTADO, NO PROBADO:** afirmación del proveedor o contrato sin ejecución
  del endpoint/capacidad correspondiente.
- **NO DISPONIBLE:** no se obtuvo esa capacidad/dato en este alcance; no demuestra
  que el proveedor nunca pueda ofrecerlo.
- **REQUIERE AUTORIZACIÓN:** acceso con aprobación/cuenta/clave o permiso de
  reutilización todavía no acreditado. No se intentó sortearlo.

Se combinaron páginas públicas mediante herramienta web con GET directos de
Python/urllib, sin autenticación ni cookies persistidas. El transporte restringido
falló con WinError 10061; el mismo acceso público fuera del sandbox sí funcionó.
La herramienta web tampoco pudo recuperar los JSON de la API: se verificaron
con HTTP directo, sin convertir esos fallos del transporte en una caída del servicio.

Las pruebas JSON/imágenes tuvieron timeout de 15 segundos y tope de 65.536 bytes;
las fichas HTML, 262.144 bytes. Las respuestas exitosas registradas no quedaron
truncadas. User-Agent de investigación, GET secuenciales, sin enumerar IDs,
descargar catálogos completos, ejecutar JavaScript remoto ni probar endpoints
internos supuestos. Los cuerpos y registro temporal quedaron fuera del repositorio;
este documento conserva muestras públicas mínimas, tamaños y hashes. No se
versionaron imágenes, SavedVariables, credenciales, cuentas o rutas personales.

Una consulta adicional a `https://ahledger.com/data` desde urllib recibió **429**.
Se detuvieron los GET a esa página, sin reintentar, rotar origen ni eludir cuotas.
No se conservaron sus headers para atribuirle un Retry-After o una causa concreta.
La representación pública de esa página sí fue legible por la herramienta web;
eso no elimina el 429 observado en el otro transporte.

## 2. Matriz comparativa

| Proveedor | Disponibilidad comprobada | API y acceso | Valor para este proyecto | Límite principal |
| --- | --- | --- | --- | --- |
| [ForeverDB](https://foreverdb.net/developers) | Página developers: GET directo 200, HTML | REQUIERE AUTORIZACIÓN; cuenta, aprobación y API key | Documenta items, contexto de build y profesiones | Ningún JSON de su API probado; permisos de caché/iconos pendientes |
| [AHledger](https://ahledger.com/developers) | Developers legible; API de cuatro items y crafting: 200 JSON | Pública sin clave, VERIFICADO POR RESPUESTA REAL | Primera opción para diseñar consultas puntuales de metadatos | Sin build/locale por item en la muestra; límites y disponibilidad variables |
| [Warcraft Forever](https://warcraftforever.games/items) | Índice legible y cuatro fichas con GET directo 200 | API JSON pública: NO DISPONIBLE en esta investigación | Contraste manual de nombres, calidad y build declarado | HTML no equivale a API ni permiso de extracción/copia |

No se acreditó una alternativa mejor que estas APIs para consultas por ID.
[La investigación del 15/10](ITEM_CATALOG_RESEARCH.md) conserva la alternativa
local ForeverTome y su revisión fija de código. No se revalidó su ejecución ni
se instaló: sigue pendiente de muestra propia y compatibilidad del cliente.
No se considera un catálogo de lanzamiento confirmado.

### 2.1 Acceso, OAuth y permisos

ForeverDB documenta clave por cuenta aprobada, enviada por header; cuotas de
60/minuto y 10.000/día. Sus reglas exigen atribución enlazada y prohíben reventa
o apropiación. [Contrato público](https://foreverdb.net/developers).
El login pide `openid` para identidad y `wow.profile` para personajes, aunque
declara no leerlos por OAuth. No se abrió consentimiento; antes de autorizar
conviene aclarar la necesidad de ese segundo scope. El Companion no necesita
implementar OAuth de Battle.net para consumir una futura clave de catálogo.
[Explicación del login](https://foreverdb.net/join).

Rutas documentadas de ForeverDB, **REQUIEREN AUTORIZACIÓN / NO PROBADAS**:
`https://foreverdb.net/api/v1/meta`, `/api/v1/items/{id}`,
`/api/v1/professions` y `/api/v1/professions/{slug}?limit=1&offset=0`
(todas bajo `https://foreverdb.net`). Documenta envoltorio `data`/`meta`;
locale e iconos de esos cuatro IDs no comprobados.

AHledger no requirió cuenta ni OAuth en las pruebas. Documenta 300 solicitudes/minuto
por dirección y 60/minuto para herramientas de mercado, caché por headers,
429/Retry-After y 503/Retry-After. Menciona claves opcionales para ampliar cuota,
pero la sección de límites también dice 300 con o sin clave: no depender de una
ampliación sin aclaración. [API](https://ahledger.com/developers).
Las cuentas opcionales usan enlaces por email; no se encontró requisito de
Battle.net para estos GET. [Términos](https://ahledger.com/terms).

Warcraft Forever permite leer las fichas sin cuenta. Su FAQ describe Battle.net
para funciones de usuario: BattleTag/ID y `wow.profile` para comprobar personajes
y propiedad de guild. No son permisos necesarios para leer estos cuatro HTML.
No se verificó el consentimiento ni se encontró contrato de API/cuotas de catálogo.
[FAQ, sección del sitio](https://warcraftforever.games/guides/faq).

### 2.2 Reutilización, caché e iconos

| Proveedor | Metadatos y almacenamiento | Iconos en aplicación propia | Atribución y riesgo |
| --- | --- | --- | --- |
| AHledger | Términos permiten uso personal/comercial de API y piden respetar caché. Caché local con TTL es una interpretación razonable; archivo permanente/republicación completa no se da por autorizado | Referencias y cuatro JPEG accesibles; derechos pertenecen a Blizzard. Falta acreditar base aplicable para mostrar/hotlinkear/rehospedar | Enlace a AHledger; conservar tags de enlaces recibidos. No reventa ni presentarlo como scan propio; servicio beta sin garantía |
| ForeverDB | Uso en aplicaciones documentado tras aprobación; persistencia, caducidad y redistribución local no están suficientemente precisadas | API de iconos/bytes no probada; autorización de arte no acreditada | Crédito visible enlazado; no reventa. Claves dependen de cuenta/aprobación |
| Warcraft Forever | No se encontró autorización de réplica/caché automatizada ni export acordado | El sitio declara política de fan content para su propio uso; no es permiso transferido al Companion | Pedir condiciones antes de automatizar; sin contrato/SLA comprobados |

Fuentes: [AHledger terms](https://ahledger.com/terms),
[AHledger developers](https://ahledger.com/developers),
[ForeverDB rules](https://foreverdb.net/developers),
[Warcraft Forever FAQ](https://warcraftforever.games/guides/faq).
Son hallazgos de condiciones publicadas, no una concesión de derechos por nuestra
parte. Disponibilidad técnica, compatibilidad del asset y permiso de uso se deben
registrar por separado. No se verificó una licencia general de Blizzard que
resuelva esta aplicación; no se copian iconos al producto con esta entrega.

## 3. Pruebas reales de items e iconos

Lote principal: **26/10/2026 21:06:59–21:07:04 UTC**
(18:06:59–18:07:04 Argentina). GET sin clave a:

| URL comprobada | HTTP | Nombre devuelto | Calidad | Clase / subclase |
| --- | --- | --- | --- | --- |
| [2589](https://api.ahledger.com/v1/items/2589?game=forever) | 200 | Linen Cloth | COMMON | Trade Goods / Cloth |
| [2770](https://api.ahledger.com/v1/items/2770?game=forever) | 200 | Copper Ore | COMMON | Trade Goods / Metal & Stone |
| [2447](https://api.ahledger.com/v1/items/2447?game=forever) | 200 | Peacebloom | COMMON | Trade Goods / Herb |
| [4604](https://api.ahledger.com/v1/items/4604?game=forever) | 200 | Forest Mushroom Cap | COMMON | Consumable / Food & Drink |

**VERIFICADO POR RESPUESTA REAL:** ID numérico coincidente, nombre inglés,
`quality`, `itemClass`, `itemSubclass`, `level`, `requiredLevel`, `vendorSell`,
`icon`, enlaces y bloque de atribución. Content-Type JSON UTF-8;
`Cache-Control: public, max-age=300`; header de cuota 300 presente.
`requiredLevel` fue null en los tres materiales y 1 en 4604.

**NO DISPONIBLE en estos JSON:** locale explícito, build, revisión por item,
canal beta/live y diferencias frente a Classic. `game=forever` selecciona el
producto solicitado; no acredita equivalencia con el build de nuestra captura.
Nombre inglés observado no autoriza inventar `enUS`. Last-Modified HTTP no es
build ni fecha de observación en juego.

Proyección reducida del JSON real de 2589, sin datos de cuenta que anonimizar:

```json
{
  "id": 2589,
  "name": "Linen Cloth",
  "quality": "COMMON",
  "itemClass": "Trade Goods",
  "itemSubclass": "Cloth",
  "level": 5,
  "requiredLevel": null,
  "vendorSell": 13,
  "icon": "https://render.worldofwarcraft.com/classic1x-us/icons/56/inv_fabric_linen_01.jpg"
}
```

Los cuatro iconos publicados se consultaron individualmente, sin cambiar sus URLs:

| ID | Recurso real bajo `https://render.worldofwarcraft.com/classic1x-us/icons/56/` | HTTP / tipo | Bytes |
| --- | --- | --- | --- |
| 2589 | [inv_fabric_linen_01.jpg](https://render.worldofwarcraft.com/classic1x-us/icons/56/inv_fabric_linen_01.jpg) | 200 / image/jpeg | 2521 |
| 2770 | [inv_ore_copper_01.jpg](https://render.worldofwarcraft.com/classic1x-us/icons/56/inv_ore_copper_01.jpg) | 200 / image/jpeg | 2175 |
| 2447 | [inv_misc_flower_02.jpg](https://render.worldofwarcraft.com/classic1x-us/icons/56/inv_misc_flower_02.jpg) | 200 / image/jpeg | 2894 |
| 4604 | [inv_mushroom_13.jpg](https://render.worldofwarcraft.com/classic1x-us/icons/56/inv_mushroom_13.jpg) | 200 / image/jpeg | 2266 |

Se comprobó firma JPEG/JFIF. No se validó dimensión decodificada ni diferencia
artística con Forever. El namespace `classic1x-us` es una limitación explícita,
no prueba de asset propio de Forever ni de correspondencia exacta con variantes.

### 3.1 Contraste HTML, versión y errores

GET directos 200 de [2589](https://warcraftforever.games/items/2589),
[2770](https://warcraftforever.games/items/2770),
[2447](https://warcraftforever.games/items/2447) y
[4604](https://warcraftforever.games/items/4604) en Warcraft Forever:
los mismos cuatro nombres, calidad Common y categoría general coincidente.
El HTML directo identifica **1.60.1.70009 en las cuatro fichas**.
La representación web en caché de 4604 mostraba 1.60.1.69893: conservar esta
discrepancia y preferir el cuerpo directo para esta sesión; no reinterpretarla
como cambio confirmado de estadísticas. Las fichas son HTML, no JSON de API.

AHledger [declara](https://ahledger.com/data) catálogo importado de build
1.60.1/70532 el 21/10, comparación con Classic y un enlace de catálogo por clase.
**DOCUMENTADO, NO PROBADO:** no se descargó ese catálogo ni se transfirió su
build global a cada respuesta por ID. Una extracción de beta no confirma el
lanzamiento. Estos cuatro materiales/consumible no prueban cómo se representan
items modificados o exclusivos de Forever; falta una muestra con cambios
conocidos y versión compatible. Los ejemplos de noviembre de la documentación
del proveedor son ejemplos, no observaciones realizadas el 26/10.

| Prueba negativa real | Resultado | Conclusión limitada |
| --- | --- | --- |
| `GET https://api.ahledger.com/v1/items/not-an-id?game=forever` | 400 JSON `{"error":"invalid request"}` | Error sintáctico observado |
| `GET https://api.ahledger.com/v1/items/2147483647?game=forever` | 400, mismo JSON | ID no aceptado en esta prueba; no establece rango general ni semántica de 404 |
| `GET https://ahledger.com/data` directo adicional | 429 | Límite real observado para esa página/transporte; sin reintento |

No se forzaron cuotas. No se comprobaron 401/403, 404 de item ausente válido,
304, 503, timeout del proveedor, reintentos o recuperación después de 429.
Los fallos locales de transporte no cuentan como pruebas de esos códigos.

### 3.2 Huellas de los cuerpos observados

SHA-256 calculado sobre bytes recibidos, antes de parsear JSON. Las URLs del
lote son las de la tabla de items; respuestas completas de 744/747/739/766 bytes.
Un cambio de hash futuro puede deberse a enlaces/metadatos, no sólo al nombre.

| Recurso | SHA-256 |
| --- | --- |
| JSON 2589 | `61c40afee17698decbdf1aec33270810c8a3ec35a7f60ed0b441f3d4bc8dd70c` |
| JSON 2770 | `c8d6327998351c5c890d238c8d300befa5a6ab100b7ec2f404bcd7fc7cf54716` |
| JSON 2447 | `6b6f823880a0e03322503884cf6789a72284d2df903fb44041071a731f9576b5` |
| JSON 4604 | `1ae4edf370e226256a20f0f4b821c93bc62c6676bdd534bc6dcbb4f4f1d4bc61` |
| JPEG 2589 | `09c1ba3f716c28da8c5a6a04ec74dac8d75966504e74715e9ce0dd9aa88b0818` |
| JPEG 2770 | `3df816f0a221bbcad7ced7839259b35bd1ca74f1249fc588a55d419dbaf5e049` |
| JPEG 2447 | `c444ae03d9ae87cd7b35b075e69e328080c54362cb867bafcd6c492fc43049dc` |
| JPEG 4604 | `890e0752333b29656d251491af213b1235acacfe0921d4196c2be37fb6530a24` |

## 4. Profesiones y recetas

Se probó este endpoint público, con una sola receta como máximo:

```text
GET https://api.ahledger.com/v1/crafting/forever.pvp.alliance.us?profession=Tailoring&limit=1
GET https://api.ahledger.com/v1/crafting/forever.pvp.alliance.us?profession=Tailoring&all=1&limit=1
```

Ambos HTTP 200, JSON UTF-8. El primero devolvió `recipes: []`, 1411 bytes;
el segundo, 2175 bytes y **una receta**, con `filters.limit: 1` y `all: true`.
En el segundo, Date HTTP 26/10/2026 21:08:14 GMT, caché pública 300 segundos y
cuota 60. SHA-256: `912bdd4589d6af16d5b747229b18854a79804ac0ab0d799032939bf0deae7017`.
El mercado es exclusivamente el ejemplo explícito de esta prueba del proveedor;
no identifica nuestras capturas ni constituye un default del Companion.

Proyección de la receta real, omitiendo métricas económicas de terceros:

```json
{
  "recipe": {
    "spellId": 2963,
    "name": "Bolt of Linen Cloth",
    "profession": "Tailoring",
    "skillRequired": 1,
    "acquisition": "unknown"
  },
  "result": {"id": 2996, "name": "Bolt of Linen Cloth", "quality": "COMMON", "qtyMin": 1, "qtyMax": 1},
  "reagents": [{"id": 2589, "name": "Linen Cloth", "qty": 2, "price": null}]
}
```

| Capacidad | AHledger, respuesta real | ForeverDB, DOCUMENTADO NO PROBADO | Warcraft Forever, HTML |
| --- | --- | --- | --- |
| Profesión | Tailoring como texto; no se probó directorio exhaustivo | Directorio y detalle paginado | Índice público con profesiones y enlaces |
| Receta | spellId 2963, nombre | Recetas por profesión | Referencias públicas; no contrato JSON probado |
| Ingredientes y cantidades | Item 2589 ×2 | Reagentes | No validados sistemáticamente aquí |
| Cantidad producida | Item 2996, min=1/max=1 | Resultados documentados | No validada aquí |
| Habilidad | skillRequired=1 | Rangos y colores | No validada aquí |
| Umbrales naranja/amarillo/verde/gris | Ausentes en esta muestra | Documentados | No validados aquí |
| Aprendizaje | acquisition=unknown; no requisitos acreditados | Fuentes, costes y distinción Classic/observado | No validado aquí |

Contrato de profesiones: [ForeverDB developers](https://foreverdb.net/developers).
Parte de entrenadores/vendedores puede ser Classic hasta observación en Forever;
una etiqueta de origen es necesaria. Índice HTML:
[Warcraft Forever professions](https://warcraftforever.games/professions).
No se generaliza una receta a todas las profesiones ni se afirma cobertura
completa. El calculador aún necesita restricciones de aprendizaje, especialización,
build y cantidades fiables. Métricas de margen/ventas estimadas recibidas en el
envoltorio de AHledger quedan fuera del catálogo y de 3A/3B.

## 5. Arquitectura mínima propuesta, todavía sin implementar

La arquitectura actual ya separa evidencia v2 de acumulados y motores. La nueva
capa sería descriptiva y opcional, sin escribir ni cambiar identidad de estados,
hechos, recibos, hashes económicos o contratos de ingestión.
`items` de Fase 2 y el catálogo fresh simulado no acreditan nombres auténticos;
`partial_items` conserva identidad, no un catálogo descriptivo verificado.
[Contexto de 5C.1](PHASE_5C1_EVIDENCE_DASHBOARD.md).

### 5.1 Registro y procedencia

Propuesta lógica independiente de precios; decidir su almacenamiento en 5D.2,
sin crear ahora tablas, migraciones o repositorios de producción:

| Campo/grupo | Regla propuesta |
| --- | --- |
| product_namespace, entity_kind, item_id | Producto explícito y tipo item/especie separados; número solo nunca identifica universalmente |
| localized_name, language | Texto y locale verificado; null si desconocido, con `observed_language` separado de locale confirmado |
| icon_ref | URL/textura original; proveedor, compatibilidad y estado de permiso independientes; placeholder si no aprobado |
| quality, category, subclass | Valor original y normalización versionada; no asignar códigos por semejanza textual |
| game_build, channel, source_revision | Nulos si no constan; no deducir de fecha HTTP ni heredar build global sin prueba |
| provider_id, source_url, source_record_id | Fuente verificable por registro/campo; enlace de atribución conservado |
| fetched_at, source_updated_at, cache_expires_at | Adquisición propia, actualización declarada y vencimiento distintos; source_updated_at puede faltar |
| response_sha256, ETag, Last-Modified | Huella y validadores de transporte; no sustituyen evidencia del cliente |
| verification_status, compatibility_status, terms_reference | Distinguir afirmación del proveedor, contraste y confirmación propia; historial de condiciones |

Guardar revisiones y conflictos por fuente/contexto; no usar último proveedor
ganador ni completar silenciosamente campos de Classic en Forever. Un hash
detecta cambios de contenido; no demuestra veracidad del dato. Evidencia HTTP
archivable sólo con autorización/retención acordada y sin headers secretos.

El binding visual debe conservar `dataset`, producto/build/canal y la `item_key`
completa. Las variantes `g:`/`gr:` no heredan sufijo, nivel o atributos particulares
desde el item base. `p:` identifica especie, no un item coincidente por número.
Metadatos del ID base pueden etiquetar sólo aquello que esté validado como
compartido, sin borrar la variante. Simulación nunca adquiere nombres auténticos
por coincidencia numérica. Un contexto incompatible o ambiguo conserva el fallback
de ID y explica la falta de binding; catálogo no define región/reino/facción del AH.

### 5.2 Interfaz de proveedor y caché

Contrato conceptual, sin código añadido:

```text
capabilities() -> campos, productos, locales/builds soportados, límites y condiciones
fetch_item(product_context, item_id, requested_locale) -> ProviderItemResult
fetch_recipes(product_context, profession_ref, cursor, limit) -> RecipePage  [opcional futura]

ProviderItemResult = Found(record, provenance, cache_policy)
                 | Missing | Ambiguous | UnsupportedContext
                 | AuthorizationRequired | RateLimited(retry_after) | Unavailable
```

El adaptador valida ID devuelto, esquema, tipos, tamaños, origen de URL y contexto.
La ausencia de build/locale produce compatibilidad desconocida, no una etiqueta
confirmada. Separar `Missing` de 400 genérico o error transitorio. No acoplar
dashboard a JSON, HTML de atribución ni SDK de un proveedor. Escapar textos y
construir atribución con texto/enlace validados, sin insertar `attribution.html`.

Consultar únicamente IDs presentes en capturas seleccionadas, deduplicados y con
presupuesto explícito. Caché autorizada por proveedor/producto/build/locale/tipo/ID,
respetando TTL y validadores; revisar permiso de retención al expirar, sin prometer
espejo offline perpetuo. Fallos/ausencias requieren políticas propias acotadas,
no ceros ni nombres inventados. Concurrencia baja, reintentos limitados, Retry-After
y detención en 429; no claves en navegador. Ninguna sincronización automática
se incorpora con esta propuesta. Evitar embeds con precios/defaults de mercado.

Recetas tendrían identidad propia por producto/build/profesión/spellId, con
ingredientes y resultados por ID/tipo, cantidades/rangos, requisitos y fuente por
relación. La receta no se identifica por el item producido: varias pueden producirlo.
Cantidades faltantes, efectos de habilidad y probabilidades no se inventan.
Un futuro calculador uniría sólo relaciones compatibles con precios propios
explícitamente seleccionados, sin importar análisis económicos del proveedor.

## 6. Recomendación y alcance propuesto para 5D.2

**Principal: AHledger para diseñar consultas puntuales**, por los GET anónimos
realmente comprobados. Es factible obtener nombres/calidad/categoría, manteniendo
la etiqueta de fuente y compatibilidad pendiente. **Alternativa: ForeverDB**,
si se obtiene aprobación y se verifican JSON reales, particularmente build y
aprendizaje de recetas. Warcraft Forever queda como contraste manual y posible
export negociado; no como scraper de producción.

Antes de habilitar metadatos como confirmados de Forever o servir iconos:

1. Aclarar con condiciones públicas o autorización el almacenamiento local,
   retención, actualización, atribución y uso/hotlink/rehosting de iconos. No se
   envió una solicitud ni se requiere entregar credenciales al agente.
2. Resolver build/locale por registro y un binding defendible a capturas; probar
   al menos un item exclusivo/modificado y variantes. No afirmar lanzamiento a
   partir de estos cuatro IDs o de un build beta/global.
3. Si se elige ForeverDB, el titular debe decidir su autorización fuera de esta
   entrega. Después, un GET acotado de meta/item/profesión bajo su aprobación;
   no pedir claves en chats ni ponerlas en fixtures.
4. Diseñar un prototipo de adaptador/caché separado de precios con estas cuatro
   respuestas como referencia mínima y fixtures públicos reducidos. Cubrir ID
   discordante, contexto ambiguo, nulls, cambios de esquema, errores, TTL,
   atribución, variantes/especies y límites; sin catálogo completo o importador
   de producción. Decidir almacenamiento sólo tras revisar condiciones.
5. Mantener el fallback de IDs y placeholder. La primera integración de nombres
   y la de imágenes requieren criterios de aceptación separados. Recetas y
   profesiones permanecen futuras, sin calculador en 5D.2 inicial.

La investigación histórica no se sobrescribe. No hay confirmación de que estas
fuentes coincidan con el cliente/capturas del usuario, ni de continuidad de datos
beta a lanzamiento. La validación económica de la primera captura auténtica
sigue siendo un trabajo independiente de 5B/5C.

## 7. Validación y estado de entrega

- HTTP real: cuatro items JSON, cuatro imágenes JPEG, dos errores 400,
  dos consultas crafting (vacía y una receta), cuatro fichas HTML y developers
  de ForeverDB. Un GET posterior de página AHledger recibió 429; sin reintento.
- Documentación pública contrastada: acceso, OAuth, cuotas, atribución y
  limitaciones. API autenticada, licencias de iconos y compatibilidad propia:
  **pendientes**, no tests aprobados.
- Comprobaciones locales: diff/alcance documental, enlaces relativos y
  `git diff --check`. No se ejecutan pytest, frontend tests, build o laboratorio
  PostgreSQL: no cambió código ni se necesita una DB para esta investigación.
- Archivos de entrega: este informe y actualización puntual de ROADMAP.
  HEAD permanece en la base indicada; sin staging, commit o push.

**NEEDS ACCESS / FURTHER RESEARCH** para una integración verificada completa.
La factibilidad de consulta puntual está demostrada; faltan las condiciones y
evidencia detalladas arriba, no funcionalidades adicionales en esta entrega.

## 8. Cierre 5D.1 para el MVP — 28/10/2026

Se releyeron únicamente [terms](https://ahledger.com/terms) y
[developers](https://ahledger.com/developers). Conservan uso personal/comercial
de la API, crédito enlazado junto a los datos, prohibición de presentar datos
como scan propio o revender un feed y obligación de honrar Cache-Control.
El endpoint elegido es exclusivamente `GET /v1/items/{id}?game=forever`, sin
autenticación. No se repitieron GET de items, iconos, crafting ni `/data`.
La evidencia remota de los cuatro IDs sigue siendo la del 26/10, no una nueva
verificación de datos ni del lanzamiento del 04/11.

Decisión: caché local temporal de metadatos según headers, con máximo conservador
de 300 segundos, sin uso vencido ni archivo permanente distribuido. Es la
aplicación operativa del contrato de API/caché publicado, no una autorización
individual del proveedor. No se obtuvo permiso adicional ni se contactó a terceros.
Si hace falta conservar nombres offline más allá del TTL, se deberá aclarar ese
uso con el proveedor antes de implementarlo. Los bytes vencidos no se sirven y
se purgan al siguiente almacenamiento del cliente; no hay historial del catálogo.

Las cuotas publicadas continúan en 300/min/dirección para API general y 60/min
para herramientas de mercado, que quedan fuera del MVP. Se respeta Retry-After
numérico o fecha HTTP y no se realizan reintentos automáticos. No se implementan
claves opcionales ni se depende de una ampliación de cuota.

**Iconos: pendiente de autorización.** El contrato identifica a Blizzard como
titular, sin acreditar aquí los derechos concretos del Companion. 5D.2 descarta
el campo remoto `icon` y muestra un placeholder geométrico local. No descarga,
hotlinkea, redistribuye ni embebe imágenes/scripts del proveedor. Locale y build
por item siguen desconocidos; `game=forever` sólo acredita el producto solicitado
al proveedor. No se heredan propiedades Classic ni builds globales a las capturas.

ForeverDB permanece alternativa futura con aprobación/clave y condiciones de
persistencia por resolver, especialmente para recetas/profesiones. No se invoca
su API ni se implementa OAuth. El cierre habilita el adaptador pequeño documentado
en 5D.2, conservando estos límites y separando nombres de compatibilidad e imágenes.
