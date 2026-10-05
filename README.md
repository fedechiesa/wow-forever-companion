# WoW Forever Companion

WoW Forever Companion es un proyecto personal de portfolio y una herramienta pensada para acompanar el juego desde el lanzamiento de WoW Forever. El foco inicial es construir Market Intelligence para el Auction House: entender precios, volumen, tendencias y oportunidades de mercado a partir de snapshots historicos.

La fuente real de datos del Auction House todavia no esta definida. Podria venir de Auctionator, otro addon, una API oficial/no oficial o archivos exportados manualmente. Por eso la primera decision arquitectonica del proyecto es desacoplar la ingestion de datos del resto de la aplicacion.

## Objetivo de v0.1

La v0.1 debe ser una primera version usable para validar el producto con datos simulados o importados desde archivos simples. No busca resolver todo el ecosistema de WoW Forever, sino demostrar que el nucleo de inteligencia de mercado funciona de punta a punta.

Alcance concreto:

- Definir un contrato comun para snapshots del Auction House.
- Ingerir datos simulados o archivos exportados en un formato controlado.
- Guardar historico de items, precios, volumen y snapshots.
- Consultar metricas basicas por item: precio minimo, precio medio, maximo, volumen, tendencia simple y volatilidad.
- Detectar oportunidades iniciales con reglas explicables.
- Preparar el backend para exponer herramientas consultables por un asistente de IA sobre datos propios.
- Proveer una interfaz simple para explorar items y ver senales de mercado.

Fuera de alcance para v0.1:

- Personajes, guild, roster, raid planner, profesiones completas o gear planning.
- Integracion definitiva con un addon especifico.
- Automatizacion compleja de compra/venta.
- Modelos predictivos avanzados.
- Optimizaciones prematuras de escala.

## Stack tentativo

- Frontend: React.
- Backend: Python + FastAPI.
- Database: PostgreSQL.
- Control de versiones: Git/GitHub.

La prioridad es mantener el sistema simple, explicable y facil de defender tecnicamente. Las abstracciones deben existir solo donde reducen acoplamiento real, especialmente alrededor de la fuente de datos del Auction House.

## Documentacion

- [Arquitectura](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)

La estructura propuesta del repositorio esta documentada en [Arquitectura](docs/ARCHITECTURE.md#estructura-propuesta-del-repositorio). Todavia no se inicializaron React, FastAPI ni PostgreSQL.

## Supuestos pendientes de validar

- Cual sera la fuente real de datos del Auction House.
- Frecuencia posible de actualizacion de snapshots.
- Campos disponibles por item, subasta y realm.
- Si existira una API confiable o si dependeremos de exports de addons.
- Como se identificaran items de forma estable en WoW Forever.
- Si habra restricciones legales, tecnicas o de terminos de uso para obtener datos.

## Principio guia

Primero construir una base pequena que permita aprender con datos reales o simulados. Despues extender. El proyecto debe poder crecer hacia features de personajes, guilds o profesiones, pero la primera version debe concentrarse en el diferencial: inteligencia de mercado para el Auction House.
