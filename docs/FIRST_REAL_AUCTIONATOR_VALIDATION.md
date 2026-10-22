# Primera validación real de Auctionator Forever

Fecha de revisión: **21/10/2026**, America/Buenos_Aires. Revisión del proyecto: `f30f0de0b7c814e80afa6d41ac8cb41776e3df0e`, rama `main`.

**Cierre técnico validado: READY FOR TRIAL REVIEW, sin autorización de importación auténtica.** La persistencia 341 está preparada con procedencia explícita, dataset `stress_test`, migración 005 y `TrialDatabase` obligatorio. La región técnica de esta captura sigue pendiente y **el archivo auténtico no se importó**. La sección 11 registra la auditoría final y las 730 regresiones aprobadas; las secciones anteriores conservan la evidencia de las etapas previas y sus estados Git históricos.

Las secciones 1–8 conservan la evidencia de la validación inicial y su investigación local, **anteriores al cambio de código**. Su diagnóstico de rechazo predeterminado sigue siendo válido; sus afirmaciones sobre falta de resultado completo del adaptador o ausencia de cambios de código describen aquella etapa. El veredicto inicial fue `INSUFFICIENT EVIDENCE`. La sección 9 describe la etapa offline posterior (`NOT READY FOR TRIAL`), superada técnicamente por la sección 10; no constituye permiso de escritura.

## 1. Procedencia y preservación

Según la procedencia informada por el operador, es un SavedVariables auténtico generado durante la **STRESS TEST de WoW Forever del 21/10/2026**, en un servidor PvP con Auction House prácticamente nuevo. **No representa el mercado de lanzamiento.** La autenticidad y ese contexto son información del operador; el hash identifica los bytes, no autentica su origen.

En su aclaración posterior, el operador confirma que obtuvo el archivo directamente de su cliente, que Auctionator estaba instalado y funcionando y que realizó un **escaneo completo** en el cual el addon informó **7 objetos procesados**. Ese conteo coincide con los siete items encontrados independientemente en el SavedVariables. No demuestra por sí solo cobertura completa del AH ni aceptación por nuestro adaptador.

| Dato | Resultado |
| --- | --- |
| Copia privada examinada | Carpeta externa `wow-beta-capture`, archivo `Auctionator.lua`; ruta completa proporcionada por el operador, omitida aquí |
| Existencia / lectura | Archivo presente; lectura completa correcta |
| Tamaño | **4.701 bytes** |
| SHA-256 inicial y final | `7d5cf3db48fa78ab19d3a359557470752e634da743cebe42833fb07c10aa458b` |
| Base nativa | `AUCTIONATOR_PRICE_DATABASE`, `__dbversion = 8` |
| Mercados | Exactamente uno: clave literal `PvP` |
| Almacenamiento de PvP | String Lua que entrega **252 bytes** serializados al lector |
| Versión interna del mercado decodificado | `version = 2` |
| Items del mercado | **7**; el marcador `version` se excluye del conteo |
| Base temporal | Desconocida; `scan_day_zero=None` |

No se ejecutó Lua. Se usó exclusivamente `LuaReader`, que interpreta literales sin runtime Lua. No se editó ni copió el archivo original al repositorio. Se calculó nuevamente su hash al terminar; coincide con el inicial. Esto verifica los bytes examinados, pero no prueba que el cliente estuviera cerrado durante la copia original.

El operador no registró el build exacto, la versión/revisión del addon, el serializador ni la región técnica durante la sesión. Esos campos se registran como **PENDIENTES para la captura**, sin completarlos por suposición. La inspección local posterior aporta los valores instalados actuales que se detallan a continuación; se distinguen de una medición efectuada durante el escaneo. También permanecen pendientes facción/alcance del AH, ruta AH efectiva y contexto del reloj. La fecha de captura no fecha automáticamente sus buckets.

### Inspección local posterior a la aclaración del operador

Se encontró una instalación local bajo `D:/World of Warcraft/_forever_`. Sólo se leyeron metadatos y código; no se inició el cliente, el launcher ni el addon. No se publican nombres o rutas de cuentas.

| Campo | Evidencia local observada | Estado respecto de la sesión de captura |
| --- | --- | --- |
| Producto instalado | Carpeta `_forever_`; `.build.info` declara producto `wowf` activo | Identificado localmente; no equivale a una región |
| Build instalado | `Wow.exe`, FileVersion/ProductVersion `1.60.1.70532`; coincide con `.build.info` | **PENDIENTE de registro de la sesión**; éste es el build presente al revisar |
| Addon instalado | `Interface/AddOns/Auctionator/Auctionator.toc`: `Version: 341`, Interface incluye `16001` | **PENDIENTE de registro de la sesión**; versión local actual comprobada, no se asume 340 |
| Revisión exacta del addon | Hashes de archivos abajo; no se identificó un commit de distribución | **PENDIENTE** para la captura |
| Vínculo con la copia | Se encontraron dos archivos llamados `Auctionator.lua` bajo `_forever_/WTF`; uno tiene 4.701 bytes y SHA-256 idéntico al de la captura; el otro no coincide | Coincidencia exacta de bytes verificada, sin exponer rutas privadas |
| Codec ejecutado durante el escaneo/guardado | Código instalado con rutas condicionales nativa/LibCBOR; ver sección 3 | **PENDIENTE**; indicios a favor de la ruta nativa, sin constatación de ejecución |
| Región técnica | No se obtuvo evidencia que la confirme | **PENDIENTE** |

Hashes SHA-256 de archivos del addon **instalado actualmente**:

| Archivo | SHA-256 |
| --- | --- |
| `Auctionator.toc` | `9ea2ac47b91451f23a7db0dbf0f8acd1b1c830ff1b0fed720f312a74008d907e` |
| `Source/Variables/Main.lua` | `7435ec19031db4cbf63e1374d605ee4abcbe9c0a59b04658d1331167fe61a717` |
| `Libs/LibCBOR/LibCBOR.lua` | `32a935204affb40630da6cf5802c30987625b8b2610221f6e8193483a9476cfe` |
| `Source/Database/Mixin.lua` | `3bf29b46f517af275c231c925ad0b6e94454119e450b8156ab2130980c769aa9` |

El `.toc` difiere de la referencia 340. Los otros tres archivos tienen exactamente los mismos hashes que la referencia local 340: esto respalda la continuidad de esas rutas concretas de serialización y l/h/a/m, **no certifica todos los cambios entre 340 y 341**. El `source_version="340"` del contrato de nuestro pipeline sigue siendo una etiqueta del formato seleccionado; no debe documentarse como versión comprobada del addon de la captura ni sobreescribirse a 341 sin revisar el contrato.

## 2. Procedimiento y frontera de seguridad

Se leyó [BETA_DATA_READINESS.md](BETA_DATA_READINESS.md), en particular su procedimiento offline de la sección 7. Se inspeccionaron los scripts disponibles y `scripts/import_auctionator.py`: la CLI importa mediante el servicio y no ofrece un dry-run completo del archivo. **No se ejecutó esa CLI**, tampoco `--check-target`, migraciones, endpoints, dashboard ni análisis contra PostgreSQL.

Las comprobaciones se ejecutaron desde `backend` mediante el Python existente, con `-B` y bloques por stdin; no se guardaron scripts auxiliares ni se usaron fixtures en sustitución de la captura. El punto de entrada del intento real fue:

```python
import os
from pathlib import Path
from app.ingestion.adapters.auctionator import AuctionatorAdapter

result = AuctionatorAdapter().load(
    Path(os.environ["BETA_COPY"]),  # Ruta privada de la captura examinada.
    source_id="stress-20261021-offline-audit",
    region="unverified-offline-only",
    dataset="real",
    scan_day_zero=None,
    allow_libcbor=False,
)
```

`source_id` y `region` son marcadores exclusivos de este intento diagnóstico, que termina antes de construir el batch. **No constituyen procedencia confirmada ni contexto reutilizable para importar.** Se dejó la región explícitamente sin verificar, sin inferirla del idioma, del huso horario o del mercado. El procedimiento operativo documentado exige una región verificada antes de continuar; aquí sólo se comprobó el rechazo de formato anterior a ese punto.

Después se inspeccionó la estructura con los lectores existentes:

```python
from app.ingestion.saved_variables import LuaReader, CBORReader

variables = LuaReader(raw).parse()
database = variables["AUCTIONATOR_PRICE_DATABASE"]
reader = CBORReader(database[b"PvP"])
realm = reader.parse()
assert reader.pos == len(database[b"PvP"]) == 252
```

Los valores decodificados se contrastaron, sin persistencia, con `normalize_item_key`, `NativeItemShape`, `NativeMarketShape`, `NativeFact` y `PartialObservation`. Se revisaron campos, días huérfanos, identidades duplicadas y límites numéricos. Para las métricas se usaron `BucketPoint`, `compute_metrics` y `bucket_start("unknown", 2485)` del proyecto. Esas comprobaciones son diagnósticas: **no son un resultado de `AuctionatorAdapter.load`, un export sellado ni una importación completada**.

Los procesos de diagnóstico no cargaron módulos `psycopg`, `app.db`, `app.core.config` ni `app.ingestion.partial_service`, según `sys.modules`. No se ejecutó la suite de integración, cuyos fixtures crean/migran schemas. No se consultó ni modificó ninguna base.

## 3. Compatibilidad del parser, CBOR y adaptador

| Etapa | Evidencia y resultado |
| --- | --- |
| Lua exterior completo | **Aceptado** por `LuaReader`; ocho globals interpretados, sin recortar el archivo |
| Base global | Tabla v8 reconocida por el adaptador |
| Mercado | Clave literal `PvP`; el código resuelve ruleset `PvP` sin mapping externo antes de intentar decodificar |
| Carga real predeterminada | **Rechazada** por `AuctionatorAdapter.load`, en su función interna `decode(data)` para el mercado serializado |
| CBOR con lector existente | **Aceptado** por `CBORReader.parse`: consume exactamente 252/252 bytes, sin bytes sobrantes |
| Formas y valores decodificados | Aceptados por los contratos individuales; detalle en la sección 4 |
| Batch + evidencia nativa generados por adaptador | **No obtenidos**: el intento se detiene en el control de codec |
| Igualdad `native.projected_observations()` / `batch.observations` | **No ejercitada**: no existe resultado completo del adaptador |
| Hash de estado / decoder / input_format del resultado | **No obtenidos**; no se fabricaron a partir del diagnóstico |

Error exacto observado:

```text
FormatError: serialized data requires explicit allow_libcbor; native CBOR is unverified
```

El punto exacto está en [auctionator.py](../backend/app/ingestion/adapters/auctionator.py), dentro de `decode`: un valor `bytes` con `allow_libcbor=False` se rechaza antes de llamar al lector CBOR. No es un error de sintaxis Lua, de versión de base ni un rechazo de precios demostrado.

### Qué sabemos del codec

Se inspeccionaron `Source/Variables/Main.lua` y `Libs/LibCBOR/LibCBOR.lua` de la referencia local citada en [AUCTIONATOR_340.md](AUCTIONATOR_340.md) y, tras la aclaración del operador, los archivos equivalentes del Auctionator 341 instalado en `_forever_`. Sus hashes coinciden exactamente, aunque la versión declarada en el `.toc` es distinta.

La referencia tiene rutas tanto `C_EncodingUtil.SerializeCBOR` como `LibCBOR:Serialize`. Sus llamadas no prueban cuál se ejecutó en el cliente de la stress test. El serializador LibCBOR inspeccionado escribe strings Lua como tipo CBOR 3; esta captura contiene **50 strings de tipo CBOR 2**, además de 22 enteros sin signo, 22 mapas y siete arrays vacíos. Los siete `l` vacíos están codificados como `0x80`, que el lector representa como tablas vacías. No aparecen floats, tags, longitudes indefinidas ni extensiones en la lectura realizada.

La diferencia entre strings tipo 2 y la ruta de strings tipo 3 de la referencia impide atribuir esta captura a esa implementación de LibCBOR sólo por poder decodificarla. Es compatible con el subconjunto de bytes que entiende el lector, pero **no identifica por sí sola al productor ni certifica soporte de `C_EncodingUtil`**.

En el código instalado, `Source/Variables/Main.lua:113–118` registra un handler `PLAYER_LOGOUT` que serializa el mercado actual mediante `C_EncodingUtil.SerializeCBOR` si existe `C_EncodingUtil`. Las líneas 132–138 permiten serializar otros mercados con una u otra ruta. El LibCBOR incluido conserva `encoder.string = encoder.utf8string` y emite strings tipo 3. El mercado PvP serializado de la captura y sus strings tipo 2, junto con la procedencia declarada por el operador, son **indicios a favor de la ruta nativa**. No se observó la condición en runtime ni una traza del handler; tampoco se probó que la instalación no hubiera cambiado desde el guardado. Se mantiene **codec PENDIENTE**, sin etiquetar el archivo como LibCBOR confirmado.

Por eso no se ejecutó un segundo intento con `allow_libcbor=True`. [BETA_DATA_READINESS.md](BETA_DATA_READINESS.md), sección 7, indica: «No activar LibCBOR sólo porque falló el primer intento: primero identificar el productor/codec de los strings.» Aplicado aquí, exige resolver la procedencia del codec antes de seleccionar esa ruta para la validación completa. El operador respondió que no había registrado esos metadatos y pidió mantenerlos pendientes, autorizando sólo investigación local de lectura. Esa investigación aporta versión/build instalados e indicios de codec; no elimina las incertidumbres de la sesión.

Se repitió la validación offline después de esta investigación: mismo tamaño y SHA-256 de la captura, siete items, índice 2485, 21 hechos nativos y el mismo `FormatError` del adaptador predeterminado. Los procesos de diagnóstico volvieron a mostrar ausencia de módulos de BD cargados. No se abrió ninguna conexión ni se importaron datos.

### Clasificación y corrección mínima propuesta

**Situación D: no se puede determinar la aceptación íntegra con la información disponible.** Está demostrado el rechazo predeterminado y la compatibilidad del lector de bytes. No se declara A por decodificar CBOR; tampoco C, porque no apareció una estructura de datos completamente distinta. No hay evidencia suficiente para afirmar que se necesita corregir las validaciones l/h/a/m.

- Si se confirma el productor LibCBOR correspondiente, repetir offline el adaptador completo con selección explícita y cotejar proyección nativa/batch. Podría bastar seleccionar el codec, sin cambios de código.
- Si se confirma `C_EncodingUtil`, la corrección acotada propuesta es admitirlo mediante una selección explícita y una identificación de formato/decoder honesta, manteniendo límites y validaciones. Primero verificar esta muestra y casos relevantes de esa ruta; no basta renombrar el flag ni anunciar soporte general por estos 252 bytes.
- Si el productor continúa desconocido, conservar el rechazo operativo. No quitar globals, transformar el Lua, redondear ni convertir el diagnóstico a HTTP para sortearlo.

No se implementó ninguna de estas propuestas.

## 4. Observaciones verificadas

Hay **siete claves originales**, todas básicas, sin prefijos de variante. En todos los casos `item_key` normalizada y `external_item_id` coinciden exactamente con la clave original, con `key_kind="item"`. No se encontraron aliases ni colisiones. Las variantes `g:`, `gr:` y `p:` **no están ejercitadas por esta muestra**; no se afirma su validación real.

Todos los items tienen exactamente un punto histórico en la clave textual ASCII **`"2485"`**. Además, cada uno tiene un `m` sin índice ni fecha. Los precios se muestran como enteros nativos en copper, sin redondeo ni nombres de items inferidos.

| Clave / ID original | Índice en h y a | Puntos históricos | l | h | a (disponibilidad) | m (sin fecha) | Origen del mínimo proyectable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `2589` | `2485` | 1 | Tabla vacía | 2000100 | 26 | 2000100 | `h_fallback` |
| `4604` | `2485` | 1 | Tabla vacía | 100 | 6 | 100 | `h_fallback` |
| `117` | `2485` | 1 | Tabla vacía | 100100 | 1 | 100100 | `h_fallback` |
| `6303` | `2485` | 1 | Tabla vacía | 100 | 16 | 100 | `h_fallback` |
| `59` | `2485` | 1 | Tabla vacía | 10100 | 1 | 10100 | `h_fallback` |
| `2447` | `2485` | 1 | Tabla vacía | 100 | 7 | 100 | `h_fallback` |
| `1372` | `2485` | 1 | Tabla vacía | 5000100 | 1 | 5000100 | `h_fallback` |

Conteos y distinciones comprobados:

- **1 mercado, 7 items, 1 índice distinto, 7 puntos históricos item/bucket**. No son siete momentos distintos.
- `l`, `h`, `a`, `m` están presentes en la estructura de cada item. **No hay ningún valor nativo l**; las siete tablas l están vacías.
- **21 hechos nativos con valor**: h=7, a=7, m=7, l=0. Pasan los contratos `NativeFact` de forma individual.
- La proyección diagnóstica validada individualmente contiene **28 observaciones**: siete `daily_minimum` de fallback, siete `daily_highest_minimum`, siete `daily_max_available` y siete `last_minimum` sin fecha. **28 no es un conteo retornado por el adaptador**, que se detuvo antes.
- La proyección de un mínimo desde h no crea un hecho nativo l. No se recupera un mínimo anterior posiblemente no retenido.
- No hay días huérfanos: cada a tiene h en la misma clave. Los días son strings soportados, no claves numéricas coercionadas.
- Todos los precios y disponibilidades observados son enteros estrictos, positivos y dentro de `0..2147483647`. No hubo fracciones que redondear, valores negativos ni valores fuera de rango. Esos casos de rechazo **no están ejercitados por el archivo real**.
- No hay a ausente, a vacía ni a con cero en estos items. Esos estados no se completan ni se dan por probados.
- No aparecen campos de item ajenos a l/h/a/m, `pending` ni otras versiones incompatibles en el contenido inspeccionado.

Los valores grandes de ciertos h/m se conservan literalmente: una muestra tan pequeña y un AH nuevo no permiten clasificarlos como errores ni como precios representativos. Que `m == h` en los siete items no fecha m ni lo convierte en otra observación temporal.

La lectura del `Source/Database/Mixin.lua` instalado confirma que `SetPrice` inicializa l/h/a vacíos y sólo escribe l cuando el precio es menor que h. Por tanto, l vacío es coherente con esa implementación; no se interpreta como corrupción ni permite reconstruir cuántas actualizaciones hubo.

**a representa disponibilidad máxima guardada; no volumen vendido, ventas confirmadas ni número de subastas. m es el último mínimo guardado; no demuestra un precio de compra actualmente disponible.**

## 5. Otras estructuras y privacidad

El Lua contiene estos ocho globals. Sólo se publican estructura y conteos necesarios:

| Global | Entradas en su tabla exterior | Alcance |
| --- | --- | --- |
| `AUCTIONATOR_CONFIG` | 67 | Configuración; contiene strings y tablas anidadas personalizables |
| `AUCTIONATOR_SAVEDVARS` | 1 | Estado auxiliar |
| `AUCTIONATOR_SHOPPING_LISTS` | 0 | Sin listas guardadas en esta copia |
| `AUCTIONATOR_PRICE_DATABASE` | 2 | Marcador v8 y mercado PvP |
| `AUCTIONATOR_POSTING_HISTORY` | 1 | Sólo `__dbversion=1`; no contiene publicaciones en esta copia |
| `AUCTIONATOR_VENDOR_PRICE_CACHE` | 14 | Marcador v1 y 13 entradas; **no son items adicionales del AH** |
| `AUCTIONATOR_RECENT_SEARCHES` | 0 | Sin búsquedas recientes guardadas |
| `AUCTIONATOR_SELLING_GROUPS` | 3 | Configuración de grupos; valores omitidos |

La inspección estructural de privacidad encontró strings no vacíos en configuración y grupos. No se imprimieron sus valores, nombres personalizados ni contenido completo. No se observaron valores tipo email en el recorrido de strings auxiliares ni claves con los indicadores de cuenta/personaje/credenciales comprobados; esto **no es una certificación de ausencia de datos personales o secretos**. Se omitieron de la documentación los ajustes, strings y claves personalizables, rutas privadas de cuenta y contenido auxiliar. El original debe permanecer fuera de Git.

## 6. Calidad para Market Intelligence 3A y señales 3B

Se ejecutó `compute_metrics` del código existente sobre **un `BucketPoint` diagnóstico por item**, con los valores reales de la tabla y origen `h_fallback`. No se construyeron IDs de base, exports ni respuestas de API ficticias.

Resultados para cada uno de los siete items:

| Capacidad | Resultado / límite |
| --- | --- |
| Mínimo, media y mediana de mínimos guardados | Se calculan; las tres coinciden con el h de su única fila. n=1 por item |
| Primera/última disponibilidad | Hay un valor a; no aporta variación temporal |
| Cambio absoluto/porcentual de precio | `insufficient_data` |
| Desviación estándar y coeficiente de variación | `insufficient_data` |
| Pendiente histórica | `insufficient_data` |
| Cambio de disponibilidad | `insufficient_data` |
| Conversión de bucket a calendario | `bucket_start("unknown", 2485)` devuelve `None` |

No hay todavía evolución temporal suficiente para una serie histórica útil. Los siete items no pueden juntarse para fabricar siete precios de una misma serie. Nuevas capturas del mismo índice documentarían estados, pero no aumentarían el número de buckets distintos.

Para 3B se inspeccionaron `signals.py` y `SignalParameters`; **no se ejecutó `MarketSignalService` ni el servicio de métricas contra BD**. La desviación histórica requiere por defecto siete precios previos, excluyendo el último, y la tendencia requiere siete observaciones. Aquí habría cero precios previos y un solo precio por item. Incluso los mínimos configurables son mayores que esta muestra. La clasificación que corresponde bajo esas reglas es `insufficient_evidence`, sin señal direccional utilizable. No se presenta como una respuesta de endpoint efectivamente obtenida.

Una presentación futura debería mostrar stress test, n=1, índice 2485 sin fecha, origen `h_fallback`, l vacío, m sin fecha y exclusión de m del análisis temporal. Los avisos del código revisado incluyen muestra pequeña, calendario desconocido, fallback h y evidencia sin fecha excluida. La cobertura dentro del único bucket no demuestra cobertura del AH ni confianza estadística. No corresponde extrapolar al lanzamiento, anunciar oportunidades de compra o interpretar precios guardados como ofertas vigentes.

## 7. Riesgos y próximos pasos antes de importar

1. Resolver el productor/codec de la sesión y conservar el registro del addon/build local ahora identificado. La aceptación del lector CBOR ya está demostrada; falta completar honestamente la selección de formato del adaptador, contemplando que el addon local declara 341 y nuestro contrato 340.
2. Confirmar región, facción/alcance del AH, producto y fuente seudónima estable; mantener `dataset=real` y procedencia stress test. No reutilizar `unverified-offline-only` ni mezclar esta historia con lanzamiento o simulación.
3. Repetir offline el adaptador completo con el codec confirmado, sobre el mismo hash. Exigir resultado nativo, igualdad proyección/batch, manifest, conteos, formato/decoder y hash de estado. Registrar por separado lo no ejercitado por esta captura.
4. Mantener `scan_day_zero=None` hasta medir el origen temporal del cliente. **No deducirlo de 2485 y 21/10/2026**, del mtime o de la fecha de importación.
5. Sólo después del GO offline y de la revisión del operador, preparar un destino `--trial` vacío y separado, verificar sus guards e identidad y acordar la escritura. No modificar `DATABASE_URL` ni usar PostgreSQL de desarrollo. La preparación, migraciones y ensayo **no están autorizados ni ejecutados en esta etapa**.
6. Tras una futura importación autorizada, comprobar hechos y proyección por export antes de habilitar lecturas analíticas. Conseguir buckets adicionales y conservar capturas privadas con contexto; no rebajar requisitos de señales para producir un resultado con n=1.

## 8. Entrega y estado Git

| Pregunta | Respuesta |
| --- | --- |
| ¿Pudimos leer el archivo? | **Sí**, Lua completo y 252 bytes de CBOR con los lectores existentes |
| ¿Nuestro adaptador lo acepta? | **No con la configuración predeterminada**; rechaza la selección de codec. Aceptación completa aún no determinada |
| ¿Cuántos items e índices? | **7 items, un índice: 2485**, en PvP |
| ¿Qué campos nativos aparecen? | **l/h/a/m** en todos; l vacío, h/a por índice y m sin fecha |
| ¿Errores o incompatibilidades? | Un `FormatError` de codec; no se detectaron campos/valores incompatibles en el diagnóstico decodificado |
| ¿Avanzar a `--trial` aislado? | **Todavía no**: resolver codec/contexto y completar la validación íntegra offline |
| ¿Estado Git? | Inicio limpio, rama `main`; única adición verificada al cierre: este informe, sin seguimiento. Sin commit ni push |

No se modificaron frontend, backend, configuración, migraciones ni datos. La única escritura solicitada es este documento. La documentación histórica de fases anteriores conserva su estado; sus frases sobre falta de datos reales o implementación de 3B corresponden a su fecha y no sustituyen esta validación.

**Veredicto de la etapa inicial: INSUFFICIENT EVIDENCE.** La actualización siguiente completa la aceptación offline mediante un perfil explícito, sin convertirla en autorización de escritura.

## 9. Compatibilidad offline con Auctionator 341: implementación y resultado actual

Actualización realizada sobre el mismo HEAD `f30f0de0b7c814e80afa6d41ac8cb41776e3df0e`, sin commit. Se volvió a leer la copia auténtica indicada por el operador; permanece fuera del repositorio. Su tamaño sigue siendo **4.701 bytes** y su SHA-256 sigue siendo `7d5cf3db48fa78ab19d3a359557470752e634da743cebe42833fb07c10aa458b`.

### 9.1 Evidencia suficiente para interpretar estos bytes

La codificación observada es un **subconjunto CBOR de longitud definida**, sin extensiones necesarias para esta muestra:

| Elementos CBOR observados | Cantidad / representación |
| --- | --- |
| Mapas, major type 5 | 22: raíz, items y tablas históricas |
| Byte strings, major type 2 | 50: claves de campos, items, días y `version`; contenido ASCII |
| Enteros sin signo, major type 0 | 22: valores nativos y versión; inmediatos o argumentos de 1, 2 y 4 bytes en big endian |
| Arrays, major type 4 | 7, todos vacíos (`0x80`), usados como tablas l vacías |
| Bytes consumidos | 252/252; sin prefijos adicionales ni bytes sobrantes |
| Floats, tags, longitudes indefinidas, compresión o extensiones | No se requieren ni se observaron al recorrer el payload |

El test auténtico reconstruye los valores económicos esperados mediante un **encoder pequeño e independiente de tests**, conservando únicamente el orden de mapas observado. Su resultado coincide **byte a byte con los 252 bytes** originales. Esto aporta evidencia de representación además de la aceptación por `CBORReader`. No se guardó el payload ni el Lua original en fixtures; los valores esperados son los de la tabla pública de la sección 4.

Se volvieron a comparar los archivos instalados 341 con la referencia 340. `Source/Variables/Main.lua`, `Libs/LibCBOR/LibCBOR.lua` y `Source/Database/Mixin.lua` tienen los mismos hashes ya documentados; los `.toc` declaran versiones diferentes. No se presupone compatibilidad general entre ambas revisiones.

Auctionator 341 selecciona la ruta mediante `if C_EncodingUtil`: serializa el mercado actual al evento `PLAYER_LOGOUT` con `C_EncodingUtil.SerializeCBOR` cuando está presente, y usa rutas nativa/LibCBOR condicionales para otros mercados y deserialización. El LibCBOR incluido serializa strings Lua como tipo 3; los strings de esta captura son tipo 2. **La ruta nativa sigue siendo una inferencia respaldada por el código y los bytes; la función efectivamente ejecutada durante la sesión permanece PENDIENTE.**

Esa incertidumbre de productor no crea una ambigüedad en la interpretación del payload observado: sus tipos, longitudes, claves, valores y estructura admiten un cotejo exacto. La nueva selección describe ese subconjunto de bytes; **no declara LibCBOR confirmado ni soporte completo de `C_EncodingUtil`**.

### 9.2 Causa del rechazo y corrección acotada

El rechazo original era deliberado: `decode` en `AuctionatorAdapter.load_bytes` detenía todo string serializado cuando `allow_libcbor=False`, antes de invocar `CBORReader`. El lector ya podía decodificar esta muestra. No fallaban la versión v8, los enteros ni l/h/a/m.

Cambios implementados:

- `serialized_codec="cbor-definite"` permite seleccionar explícitamente el lector CBOR acotado **sin atribuirle un productor**. La configuración predeterminada sigue rechazando strings serializados. No hay autodetección permisiva ni fallback después de errores.
- Se rechazan perfiles desconocidos, la selección simultánea con `allow_libcbor=True` y versiones de formato distintas de 340/341. La selección LibCBOR anterior se conserva.
- `source_version="341"` construye `Auctionator341Batch`, que hereda las validaciones existentes. El contrato base `PartialBatch` y HTTP siguen admitiendo únicamente 340; no se habilitó la importación HTTP de 341.
- La evidencia distingue `input_format="cbor_definite"` y `decoder_version="auctionator-v8-v2"`. Una tabla producida por el CBOR exterior ya no se cuenta como Lua de entrada: un mercado íntegramente serializado se etiqueta con su formato serializado; los casos realmente mixtos siguen siendo `mixed`. Esto también corrige esa etiqueta para mercados LibCBOR completos, sin modificar sus hechos, observaciones ni hash de estado.
- `PartialIngestionService` rechaza los perfiles offline nuevos **antes de conectar o registrar un run failed**. Este guard mantiene acotado el soporte y evita trasladar los metadatos nuevos a un esquema que aún no los admite.
- `CBORReader` sólo recibió una aclaración documental: **no se amplió su gramática ni se relajó ningún control**. Se conservan 16 MiB, profundidad 32, presupuesto compartido de un millón de nodos, límites de estructura/hechos/observaciones, tipos estrictos y comprobaciones semánticas. No se instalaron dependencias.

No se alteraron frontend, estadísticas, señales, archivos del juego, la referencia externa ni migraciones. No se ejecutaron Lua, `eval`, CLI de importación, `--trial`, probes de BD ni migraciones.

### 9.3 Prueba auténtica por la ruta normal del adaptador

Con `BETA_COPY` apuntando privadamente a la copia examinada, se ejecutó el equivalente a:

```python
import os
from pathlib import Path
from app.ingestion.adapters.auctionator import AuctionatorAdapter

r = AuctionatorAdapter().load(
    Path(os.environ["BETA_COPY"]),
    source_id="stress-20261021-offline-audit",
    region="unverified-offline-only",
    dataset="real",
    source_version="341",
    serialized_codec="cbor-definite",
    scan_day_zero=None,
)
assert r.native is not None
assert sorted(o.model_dump_json() for o in r.native.projected_observations()) == sorted(
    o.model_dump_json() for o in r.batch.observations
)
```

El marcador de región **no es una región real inferida ni un valor aprobado para persistir**. La fuente seudónima es contexto diagnóstico. El formato 341 se selecciona por la instalación observada; el SavedVariables no declara la revisión del addon. No se sustituyeron valores faltantes del archivo.

| Comprobación | Resultado completo del adaptador |
| --- | --- |
| Mercado / ruleset | `PvP` / `PvP`, sin mapping externo |
| Items y claves originales | 7: `2589`, `4604`, `117`, `6303`, `59`, `2447`, `1372` |
| Índices | Sólo `2485`; claves originales textuales `"2485"` preservadas |
| Campos presentes | a/h/l/m en los siete items; l vacío |
| Hechos nativos | **21**: h=7, a=7, m=7, l=0 |
| Observaciones normalizadas | **28**: mínimo fallback=7, mayor mínimo=7, disponibilidad=7 y último mínimo sin fecha=7 |
| Cotejo con origen | Los precios y cantidades exactos coinciden con cada fila de la sección 4 y con la reconstrucción independiente del payload |
| Proyección nativa / batch | Igualdad exacta, incluidas identidades, índices, estadísticas y valores |
| Identidad | Claves originales, item_key, ID externo y `key_kind=item` preservados, sin colisiones ni variantes inventadas |
| Formato / decoder | `cbor_definite` / `auctionator-v8-v2` |
| Tiempo | `scan_day_zero=None`; base temporal desconocida. m sigue sin fecha |
| Hash de estado con el contexto diagnóstico anterior | `1ca0ca85e52eb9edbb788c952c81fd2f6821bcefba85472455ba7e3a89fad4f6` |
| Hash de evidencia normalizada del batch con ese contexto | `28f8a78fea353989682bd68d5c710fdaead8d7554b130155075862b30dd21d00` |

Ahora los conteos **21/28 sí provienen del resultado real de `AuctionatorAdapter.load`**, además del cotejo diagnóstico anterior. No hay hechos l fabricados, ceros de relleno, registros adicionales ni nombres de items inferidos. Los hashes de estado/batch incluyen el contexto elegido; cambiar a una región/fuente verificada cambiará esos hashes. No representan un export persistido ni una recepción en BD.

El proceso directo de validación volvió a comprobar que no estaban cargados `psycopg`, `app.db`, `app.core.config` ni `app.ingestion.partial_service`. El SHA-256 del original se reconfirmó al cierre.

### 9.4 Regresiones y seguridad

**162 tests aprobados, cero skips en esta ejecución y cero intentos de conexión a BD.** Suites ejecutadas:

- `tests/test_auctionator.py`
- `tests/test_hardening_parser.py`
- `tests/test_native_exports.py`
- `tests/test_auctionator_cbor.py` (nueva)

La suite nueva incluye la captura auténtica mediante `AUCTIONATOR_REAL_CAPTURE`, con tamaño y SHA-256 fijados. Si no se configura esa variable, ese caso se omite explícitamente; si se configura una ruta inexistente o un archivo distinto, falla. Las regresiones construidas no reemplazan el caso auténtico.

Se cubrieron fixtures 340 Lua/LibCBOR, el perfil 341 real, todas las truncaciones de un payload construido válido, CBOR malformado y con bytes sobrantes, tags, longitudes indefinidas, claves duplicadas incluyendo byte/text aliases, profundidad excesiva, límites de tamaño/contenedores/presupuesto compartido, límites de estructura/observaciones, precios y cantidades inválidos, floats de 16/32/64 bits sin redondeo, aliases contradictorios, días huérfanos, mercados desconocidos, mappings inválidos, variantes ambiguas y perfiles no soportados. También se comprobaron preservación de variantes soportadas, l explícito frente a fallback, a ausente/vacío/cero, conservación de la ruta 340 y bloqueo previo a BD de los perfiles nuevos.

La ejecución usó `python -B`, `-p no:cacheprovider` y un bloqueo de conexiones en el driver. Para reproducir desde `backend`, establecer `AUCTIONATOR_REAL_CAPTURE` privadamente y ejecutar:

```powershell
@'
import psycopg
import pytest
attempts = []
def forbid_connection(*args, **kwargs):
    attempts.append(True)
    raise AssertionError("Database connections are forbidden in this offline run")
psycopg.connect = forbid_connection
psycopg.Connection.connect = forbid_connection
psycopg.AsyncConnection.connect = forbid_connection
code = pytest.main([
    "-q", "-p", "no:cacheprovider",
    "tests/test_auctionator_cbor.py", "tests/test_auctionator.py",
    "tests/test_hardening_parser.py", "tests/test_native_exports.py",
])
print("Database connection attempts:", len(attempts))
raise SystemExit(code or bool(attempts))
'@ | .\.venv\Scripts\python.exe -B -
```

Los tests que ejercitan rechazo HTTP/servicio sólo alcanzan validaciones previas a persistencia; los guards/mocks y el bloqueo del driver impiden IO. No se ejecutaron suites de integración ni pruebas que crean schemas. Se observó un aviso ya existente de deprecación Starlette/httpx; no hubo errores ni regresiones funcionales en las suites ejecutadas. `git diff --check` y la comprobación de whitespace de los archivos nuevos pasaron.

### 9.5 Límites y condiciones antes de un trial

**La compatibilidad offline está resuelta para esta captura y este subconjunto. La suficiencia estadística sigue siendo n=1 por item**, con las limitaciones de la sección 6. No se modificaron ni rebajaron umbrales de 3A/3B. Siete items no son siete buckets; a no es volumen vendido y m no es una oferta de compra actual.

El esquema existente conserva `source_version='340'`, `input_format` limitado a `lua_tables/libcbor/mixed` y `decoder_version='auctionator340-v1'` en las migraciones 003/004. La CLI tampoco expone el perfil nuevo. **No intentar sortear estas fronteras etiquetando la captura como LibCBOR, cambiándola a 340, quitando su evidencia o enviándola por HTTP.** No se diseñó ni ejecutó una migración en esta tarea; los servicios analíticos continúan con su contrato anterior.

Pendientes antes de considerar un trial: confirmar región y contexto de fuente/alcance, revisar la evidencia de la sesión, acordar el soporte de persistencia/lectura para los metadatos nuevos y preparar un destino aislado bajo una autorización posterior. El codec productor efectivo sigue pendiente; el perfil CBOR observado ya tiene una interpretación segura y no depende de inventar ese dato. La base temporal desconocida se conserva y no se deduce de 2485 ni de la fecha de captura.

### 9.6 Archivos y estado Git

Archivos de implementación modificados:

- `backend/app/ingestion/adapters/auctionator.py`: selección explícita, formato 341 y procedencia del transporte.
- `backend/app/ingestion/partial_contracts.py`: batch 341 exclusivo de validación offline; contrato base/HTTP 340 conservado.
- `backend/app/ingestion/native_exports.py`: etiquetas nuevas de formato y decoder.
- `backend/app/ingestion/saved_variables.py`: aclaración documental; algoritmo y límites sin cambios.
- `backend/app/ingestion/partial_service.py`: guard de perfiles offline antes de conexiones o registro de fallos.

Archivos sin seguimiento: `backend/tests/test_auctionator_cbor.py` (nuevo) y este informe, ya sin seguimiento al iniciar la tarea. Rama `main`, HEAD sin cambios. No se añadió el SavedVariables original al repositorio. Sin commit, push, conexiones, importaciones ni escrituras de datos en ninguna BD.

**Veredicto final actualizado: NOT READY FOR TRIAL.** El parsing y la validación offline del archivo auténtico son satisfactorios. Falta habilitar y revisar la persistencia de esos metadatos y confirmar el contexto requerido; esta tarea no autoriza ninguna escritura en base de datos.

## 10. Persistencia segura 341 preparada para revisión

Entrega posterior del **21/10/2026**, sobre el mismo HEAD sin commit. Se implementó la persistencia del formato 341 **cuando existen metadatos verificados y un target trial válido**. No se importó el SavedVariables auténtico ni se migró/modificó desarrollo o la base de tests existente. Las escrituras de validación se limitaron a fixtures sintéticos en un laboratorio nuevo.

### Bloqueo original y necesidad de migración

El esquema de hechos/observaciones ya representa correctamente l/h/a/m, su presencia, variantes, mercado, fuente y tiempo desconocido. El bloqueo era de **metadatos y política de seguridad**, no un formato de precios diferente: CHECK de versión 340, etiquetas de formato/decoder antiguas y guard offline deliberado.

Se añadió `005_auctionator_341_provenance.sql`, sin editar 003/004. Amplía las listas permitidas, exige procedencia coherente en exports 341 y añade un guard complementario para recepciones con el decoder nuevo. **No crea columnas, tablas ni secuencias, no transforma filas y no reconstruye historia.** Conserva todos los triggers de sellado, inmutabilidad, coherencia y contexto existentes. Los CHECK ampliados se agregan y validan transaccionalmente; sólo se ejecutó en el laboratorio nuevo y schemas de prueba de ese mismo laboratorio.

### Metadatos explícitos y preservación de origen

`CaptureProvenance` exige hash de bytes, versión de formato seleccionada, fuente seudónima, región, dataset/fase, mercados/rulesets exactos y refs de evidencia de región, mercado y origen. Se rechazan campos ausentes, placeholders, JSON con claves duplicadas, contradicciones y valores que no coincidan con el input/contexto. La referencia es una attestation del operador: el código comprueba concordancia, **no autentica automáticamente el contenido de un registro externo**.

Los claims de instalación observada se almacenan separados de los confirmados durante captura, cada uno con su ref. El build instalado **1.60.1.70532** y addon instalado **341** no se convierten automáticamente en datos confirmados de la sesión. El productor efectivo de codec puede seguir `unverified` con `cbor-definite`; no se inventa una prueba de `C_EncodingUtil`. Los hechos l/h/a/m continúan siendo evidencia nativa independiente de esas attestaciones.

La procedencia se almacena en el **manifest existente, sellado e inmutable**. Los campos de transporte ya existentes conservan perfil/decoder y los runs conservan hash/ruta. El hash de bytes exigido al JSON se coteja antes de escribir y permanece en cada recepción; se excluye del manifest canónico para reutilizar exports equivalentes con igual contexto. Los refs/claims sí participan del hash de estado. El manifest 340 sin procedencia y sus hashes no cambian.

Para esta captura se requiere **`dataset=stress_test`, `capture_phase=stress_test`, `source_type=auctionator`**. Esta extensión sustituye para este caso la recomendación histórica de `dataset=real`: la autenticidad permanece expresada por origen/evidencia y la fuente Auctionator; el dataset separa el contexto de stress del lanzamiento (`real`) y de simulación (`simulated`). La unicidad de mercado existente hace efectiva esa separación sin cambiar la clave raw `PvP`. Items/variantes conservan su catálogo compartido por identidad; los datos de mercado se separan por market_id, fuente y contexto temporal.

### Guard de trial y bloqueo antes de escritura

Los perfiles nuevos sólo se aceptan para persistencia mediante `PartialIngestionService(trial_target=target)`, donde target es `TrialDatabase`. Una factory arbitraria o la ruta ordinaria no habilitan 341. El CLI exige `--trial`, contexto explícito y `--provenance-file`; el contrato HTTP permanece en 340 y no admite 341/stress_test.

Se valida nuevamente el batch, la procedencia ligada al hash y mercados y la igualdad entre proyección nativa y observaciones antes de entrar al escritor. `TrialDatabase` no cambió: mantiene selección explícita, identidad efectiva de cluster/OID, comparación con el protegido, conexión directa estable y revalidación dentro de la transacción antes de cada escritor. Retry y registro de failed usan el mismo target controlado y redacción fija. Antes de cada INSERT de run se comprueba que el destino tenga 005; un destino no preparado se rechaza sin consumir la secuencia de runs.

No hay migración automática al importar ni selección automática de región. No se interpreta 2485 como fecha civil ni se cambia el número de buckets. El flujo 340 anterior conserva su servicio/factory, valores, codec y guards.

### Validación ejecutada y preservación

Laboratorio nuevo: **`wow_341_persistence_8630425299b0_test`, OID 422588**, distinto por identidad efectiva de las bases protegidas. Se aplicaron allí 001–005 bajo `TrialDatabase`. Los tests de escritura usaron únicamente fixtures sintéticos, tanto en public como en schemas efímeros del mismo laboratorio; no se limpió ni migró ninguna base anterior.

- **333 tests aprobados** en la suite completa de parser, hardening, evidencia nativa, CLI/guard, ingestión parcial, exports, concurrencia, rollback y migraciones.
- Tras añadir el preflight de schema y la prueba end-to-end del CLI 341, **140 tests focalizados aprobados**, incluidos cuatro nuevos. Total de **337 casos distintos aprobados**, sin sumar como nuevos los casos repetidos.
- Se probaron versión 340, 341/cbor-definite, regiones ausentes/inválidas, metadatos incompletos/contradictorios, variantes, l/h/a/m/fallback, mismo archivo, bytes equivalentes, exports distintos del mismo mercado, separación stress/launch/simulation, concurrencia, failed/retry, integridad y bloqueo previo a filas/secuencias. La migración 005 preservó exactamente filas y secuencias de exports 340 ya sellados en una prueba de upgrade.
- La captura auténtica se volvió a leer **sólo offline**. El runner prohibió crear un run con su hash; hubo **cero intentos**. La consulta final del laboratorio encontró **cero runs auténticos**. Sus siete items, 21 hechos, 28 observaciones y un bucket siguen siendo los de la sección 9.
- El primer intento de preparar temporales de pytest falló por ACL de Windows/Python `mkdir(0700)`; se corrigió exclusivamente la herencia de permisos de una carpeta temporal nueva de tests. No se cambiaron controles del parser, permisos de directorios existentes ni lógica de producto para resolverlo. Las ejecuciones finales pasaron, con el warning ya existente Starlette/httpx.

Control antes/después de las bases existentes:

| Base protegida | Tablas | Filas totales | Secuencias | Resultado |
| --- | --- | --- | --- | --- |
| Desarrollo | 13 | 16.785 | 11 | Identidad, hashes de todas las filas, last_value/is_called y restricciones idénticos |
| Tests existente | 13 | 4 | 11 | Identidad, hashes de todas las filas, last_value/is_called y restricciones idénticos |

Hash agregado del control completo antes/después: `308c9223cf677c728be3c12509870078e9dd330df2f713a1f959d02143057d23`. Desarrollo conserva sus **16.628 observaciones parciales**. El original privado mantiene tamaño 4.701 y SHA-256 `7d5cf3db48fa78ab19d3a359557470752e634da743cebe42833fb07c10aa458b`. Los snapshots privados sólo guardan conteos/hashes/estados de secuencia, sin DSNs ni filas originales. El laboratorio sí cambió por los fixtures; no se declara preservado ni se usará como primer trial auténtico.

### Condiciones pendientes y siguiente revisión

El procedimiento exacto, plantilla JSON deliberadamente incompleta y comando **no ejecutado** del futuro trial están en [BETA_DATA_READINESS.md, sección 14](BETA_DATA_READINESS.md#14-persistencia-341-con-procedencia-verificada-y-destino-trial).

Antes de ejecutar una escritura auténtica deben cumplirse todas estas condiciones:

1. Región técnica acreditada y asociada a este producto/mercado/captura; origen seudónimo y alcance/facción del AH revisados, sin deducirlos del idioma o PvP.
2. JSON privado completo, hash coincidente, `stress_test` explícito y refs revisados; repetir offline con ese contexto y cotejar manifest, hechos y proyección. Mantener separados los claims de instalación y captura y conservar el productor de codec como no verificado si falta evidencia.
3. Revisión del diff/migración/resultados y **autorización posterior para importar el archivo real**.
4. Otro laboratorio vacío para la captura de aceptación, DSN/nombre explícitos, identidad distinta, migraciones 001–005 verificadas y conexión directa estable bajo el guard. No tocar DATABASE_URL ni desarrollo ni reutilizar datos sintéticos del laboratorio de regresiones.

El desconocimiento del origen temporal se conserva como `unknown`; el de productor no se reemplaza por una inferencia afirmada. La aceptación de persistencia tampoco mejora la calidad estadística: n=1 por item sigue sin permitir evolución histórica ni señales útiles. **No se modificaron frontend, estadísticas 3A ni señales 3B**; esta entrega no habilita su lectura de 341/stress_test y no debe conectarse el dashboard habitual al laboratorio.

Archivos nuevos de esta etapa: `backend/app/ingestion/capture_provenance.py`, migración 005 y suites `test_341_persistence.py`/`test_341_persistence_integration.py`. Se actualizaron adaptador, contratos/evidencia nativa, servicio, CLI, tests de migración/guard y ambos informes. Los cambios offline previos siguen en el working tree. Sin SavedVariables original en Git, sin commit ni push, HEAD sin cambios.

Inventario final de Git (incluye la etapa offline previa): **nueve archivos modificados y seis sin seguimiento**:

```text
M  backend/app/ingestion/adapters/auctionator.py
M  backend/app/ingestion/native_exports.py
M  backend/app/ingestion/partial_contracts.py
M  backend/app/ingestion/partial_service.py
M  backend/app/ingestion/saved_variables.py
M  backend/scripts/import_auctionator.py
M  backend/tests/test_export_migration.py
M  backend/tests/test_trial_database_integration.py
M  docs/BETA_DATA_READINESS.md
?? backend/app/ingestion/capture_provenance.py
?? backend/migrations/005_auctionator_341_provenance.sql
?? backend/tests/test_341_persistence.py
?? backend/tests/test_341_persistence_integration.py
?? backend/tests/test_auctionator_cbor.py
?? docs/FIRST_REAL_AUCTIONATOR_VALIDATION.md
```

**Veredicto final: READY FOR TRIAL REVIEW.** El código y procedimiento pueden revisarse; la captura auténtica continúa sin importar y su región pendiente mantiene el NO GO de ejecución.

## 11. Cierre técnico de la integración y auditoría final

La revisión final del **21/10/2026** comprende los quince archivos de la entrega anterior y `README.md`, actualizado porque todavía describía la captura auténtica como inexistente. Se revisaron diff completo, nuevos módulos/tests, migración 005, provenance, dataset, idempotencia y guards. Todos los cambios corresponden a integración 341, documentación de estado o regresiones. No se agregan nuevas funcionalidades de captura, sincronización o análisis.

### Hallazgo y corrección acotada

El adaptador trataba un marcador de versión de mercado **presente pero nulo** como si estuviera ausente, porque comprobaba `version is not None`. Eso podía perder la distinción entre una estructura no soportada y la ausencia admitida del marcador. La comprobación ahora distingue presencia de clave: si `version` existe debe ser exactamente el entero 2. Se agregaron cinco regresiones para null, booleano, string y enteros incompatibles. El marcador ausente sigue soportado; el de la primera captura es 2 y no se alteran sus valores ni semántica. No fue necesario rediseñar ni añadir otra migración.

No se encontraron otros bloqueos críticos dentro del alcance revisado. Se conservaron límites Lua/CBOR, enteros estrictos sin redondeo, l/h/a/m, identidad/variantes, tiempo desconocido, aislamiento de dataset, hashes/procedencia y el guard de destino. Los registros 340 y sus manifests mantienen compatibilidad. La migración 005 conserva los guards previos y su prueba de upgrade mantiene filas y secuencias de evidencia 340 sellada.

### Regresiones finales y portabilidad

Se ejecutó **todo `backend/tests`**: **730 tests aprobados, uno omitido y un warning existente de deprecación Starlette/httpx**. Incluye adaptador/codecs, contratos, exports, ingestión, idempotencia, concurrencia, fallos/retries, aislamiento, CLI, migraciones y regresiones de 3A/3B existentes; no se modificó su implementación ni el frontend.

El único omitido fue `test_authentic_341_capture_offline`: `AUCTIONATOR_REAL_CAPTURE` se dejó deliberadamente sin configurar. La compatibilidad auténtica permanece acreditada por las ejecuciones offline anteriores de este informe; **no se atribuye una nueva lectura del original a este cierre**. Ningún test obligatorio depende de rutas privadas ni de tener la captura en otra computadora. Los tests de integración requieren conexiones explícitas de laboratorio, no una captura auténtica. La inspección de los archivos añadidos de tests no encontró rutas privadas de Windows.

La ejecución usó un target nuevo `wow_341_close_target_6bdc10a561_test` (OID 461107) y una referencia protegida desechable `wow_341_close_protected_928f0886fb_test`. `DATABASE_URL`/`TEST_DATABASE_URL` se seleccionaron **sólo en el proceso hijo de tests**, sin editar `.env` ni configuración persistente. Esto permitió probar el guard sin abrir conexiones a desarrollo ni a la base de tests preexistente. El target se preparó con 001–005 y recibió exclusivamente fixtures sintéticos; la referencia protegida permaneció vacía.

El control del driver registró 1.376 sesiones exclusivamente en esos dos laboratorios, **cero intentos fuera de ellos y cero intentos de persistir el hash auténtico**. La consulta final encontró cero runs con ese hash. Los procesos de startup de CLI sólo ejercitaron ayuda o fallos previos a conexión con configuración sintética. Desarrollo no recibió conexiones, escrituras ni migraciones en este cierre. Los cotejos de filas/secuencias de la sección 10 pertenecen a la etapa anterior; no se repitieron contra desarrollo para respetar la restricción actual de cero conexiones.

La migración 005 se volvió a aplicar en un destino vacío y en schemas efímeros de laboratorio, con repetición sin pendientes y prueba de preservación de exports 340. No se aplicó a ninguna base de desarrollo. Los temporales y controles del runner quedaron fuera de Git. `git diff --check`, sintaxis, whitespace y enlaces de documentación pasaron.

### Archivos revisados y estado de publicación

El inventario histórico de la sección 10 se conserva; el cierre agrega el README a esos quince archivos. Se comprobó que no se incluyeran SavedVariables, copias Lua, `.env`, secretos, bases de datos ni artefactos generados. El test auténtico usa una ruta recibida sólo por variable opt-in; no incorpora el original al repo. La corrección de versión nula está en el adaptador y su suite existente.

El HEAD base de revisión y `origin/main` coincidían en `f30f0de0b7c814e80afa6d41ac8cb41776e3df0e`. El código queda apto para el commit/push de cierre autorizados, sujetos al cotejo final con remoto; el hash y resultado efectivos se informan en la entrega Git. Los estados «sin commit» de secciones anteriores describen sus etapas previas, no el estado posterior a la publicación.

### Pendientes auténticos y próximo paso

Continúan pendientes la región técnica, la procedencia completa/alcance y autorización específica del primer trial auténtico. Build exacto en la sesión y productor efectivo del codec permanecen sin confirmar; no se promueven los valores instalados actuales a hechos de captura. Se conserva el índice 2485 sin fecha civil, n=1 por item y procedencia stress test, que no representa el lanzamiento.

El operador informó una segunda captura posterior con cambios y más items. **No se inspeccionó, incorporó, importó ni validó su evolución en este cierre.** Se utilizará en la próxima etapa con copias privadas y trazabilidad.

El roadmap de **Fase 5A — Local Capture Companion** queda en el [README](../README.md): primero definir el contrato y los casos de estabilidad de escritura, archivado independiente, hash de archivo frente a estado de precios y trazabilidad. Después podrá implementarse un programa Windows sin PostgreSQL ni envío automático en su primera entrega. Sincronización autenticada, objetivo de dos a cuatro escaneos manuales diarios, histórico real, estacionalidad semanal y modelos predictivos quedan para fases posteriores. Nada de ello se implementó aquí.

**Cierre técnico aprobado. El primer trial auténtico sigue pendiente de región, procedencia y revisión explícita; no se ejecutó ninguna importación auténtica.**
