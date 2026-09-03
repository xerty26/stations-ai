import os
import json
import requests
import httpx
from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import google.generativeai as genai
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

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
api_url = "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/"

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
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# FUNCTIONS ------------
def parse_price(val):
    return float(val.replace(",", ".")) if val else None

def normalize_station(station):
    return {
        "id": station.get("IDEESS"),
        "label": station.get("Rótulo", None).strip(),
        "city": station.get("Municipio", None).strip().lower(),
        "prov": station.get("Provincia", "").strip().lower(),
        "cp": station.get("C.P.", None),
        "address": station.get("Dirección", None).strip(),
        "longitude": station.get("Longitud (WGS84)", None),
        "latitude": station.get("Latitud", None),
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
        "hours": station.get("Horario", None).strip(),
    }


# ROUTES ------------

@app.get("/")
def home():
    return {"message": "Gasolineras IA API activa"}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "FastAPI + Gemini on Vercel"}

@app.get("/stations/{prov}/report")
def get_province_ai_report(
    prov: str = "madrid", 
    gasoline_type: str = "gasolina_95_e5"
):

    response = requests.get(api_url)
    if response.status_code == 200:
        data = response.json()
        stationsFilter, error = [normalize_station(station) for station in data.get("ListaEESSPrecio", []) if station.get("Provincia", "") == prov.lower()], None
        if error:
            raise HTTPException(status_code=500, detail=error)

        if not stationsFilter:
            return {"error": f"No se encontraron estaciones en {prov}"}

        valid_stations = [s for s in stationsFilter if s["prices"].get(gasoline_type) is not None]
        top_baratas = sorted(valid_stations, key=lambda x: x["prices"][gasoline_type])[:10]

        prompt = f"""
        Eres un asistente experto en ahorro de combustible y analista de mercado.
        A continuación tienes un listado de las 10 gasolineras más baratas en la provincia de {prov.upper()} para el combustible '{gasoline_type}':

        {top_baratas}

        En formato JSON solo para parsear con json.loads:
        1. **best_option**: La mejor opción absoluta: Nombre, dirección, municipio, precio, horario y link en google maps.
        2. **alternative_options**: 2 opciones destacadas (por ejemplo, por horario 24h o marcas reconocidas).
        3. **saving_advice**: un breve comentario sobre la diferencia de precio entre la más barata y la más cara del TOP 10. También añade aquí cuantos km es factible recorrer para repostar en la más barata.
        4. **complete_info**: genera un informe breve y estructurado en español orientado al usuario final con los campos anteriores.

        Mantén un tono profesional, claro y directo.
        """

        try:
            model = genai.GenerativeModel("gemini-3.6-flash")
            ai_response = model.generate_content(prompt)

            return {
                "province": prov,
                "combustible_analizado": gasoline_type,
                "total_estaciones_provincia": len(stationsFilter),
                "ia": json.loads(ai_response.text),
                "top_10_estaciones": top_baratas
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al generar informe con IA: {str(e)}")

@app.get("/cron/update-data")
def cron_update_gas_stations(authorization: Optional[str] = Header(None)):
    # cron_secret = os.getenv("CRON_SECRET")
    # if cron_secret and authorization != f"Bearer {cron_secret}":
    #     raise HTTPException(status_code=401, detail="No autorizado")

    if not engine:
        raise HTTPException(status_code=500, detail="DATABASE_URL no configurada")

    with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        res = client.get(api_url)
        res.raise_for_status()
        data = res.json()
        raw_stations = [normalize_station(station) for station in data.get("ListaEESSPrecio", [])]

        with engine.begin() as conn:
            for raw in raw_stations:
                st = raw
                if not st["id"]:
                    continue

                # 1. Upsert en tabla estaciones
                conn.execute(
                    text("""
                        INSERT INTO estaciones (id, label, city, prov, cp, address, latitude, longitude, hours)
                        VALUES (:id, :label, :city, :prov, :cp, :address, :latitude, :longitude, :hours)
                        ON CONFLICT (id) DO UPDATE SET
                            label = EXCLUDED.label,
                            city = EXCLUDED.city,
                            prov = EXCLUDED.prov,
                            address = EXCLUDED.address,
                            hours = EXCLUDED.hours,
                            updated_at = CURRENT_TIMESTAMP;
                    """),
                    {
                        "id": st["id"],
                        "label": st["label"],
                        "city": st["city"],
                        "prov": st["prov"],
                        "cp": st["cp"],
                        "address": st["address"],
                        "latitude": st["latitude"],
                        "longitude": st["longitude"],
                        "hours": st["hours"],
                    }
                )

                # 2. Upsert en tabla precios usando el diccionario de precios convertido a JSON
                conn.execute(
                    text("""
                        INSERT INTO precios (estacion_id, prices)
                        VALUES (:estacion_id, :prices::jsonb)
                        ON CONFLICT (estacion_id) DO UPDATE SET
                            prices = EXCLUDED.prices,
                            updated_at = CURRENT_TIMESTAMP;
                    """),
                    {
                        "estacion_id": st["id"],
                        "prices": json.dumps(st["prices"])
                    }
                )

        return {"status": "success", "total_procesadas": len(raw_stations)}