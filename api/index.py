import os
import json
import re
import time
import io
import secrets
import hashlib
import math
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from functools import lru_cache
from typing import Optional
from dotenv import load_dotenv
import google.generativeai as genai
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from curl_cffi import requests as curl_requests

# INIT ------------
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI(title="Gasolineras IA API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
API_URL = os.getenv("URL_MINETUR")

engine = None
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            connect_args={"sslmode": "require"}
        )
    except Exception as e:
        print(f"Error al inicializar el engine de SQLAlchemy: {e}")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

PROVINCIA_IDS = {
    # "01": "Araba/Álava",
    # "02": "Albacete",
    # "03": "Alicante/Alacant",
    # "04": "Almería",
    # "05": "Ávila",
    # "06": "Badajoz",
    # "07": "Balears (Illes)",
    #"08": "Barcelona",
    # "09": "Burgos",
    # "10": "Cáceres",
    # "11": "Cádiz",
    # "12": "Castellón/Castelló",
    # "13": "Ciudad Real",
    # "14": "Córdoba",
    # "15": "Coruña (A)",
    # "16": "Cuenca",
    # "17": "Girona",
    # "18": "Granada",
    # "19": "Guadalajara",
    # "20": "Gipuzkoa",
    # "21": "Huelva",
    # "22": "Huesca",
    # "23": "Jaén",
    # "24": "León",
    # "25": "Lleida",
    # "26": "Rioja (La)",
    # "27": "Lugo",
    "28": "Madrid",
    # "29": "Málaga",
    # "30": "Murcia",
    # "31": "Navarra",
    # "32": "Ourense",
    # "33": "Asturias",
    # "34": "Palencia",
    # "35": "Palmas (Las)",
    # "36": "Pontevedra",
    # "37": "Salamanca",
    # "38": "Santa Cruz de Tenerife",
    # "39": "Cantabria",
    # "40": "Segovia",
    # "41": "Sevilla",
    # "42": "Soria",
    # "43": "Tarragona",
    # "44": "Teruel",
    "45": "Toledo",
    # "46": "Valencia/València",
    # "47": "Valladolid",
    # "48": "Bizkaia",
    # "49": "Zamora",
    # "50": "Zaragoza",
    # "51": "Ceuta",
    # "52": "Melilla"
}

# FUNCTIONS ------------

def fetch_ministerio(provincia_id):
    response = curl_requests.get(
        f"{API_URL}/{provincia_id}", 
        impersonate="chrome120", 
        timeout=30,
        headers=HEADERS
    )
    response.raise_for_status()
    return response.json()

def chunk_list(data_list, chunk_size=1000):
    for i in range(0, len(data_list), chunk_size):
        yield data_list[i:i + chunk_size]

def parse_price(val):
    return float(val.replace(",", ".")) if val else None

def parse_coord(val):
    if not val:
        return None
    try:
        return float(str(val).replace(",", "."))
    except (ValueError, TypeError):
        return None

def normalize_station(station):
    return {
        "id": station.get("IDEESS"),
        "label": station.get("Rótulo", None).strip() if station.get("Rótulo") else None,
        "city": station.get("Municipio", None).strip().lower() if station.get("Municipio") else None,
        "prov": station.get("Provincia", "").strip().lower(),
        "cp": station.get("C.P.", None),
        "address": station.get("Dirección", None).strip() if station.get("Dirección") else None,
        "longitude": parse_coord(station.get("Longitud (WGS84)", None)),
        "latitude": parse_coord(station.get("Latitud", None)),
        "prices": {
            "adblue": parse_price(station.get("Precio Adblue", None)),
            "amoniaco": parse_price(station.get("Precio Amoniaco", None)),
            "biodiesel": parse_price(station.get("Precio Biodiesel", None)),
            "bioetanol": parse_price(station.get("Precio Bioetanol", None)),
            "biogas_natural_comprimido": parse_price(station.get("Precio Biogas Natural Comprimido", None)),
            "biogas_natural_licuado": parse_price(station.get("Precio Biogas Natural Licuado", None)),
            "diesel_renovable": parse_price(station.get("Precio Diésel Renovable", None)),
            "gas_natural_comprimido": parse_price(station.get("Precio Gas Natural Comprimido", None)),
            "gas_natural_licuado": parse_price(station.get("Precio Gas Natural Licuado", None)),
            "gases_licuados_del_petroleo": parse_price(station.get("Precio Gases licuados del petróleo", None)),
            "gasoleo_a": parse_price(station.get("Precio Gasoleo A", None)),
            "gasoleo_b": parse_price(station.get("Precio Gasoleo B", None)),
            "gasoleo_premium": parse_price(station.get("Precio Gasoleo Premium", None)),
            "gasolina_95_e10": parse_price(station.get("Precio Gasolina 95 E10", None)),
            "gasolina_95_e25": parse_price(station.get("Precio Gasolina 95 E25", None)),
            "gasolina_95_e5": parse_price(station.get("Precio Gasolina 95 E5", None)),
            "gasolina_95_e5_premium": parse_price(station.get("Precio Gasolina 95 E5 Premium", None)),
            "gasolina_95_e85": parse_price(station.get("Precio Gasolina 95 E85", None)),
            "gasolina_98_e10": parse_price(station.get("Precio Gasolina 98 E10", None)),
            "gasolina_98_e5": parse_price(station.get("Precio Gasolina 98 E5", None)),
            "gasolina_renovable": parse_price(station.get("Precio Gasolina Renovable", None)),
            "hidrogeno": parse_price(station.get("Precio Hidrogeno", None)),
            "metanol": parse_price(station.get("Precio Metanol", None)),
        },
        "hours": station.get("Horario", None).strip() if station.get("Horario") else None,
    }

def process_all_provinces():
    if not engine:
        print("[CRON] Error: DATABASE_URL no configurada")
        return

    print("[CRON] Iniciando actualización completa de España...")
    total_procesadas = 0

    stmt_estaciones = text("""
        INSERT INTO estaciones (id, label, city, prov, cp, address, latitude, longitude, hours)
        VALUES (:id, :label, :city, :prov, :cp, :address, :latitude, :longitude, :hours)
        ON CONFLICT (id) DO UPDATE SET
            label = EXCLUDED.label,
            city = EXCLUDED.city,
            prov = EXCLUDED.prov,
            cp = EXCLUDED.cp,
            address = EXCLUDED.address,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            hours = EXCLUDED.hours,
            updated_at = CURRENT_TIMESTAMP;
    """)

    stmt_precios = text("""
        INSERT INTO precios (estacion_id, prices)
        VALUES (:estacion_id, CAST(:prices AS jsonb))
        ON CONFLICT (estacion_id) DO UPDATE SET
            prices = EXCLUDED.prices,
            updated_at = CURRENT_TIMESTAMP;
    """)

    for prov_id in PROVINCIA_IDS:
        try:
            data = fetch_ministerio(prov_id)
            raw_stations = [normalize_station(st) for st in data.get("ListaEESSPrecio", []) if st and st.get("IDEESS")]

            batch_estaciones = [
                {
                    "id": st["id"], "label": st["label"], "city": st["city"],
                    "prov": st["prov"], "cp": st["cp"], "address": st["address"],
                    "latitude": st["latitude"], "longitude": st["longitude"], "hours": st["hours"]
                }
                for st in raw_stations if st.get("id")
            ]

            batch_precios = [
                {
                    "estacion_id": st["id"],
                    "prices": json.dumps(st["prices"])
                }
                for st in raw_stations if st.get("id")
            ]

            with engine.begin() as conn:
                if batch_estaciones:
                    conn.execute(stmt_estaciones, batch_estaciones)
                if batch_precios:
                    conn.execute(stmt_precios, batch_precios)

            total_procesadas += len(raw_stations)
            time.sleep(0.1)

        except Exception as e:
            print(f"[CRON] Error procesando provincia {prov_id}: {e}")

    print(f"[CRON] Finalizada actualización nacional. Total estaciones: {total_procesadas}")

def get_geo_cache_key(lat: float, lng: float, radius: float, fuel: str) -> str:
    GRID_STEP = 0.05
    grid_lat = round(math.floor(lat / GRID_STEP) * GRID_STEP, 3)
    grid_lng = round(math.floor(lng / GRID_STEP) * GRID_STEP, 3)
    raw_key = f"{grid_lat}_{grid_lng}_{radius}_{fuel}"

    return hashlib.md5(raw_key.encode()).hexdigest()

# ROUTES ------------

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "up"}

@app.get("/stations/nearby/report")
def get_nearby_ai_report(
    response: Response,
    user_lat: float = 40.252125,
    user_lng: float = -4.189412,
    radius_km: float = 20,
    fuel: str = "gasolina_95_e5"
    ):
    response.headers["Cache-Control"] = "public, max-age=3600"
    
    if not engine:
        raise HTTPException(status_code=500, detail="DATABASE_URL no configurada")

    cache_key = get_geo_cache_key(user_lat, user_lng, radius_km, fuel)
    check_cache_sql = text("""
        SELECT response_json 
        FROM ai_reports_cache 
        WHERE cache_key = :key 
        AND created_at > NOW() - INTERVAL '4 hours';
    """)

    try:
        with engine.connect() as conn:
            cached_result = conn.execute(check_cache_sql, {"key": cache_key}).fetchone()
            if cached_result:
                return cached_result.response_json
    except Exception as e:
        print(f"Error consultando caché: {e}")

    query_sql = text("""
        WITH estaciones_distancia AS (
            SELECT 
                e.id,
                e.label,
                e.city,
                e.prov,
                e.address,
                e.hours,
                e.latitude,
                e.longitude,
                p.prices,
                (
                    6371 * acos(
                        LEAST(1.0, GREATEST(-1.0,
                            cos(radians(:user_lat)) * cos(radians(CAST(e.latitude AS double precision))) *
                            cos(radians(CAST(e.longitude AS double precision)) - radians(:user_lng)) +
                            sin(radians(:user_lat)) * sin(radians(CAST(e.latitude AS double precision)))
                        ))
                    )
                ) AS distancia_km
            FROM estaciones e
            JOIN precios p ON e.id = p.estacion_id
            WHERE e.latitude IS NOT NULL AND e.longitude IS NOT NULL
        )
        SELECT * FROM estaciones_distancia
        WHERE distancia_km <= :radius_km
        ORDER BY distancia_km ASC;
    """)

    try:
        with engine.connect() as conn:
            result = conn.execute(query_sql, {
                "user_lat": user_lat,
                "user_lng": user_lng,
                "radius_km": radius_km
            })
            rows = result.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar la base de datos: {str(e)}")

    if not rows:
        raise HTTPException(
            status_code=404, 
            detail=f"No se encontraron estaciones en un radio de {radius_km} km de la ubicación proporcionada."
        )

    stations_data = []
    for row in rows:
        prices_dict = row.prices if isinstance(row.prices, dict) else json.loads(row.prices or "{}")
        price_val = prices_dict.get(fuel)
        numeric_price = None
        if price_val is not None:
            try:
                numeric_price = float(str(price_val).replace(",", "."))
            except ValueError:
                pass

        if numeric_price is not None:
            lat = str(row.latitude).replace(",", ".") if row.latitude else ""
            lon = str(row.longitude).replace(",", ".") if row.longitude else ""
            gmaps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}" if lat and lon else ""

            stations_data.append({
                "id": row.id,
                "label": row.label,
                "city": row.city,
                "prov": row.prov,
                "address": row.address,
                "hours": row.hours,
                "distancia_km": round(row.distancia_km, 2),
                "prices": prices_dict,
                "price": numeric_price,
                "google_maps_url": gmaps_url
            })

    if not stations_data:
        raise HTTPException(
            status_code=404, 
            detail=f"Se encontraron estaciones en el radio de {radius_km} km, pero ninguna tiene precio disponible para '{fuel}'."
        )
    
    prov_name = stations_data[0]["prov"] or "tu zona"
    top_baratas = sorted(stations_data, key=lambda x: x["price"])[:5]
    top_prompt_data = [
        {
            "nombre": s["label"],
            "municipio": s["city"],
            "direccion": s["address"],
            "horario": s["hours"],
            "precio": s["price"],
            "maps_url": s["google_maps_url"]
        }
        for s in top_baratas
    ]

    prompt = f"""
    Eres un asistente experto en ahorro de combustible y analista de mercado.
    A continuación tienes un listado de las 5 gasolineras más baratas en la provincia de {prov_name.upper()} para el combustible '{fuel}':

    {json.dumps(top_prompt_data, ensure_ascii=False, indent=2)}

    Devuelve ÚNICAMENTE un objeto JSON con la siguiente estructura (sin formato Markdown, ni triple comilla ```json):
    {{
        "best_option": {{
            "nombre": "string",
            "direccion": "string",
            "municipio": "string",
            "precio": number,
            "horario": "string",
            "google_maps_url": "string"
        }},
        "alternative_options": [
            {{
                "nombre": "string",
                "motivo": "string",
                "precio": number,
                "google_maps_url": "string"
            }}
        ],
        "saving_advice": "string",
        "complete_info": "string"
    }}

    saving_advice y complete_info deben ser strings con la información relevante para el usuario y en cada una de ellas se conciso para que no sea más largo de 30 caracteres.
    """

    try:
        generation_config = {
            "temperature": 0.2,
            "max_output_tokens": 5000,
            "response_mime_type": "application/json"
        }
        model = genai.GenerativeModel("gemini-3.6-flash", generation_config=generation_config)
        ai_response = model.generate_content(prompt)
        raw_text = ai_response.text.strip() if ai_response and hasattr(ai_response, "text") else ""
        ia_parsed = json.loads(raw_text)

        response_data = {
            "ubicacion_usuario": {"lat": user_lat, "lng": user_lng},
            "radio_km": radius_km,
            "provincia_detectada": prov_name,
            "combustible_analizado": fuel,
            "total_estaciones_en_radio": len(stations_data),
            "ia": ia_parsed,
            "top_estaciones": top_baratas
        }

        save_cache_sql = text("""
            INSERT INTO ai_reports_cache (cache_key, response_json, created_at)
            VALUES (:key, CAST(:payload AS jsonb), NOW())
            ON CONFLICT (cache_key) 
            DO UPDATE SET response_json = EXCLUDED.response_json, created_at = NOW();
        """)

        try:
            with engine.begin() as conn:
                conn.execute(save_cache_sql, {
                    "key": cache_key, 
                    "payload": json.dumps(response_data)
                })
        except Exception as e:
            print(f"Error guardando en caché: {e}")

        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar informe con IA: {str(e)}")

@app.get("/cron/update-data")
def cron_update_gas_stations(
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None)
    ):
    if not engine:
        raise HTTPException(status_code=500, detail="DATABASE_URL no configurada")

    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret:
        expected_header = f"Bearer {cron_secret}"
        if not authorization or not secrets.compare_digest(authorization, expected_header):
            raise HTTPException(status_code=401, detail="No autorizado")
        
    background_tasks.add_task(process_all_provinces)

    return {
        "status": "accepted",
        "message": "Actualización nacional iniciada en segundo plano para las 52 provincias."
    }