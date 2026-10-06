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

## Stack

- Frontend: React.
- Backend: Python + FastAPI.
- Database: PostgreSQL.
- Control de versiones: Git/GitHub.

La prioridad es mantener el sistema simple, explicable y facil de defender tecnicamente. Las abstracciones deben existir solo donde reducen acoplamiento real, especialmente alrededor de la fuente de datos del Auction House.

## Documentacion

- [Arquitectura](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)

La estructura propuesta del repositorio esta documentada en [Arquitectura](docs/ARCHITECTURE.md#estructura-propuesta-del-repositorio).

## Desarrollo local

### Requisitos

- Python 3.11 o superior.
- Node.js 20 o superior.
- npm.
- PostgreSQL local, o Docker con Docker Compose para levantar solo la base de datos.

Docker se usa unicamente como opcion simple para PostgreSQL local. El frontend y el backend corren directamente en la maquina de desarrollo.

### 1. Configurar variables de entorno

Desde la raiz del repo:

```powershell
Copy-Item .env.example .env
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
```

Los archivos `.env` locales estan ignorados por Git. Los valores incluidos son defaults de desarrollo y pueden ajustarse segun tu instalacion local.

### 2. Levantar PostgreSQL

Opcion con Docker:

```powershell
docker compose up -d postgres
```

Opcion sin Docker:

1. Instalar PostgreSQL localmente.
2. Crear una base `wow_forever_companion`.
3. Crear un usuario `wow` con password `wow_dev_password`, o ajustar `backend\.env`.
4. Verificar que `DATABASE_URL` apunte a tu instancia local.

La comprobacion del backend esta disponible en:

```text
GET http://127.0.0.1:8000/health/db
```

### 3. Levantar el backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Health check:

```text
GET http://127.0.0.1:8000/health
```

### 4. Levantar el frontend

En otra terminal:

```powershell
cd frontend
npm install
npm run dev
```

La app queda disponible en:

```text
http://127.0.0.1:5173/
```

Por ahora el frontend solo muestra una pantalla tecnica minima y comprueba que el backend este disponible. Todavia no hay UI real de Auction House, datos simulados, Market Intelligence ni IA.

### 5. Validaciones utiles

```powershell
# Backend vivo
Invoke-RestMethod http://127.0.0.1:8000/health

# Conexion backend -> PostgreSQL
Invoke-RestMethod http://127.0.0.1:8000/health/db

# Frontend compila
cd frontend
npm run build
```

## Supuestos pendientes de validar

- Cual sera la fuente real de datos del Auction House.
- Frecuencia posible de actualizacion de snapshots.
- Campos disponibles por item, subasta y realm.
- Si existira una API confiable o si dependeremos de exports de addons.
- Como se identificaran items de forma estable en WoW Forever.
- Si habra restricciones legales, tecnicas o de terminos de uso para obtener datos.

## Principio guia

Primero construir una base pequena que permita aprender con datos reales o simulados. Despues extender. El proyecto debe poder crecer hacia features de personajes, guilds o profesiones, pero la primera version debe concentrarse en el diferencial: inteligencia de mercado para el Auction House.
