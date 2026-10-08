# Auctionator 340: evidencia y alcance de Fase 2.5

Inspección local realizada el 2026-10-08 sobre
`C:\Users\user\Desktop\auctionator-reference\Auctionator`.
La referencia externa no se modifica, no se copia al proyecto y no se versiona.
Los fixtures son pequeños ejemplos construidos a partir del esquema inspeccionado;
no son exports reales de Forever ni código del addon.

## Fuente comprobada

| Archivo de referencia | Evidencia |
| --- | --- |
| `Auctionator.toc` | Version 340, Interface incluye 16001; declara SavedVariables |
| `Source/Database/Mixin.lua` | `SetPrice`, `GetPriceHistory`, índices diarios, poda |
| `Source/Variables/Main.lua` | DB global v8, realm `version=2`, tablas y strings CBOR de realm/item |
| `Source/Constants/Main.lua` | SCAN_DAY_0 construido con `time({year=2020, month=1, day=1, hour=0})` |
| `Source_ModernAH/Variables/Main.lua` | Claves PvE/PvP/RP/HC cuando están activos los nombres regionales; fallback conectado |
| `Source_LegacyAH/Variables/Main.lua` | Clave realm + facción, sin asumir un ruleset |
| `Source/Utilities/DBKeyFromLink.lua` | ID básico, `gr:ID:sufijo`, `g:ID:nivel`, `p:speciesID` |
| `Source_ModernAH/Utilities/DBKeyFromBrowseResult.lua` | ID básico, gear level y pet species |
| `Libs/LibCBOR/LibCBOR.lua` | Serialización CBOR definida, strings, mapas y arrays |
| `Source/PostingHistory/Mixin.lua` | Publicaciones propias con `time`; no ventas confirmadas ni observaciones del mercado global |

SHA-256 para reproducir la inspección sin incluir el addon:

| Archivo | SHA-256 |
| --- | --- |
| `Auctionator.toc` | `81E9F874419B90A66FD687F600051F8C4A7B3EFAB3013B7DF9D733BACF884C16` |
| `Source/Database/Mixin.lua` | `3BF29B46F517AF275C231C925AD0B6E94454119E450B8156AB2130980C769AA9` |
| `Source/Variables/Main.lua` | `7435EC19031DB4CBF63E1374D605EE4ABCBE9C0A59B04658D1331167FE61A717` |
| `Source_ModernAH/Variables/Main.lua` | `404582946DFB3361AC440CCB11C3EA5D484A2855EB98FB5DBCDBAAD874D8911F` |
| `Libs/LibCBOR/LibCBOR.lua` | `32A935204AFFB40630DA6CF5802C30987625B8B2610221F6E8193483A9476CFE` |

## Semántica que se conserva

| Campo del addon | Contrato | Significado |
| --- | --- | --- |
| `h[day]` | `daily_highest_minimum` | Mayor mínimo visto ese día, no mayor precio de todas las subastas |
| `l[day]` o fallback `h[day]` | `daily_minimum` | Mínimo histórico almacenado, usando exactamente el fallback de GetPriceHistory |
| `a[day]` si existe | `daily_max_available` | Mayor cantidad disponible observada, no unidades vendidas |
| `m` si existe | `last_minimum` | Último mínimo guardado; sin timestamp ni vínculo fiable con un día |

Los precios están en copper. `a` es disponibilidad y puede faltar por completo.
No se producen promedio de listings, precio máximo de todas las subastas,
`auction_count`, ventas, vendedores, nombre/calidad del item ni timestamps de scans.
`AUCTIONATOR_POSTING_HISTORY` se lee únicamente como literal y no se importa:
sus entradas son publicaciones propias, no ventas ni histórico completo del mercado.

Una sutileza del código: `SetPrice` actualiza `h` antes de decidir guardar `l`.
Una secuencia ascendente puede dejar `l` ausente, aunque hubiera un precio anterior
menor. El parser conserva el dato tal como lo muestra `GetPriceHistory`; no
reconstruye mínimos perdidos. El simulador reproduce ese orden de actualización.

El índice es `floor((time() - SCAN_DAY_0)/86400)`. La base depende del `time`
del cliente, y no está incluida en la base de precios. Por defecto se conserva
`scan_day` con `temporal_basis="unknown"` y `day_start=null`. Opcionalmente el
operador puede proporcionar una base ISO con timezone verificada: permite calcular
el comienzo del bucket de 86400 segundos, nunca un timestamp de scan individual.
Un índice cuyo calendario exceda el rango datetime conserva el índice y devuelve
`day_start=null`. No se usa la fecha de importación como fecha de observación.

Además, `daysSinceZero` se calcula una sola vez al cargar `Source/Database/Mixin.lua`.
`SetPrice` reutiliza ese índice durante la sesión; no vuelve a calcularlo en cada
scan. Una sesión que cruza el límite diario puede seguir escribiendo en el bucket
anterior hasta recargar. El importador conserva ese índice tal cual: no reasigna
datos según la hora de importación ni garantiza buckets de calendario por scan.

## Formatos efectivamente soportados

- SavedVariables Lua con asignaciones globales a literales: tablas, strings con
  escapes decimales de bytes, enteros, números, booleanos y nil; comentarios de
  una línea y separadores habituales. Sólo la base de precios v8 se normaliza.
- Mercados y entradas de precio como tablas, con realm `version=2` o sin marcador
  para la ruta histórica de entradas por item. Se rechazan otros marcadores y
  campos históricos ambiguos como `pending`.
- Strings CBOR a nivel de mercado o item, únicamente con selección explícita de
  LibCBOR (`--allow-libcbor`). El lector soporta longitudes definidas, enteros,
  strings de bytes/texto, mapas, arrays y simples true/false/null. Arrays vacíos
  representan tablas vacías; los strings conservan bytes antes de interpretar claves.
- IDs normalizados quitando ceros iniciales, conservando cada variante gear/sufijo
  y manteniendo especies pet en un namespace diferente. `p:123` no es el item 123.
- Claves PvE/PvP/HC/RP literales conservan su ruleset. Cualquier otra clave requiere
  un mapping explícito; realm/facción se conserva y nunca se traduce por suposición.

El parser no ejecuta Lua, no llama a eval/exec ni carga un intérprete. Rechaza
funciones, expresiones, llamadas, asignaciones indexadas, claves duplicadas,
strings largos Lua, escapes no soportados, tags/extensiones/floats CBOR, tamaños
indefinidos, bytes sobrantes y estructuras corruptas. Límites: 16 MiB por archivo,
profundidad 32 y un millón de nodos compartidos entre Lua y todos sus decoders CBOR;
máximo 200.000 estadísticas por batch, comprobado antes de construir cada una.
Los contenedores CBOR declaran su tamaño y se rechazan antes de decodificar hijos
si exceden el presupuesto restante. La normalización de BOM/whitespace inicial
también se usa al detectar el marcador de simulación; sólo protege contra errores
de etiquetado, no demuestra autenticidad. No hay firma criptográfica del fixture.
El archivo se lee con límite antes del parsing. Precios, disponibilidad e índices
son enteros estrictos en `0..2147483647`, coherentes con PostgreSQL INTEGER.

### Precios fraccionarios legítimos: limitación explícita

`Source_ModernAH/FullScan/Mixins/Frame.lua:GetInfo` calcula `buyoutPrice / count`,
sin floor. Por ejemplo, un stack de 3 unidades con buyout 100 copper produce un
precio por unidad no entero. `SetPrice` conserva ese número; LibCBOR usa floats
para valores no enteros. Es incorrecto afirmar que todo precio del addon es entero.

El contrato actual sigue rechazando precios fraccionarios tanto Lua como CBOR/HTTP,
sin redondear ni truncar. Los tokens decimales Lua se leen con Decimal, conservando
el literal hasta su rechazo explícito; no se convierten a float binario en el parser.
Esta restricción excluye exports legítimos de ModernAH y debe aparecer en el alcance
del soporte. Una fracción CBOR exactamente representable, como 1.5, también se rechaza.

Representación futura candidata: numerador/denominador con aritmética racional y
columnas PostgreSQL NUMERIC sin scale fijo, separadas de disponibilidad/índices.
Para conservar el precio original exacto se necesitarían buyout/count originales;
esa pareja no está en la base de precios agregada. Un Decimal del texto exportado
conserva el literal serializado, pero no demuestra la razón original del scan;
un codec IEEE754 exigiría decidir si se conserva el racional del valor serializado.
No se fija una escala decimal ni se reconstruye un denominador por suposición.

## Procedencia e identidad

`source_version=340` expresa el formato seleccionado por el operador/parser; el
SavedVariables no certifica por sí solo la versión del addon. `database_version=8`
sí debe estar presente y coincidir. `region` y `source_id` son contexto externo
obligatorio, no campos supuestamente extraídos del addon. Usar un source_id estable
para la misma cuenta/export y contexto de reloj; otra cuenta debe usar otro ID.
Cambiar la base temporal conserva series separadas: no se fusiona automáticamente
una serie con base desconocida con otra de base conocida.

Identidad diaria: mercado (region + clave exacta + dataset), item con variante,
source_id + source_type + temporal_basis + scan_day + statistic. Una nueva lectura
del mismo día puede extender los extremos acumulados por el importador: mínimo menor, máximo de mínimos mayor,
disponibilidad mayor. No se inventan observaciones en días ausentes; una lectura
vieja no degrada los extremos. Fuentes independientes se mantienen separadas.

**Límite de equivalencia detectado por auditoría:** estos extremos acumulados entre
imports no representan necesariamente GetPriceHistory del último export. Con l
ausente, un export h=100 produce minSeen=100 y otro h=200 produce minSeen=200,
mientras la tabla acumulada conserva daily_minimum=100. El adapter sí refleja cada
export; la persistencia 003 pierde esa distinción. No debe anunciarse el acumulado
como el estado más reciente del addon. La 004 conserva evidencia nativa por
exportación aparte del acumulado: sólo hechos l/h/a/m presentes, claves originales
y un manifest con campos/tablas presentes o vacíos. La consulta por export_id
proyecta ese estado exclusivamente y distingue l de h_fallback; no persiste un l
inventado. No se reconstruyen exports previos desde extremos. La equivalencia
cubre valores decodificados aceptados, no bytes del Lua, orden de presentación,
PrettyDate del cliente ni todos los formatos/precios legítimos del addon.

Hardening de concurrencia: el servicio adquiere todos los locks de items por
item_key global, luego todos los de mercados, luego escribe observaciones en orden
consistente, con evidencia después de catálogos y vínculos después del acumulado.
Mantiene los locks hasta validar y confirmar el batch. Se comprueba
daily_minimum <= daily_highest_minimum incluyendo valores previos y estadísticas
partidas entre batches, rechazando atómicamente combinaciones contradictorias.
Esta garantía pertenece al servicio; escrituras SQL manuales o importadores de
versiones anteriores no se consideran parte del contrato protegido. Sólo SQLSTATE
40P01 permite reintentar la transacción entera: máximo tres intentos, con esperas
de 10 y 20 ms. Se registra failed únicamente al agotar retries o ante otro error SQL.

`m` usa además un hash del contenido normalizado del batch, pues no tiene día
verificable. Cambios de whitespace, orden o transporte no duplican la misma
evidencia. Otro estado del export conserva una nueva evidencia sin asignarle una
fecha histórica. No es una serie de scans ni puede ordenarse por observación real.

El SHA-256 de los bytes originales queda en cada import de archivo; HTTP hashea
su JSON normalizado. `first_import_id` y `last_import_id` enlazan la procedencia de
cada estadística vigente. La fecha de importación es generada por PostgreSQL.
Los intentos completados/duplicados/fallidos se registran en `partial_import_runs`;
parsing/validación previos no llegan a persistencia. Un error SQL revierte todo el
batch y registra failed en otra transacción si PostgreSQL continúa disponible.
La tabla 003 no conserva una copia histórica de cada extremo reemplazado. Desde
004 los archivos aceptados por el adapter conservan su estado nativo separado;
el POST que sólo aporta PartialBatch normalizado no permite reconstruirlo y
declara evidencia unavailable. Estados idénticos reutilizan export_id, con hash
canónico v1 que incluye presencia/ausencia y contexto pero no whitespace, ruta,
codec ni recepción. Cada recepción conserva su hash de bytes y referencia en el
run vinculado. No se infiere un timestamp del archivo ni una cronología de scans.
Un export tardío preserva su contenido y puede ampliar extremos; ausencias no
borran acumulados. Detalle y validación en [PHASE_25_EXPORT_EVIDENCE.md](PHASE_25_EXPORT_EVIDENCE.md).

## Pendiente de validación real de Forever

- Un SavedVariables auténtico de cliente 1.60.1 con Auctionator 340; los fixtures
  actuales sólo verifican estructuras del código inspeccionado.
- Confirmar cuál ruta de AH y claves de mercado activa ese cliente. El `.toc`
  contiene rutas ModernAH y LegacyAH, por lo que no se asume que Forever siempre
  exporte reglas regionales.
- Serialización nativa `C_EncodingUtil.SerializeCBOR/DeserializeCBOR`: las llamadas
  existen, pero su implementación no está en el addon. No se anuncia soporte para
  ese codec ni para posibles compresiones/extensiones del cliente. Una selección
  de LibCBOR no verifica automáticamente que un export nativo use ese formato.
- Capturar el SCAN_DAY_0 del cliente y su contexto de reloj antes de convertir días
  reales a calendario. No inferirlo de filesystem mtime ni imported_at.
- Frecuencia, poda efectiva del histórico, tamaño real y cobertura de mercado.
- Resolver catálogos reales por otra fuente verificable; la base de precios no
  contiene los nombres. El catálogo del simulador es explícitamente ficticio.

Fase 2.5 está implementada y validada con fixtures y PostgreSQL; permanece pendiente
de validación con SavedVariables real. Fase 3 no se implementa.
