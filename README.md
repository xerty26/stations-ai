# stations-ai

API de gasolineras con informes generados por IA. Consulta los precios oficiales del Ministerio de Industria (España), filtra por provincia y tipo de combustible, y usa **Google Gemini** para devolver un resumen con la mejor opción, alternativas y consejos de ahorro.

Desplegada pensada para **Vercel** (FastAPI serverless + cron cada 4 horas).

## Stack

- [FastAPI](https://fastapi.tiangolo.com/)
- [Google Generative AI (Gemini)](https://ai.google.dev/)
- Datos oficiales: [API Precios Carburantes (Ministerio)](https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/)
- Despliegue: Vercel (`vercel.json`)

## Requisitos

- Python 3.10+
- Cuenta / API key de Gemini
- (Opcional) secreto para proteger el cron y URL de base de datos

## Configuración

1. Clona el repositorio y entra en el directorio:

```bash
git clone <url-del-repo>
cd stations-ai
```

2. Crea un entorno virtual e instala dependencias:

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Copia el ejemplo de variables de entorno y rellénalas:

```bash
cp .env.example .env
```

| Variable | Descripción |
|---|---|
| `GEMINI_API_KEY` | API key de Google Gemini |
| `CRON_SECRET` | Token Bearer para autorizar `/api/cron/update-data` |
| `DATABASE_URL` | URL PostgreSQL (preparada; persistencia aún pendiente) |

## Desarrollo local

Con el entorno activado y el `.env` configurado:

```bash
uvicorn api.index:app --reload --port 8000
```

La API queda en `http://localhost:8000`. Documentación interactiva en `/docs` (Swagger) si el entorno lo expone.

## Endpoints

### `GET /api/health`

Comprueba que el servicio está vivo.

```json
{ "status": "ok", "service": "FastAPI + Gemini on Vercel" }
```

### `GET /api/stations/{prov}/report`

Genera un informe IA de las gasolineras más baratas de una provincia.

**Parámetros**

| Nombre | Dónde | Ejemplo | Descripción |
|---|---|---|---|
| `prov` | path | `madrid` | Provincia (sin acentos, case-insensitive) |
| `gasoline_type` | query | `gasolina_95_e5` | Clave del combustible a analizar |

**Ejemplo**

```bash
curl "http://localhost:8000/api/stations/madrid/report?gasoline_type=gasolina_95_e5"
```

**Respuesta (estructura)**

- `province` — provincia consultada  
- `combustible_analizado` — tipo de combustible  
- `total_estaciones_provincia` — estaciones encontradas  
- `ia` — JSON de Gemini (`best_option`, `alternative_options`, `saving_advice`, `complete_info`)  
- `top_10_estaciones` — las 10 más baratas normalizadas  

### `GET /api/cron/update-data`

Job pensado para Vercel Cron (cada 4 horas). Requiere cabecera:

```http
Authorization: Bearer <CRON_SECRET>
```

Actualmente responde éxito; la persistencia en BBDD está marcada como TODO.

## Tipos de combustible

Claves disponibles en `prices` (usarlas en `gasoline_type`):

`adblue`, `amoniaco`, `biodiesel`, `bioetanol`, `biogas_natural_comprimido`, `biogas_natural_licuado`, `diesel_renovable`, `gas_natural_comprimido`, `gas_natural_licuado`, `gases_licuados_del_petroleo`, `gasoleo_a`, `gasoleo_b`, `gasoleo_premium`, `gasolina_95_e10`, `gasolina_95_e25`, `gasolina_95_e5`, `gasolina_95_e5_premium`, `gasolina_95_e85`, `gasolina_98_e10`, `gasolina_98_e5`, `gasolina_renovable`, `hidrogeno`, `metanol`

## Despliegue en Vercel

1. Conecta el repo a Vercel.
2. Define las variables de entorno en el panel del proyecto (`GEMINI_API_KEY`, `CRON_SECRET`, etc.).
3. `vercel.json` ya reescribe `/api/*` a `api/index.py` y programa el cron:

```json
"schedule": "0 */4 * * *"
```

## Estructura

```
stations-ai/
├── api/
│   └── index.py      # App FastAPI (health, report, cron)
├── .env.example
├── requirements.txt
├── vercel.json
└── README.md
```

## Licencia

Uso interno / proyecto de prueba. Los datos de precios pertenecen al Ministerio de Industria, Comercio y Turismo.
