# Fase 6 — Prelaunch Readiness Check

28/10/2026, America/Buenos_Aires. Base: `911633c3ed191b50881276001e60049e744f0123`,
main inicialmente limpio. Fecha objetivo comunicada: 04/11/2026.
**Ensayo sintético aprobado; lanzamiento condicionado a verificación auténtica.**
No se necesita una funcionalidad nueva para el recorrido ensayado. No se importó
ninguna captura privada auténtica, no se conectó PostgreSQL de desarrollo, no se
activó sincronización ni cambiaron aplicación, motores 3A/3B, UI o migraciones.
Entrega inicial sin staging, commit ni push. El usuario aprobó después el ensayo
y autorizó su cierre y publicación en main, exclusivamente para Fase 6.
[Manual operativo](LAUNCH_DAY_RUNBOOK.md).

## Flujo reconstruido y decisiones manuales

Se revisaron README, ARCHITECTURE, ROADMAP, 5A.1/5A.2, 5B.1/5B.2, 5C.1 y
5D.1/5D.2, más CLI, watcher, preflight, TrialDatabase, escritores/lectores y tests.
Los veredictos antiguos dentro de esos documentos se leyeron como históricos;
el ensayo utiliza los contratos publicados actuales y migraciones 001–006.

```text
Auctionator.lua → watcher local → captures/<SHA>/{original,metadata}
                                ↓ selección manual + contexto privado revisado
                         preflight offline
                                ↓ verificación manual del target autorizado
                         TrialDatabase → estado v2 sellado + hechos + recibos
                                ↓
                         LocalEvidenceReader → API GET → dashboard
```

| Paso | Entrada/configuración requerida | Intervención y resultado |
| --- | --- | --- |
| Origen | Instalación/WTF y SavedVariables correctos, perfil/codec soportado | Operador elige ruta; scan y `/reload` manuales. No se controló ni supuso disponible WoW. |
| Watcher | Python, ruta de origen, archivo privado externo, timings, selecciones de perfil | Arranque foreground y parada manual. Original íntegro y metadato publicado; sin .env/SQL/HTTP. |
| Contexto | SHA completo, observador, región, economía/alcance/facción, fase/dataset y evidence_refs | Preparación humana por captura; no se deduce desde PvP ni del nombre del personaje. |
| Preflight | Archivo publicado + contexto verified-local-capture-v1 | Recalcula bytes/evidencia, comprueba codec, integridad y rango; no verifica target ni importa. |
| Trial | Target y referencia protegida explícitos, identidades físicas distintas, target `_test`, esquema 006 | Check-target y orden manual de ingestión. Revalidación del target antes de cada escritor. |
| Lectura | DSN explícito del target; dataset/economía/estado | Lector privado o API pública GET, READ ONLY. API no migra ni importa. |
| UI | FastAPI, VITE_API_BASE_URL y CORS concordantes | Selección explícita y búsqueda por ID; catálogo opcional sin alterar hechos. |
| Backup | Archivo detenido, destino privado nuevo fuera de repositorio/WTF | Copia completa y comparación SHA-256, incluidos pendientes. Sidecars también deben respaldarse. |

## Laboratorio y protección

Se creó un contenedor PostgreSQL 16 nuevo, con etiqueta de propósito de ensayo,
credencial aleatoria temporal y puerto asignado por Docker enlazado únicamente a
127.0.0.1. El contenedor de desarrollo existente no se seleccionó ni modificó.
Se crearon una referencia protegida nueva, sin tablas/secuencias, y un target
nuevo terminado en `_test`, comprobado vacío antes de aplicar las seis migraciones.
La repetición del ensayo usó otro target nuevo; el intento anterior quedó conservado.

En procesos de pruebas/CLI/API se instaló un guard **temporal externo al repo**:
sólo host loopback, puerto del clúster nuevo y nombres explícitos del target y
referencia; para el test de esquema ausente, su base efímera `unprepared_<UUID>_test`
en ese mismo clúster. En watcher/preflight se bloquearon todas las conexiones.
La referencia se comparó por filas/secuencias antes/después. No se usó desarrollo
como referencia; no hay fingerprint de desarrollo porque no se lo conectó.
No se modificaron `.env` del usuario. Originales, contextos, credenciales, logs,
backup y artefactos HTTP se guardaron en temporales externos y no entran en Git.

## Ensayo de captura y persistencia

`tests/test_prelaunch_readiness.py` es opt-in: exige cuatro variables explícitas,
referencia concordante con DATABASE_URL, destino sin exports y artefactos externos.
Usa un prefijo SIMULATED reconocido por el parser y contexto dataset simulated;
el fixture no se puede reasignar a launch para simular autenticidad.

- Se inició **la CLI real del watcher**, padre existente y archivo inicialmente
  ausente. Detectó creación/cambios, esperó estabilidad y rechazó un Lua incompleto.
- Se guardaron A y B, con item 2589 y diferentes l/h/a/m en **el mismo bucket 2485**.
  El nombre del item no se resuelve para este dataset sintético.
- Repetir A dejó dos originales. Se terminó el proceso y reinició; siguió habiendo
  dos capturas publicadas. La prueba de reinicio fue abrupta deliberadamente;
  Ctrl+C normal conserva la validación previa de 5A y sus tests de consola.
- Hashes SHA-256 de todos los originales A/B y bytes comparados con el productor;
  el watcher no modificó el origen. DB configurada como caída durante el archivo.
- Preflight real por CLI en proceso separado y sin SQL/settings; devolvió
  import_performed=false y target_verified=false. Check-target real posterior.
- Ingestión manual real por CLI: A=completed/export 1, B=completed/export 2,
  repetición A=duplicate/export 1. **8 hechos nativos, 3 recibos**, dos para A.
  Ninguna fila acumulada 003 creada por ese flujo; observations_changed=0.
- Mismo target y referencia física: bloqueo sin modificar filas o secuencias.
- Se provocó CheckViolation después de escribir evidencia dentro de la transacción:
  rollback de estado/hechos/recibos, preservación de datos anteriores. Sólo quedó
  el registro auditado failed; secuencias PostgreSQL pueden consumir valores.
- Precios **2147483648 y 9223372036854775807** archivados exactos e íntegros;
  ingestión completa bloqueada por price_exceeds_persistence_int32, sin cambios
  en ninguna fila ni secuencia. No se truncó ni se quitó el item caro.

Resultado del nuevo ensayo: **1 aprobado, 11,86s**. Los cinco originales finales
(A, B, vector de rollback y dos vectores extremos) permanecen fuera de Git.
Backup PowerShell verificado: **11 archivos** (cinco pares y lock), hashes idénticos,
fuente sin modificaciones. Copia en el mismo volumen temporal sólo valida el
procedimiento; no prueba tolerancia a pérdida física del disco.

## Consulta real y frontend

LocalEvidenceReader leyó los dos estados, los cuatro hechos por estado y los
recibos de A. Se inició FastAPI sólo en loopback con DATABASE_URL apuntando al
target de laboratorio y caché de catálogo vacía independiente.

El **App React real**, compilado con su base URL de ensayo y montado con jsdom,
usó fetch/HTTP reales a FastAPI → PostgreSQL: **6 GET**, cero requests externos.
Se eligió simulated → economía sintética → export 1; se verificaron item/precios,
bucket 2485, dos recibos, procedencia y búsqueda 2589; luego se eligió export 2.
No se usaron mocks de transporte en este recorrido. No se convierte en prueba de
layout de navegador: el responsive conserva DOM/CSS y aprobación previa de 5C.1.

GET de hechos/recibos con dataset ajeno: 404. El mercado v2 no aparece en el
catálogo `/partial/markets`. `/catalog/items` vacío: IDs; ningún request a AHledger.
La atribución, nombres sólo con procedencia/TTL, separación launch/simulated,
caducidad sin polling e imágenes con placeholder se revalidan además en los
tests montados de evidencia publicados. No se sembró un nombre auténtico en el lab.

Arranque Vite real en loopback comprobado, GET HTTP de la página, health y CORS
con origen concordante. Se comprobaron también los comandos PowerShell de
dependencias, check-target y backup del runbook. No se afirma validación del
WTF real, primer `/reload`, datos de lanzamiento ni recuperación pg_restore.

## Bloqueos prelaunch

| Punto | Clasificación | Acción necesaria, sin inventar datos |
| --- | --- | --- |
| A. Ruta real y primer `/reload` | **BLOQUEANTE para archivado** auténtico verificado mientras no se seleccione origen vivo correcto y se compruebe el guardado | Elegir instalación/cuenta en privado, arrancar watcher, scan y `/reload` manuales; verificar publicación y hashes. Hoy no se dispuso del cliente. |
| B. Región/economía/alcance auténticos | **BLOQUEANTE para importación** | Aportar evidencia de cada claim por captura y preparar contexto privado completo. Mientras tanto archivar; PvP no basta, facción desconocida no implica AH shared. |
| C. Precios >2**31-1 | **BLOQUEANTE para importación** de toda esa captura | Conservar evidencia local exacta hasta 2**63-1; no importación parcial ni redondeo. Cambiar el límite requeriría otra decisión de diseño, fuera de esta fase. |
| D. Catálogo vencido/caído | **NO BLOQUEANTE para el MVP** | Item ID como fallback, evidencia/precios intactos. Renovación manual acotada y atribución; sin iconos remotos hasta permiso ni almacenamiento vencido. |
| E. Separación stress_test/launch/simulated | **NO BLOQUEANTE para el MVP**: guards y partición verificados con fixtures | Elegir fase real con evidencia. Si se desconoce, bloquea esa importación; no reasignar capturas entre datasets para conseguir catálogo o completar una demo. |

Además, formatos no soportados, archivo >16 MiB, precios >2**63-1, cantidades o
índices fuera de su límite pueden bloquear **archivado válido**. Conservar el bruto
en privado y revisar compatibilidad sin cambiar guards. Un estado que nunca se
guardó en disco o se sobrescribió entre sondeos no puede recuperarse por polling.

## Criterios de aceptación y entrega

| Criterio | Resultado |
| --- | --- |
| Capturas nuevas sin conexión DB | Aprobado con CLI real y fixtures; A pendiente para origen auténtico. |
| Evitar duplicados | Aprobado por bytes, estado y reinicio; reimport conserva hechos y agrega recibo. |
| Importación sintética reproducible/protegida | Aprobado, target nuevo y referencia distinta; comandos en runbook. |
| Dashboard consulta persistencia | Aprobado mediante React montado y HTTP real; sin nueva QA visual de navegador. |
| Rechazos sin alterar datos anteriores | Aprobado, destino inválido, rollback y extremos numéricos. |
| Instrucciones operativas claras | Runbook separa hoy/lanzamiento, consolas, preflight, protección, backup y recuperación. |

No hay un criterio sintético fallido que requiera corregir producto. La primera
sesión real sigue condicionada a A/B y fase verificada; aprobar este ensayo no
autoriza importar capturas auténticas. Se puede priorizar archivo local aunque
SQL o catálogo no estén listos.

## Validación final y estado Git

- Regresión backend completa publicada: **1159 aprobados, 1 omitido**, 289,45s.
  Se ejecutó con `--ignore=tests/test_prelaunch_readiness.py`, porque ese ensayo
  requiere su propio target vacío. El único omitido es el opt-in de captura
  auténtica, no configurado. Tres advertencias preexistentes: Starlette/httpx y
  dos fixtures Pydantic deliberadamente inválidos.
- Ensayo nuevo: **1 aprobado** en 11,86s; receta PowerShell del runbook comprobada
  literalmente con otra pareja nueva de bases: **1 aprobado** en 10,59s.
  Es el mismo caso repetido; no se cuentan dos tests distintos.
- Frontend: **149 aprobados** (82 + 36 + 31), build de producción correcto.
  Prueba React/HTTP real adicional aprobada, Vite HTTP 200, health y CORS correctos.
- OpenAPI `--check`, sintaxis Python y PowerShell, enlaces locales y
  `git diff --check` correctos; escaneo de alcance/firmas de secretos sin hallazgos.

Los primeros intentos corrigieron únicamente infraestructura de prueba:
el productor sintético debía esperar el handle de lectura Windows; el harness
usaba un campo de la proyección web en lugar del lector privado. En la primera
regresión el guard temporal precargaba psycopg e impedía dos pruebas de imports
offline, y rechazaba la base efímera de un test de esquema ausente. Se corrigió
ese guard externo y se repitió la suite completa con cero fallos. El ensayo React
también necesitó modo test para act(). No se corrigió ni debilitó producto.

Auditoría física final: **dos referencias protegidas nuevas sin tablas ni secuencias**,
estados originales sellados, ocho hechos y tres recibos conservados en ambos ensayos.
El guard registró **3483 conexiones autorizadas** al clúster nuevo y tres intentos
bloqueados de los escenarios negativos/infra inicial; **cero conexiones a desarrollo**.
La ejecución literal del runbook usó además su pareja nueva explícita en el mismo
clúster; no se suman sus conexiones a la telemetría del guard temporal.

Se detuvieron el FastAPI y Vite del ensayo y el contenedor nuevo, después de
verificar sus identidades. Datos y artefactos sintéticos conservados; ningún
watcher, servicio de sync o nueva tarea quedó activo. El contenedor de desarrollo
existente permaneció en ejecución y no se modificó.

Archivos de entrega: README.md, docs/ARCHITECTURE.md, docs/ROADMAP.md,
docs/LAUNCH_DAY_RUNBOOK.md, este informe y backend/tests/test_prelaunch_readiness.py.
Estado de la entrega inicial: **3 modificados y 3 sin seguimiento**, índice sin cambios. HEAD permanecía en
`911633c3ed191b50881276001e60049e744f0123`; **sin commit ni push**. Se preservan
los documentos históricos 5A–5D y todo el código productivo publicado. Los archivos
privados y respuestas de runtime no forman parte de esos seis archivos.

## Cierre formal aprobado

Se revisaron los seis archivos pendientes, los resultados conservados del ensayo,
la separación entre comandos sintéticos y operación auténtica, y los bloqueos
anteriores. El cierre publica únicamente documentación y el test opt-in sintético;
no cambia aplicación, esquemas, límites numéricos o políticas de ingestión.
README y ROADMAP enlazan el informe y runbook; no se inicia otra fase.

Ruta WTF, primer `/reload`, contexto económico auténtico y autorización de primera
importación continúan pendientes. Launch sigue separado de simulated/stress_test;
ningún fixture se convierte en evidencia auténtica. No se reinició el laboratorio
ni se conectó desarrollo para esta revisión final. Los comandos que requieren
cliente o datos reales continúan condicionados; su prueba sintética no los valida
con WoW real. La validación final de publicación queda registrada debajo.

Verificaciones del cierre: **286 tests backend aprobados, 1 omitido**, 27,45s;
se bloqueó psycopg.connect y se dejó el ensayo PostgreSQL opt-in desactivado.
No se reejecutó la importación sintética ya aprobada ni la regresión SQL completa;
sus resultados anteriores se contrastaron con los artefactos conservados fuera de
Git. **149 tests frontend** y build correctos, OpenAPI --check, sintaxis de los
13 bloques PowerShell, enlaces, privacidad, alcance y git diff --check aprobados.
Los tres warnings backend siguen siendo los preexistentes descritos arriba.
La revisión confirma sólo estos seis archivos para publicar en main, sin añadir
bases temporales, copias Lua, sidecars, logs, backups o credenciales al índice.
