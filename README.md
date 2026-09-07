# stations-ai

Gas station API with AI-generated reports. Stores official fuel prices from Spain’s Ministry of Industry in PostgreSQL, finds stations by geolocation and radius, and uses **Google Gemini** to return a summary with the best option, alternatives, and saving tips.

Built for **Vercel** (FastAPI serverless + daily cron).

## Stack

- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/) + PostgreSQL
- [Google Gen AI (Gemini)](https://ai.google.dev/) (`google-genai`)
- [slowapi](https://github.com/laurentS/slowapi) (rate limiting)
- [curl_cffi](https://github.com/lexiforest/curl_cffi) (Minetur fetch)
- Official data: Fuel Prices API (Spanish Ministry)
- Deployment: Vercel (`vercel.json`)

## Requirements

- Python 3.10+
- Gemini API key
- PostgreSQL with `estaciones`, `precios`, and `ai_reports_cache` tables
- Secret to protect the cron endpoint

## Setup

1. Clone the repository and enter the project directory:

```bash
git clone <repo-url>
cd stations-ai
```

2. Create a virtual environment and install dependencies:

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Copy the environment example and fill in the values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key |
| `CRON_SECRET` | Bearer token to authorize `/cron/update-data` |
| `DATABASE_URL` | PostgreSQL URL (`postgresql://...`; `postgres://` is also accepted) |
| `URL_MINETUR` | Base URL of the Ministry’s per-province fuel prices API |

## Local development

With the virtualenv activated and `.env` configured:

```bash
uvicorn api.index:app --reload --port 8000
```

The API is available at `http://localhost:8000`. Interactive docs at `/docs`.

## Endpoints

### `GET /health`

Health check.

```json
{ "status": "ok", "service": "up" }
```

### `GET /stations/nearby/report`

Generates an AI report for the cheapest gas stations near a location.

- Rate limit: **5 requests/minute** per IP
- Response header: `Cache-Control: public, max-age=3600`
- DB cache (`ai_reports_cache`) keyed by geo grid (~0.05°) + radius + fuel, valid for **4 hours** (`created_at` in UTC)

**Query parameters**

| Name | Example | Description |
|---|---|---|
| `user_lat` | `40.252125` | User latitude |
| `user_lng` | `-4.189412` | User longitude |
| `radius_km` | `20` | Search radius in km |
| `fuel` | `gasolina_95_e5` | Fuel key to analyze |

**Example**

```bash
curl "http://localhost:8000/stations/nearby/report?user_lat=40.25&user_lng=-4.19&radius_km=20&fuel=gasolina_95_e5"
```

**Flow**

1. Look up a cached report (`cache_key` = MD5 of grid + radius + fuel).
2. If no valid cache, query stations within radius (Haversine formula in SQL).
3. Keep stations with a price for `fuel`, take the **5 cheapest**, and request a Gemini report.
4. Upsert the result into `ai_reports_cache` and return it.

**Response shape**

- `ubicacion_usuario` — `{ lat, lng }`
- `radio_km` — radius used
- `provincia_detectada` — province of the nearest station with a price
- `combustible_analizado` — fuel type
- `total_estaciones_en_radio` — stations with a valid price in the radius
- `ia` — Gemini JSON (`best_option`, `alternative_options`, `saving_advice`, `complete_info`)
- `top_estaciones` — top 5 cheapest (includes `distancia_km`, `price`, `google_maps_url`, etc.)

### `GET /cron/update-data`

Sync job (Vercel Cron: **daily at 06:00 UTC**). Requires header:

```http
Authorization: Bearer <CRON_SECRET>
```

Starts `process_all_provinces()` in the background: downloads Minetur data per province, normalizes stations/prices, and upserts into `estaciones` and `precios`.

Responds immediately:

```json
{
  "status": "accepted",
  "message": "Actualización nacional iniciada en segundo plano para las N provincias."
}
```

> In code, `PROVINCIA_IDS` may only enable a subset (e.g. Madrid and Toledo) while testing; the rest are commented out.

## Data model (PostgreSQL)

| Table | Purpose |
|---|---|
| `estaciones` | Station metadata (id, label, city, coords, hours…) |
| `precios` | Price JSONB per `estacion_id` |
| `ai_reports_cache` | Cached AI reports (`cache_key`, `response_json`, `created_at`) |

## Fuel types

Keys available in `prices` / `fuel` parameter:

`adblue`, `amoniaco`, `biodiesel`, `bioetanol`, `biogas_natural_comprimido`, `biogas_natural_licuado`, `diesel_renovable`, `gas_natural_comprimido`, `gas_natural_licuado`, `gases_licuados_del_petroleo`, `gasoleo_a`, `gasoleo_b`, `gasoleo_premium`, `gasolina_95_e10`, `gasolina_95_e25`, `gasolina_95_e5`, `gasolina_95_e5_premium`, `gasolina_95_e85`, `gasolina_98_e10`, `gasolina_98_e5`, `gasolina_renovable`, `hidrogeno`, `metanol`

## Deploy on Vercel

1. Connect the repo to Vercel.
2. Set environment variables (`GEMINI_API_KEY`, `CRON_SECRET`, `DATABASE_URL`, `URL_MINETUR`).
3. `vercel.json` builds `api/index.py` with `@vercel/python`, routes all traffic to that app, and schedules the cron:

```json
"path": "/cron/update-data",
"schedule": "0 6 * * *"
```

## Project structure

```
stations-ai/
├── api/
│   └── index.py      # FastAPI: health, nearby/report, cron + Minetur sync
├── .env.example
├── requirements.txt
├── vercel.json
└── README.md
```

## License

Internal / experimental use. Fuel price data belongs to the Spanish Ministry of Industry, Trade and Tourism.
